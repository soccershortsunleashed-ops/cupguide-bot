import logging
from app.services.telegram_service import telegram_service
from app.services.message_service import message_service
from app.models.message import MessageStatus

logger = logging.getLogger(__name__)

class PublicationService:
    async def publish_message(self, message_id: int, text_type: str, target_channel_id: int = None):
        """
        text_type: 'summary' or 'rewrite'
        """
        messages = await message_service.get_messages()
        message = next((m for m in messages if m.id == message_id), None)
        
        if not message:
            raise ValueError("Message not found")
            
        text_to_send = None
        if text_type == 'summary':
            text_to_send = message.summary
        elif text_type == 'rewrite':
            text_to_send = message.rewrite
        else:
            raise ValueError("Invalid text_type. Must be 'summary' or 'rewrite'")
            
        if not text_to_send:
            raise ValueError(f"No {text_type} available for this message")

        # If target_channel_id is not provided, try to find a default target channel
        if not target_channel_id:
            from app.services.channel_service import channel_service
            channels = await channel_service.get_channels()
            targets = [c for c in channels if c.type == 'target']
            if not targets:
                raise ValueError("No target channels configured")
            target_channel_id = targets[0].id

        client = await telegram_service.get_client()
        try:
            # Prepare all media files if exist
            files_to_send = []
            if message.media_files:
                import os
                from app.core.config import settings
                
                for media_file in message.media_files:
                    # media_file.path is like "/static/media/filename.jpg"
                    filename = os.path.basename(media_file.path)
                    file_path = os.path.join(settings.BASE_DIR, "static", "media", filename)
                    if os.path.exists(file_path):
                        files_to_send.append(file_path)

            # Send message with all media files
            if files_to_send:
                # If multiple files, send as album
                if len(files_to_send) > 1:
                    await client.send_file(
                        target_channel_id,
                        files_to_send,
                        caption=text_to_send
                    )
                else:
                    # Single file
                    await client.send_message(
                        target_channel_id,
                        text_to_send,
                        file=files_to_send[0]
                    )
            else:
                # No media, just text
                await client.send_message(target_channel_id, text_to_send)
            
            # Update status
            message.status = MessageStatus.PUBLISHED
            await message_service.update_message(message)
            
            return {"status": "published", "channel_id": target_channel_id}
        except Exception as e:
            logger.error(f"Error publishing message: {e}")
            raise ValueError(f"Failed to publish: {str(e)}")

publication_service = PublicationService()
