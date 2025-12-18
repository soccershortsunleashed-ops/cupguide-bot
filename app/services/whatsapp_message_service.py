import json
import os
import aiofiles
import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import hashlib
from app.core.config import settings
from app.models.whatsapp_message import WhatsAppMessage, WhatsAppMessageStatus

logger = logging.getLogger(__name__)

class WhatsAppMessageService:
    def __init__(self):
        self.file_path = os.path.join(settings.DATA_DIR, "whatsapp_messages.json")
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def _generate_message_id(self, chat_name: str, sender: str, text: str, date: datetime) -> str:
        """Generate unique message ID from content"""
        content = f"{chat_name}|{sender or ''}|{text}|{date.isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()

    async def get_messages(
        self, 
        chat_name: Optional[str] = None,
        status: Optional[WhatsAppMessageStatus] = None,
        since: Optional[datetime] = None
    ) -> List[WhatsAppMessage]:
        async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            
            # OPTIMIZATION: Filter in raw data before creating objects (much faster for large datasets)
            # Normalize since date for comparison
            if since:
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
            
            # Pre-filter raw data to reduce object creation overhead
            filtered_data = []
            for item in data:
                # Quick filters on raw dict (no object creation yet)
                if chat_name and item.get('chat_name') != chat_name:
                    continue
                if status:
                    item_status = item.get('status')
                    status_value = status.value if hasattr(status, 'value') else str(status)
                    if item_status != status_value:
                        continue
                
                if since:
                    # Parse date string quickly without full object creation
                    date_str = item.get('date')
                    if date_str:
                        try:
                            if isinstance(date_str, str):
                                # Try ISO format parsing (most common)
                                if 'T' in date_str or '+' in date_str or 'Z' in date_str:
                                    # ISO format: parse manually for speed
                                    try:
                                        # Try simple ISO parse first
                                        if date_str.endswith('Z'):
                                            date_str = date_str[:-1] + '+00:00'
                                        msg_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                    except:
                                        # Fallback to slower parser
                                        from dateutil import parser
                                        msg_date = parser.isoparse(date_str)
                                else:
                                    # Not ISO format, use dateutil
                                    from dateutil import parser
                                    msg_date = parser.isoparse(date_str)
                            else:
                                # Already a datetime-like object
                                msg_date = date_str
                            
                            if msg_date.tzinfo is None:
                                msg_date = msg_date.replace(tzinfo=timezone.utc)
                            elif msg_date.tzinfo != timezone.utc:
                                msg_date = msg_date.astimezone(timezone.utc)
                            
                            if msg_date < since:
                                continue  # Skip old messages
                        except Exception:
                            # If date parsing fails, include the message (better safe than sorry)
                            pass
                
                filtered_data.append(item)
            
            # Now create objects only for filtered data (much faster!)
            messages = []
            local_tz = datetime.now().astimezone().tzinfo
            for item in filtered_data:
                try:
                    msg = WhatsAppMessage(**item)
                    # Fix naive datetimes
                    if msg.date.tzinfo is None:
                        msg.date = msg.date.replace(tzinfo=local_tz)
                    messages.append(msg)
                except Exception as e:
                    logger.warning(f"Error creating WhatsAppMessage from item: {e}, skipping")
                    continue
            
            # Sort by date desc
            messages.sort(key=lambda x: x.date, reverse=True)
            logger.info(f"📱 WhatsAppMessageService: Loaded {len(messages)} messages (filtered from {len(data)} total). Since date: {since}")
            if messages:
                logger.info(f"📱 WhatsAppMessageService: Date range: {messages[-1].date} to {messages[0].date}")
            return messages

    async def cleanup_old_messages(self, days: int = 7):
        """
        Удаляет WhatsApp сообщения старше указанного количества дней
        """
        from datetime import datetime, timezone, timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
        
        original_count = len(data)
        
        # Фильтруем сообщения
        filtered_data = []
        for item in data:
            msg = WhatsAppMessage(**item)
            # Преобразуем дату в timezone-aware если нужно
            msg_date = msg.date
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            elif msg_date.tzinfo != timezone.utc:
                msg_date = msg_date.astimezone(timezone.utc)
            
            if msg_date >= cutoff_date:
                filtered_data.append(item)
        
        removed_count = original_count - len(filtered_data)
        
        if removed_count > 0:
            async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(filtered_data, ensure_ascii=False, indent=2))
            logger.info(f"🧹 Cleaned up {removed_count} old WhatsApp messages (older than {days} days). Remaining: {len(filtered_data)}")
        
        return removed_count

    async def save_message(self, message: WhatsAppMessage):
        messages = await self.get_messages()
        
        # Generate unique ID if not set
        if not message.message_id:
            message.message_id = self._generate_message_id(
                message.chat_name,
                message.sender or "",
                message.text,
                message.date
            )
        
        # Check if exists
        existing_index = None
        for i, m in enumerate(messages):
            if m.message_id == message.message_id:
                existing_index = i
                break
        
        if existing_index is not None:
            # Message exists - update it if new message has media and old one doesn't, or if sender is missing
            existing = messages[existing_index]
            has_new_media = message.media_path or message.media_files
            has_existing_media = existing.media_path or existing.media_files
            needs_update = False
            
            # Update sender if new message has it and old one doesn't
            if message.sender and not existing.sender:
                existing.sender = message.sender
                needs_update = True
                logger.info(f"✅ Updating existing message {message.message_id} with sender: {message.sender}")
            
            # Update media if new message has it and old one doesn't
            if has_new_media and not has_existing_media:
                existing.media_type = message.media_type
                existing.media_path = message.media_path
                existing.media_files = message.media_files
                needs_update = True
                # Updated existing message with media (removed verbose logging)
            elif has_new_media and has_existing_media:
                # Both have media - check if new one is different/better
                if message.media_files and (not existing.media_files or len(message.media_files) > len(existing.media_files)):
                    existing.media_type = message.media_type
                    existing.media_path = message.media_path
                    existing.media_files = message.media_files
                    needs_update = True
                    logger.info(f"✅ Updated existing message {message.message_id} with better media info")
            
            if needs_update:
                messages[existing_index] = existing
                await self._save_all(messages)
            else:
                logger.debug(f"Message {message.message_id} already exists, skipping")
            return  # Already exists (and updated if needed)
        
        # Auto-generate ID for database
        if message.id is None:
            message.id = max([m.id for m in messages if m.id], default=0) + 1
            
        messages.append(message)
        await self._save_all(messages)

    async def _save_all(self, messages: List[WhatsAppMessage]):
        data = [json.loads(m.json()) for m in messages]
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

whatsapp_message_service = WhatsAppMessageService()
