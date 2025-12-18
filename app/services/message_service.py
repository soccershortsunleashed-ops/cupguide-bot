import json
import os
import aiofiles
from typing import List, Optional
from datetime import datetime
from app.core.config import settings
from app.models.message import Message, MessageStatus

class MessageService:
    def __init__(self):
        self.file_path = settings.MESSAGES_FILE
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    async def get_messages(self, status: Optional[MessageStatus] = None) -> List[Message]:
        async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            data = json.loads(content)
            
            # Migrate old format and RECOVER missing media from disk
            from app.models.message import MediaFile
            from app.core.config import settings
            import os
            
            media_dir = os.path.join(settings.BASE_DIR, "static", "media")
            needs_save = False
            
            for item in data:
                # 1. Migration: If old format exists
                if 'media_path' in item and item['media_path'] and 'media_files' not in item:
                    item['media_files'] = [{
                        'path': item['media_path'],
                        'type': item.get('media_type', 'photo')
                    }]
                    needs_save = True
                
                # 2. Initialization: Ensure list exists
                if 'media_files' not in item:
                    item['media_files'] = []
                    
                # 3. RECOVERY: If no media files, check disk for orphans
                if not item['media_files']:
                    # Check for photo
                    photo_name = f"{item['channel_id']}_{item['id']}.jpg"
                    photo_path = os.path.join(media_dir, photo_name)
                    
                    # Check for video
                    video_name = f"{item['channel_id']}_{item['id']}.mp4"
                    video_path = os.path.join(media_dir, video_name)
                    
                    if os.path.exists(photo_path):
                        item['media_files'].append({
                            'path': f"/static/media/{photo_name}",
                            'type': 'photo'
                        })
                        needs_save = True
                    elif os.path.exists(video_path):
                        item['media_files'].append({
                            'path': f"/static/media/{video_name}",
                            'type': 'video'
                        })
                        needs_save = True
            
            # Save migrated/recovered data back to file
            if needs_save:
                async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as fw:
                    await fw.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            
            messages = [Message(**item) for item in data]
            
            if status:
                messages = [m for m in messages if m.status == status]
            
            # Sort by date desc
            messages.sort(key=lambda x: x.date, reverse=True)
            return messages

    async def save_message(self, message: Message):
        messages = await self.get_messages()
        
        # Check if exists
        if any(m.id == message.id and m.channel_id == message.channel_id for m in messages):
            return # Already exists
            
        messages.append(message)
        await self._save_all(messages)

    async def update_message(self, message: Message):
        messages = await self.get_messages()
        for i, m in enumerate(messages):
            if m.id == message.id and m.channel_id == message.channel_id:
                messages[i] = message
                break
        await self._save_all(messages)

    async def _save_all(self, messages: List[Message]):
        data = [json.loads(m.json()) for m in messages]
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    
    async def cleanup_old_messages(self, days: int = 7):
        """
        Удаляет сообщения старше указанного количества дней
        """
        from datetime import datetime, timezone, timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        messages = await self.get_messages()
        original_count = len(messages)
        
        # Фильтруем сообщения - оставляем только те, что новее cutoff_date
        filtered_messages = []
        for msg in messages:
            # Преобразуем дату сообщения в timezone-aware если нужно
            msg_date = msg.date
            if msg_date.tzinfo is None:
                msg_date = msg_date.replace(tzinfo=timezone.utc)
            elif msg_date.tzinfo != timezone.utc:
                msg_date = msg_date.astimezone(timezone.utc)
            
            if msg_date >= cutoff_date:
                filtered_messages.append(msg)
        
        removed_count = original_count - len(filtered_messages)
        
        if removed_count > 0:
            await self._save_all(filtered_messages)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🧹 Cleaned up {removed_count} old messages (older than {days} days). Remaining: {len(filtered_messages)}")
        
        return removed_count

message_service = MessageService()
