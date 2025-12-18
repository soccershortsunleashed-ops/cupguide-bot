import json
import os
import aiofiles
from typing import List, Optional, Union
from app.core.config import settings
from app.models.channel import Channel, ChannelType
from app.services.telegram_service import telegram_service
from telethon.tl.types import Channel as TelethonChannel, Chat, User

class ChannelService:
    def __init__(self):
        self.file_path = settings.CHANNELS_FILE
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    async def get_channels(self) -> List[Channel]:
        # Load Telegram channels from file
        telegram_channels = []
        if os.path.exists(self.file_path):
            async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                telegram_channels = [Channel(**item) for item in data]
        
        # Load WhatsApp chats
        from app.services.whatsapp_service import whatsapp_service
        whatsapp_channels = await whatsapp_service.get_monitored_chats_as_channels()
        
        return telegram_channels + whatsapp_channels

    async def save_channels(self, channels: List[Channel]):
        # Only save Telegram channels to the JSON file
        from app.models.channel import Platform
        telegram_channels = [c.dict() for c in channels if c.platform == Platform.TELEGRAM]
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(telegram_channels, ensure_ascii=False, indent=2))

    async def add_channel(self, identifier: str, type: ChannelType) -> Channel:
        client = await telegram_service.get_client()
        
        try:
            entity = await client.get_entity(identifier)
        except ValueError:
            raise ValueError(f"Channel '{identifier}' not found or not accessible")

        # Extract basic info
        channel_id = entity.id
        title = getattr(entity, 'title', None)
        username = getattr(entity, 'username', None)
        
        if not title:
            # Fallback for users/chats if title is missing
            title = f"{getattr(entity, 'first_name', '')} {getattr(entity, 'last_name', '')}".strip()

        # Check if already exists
        channels = await self.get_channels()
        if any(c.id == channel_id for c in channels):
            raise ValueError("Channel already exists in the list")

        new_channel = Channel(
            id=channel_id,
            title=title,
            username=username,
            type=type
        )
        
        channels.append(new_channel)
        await self.save_channels(channels)
        return new_channel

    async def delete_channel(self, channel_id: Union[int, str]):
        from app.models.channel import Platform
        from app.services.whatsapp_service import whatsapp_service

        channels = await self.get_channels()
        
        # Find the channel to delete to check its platform
        target_channel = next((c for c in channels if str(c.id) == str(channel_id)), None)
        
        if not target_channel:
            return

        if target_channel.platform == Platform.WHATSAPP:
            await whatsapp_service.remove_monitored_chat(str(channel_id))
        else:
            # It's a Telegram channel, remove from list
            channels = [c for c in channels if str(c.id) != str(channel_id)]
            
        # Always save to ensure the file is clean of any non-Telegram channels
        # (This fixes the issue where WhatsApp channels were accidentally saved to the file)
        await self.save_channels(channels)

channel_service = ChannelService()
