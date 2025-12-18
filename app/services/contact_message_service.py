import json
import os
import aiofiles
from typing import List, Optional
from datetime import datetime
from app.core.config import settings
from app.models.contact_message import ContactMessage


class ContactMessageService:
    """Service for managing WhatsApp messages from contact dialogs"""
    
    def __init__(self, data_file: str = "app/data/contact_messages.json"):
        self.data_file = data_file
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Create the data file if it doesn't exist"""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
    
    async def get_all_messages(self) -> List[ContactMessage]:
        """Get all messages"""
        async with aiofiles.open(self.data_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            return [ContactMessage(**item) for item in data]
    
    async def get_messages_by_contact(
        self, 
        contact_id: int,
        limit: Optional[int] = None,
        since: Optional[datetime] = None
    ) -> List[ContactMessage]:
        """Get messages for a specific contact"""
        all_messages = await self.get_all_messages()
        
        # Filter by contact_id
        messages = [m for m in all_messages if m.contact_id == contact_id]
        
        # Filter by timestamp
        if since:
            messages = [m for m in messages if m.timestamp >= since]
        
        # Sort by timestamp (newest first)
        messages.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Limit results
        if limit:
            messages = messages[:limit]
        
        return messages
    
    async def save_message(self, message: ContactMessage) -> ContactMessage:
        """Save a single message"""
        messages = await self.get_all_messages()
        
        # Auto-generate ID if not set
        if message.id is None:
            message.id = max([m.id for m in messages if m.id], default=0) + 1
        
        # Check if message already exists by whatsapp_msg_id
        if message.whatsapp_msg_id:
            existing = [m for m in messages if m.whatsapp_msg_id == message.whatsapp_msg_id]
            if existing:
                return existing[0]  # Already exists, return existing
        
        messages.append(message)
        await self._save_all(messages)
        return message
    
    async def save_messages_bulk(self, new_messages: List[ContactMessage]) -> dict:
        """
        Save multiple messages at once.
        Returns: {saved: int, skipped: int}
        """
        messages = await self.get_all_messages()
        
        saved_count = 0
        skipped_count = 0
        
        # Get max ID
        max_id = max([m.id for m in messages if m.id], default=0)
        
        for msg in new_messages:
            # Check if message already exists for THIS contact
            # Must match both contact_id AND whatsapp_msg_id
            if msg.whatsapp_msg_id:
                exists = any(
                    m.contact_id == msg.contact_id and m.whatsapp_msg_id == msg.whatsapp_msg_id
                    for m in messages
                )
                if exists:
                    skipped_count += 1
                    continue
            
            # Auto-generate ID
            if msg.id is None:
                max_id += 1
                msg.id = max_id
            
            messages.append(msg)
            saved_count += 1
        
        if saved_count > 0:
            await self._save_all(messages)
        
        return {"saved": saved_count, "skipped": skipped_count}
    
    async def get_latest_message_timestamp(self, contact_id: int) -> Optional[datetime]:
        """Get timestamp of the most recent message for a contact"""
        messages = await self.get_messages_by_contact(contact_id, limit=1)
        return messages[0].timestamp if messages else None
    
    async def _save_all(self, messages: List[ContactMessage]):
        """Save all messages to file (atomic write)"""
        import tempfile
        
        # Convert to JSON-serializable format
        data = [json.loads(m.json()) for m in messages]
        
        # Write to temp file first
        temp_fd, temp_path = tempfile.mkstemp(suffix='.json', text=True)
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Atomic replace
            os.replace(temp_path, self.data_file)
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e


# Singleton instance
contact_message_service = ContactMessageService()
