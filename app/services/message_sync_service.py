import logging
import asyncio
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from app.services.contact_service import contact_service
from app.services.contact_message_service import contact_message_service
from app.services.green_api_service import green_api_service
from app.models.contact_message import ContactMessage

logger = logging.getLogger(__name__)


class MessageSyncService:
    """Service for synchronizing WhatsApp messages via Green API"""

    async def _retry_fetch(self, fetch_func, *args, max_tries: int = 4, base_delay: int = 1):
        """Retry helper with exponential backoff for API calls."""
        delay = base_delay
        for attempt in range(1, max_tries + 1):
            try:
                return await fetch_func(*args)
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{max_tries} failed for {fetch_func.__name__}: {e}")
                if attempt == max_tries:
                    raise
                await asyncio.sleep(delay)
                delay *= 2

    async def process_global_notifications(self) -> Dict[str, int]:
        """
        Process all pending notifications from Green API and dispatch them to the correct contacts.
        This prevents data loss (deleting notifications for other contacts) and leaks.
        """
        processed_count = 0
        errors = 0
        max_notifications = 100  # Limit per batch
        
        # Cache contacts for quick lookup: clean_phone -> contact_id
        contacts = await contact_service.get_contacts()
        contact_map = {}
        for c in contacts:
            if c.phone:
                clean = ''.join(filter(str.isdigit, c.phone))
                contact_map[f"{clean}@c.us"] = c.id
        
        logger.info(f"Starting global notification processing. Known contacts: {len(contact_map)}")
        
        for i in range(max_notifications):
            try:
                notification = await green_api_service.receive_notification()
                if not notification:
                    break  # Queue is empty
                
                receipt_id = notification.get('receiptId')
                body = notification.get('body', {})
                type_webhook = body.get('typeWebhook')
                
                logger.debug(f"Processing notification #{i+1}: type={type_webhook}, receiptId={receipt_id}")
                
                # Handle message events
                if type_webhook in ['incomingMessageReceived', 'outgoingMessageReceived', 'outgoingAPIMessageReceived']:
                    message_data = body.get('messageData', {})
                    sender_data = body.get('senderData', {})
                    instance_data = body.get('instanceData', {})
                    
                    # Skip reaction messages - они бесполезны
                    type_message = message_data.get('typeMessage', '')
                    if 'reaction' in type_message.lower() or type_message == 'reactionMessage':
                        logger.debug(f"Skipping reaction message notification: {receipt_id}")
                        if receipt_id:
                            await green_api_service.delete_notification(receipt_id)
                        continue
                    
                    # Determine Chat ID (who is this message associated with?)
                    # For incoming: senderData.chatId or messageData.chatId
                    # For outgoing: messageData.chatId (the recipient)
                    chat_id = message_data.get('chatId') or sender_data.get('chatId')
                    
                    # --- Task 5: Group Monitoring ---
                    # Check if this is from the monitored tournament group
                    # Group ID: 120363304781973950@g.us
                    TARGET_GROUP_ID = "120363304781973950@g.us"
                    
                    if chat_id == TARGET_GROUP_ID:
                        logger.info(f"Received message from monitored group: {chat_id}")
                        # Import here to avoid circular imports
                        from app.services.tournament_service import tournament_service
                        
                        # Construct message object for tournament service
                        raw_msg = body.copy()
                        raw_msg.update(message_data)
                        raw_msg['chatId'] = chat_id
                        
                        # Process asynchronously
                        try:
                            await tournament_service.process_message(raw_msg)
                        except Exception as e:
                            logger.error(f"Error processing tournament message: {e}")
                        
                        # Also save as regular WhatsApp message for display in UI
                        try:
                            from app.services.whatsapp_message_service import whatsapp_message_service
                            from app.models.whatsapp_message import WhatsAppMessage
                            from datetime import datetime
                            
                            # Get group name from Green API
                            from app.services.green_api_service import green_api_service
                            
                            # Try to get group name from Green API
                            group_name = TARGET_GROUP_ID
                            try:
                                # Method 1: Try get_chats() first - it's more reliable
                                chats = await green_api_service.get_chats()
                                for chat in chats:
                                    if chat.get('id') == TARGET_GROUP_ID and chat.get('type') == 'group':
                                        group_name = chat.get('name', TARGET_GROUP_ID)
                                        logger.info(f"✅ Using group name '{group_name}' from get_chats()")
                                        break
                                
                                # Method 2: If not found, try get_group_data()
                                if group_name == TARGET_GROUP_ID:
                                    group_data = await green_api_service.get_group_data(TARGET_GROUP_ID)
                                    if group_data and isinstance(group_data, dict):
                                        group_name = (group_data.get('name') or 
                                                     group_data.get('title') or
                                                     group_data.get('subject') or
                                                     TARGET_GROUP_ID)
                                        if group_name != TARGET_GROUP_ID:
                                            logger.info(f"✅ Using group name '{group_name}' from get_group_data()")
                            except Exception as e:
                                logger.warning(f"Could not get group name for {TARGET_GROUP_ID}: {e}")
                                # Use ID as fallback
                                group_name = TARGET_GROUP_ID
                            
                            # Extract text
                            text = message_data.get('textMessage') or message_data.get('extendedTextMessageData', {}).get('text') or ''
                            
                            # Extract timestamp
                            timestamp = message_data.get('timestampMessage') or body.get('timestamp')
                            if isinstance(timestamp, int):
                                if timestamp > 1000000000000:
                                    msg_date = datetime.fromtimestamp(timestamp / 1000)
                                else:
                                    msg_date = datetime.fromtimestamp(timestamp)
                            else:
                                msg_date = datetime.now()
                            
                            # Extract sender
                            sender = sender_data.get('senderName') or sender_data.get('sender') or 'Unknown'
                            
                            # Extract sender_id from message_data or sender_data
                            sender_id = (message_data.get('senderId') or 
                                        sender_data.get('senderId') if isinstance(sender_data, dict) else None)
                            
                            # Create WhatsApp message
                            # Use group ID for channel_id matching, not the display name
                            wa_message = WhatsAppMessage(
                                chat_name=TARGET_GROUP_ID,  # Use group ID for channel_id matching
                                sender=sender,
                                sender_id=sender_id if sender_id and '@c.us' in sender_id else None,  # Сохраняем WhatsApp ID автора
                                text=text,
                                date=msg_date,
                                message_id=message_data.get('idMessage', ''),
                                media_type=None,
                                media_path=None,
                                media_files=None
                            )
                            
                            await whatsapp_message_service.save_message(wa_message)
                            logger.info(f"Saved WhatsApp message from group {group_name}")
                            
                            # Триггерим анализ автора сразу после сохранения сообщения
                            if sender and sender != 'Unknown':
                                try:
                                    import asyncio
                                    from app.services.author_analysis_service import author_analysis_service
                                    
                                    async def run_analysis_with_error_handling():
                                        try:
                                            await author_analysis_service.analyze_author_immediately(
                                                sender_name=sender,
                                                sender_id=sender_id,
                                                group_id=TARGET_GROUP_ID,
                                                group_name=group_name
                                            )
                                        except Exception as e:
                                            logger.error(f"Error in background author analysis for {sender}: {e}", exc_info=True)
                                    
                                    asyncio.create_task(run_analysis_with_error_handling())
                                    logger.info(f"Triggered immediate analysis for author: {sender}")
                                except Exception as e:
                                    logger.error(f"Could not trigger immediate author analysis: {e}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Error saving WhatsApp message from group: {e}")
                    
                    # --- Existing Contact Logic ---
                    if chat_id and chat_id in contact_map:
                        contact_id = contact_map[chat_id]
                        
                        # Construct a raw message object compatible with _parse_green_api_message
                        # We need to merge fields to look like a history message
                        raw_msg = body.copy()
                        raw_msg.update(message_data)
                        raw_msg['chatId'] = chat_id
                        
                        # Determine type for parser
                        if type_webhook == 'incomingMessageReceived':
                            raw_msg['type'] = 'incoming'
                        else:
                            raw_msg['type'] = 'outgoing'
                            
                        # Parse and save
                        try:
                            contact_msg = await self._parse_green_api_message(raw_msg, contact_id)
                            if contact_msg:
                                await contact_message_service.save_message(contact_msg)
                                processed_count += 1
                                logger.info(f"Saved message {contact_msg.whatsapp_msg_id} for contact {contact_id}")
                        except Exception as e:
                            logger.error(f"Error parsing/saving notification message: {e}")
                            errors += 1
                    else:
                        logger.debug(f"Ignored notification for unknown chat: {chat_id}")
                
                # Always delete notification after processing to unblock queue
                if receipt_id:
                    await green_api_service.delete_notification(receipt_id)
                    
            except Exception as e:
                logger.error(f"Error in notification loop: {e}")
                errors += 1
                
        logger.info(f"Global notification processing finished. Processed: {processed_count}, Errors: {errors}")
        return {"processed": processed_count, "errors": errors}

    async def sync_contact_messages(
        self,
        contact_id: int,
        full_sync: bool = False
    ) -> Dict[str, int]:
        """
        Sync messages for a single contact.
        1. Process global notifications (to catch any pending real-time messages).
        2. Fetch chat history from API (to fill gaps).
        """
        result = {"synced": 0, "skipped": 0, "errors": []}
        
        # 1. Process global notifications first
        try:
            await self.process_global_notifications()
        except Exception as e:
            logger.error(f"Error in global notification processing during sync: {e}")
            result["errors"].append(f"Notification error: {str(e)}")

        try:
            # Get contact
            contact = await contact_service.get_contact_by_id(contact_id)
            if not contact:
                result["errors"].append(f"Contact {contact_id} not found")
                return result

            # 2. Fetch chat history
            raw_messages = await self._retry_fetch(green_api_service.get_chat_history, contact.phone)
            logger.info(f"Fetched {len(raw_messages)} messages from chat history for {contact.name}")
            
            if not raw_messages:
                contact.last_sync_at = datetime.now()
                await contact_service.update_contact(contact_id, contact)
                return result

            messages_to_save: List[ContactMessage] = []
            for msg in raw_messages:
                try:
                    contact_msg = await self._parse_green_api_message(msg, contact_id)
                    if contact_msg:
                        if full_sync or not contact.last_sync_at or contact_msg.timestamp > contact.last_sync_at:
                            messages_to_save.append(contact_msg)
                        else:
                            result["skipped"] += 1
                except Exception as e:
                    logger.error(f"Error parsing message: {e}")
                    result["errors"].append(str(e))

            if messages_to_save:
                save_result = await contact_message_service.save_messages_bulk(messages_to_save)
                result["synced"] = save_result.get("saved", 0)
                result["skipped"] += save_result.get("skipped", 0)

            # Update last sync timestamp
            contact.last_sync_at = datetime.now()
            await contact_service.update_contact(contact_id, contact)
            logger.info(f"Sync completed for contact {contact_id}: {result}")
            
        except Exception as e:
            logger.error(f"Error syncing contact {contact_id}: {e}")
            result["errors"].append(str(e))
            
        return result

    async def sync_all_contacts(
        self,
        full_sync: bool = False,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, int]:
        """Sync messages for all contacts.

        Args:
            full_sync: If True, ignore last_sync_at for all contacts
            progress_callback: Optional callback for progress updates
        """
        result = {
            "total": 0,
            "processed": 0,
            "failed": 0,
            "synced_messages": 0,
            "errors": []
        }
        try:
            contacts = await contact_service.get_contacts()
            result["total"] = len(contacts)
            for contact in contacts:
                try:
                    if progress_callback:
                        await progress_callback(result["processed"] + 1, result["total"], contact.name)
                    sync_result = await self.sync_contact_messages(contact.id, full_sync=False)
                    result["processed"] += 1
                    result["synced_messages"] += sync_result["synced"]
                    if sync_result["errors"]:
                        result["failed"] += 1
                        result["errors"].extend(sync_result["errors"])
                except Exception as e:
                    logger.error(f"Error syncing contact {contact.id}: {e}")
                    result["failed"] += 1
                    result["errors"].append(f"{contact.name}: {str(e)}")
            logger.info(f"Bulk sync completed: {result}")
        except Exception as e:
            logger.error(f"Error in bulk sync: {e}")
            result["errors"].append(str(e))
        return result

    async def should_trigger_ai_analysis(self, contact_id: int, new_messages_count: int) -> bool:
        """Determine if AI analysis should be triggered for a contact.

        Triggers if:
        - New messages count > 3
        - Or last analysis was > 24 hours ago
        """
        if new_messages_count > 3:
            return True
        from app.services.contact_insight_service import contact_insight_service
        insight = await contact_insight_service.get_insights(contact_id)
        if not insight:
            return new_messages_count > 0
        time_since_analysis = datetime.now() - insight.updated_at
        return time_since_analysis > timedelta(hours=24) and new_messages_count > 0

    async def _parse_green_api_message(self, raw_message: dict, contact_id: int) -> Optional[ContactMessage]:
        """Parse a message from Green API format to ContactMessage.

        Green API message format (example):
        {
            "idMessage": "...",
            "timestamp": 1700000000,
            "typeMessage": "textMessage",
            "chatId": "79001234567@c.us",
            "senderId": "79001234567@c.us",
            "senderName": "Contact Name",
            "textMessage": "Message text",
            "type": "incoming" or "outgoing"
        }
        """
        try:
            logger.info(f"Parsing raw message: {raw_message}")
            msg_type = raw_message.get("type", "")
            if msg_type not in ["incoming", "outgoing"]:
                type_message = raw_message.get("typeMessage", "")
                if "incoming" in type_message.lower():
                    msg_type = "incoming"
                elif "outgoing" in type_message.lower():
                    msg_type = "outgoing"
                else:
                    msg_type = "incoming"
            direction = "in" if msg_type == "incoming" else "out"
            
            # First check if this is a media message
            whatsapp_msg_id = raw_message.get("idMessage")
            media_info = await self._extract_media_info(raw_message, contact_id, whatsapp_msg_id)
            
            # Extract text
            text = self._extract_text_from_message(raw_message)
            
            # Skip only if NO text AND NO media
            if not text and not media_info.get("media_type"):
                logger.warning(f"Skipping message without text or media: {whatsapp_msg_id}")
                return None
            
            # If no text but has media, use a placeholder
            if not text and media_info.get("media_type"):
                text = f"[{media_info['media_type']}]"
            
            timestamp = raw_message.get("timestamp")
            dt = datetime.now()
            if isinstance(timestamp, int):
                if timestamp > 1000000000000:
                    dt = datetime.fromtimestamp(timestamp / 1000)
                else:
                    dt = datetime.fromtimestamp(timestamp)
            elif isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp)
                except ValueError:
                    logger.warning(f"Could not parse timestamp string: {timestamp}")
            
            sender_name = raw_message.get("senderName")
            
            if media_info.get("media_url"):
                logger.debug(f"Media URL found for message {whatsapp_msg_id}: {media_info['media_url']}")
            
            parsed_msg = ContactMessage(
                contact_id=contact_id,
                direction=direction,
                message=text,
                timestamp=dt,
                whatsapp_msg_id=whatsapp_msg_id,
                loaded_via="greenapi",
                sender_name=sender_name,
                media_type=media_info.get("media_type"),
                media_path=media_info.get("media_path"),
                media_url=media_info.get("media_url"),
                media_filename=media_info.get("media_filename"),
                media_mime_type=media_info.get("media_mime_type")
            )
            logger.info(f"Successfully parsed message: {parsed_msg}")
            return parsed_msg
        except Exception as e:
            logger.error(f"Error parsing message: {e}, raw: {raw_message}")
            return None

    def _extract_text_from_message(self, msg: dict) -> str:
        """Extract text content from various Green API message types."""
        type_message = msg.get("typeMessage", "")
        if type_message == "textMessage":
            return msg.get("textMessageData", {}).get("textMessage") or msg.get("textMessage") or ""
        elif type_message == "extendedTextMessage":
            return msg.get("extendedTextMessageData", {}).get("text") or msg.get("textMessage") or ""
        elif type_message == "quotedMessage":
            return msg.get("extendedTextMessageData", {}).get("text") or msg.get("textMessage") or ""
        elif type_message == "imageMessage":
            caption = msg.get("imageMessageData", {}).get("caption", "")
            return f"[Фото] {caption}".strip()
        elif type_message == "videoMessage":
            caption = msg.get("videoMessageData", {}).get("caption", "")
            return f"[Видео] {caption}".strip()
        elif type_message == "documentMessage":
            filename = msg.get("documentMessageData", {}).get("fileName", "")
            return f"[Документ] {filename}".strip()
        elif type_message == "audioMessage":
            return "[Аудио]"
        return msg.get("textMessage") or msg.get("text") or msg.get("body") or ""

    async def _extract_media_info(self, msg: dict, contact_id: int, whatsapp_msg_id: str) -> dict:
        """Extract media information from Green API message and download the file.
        
        Handles two formats:
        1. Incoming messages: downloadUrl, fileName, mimeType at top level
        2. Outgoing messages: nested in imageMessageData/videoMessageData etc.

        Returns dict with media_type, media_path, media_url, media_filename, media_mime_type
        """
        import os
        import aiofiles
        from app.core.config import settings
        from app.services.green_api_service import green_api_service
        
        result = {"media_type": None, "media_path": None, "media_url": None, "media_filename": None, "media_mime_type": None}
        type_message = msg.get("typeMessage", "")
        media_type_map = {
            "imageMessage": "image",
            "videoMessage": "video",
            "documentMessage": "document",
            "audioMessage": "audio",
            "stickerMessage": "sticker"
        }
        
        if type_message not in media_type_map:
            return result
            
        result["media_type"] = media_type_map[type_message]
        
        # Check if downloadUrl exists at top level (incoming messages format)
        download_url = msg.get("downloadUrl")
        
        if download_url:
            # Incoming message format - media info at top level
            result["media_url"] = download_url
            filename = msg.get("fileName") or msg.get("filename")
            mime_type = msg.get("mimeType") or msg.get("mimetype")
        else:
            # Outgoing message format - media info in nested data
            # Get media data based on message type
            media_data = None
            if type_message == "imageMessage":
                media_data = msg.get("imageMessageData", {})
            elif type_message == "videoMessage":
                media_data = msg.get("videoMessageData", {})
            elif type_message == "documentMessage":
                media_data = msg.get("documentMessageData", {})
            elif type_message == "audioMessage":
                media_data = msg.get("audioMessageData", {})
            elif type_message == "stickerMessage":
                media_data = msg.get("stickerMessageData", {})
                
            if not media_data:
                logger.warning(f"No media data found for {type_message} message {whatsapp_msg_id}")
                return result
            
            download_url = media_data.get("downloadUrl") or media_data.get("url")
            result["media_url"] = download_url
            filename = media_data.get("fileName") or media_data.get("filename")
            mime_type = media_data.get("mimeType") or media_data.get("mimetype")
        
        # Determine filename if not provided
        if not filename:
            ext_map = {"image": ".jpg", "video": ".mp4", "audio": ".ogg", "sticker": ".webp", "document": ".pdf"}
            ext = ext_map.get(result["media_type"], "")
            filename = f"{whatsapp_msg_id}{ext}"
            
        result["media_filename"] = filename
        result["media_mime_type"] = mime_type
        
        # Try to download media
        if download_url:
            try:
                # Download media directly from downloadUrl (direct HTTP GET, not via Green API endpoint)
                media_dir = os.path.join(settings.DATA_DIR, "media", "whatsapp", str(contact_id))
                os.makedirs(media_dir, exist_ok=True)
                save_path = os.path.join(media_dir, filename)
                
                success = await green_api_service.download_media_file(download_url, save_path)
                if success:
                    result["media_path"] = f"/media/whatsapp/{contact_id}/{filename}"
                    # Downloaded media file successfully (removed verbose logging)
                else:
                    logger.error(f"Failed to download media from {download_url}")
                    
            except Exception as e:
                logger.error(f"Error downloading media: {e}")
        else:
            # No downloadUrl - try download_file_by_id as fallback
            chat_id = msg.get("chatId")
            if chat_id:
                try:
                    # Downloading media file (removed verbose logging)
                    file_data = await green_api_service.download_file_by_id(chat_id, whatsapp_msg_id)
                    
                    if file_data:
                        media_dir = os.path.join(settings.DATA_DIR, "media", "whatsapp", str(contact_id))
                        os.makedirs(media_dir, exist_ok=True)
                        save_path = os.path.join(media_dir, filename)
                        
                        async with aiofiles.open(save_path, "wb") as f:
                            await f.write(file_data)
                        
                        result["media_path"] = f"/media/whatsapp/{contact_id}/{filename}"
                        # Downloaded media file successfully (removed verbose logging)
                    else:
                        logger.error(f"Failed to download media file {whatsapp_msg_id}")
                        
                except Exception as e:
                    logger.error(f"Error downloading media via download_file_by_id: {e}")
            else:
                logger.warning(f"No downloadUrl or chatId for media message {whatsapp_msg_id}")
            
        return result

# Singleton instance
message_sync_service = MessageSyncService()
