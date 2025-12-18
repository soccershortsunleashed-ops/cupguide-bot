import asyncio
import logging
from datetime import datetime, timedelta, timezone
from app.services.telegram_service import telegram_service
from app.services.channel_service import channel_service
from app.services.message_service import message_service
from app.models.channel import ChannelType
from app.models.message import Message, MessageStatus, MediaFile

logger = logging.getLogger(__name__)

class MonitoringService:
    def __init__(self):
        self.is_running = False
        self.task = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("Monitoring service started")

    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Monitoring service stopped")

    async def _monitor_loop(self):
        while self.is_running:
            try:
                await self.check_channels()
            except ModuleNotFoundError as e:
                # Игнорируем ошибку blinker - не критично для работы
                if 'blinker' in str(e):
                    pass  # Тихо игнорируем
                else:
                    logger.error(f"Module error in monitoring loop: {e}")
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            # Wait for 60 seconds before next check
            await asyncio.sleep(60)

    async def force_check(self):
        """Manually trigger a check"""
        logger.info("Force check triggered")
        # Always run check, even if monitoring loop is not running
        # This allows manual checks via API
        await self.check_channels()

    async def check_channels(self):
        client = await telegram_service.get_client()
        if not await client.is_user_authorized():
            logger.warning("Monitoring skipped: User not authorized")
            return

        from app.models.channel import Platform
        channels = await channel_service.get_channels()
        source_channels = [c for c in channels if c.type == ChannelType.SOURCE and c.platform == Platform.TELEGRAM]

        for channel in source_channels:
            try:
                logger.info(f"Checking channel: {channel.title}")
                
                # Get entity to ensure it's in cache (fixes "Could not find the input entity" error)
                try:
                    # Try to get entity by username first (more reliable)
                    if channel.username:
                        entity = await client.get_entity(channel.username)
                    else:
                        # Fallback to ID, but ensure entity is loaded
                        entity = await client.get_entity(channel.id)
                except Exception as e:
                    logger.error(f"Could not get entity for channel {channel.title} (ID: {channel.id}, username: {channel.username}): {e}")
                    continue
                
                # Get messages for last 7 days (increased from 24 hours to catch more messages)
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
                
                # Track processed grouped_ids to avoid duplicates
                processed_groups = set()
                
                # Get existing messages to check for duplicates
                existing_messages = await message_service.get_messages()
                existing_ids = {m.id for m in existing_messages if m.channel_id == channel.id}
                existing_groups = {m.grouped_id for m in existing_messages if m.grouped_id and m.channel_id == channel.id}
                
                # Увеличиваем лимит до 500 сообщений для загрузки большего количества сообщений
                # Это поможет загрузить все сообщения за последние 7 дней
                async for msg in client.iter_messages(entity, limit=500):
                    if msg.date < cutoff_date:
                        break
                    
                    # Skip if we already processed this group in this run
                    if hasattr(msg, 'grouped_id') and msg.grouped_id and msg.grouped_id in processed_groups:
                        logger.debug(f"Skipping message {msg.id} - group {msg.grouped_id} already processed")
                        continue

                    # Skip if we already have this group in DB
                    if hasattr(msg, 'grouped_id') and msg.grouped_id and msg.grouped_id in existing_groups:
                        logger.debug(f"Skipping message {msg.id} - group {msg.grouped_id} already in DB")
                        continue
                        
                    # Skip if message exists (and not part of a new group we are processing)
                    if msg.id in existing_ids:
                        logger.debug(f"Skipping message {msg.id} - already exists in DB")
                        continue
                    
                    logger.debug(f"Processing message {msg.id} (has media: {bool(msg.media)}, grouped_id: {getattr(msg, 'grouped_id', None)})")
                        
                    # Download all media files
                    media_files = []
                    current_grouped_id = None
                    
                    if msg.media:
                        import os
                        from app.core.config import settings
                        
                        # Create media directory if not exists
                        # Use app/static/media to match the /static mount in main.py
                        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        media_dir = os.path.join(app_dir, "static", "media")
                        os.makedirs(media_dir, exist_ok=True)
                        logger.debug(f"Media directory: {media_dir}")
                        
                        # Check if it's a grouped media (album with multiple photos/videos)
                        if hasattr(msg, 'grouped_id') and msg.grouped_id:
                            current_grouped_id = msg.grouped_id
                            processed_groups.add(msg.grouped_id)
                            
                            # Get all messages in the group
                            # Use iter_messages to find all messages with the same grouped_id
                            group_messages = []
                            target_grouped_id = msg.grouped_id
                            logger.info(f"Searching for grouped messages with grouped_id={target_grouped_id} around message {msg.id}")
                            
                            # Method 1: Search in recent messages (last 500) to find all in the group
                            # Use larger limit to catch all messages in group
                            async for potential_msg in client.iter_messages(entity, limit=500):
                                if hasattr(potential_msg, 'grouped_id') and potential_msg.grouped_id == target_grouped_id:
                                    # Check if not already in list (by ID)
                                    if not any(m.id == potential_msg.id for m in group_messages):
                                        group_messages.append(potential_msg)
                                        logger.debug(f"Found grouped message {potential_msg.id} in group {target_grouped_id}")
                            
                            # Method 2: Also search by ID range as additional check
                            # Search wider range to catch all messages in group (especially if they're far apart)
                            search_range = 200  # Increased range
                            logger.debug(f"Also searching ID range {msg.id - search_range} to {msg.id + search_range}")
                            found_by_range = 0
                            for msg_id in range(max(1, msg.id - search_range), msg.id + search_range + 1):
                                # Skip if already found
                                if any(m.id == msg_id for m in group_messages):
                                    continue
                                try:
                                    potential_msg = await client.get_messages(entity, ids=msg_id)
                                    if potential_msg and hasattr(potential_msg, 'grouped_id') and potential_msg.grouped_id == target_grouped_id:
                                        if not any(m.id == potential_msg.id for m in group_messages):
                                            group_messages.append(potential_msg)
                                            found_by_range += 1
                                            logger.debug(f"Found grouped message {msg_id} in group {target_grouped_id} (ID range search)")
                                except Exception:
                                    # Message ID doesn't exist, continue
                                    continue
                            
                            if found_by_range > 0:
                                logger.info(f"Found {found_by_range} additional messages via ID range search")
                            
                            if not group_messages:
                                logger.warning(f"No grouped messages found for grouped_id={target_grouped_id}, using current message only")
                                group_messages = [msg]
                            else:
                                # Always include the current message if not already in list
                                if not any(m.id == msg.id for m in group_messages):
                                    group_messages.append(msg)
                                    logger.debug(f"Added current message {msg.id} to group")
                            
                            # Sort group messages by ID to ensure consistent order
                            group_messages.sort(key=lambda x: x.id)
                            logger.info(f"Found {len(group_messages)} messages in group {target_grouped_id} (IDs: {[m.id for m in group_messages]})")
                            
                            # Use the first message in group as the main message ID if possible, 
                            # or keep the current msg.id if it has text. 
                            # Actually, better to aggregate text and use the ID of the message that has text, 
                            # or the first one if multiple/none have text.
                            
                            # Let's find the message with the caption
                            main_msg = next((m for m in group_messages if m.text), group_messages[0])
                            
                            # If the current iteration 'msg' is NOT the main_msg, we should skip saving THIS 'msg' 
                            # and wait until iter_messages hits 'main_msg' OR force save 'main_msg' now.
                            # Better: force save 'main_msg' now and add its ID to existing_ids to skip later.
                            
                            msg = main_msg # Swap current msg with main_msg to save correct ID/Text
                            existing_ids.add(msg.id) # Mark as processed
                            
                            # Download each media in the group
                            logger.info(f"Processing {len(group_messages)} messages in group for media download")
                            for grouped_msg in group_messages:
                                if grouped_msg.media:
                                    try:
                                        # Determine file type and extension
                                        if grouped_msg.photo:
                                            filename = f"{channel.id}_{grouped_msg.id}.jpg"
                                            media_type = "photo"
                                        elif grouped_msg.video:
                                            filename = f"{channel.id}_{grouped_msg.id}.mp4"
                                            media_type = "video"
                                        elif grouped_msg.document:
                                            # Handle documents (PDFs, etc.)
                                            ext = grouped_msg.document.mime_type.split('/')[-1] if grouped_msg.document.mime_type else 'bin'
                                            filename = f"{channel.id}_{grouped_msg.id}.{ext}"
                                            media_type = "document"
                                        else:
                                            logger.debug(f"Message {grouped_msg.id} has media but unknown type, skipping")
                                            continue  # Skip unknown media types
                                        
                                        file_path = os.path.join(media_dir, filename)
                                        if not os.path.exists(file_path):
                                            try:
                                                # Downloading media (removed verbose logging)
                                                # Download using the message object, not just the media attribute
                                                await client.download_media(grouped_msg, file=file_path)
                                                # Verify file was created
                                                if os.path.exists(file_path):
                                                    # Downloaded successfully (removed verbose logging)
                                                    pass
                                                else:
                                                    logger.error(f"❌ File {filename} was not created after download!")
                                                    continue
                                            except Exception as download_error:
                                                logger.error(f"❌ Failed to download grouped media {filename} (msg {grouped_msg.id}): {download_error}")
                                                continue
                                        else:
                                            logger.debug(f"File {filename} already exists, skipping download")
                                        
                                        media_files.append(MediaFile(
                                            path=f"/static/media/{filename}",
                                            type=media_type
                                        ))
                                        logger.debug(f"Added {filename} to media_files list")
                                    except Exception as e:
                                        logger.error(f"Error processing grouped media {grouped_msg.id}: {e}")
                                        continue
                            
                            # Total media files prepared for group (removed verbose logging)
                        else:
                            # Single media file
                            if msg.media:
                                try:
                                    filename = f"{channel.id}_{msg.id}"
                                    media_type = None
                                    
                                    if msg.photo:
                                        filename += ".jpg"
                                        media_type = "photo"
                                    elif msg.video:
                                        filename += ".mp4"
                                        media_type = "video"
                                    elif msg.document:
                                        # Handle documents
                                        ext = msg.document.mime_type.split('/')[-1] if msg.document.mime_type else 'bin'
                                        filename += f".{ext}"
                                        media_type = "document"
                                    
                                    if media_type:
                                        file_path = os.path.join(media_dir, filename)
                                        if not os.path.exists(file_path):
                                            try:
                                                # Download using the message object
                                                await client.download_media(msg, file=file_path)
                                                # Downloaded media successfully (removed verbose logging)
                                                # Verify file was created
                                                if not os.path.exists(file_path):
                                                    logger.error(f"File {filename} was not created after download!")
                                            except Exception as download_error:
                                                logger.error(f"Failed to download media {filename}: {download_error}")
                                                # Continue without adding to media_files if download failed
                                                continue
                                        media_files.append(MediaFile(
                                            path=f"/static/media/{filename}",
                                            type=media_type
                                        ))
                                except Exception as e:
                                    logger.error(f"Error downloading media for message {msg.id}: {e}")

                    # Create message object
                    new_message = Message(
                        id=msg.id,
                        channel_id=channel.id,
                        channel_title=channel.title,
                        text=msg.text or "",  # Allow empty text if media is present
                        date=msg.date,
                        url=f"https://t.me/{channel.username}/{msg.id}" if channel.username else None,
                        status=MessageStatus.NEW,
                        media_files=media_files,
                        grouped_id=current_grouped_id
                    )
                    
                    await message_service.save_message(new_message)
                    
            except Exception as e:
                logger.error(f"Error checking channel {channel.title}: {e}")
        
        # Очищаем старые сообщения (старше 7 дней) после проверки всех каналов
        try:
            removed_tg = await message_service.cleanup_old_messages(days=7)
            if removed_tg > 0:
                logger.info(f"🧹 Cleaned up {removed_tg} old Telegram messages")
        except Exception as e:
            logger.error(f"Error cleaning up old Telegram messages: {e}")
        
        # Очищаем старые WhatsApp сообщения
        try:
            from app.services.whatsapp_message_service import whatsapp_message_service
            removed_wa = await whatsapp_message_service.cleanup_old_messages(days=7)
            if removed_wa > 0:
                logger.info(f"🧹 Cleaned up {removed_wa} old WhatsApp messages")
        except Exception as e:
            logger.error(f"Error cleaning up old WhatsApp messages: {e}")

monitoring_service = MonitoringService()
