from fastapi import APIRouter, HTTPException, Path, Body
from typing import List, Optional
from pydantic import BaseModel
import logging
import os
from datetime import datetime, timezone, timedelta
from app.models.message import Message, MessageStatus
from app.services.message_service import message_service
from app.services.llm_service import llm_service
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

class MessagesResponse(BaseModel):
    """Response model with cursor-based pagination (like Instagram/VK)"""
    messages: List[Message]
    has_more: bool
    next_cursor: Optional[str] = None

@router.get("/", response_model=MessagesResponse)
async def list_messages(
    status: Optional[MessageStatus] = None, 
    force_update: bool = False,
    after: Optional[str] = None,  # Cursor for pagination (message ID)
    limit: int = 100  # Number of messages to return (increased to include WhatsApp messages)
):
    """
    Get messages with cursor-based pagination (like Instagram/VK).
    Use 'after' parameter with message ID to get older messages.
    """
    if force_update:
        from app.services.monitoring_service import monitoring_service
        await monitoring_service.force_check()
    
    # Get Telegram messages
    logger.info(f"📱 Starting to fetch messages. Status filter: {status}, limit: {limit}, after: {after}")
    tg_messages = await message_service.get_messages(status)
    logger.info(f"📱 Loaded {len(tg_messages)} Telegram messages")
    
    # Get WhatsApp messages (only last 7 days)
    unified_wa_messages = []
    try:
        from app.services.whatsapp_message_service import whatsapp_message_service
        # Фильтруем WhatsApp сообщения - только за последние 7 дней
        since_date = datetime.now(timezone.utc) - timedelta(days=7)
        logger.info(f"📱 Fetching WhatsApp messages since {since_date}")
        wa_messages = await whatsapp_message_service.get_messages(since=since_date)
        logger.info(f"📱 Loaded {len(wa_messages)} WhatsApp messages from service")
        
        # Convert WhatsApp messages to unified Message format
        from app.models.message import MediaFile
        
        logger.info(f"📱 Starting conversion of {len(wa_messages)} WhatsApp messages")
        for idx, wa_msg in enumerate(wa_messages):
            try:
                logger.debug(f"📱 Converting WhatsApp message {idx+1}/{len(wa_messages)}: chat_name={wa_msg.chat_name}, date={wa_msg.date}, text_len={len(wa_msg.text) if wa_msg.text else 0}")
                # Map media files
                media_files = []
                if wa_msg.media_files:
                    for mf in wa_msg.media_files:
                        media_files.append(MediaFile(path=mf['path'], type=mf['type']))
                elif wa_msg.media_path: # Legacy/Single media
                     media_files.append(MediaFile(path=wa_msg.media_path, type=wa_msg.media_type or 'photo'))

                # For WhatsApp messages, chat_name might be group ID or display name
                # We need to match it with channel.id from /channels/ endpoint
                # If chat_name is a group ID (ends with @g.us), use it directly
                # Otherwise, try to find matching channel by title
                channel_id = wa_msg.chat_name
                channel_title = wa_msg.chat_name
                
                # If chat_name is not a group ID, try to find the channel by title
                if not channel_id.endswith('@g.us'):
                    from app.services.channel_service import channel_service
                    all_channels = await channel_service.get_channels()
                    matching_channel = next((c for c in all_channels if c.title == wa_msg.chat_name and c.platform.value == 'whatsapp'), None)
                    if matching_channel:
                        channel_id = matching_channel.id
                        channel_title = matching_channel.title
                        logger.debug(f"Mapped WhatsApp message chat_name '{wa_msg.chat_name}' to channel_id '{channel_id}'")
                    else:
                        logger.warning(f"Could not find matching channel for WhatsApp message with chat_name '{wa_msg.chat_name}'")
                else:
                    # chat_name is already a group ID, use it directly
                    logger.debug(f"Using group ID directly as channel_id: {channel_id}")

                # Filter out numeric IDs that are not phone numbers
                final_sender = None
                if wa_msg.sender and wa_msg.sender != 'Unknown':
                    # Check if sender is a valid phone number (Russian format: starts with 7 or 8, 10-11 digits)
                    sender_str = str(wa_msg.sender)
                    is_phone_number = (sender_str.isdigit() and 
                                       (sender_str.startswith('7') or sender_str.startswith('8')) and 
                                       10 <= len(sender_str) <= 11)
                    # Only use sender if it's a phone number or contains non-digit characters (i.e., it's a name)
                    if not sender_str.isdigit() or is_phone_number:
                        final_sender = wa_msg.sender
                    else:
                        # It's a numeric ID that's not a phone number - don't use it
                        logger.debug(f"Filtering out numeric ID '{wa_msg.sender}' as sender for message {wa_msg.message_id} (not a phone number)")
                
                # Ищем контакт по WhatsApp ID для добавления author_contact_id
                author_contact_id = None
                if wa_msg.sender_id and '@c.us' in wa_msg.sender_id:
                    try:
                        from app.services.contact_service import contact_service
                        contacts = await contact_service.get_contacts()
                        # Ищем контакт по WhatsApp ID
                        for contact in contacts:
                            if contact.whatsapp_id == wa_msg.sender_id:
                                author_contact_id = contact.id
                                logger.debug(f"Found contact {contact.id} for WhatsApp ID {wa_msg.sender_id}")
                                break
                    except Exception as e:
                        logger.debug(f"Error looking up contact for {wa_msg.sender_id}: {e}")
                
                unified_wa_messages.append(Message(
                    id=wa_msg.message_id, # Use hash as ID
                    channel_id=channel_id, # Use group ID for matching with channels
                    channel_title=channel_title, # Use display name for UI
                    text=wa_msg.text,
                    date=wa_msg.date,
                    url=None,
                    status=MessageStatus.NEW, # Default status
                    media_files=media_files,
                    sender=final_sender,  # Автор сообщения
                    author_contact_id=author_contact_id  # ID контакта автора
                ))
                logger.info(f"✅ WhatsApp message {wa_msg.message_id}: channel_id={channel_id}, channel_title={channel_title}, chat_name={wa_msg.chat_name}")
                if final_sender:
                    logger.info(f"✅ Message {wa_msg.message_id} has sender: {final_sender}")
            except Exception as e:
                import logging
                logger.error(f"Error converting WhatsApp message {wa_msg.id}: {e}", exc_info=True)
                continue
    except Exception as e:
        import logging
        logger.error(f"Error fetching WhatsApp messages: {e}", exc_info=True)
        # Continue without WhatsApp messages
        pass
    
    wa_channel_ids = set(m.channel_id for m in unified_wa_messages)
    logger.info(f"✅ Converted {len(unified_wa_messages)} WhatsApp messages. Channel IDs: {wa_channel_ids}")
    if wa_channel_ids:
        logger.info(f"📱 WhatsApp channel IDs details: {[{'id': str(cid), 'count': len([m for m in unified_wa_messages if m.channel_id == cid])} for cid in wa_channel_ids]}")
    
    try:
        # Merge and sort
        all_messages = tg_messages + unified_wa_messages
        logger.info(f"📊 Total messages before sort: {len(tg_messages)} Telegram + {len(unified_wa_messages)} WhatsApp = {len(all_messages)} total")
        all_messages.sort(key=lambda x: x.date, reverse=True)  # Newest first
        logger.info(f"📊 After sort, first 5 message dates: {[m.date.isoformat() for m in all_messages[:5]]}")
        
        # Apply cursor-based pagination (like Instagram/VK)
        if after:
            # Find the message with ID = after, then return messages after it
            # Convert both to string for comparison (id can be int or str)
            after_str = str(after)
            after_index = next((i for i, m in enumerate(all_messages) if str(m.id) == after_str), None)
            if after_index is not None:
                all_messages = all_messages[after_index + 1:]
            else:
                # Cursor not found, return empty
                all_messages = []
        
        # Apply limit
        paginated_messages = all_messages[:limit]
        logger.info(f"📊 After pagination (limit={limit}): {len(paginated_messages)} messages. Channel IDs: {set(str(m.channel_id) for m in paginated_messages)}")
        
        # Determine if there are more messages
        has_more = len(all_messages) > limit
        # Convert id to string for cursor (like Instagram/VK)
        # Only set next_cursor if we have messages and there are more
        next_cursor = None
        if paginated_messages and has_more:
            try:
                next_cursor = str(paginated_messages[-1].id)
            except (IndexError, AttributeError) as e:
                logger.warning(f"Could not get next_cursor: {e}")
                next_cursor = None
        
        return MessagesResponse(
            messages=paginated_messages,
            has_more=has_more,
            next_cursor=next_cursor
        )
    except Exception as e:
        logger.error(f"Error in list_messages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/{message_id}/summary", response_model=Message)
async def generate_summary(message_id: int = Path(..., title="The ID of the message")):
    messages = await message_service.get_messages()
    # Find message (inefficient but works for JSON)
    message = next((m for m in messages if m.id == message_id), None)
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
        
    try:
        summary = await llm_service.make_summary(message.text)
        message.summary = summary
        await message_service.update_message(message)
        return message
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{message_id}/rewrite", response_model=Message)
async def generate_rewrite(message_id: int = Path(..., title="The ID of the message")):
    messages = await message_service.get_messages()
    message = next((m for m in messages if m.id == message_id), None)
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
        
    try:
        rewrite = await llm_service.make_rewrite(message.text)
        message.rewrite = rewrite
        await message_service.update_message(message)
        return message
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PublishRequest(BaseModel):
    text_type: str  # 'summary' or 'rewrite'
    target_channel_id: Optional[int] = None

@router.post("/{message_id}/publish")
async def publish_message(
    message_id: int = Path(..., title="The ID of the message"),
    request: PublishRequest = Body(...)
):
    from app.services.publication_service import publication_service
    try:
        return await publication_service.publish_message(
            message_id=message_id,
            text_type=request.text_type,
            target_channel_id=request.target_channel_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/redownload-media")
async def redownload_media():
    """Re-download all media files from existing messages"""
    import os
    import logging
    from app.services.telegram_service import telegram_service
    from app.models.message import MediaFile
    from app.core.config import settings
    
    logger = logging.getLogger(__name__)
    
    try:
        client = await telegram_service.get_client()
        
        if not await client.is_user_authorized():
            raise HTTPException(status_code=401, detail="Not authorized in Telegram")
        
        messages = await message_service.get_messages()
        # Use app/static/media to match the /static mount in main.py
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        media_dir = os.path.join(app_dir, "static", "media")
        os.makedirs(media_dir, exist_ok=True)
        # Processing messages for media redownload (removed verbose logging)
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for message in messages:
            try:
                # Get entity for the channel first
                try:
                    from app.services.channel_service import channel_service
                    channels = await channel_service.get_channels()
                    channel = next((c for c in channels if str(c.id) == str(message.channel_id)), None)
                    if channel:
                        if channel.username:
                            entity = await client.get_entity(channel.username)
                        else:
                            entity = await client.get_entity(channel.id)
                    else:
                        entity = await client.get_entity(message.channel_id)
                except Exception as e:
                    logger.warning(f"Could not get entity for channel {message.channel_id}: {e}, trying direct ID")
                    try:
                        entity = await client.get_entity(message.channel_id)
                    except Exception:
                        logger.error(f"Failed to get entity for channel {message.channel_id}, skipping message {message.id}")
                        continue
                
                # Get message from Telegram
                tg_msg = await client.get_messages(entity, ids=message.id)
                
                if not tg_msg:
                    skipped_count += 1
                    logger.debug(f"Message {message.id} not found in Telegram")
                    continue
                
                if not tg_msg.media:
                    skipped_count += 1
                    logger.debug(f"Message {message.id} has no media")
                    continue
                
                media_files = []
                
                # Check if it's a grouped media (album)
                if hasattr(tg_msg, 'grouped_id') and tg_msg.grouped_id:
                    
                    # Get all messages in the group - use improved search
                    group_messages = []
                    target_grouped_id = tg_msg.grouped_id
                    logger.info(f"Searching for grouped messages with grouped_id={target_grouped_id} for message {message.id}")
                    
                    # Method 1: Search in recent messages
                    async for grouped_msg in client.iter_messages(entity, limit=500):
                        if hasattr(grouped_msg, 'grouped_id') and grouped_msg.grouped_id == target_grouped_id:
                            if not any(m.id == grouped_msg.id for m in group_messages):
                                group_messages.append(grouped_msg)
                    
                    # Method 2: Also search by ID range
                    search_range = 200
                    for msg_id in range(max(1, message.id - search_range), message.id + search_range + 1):
                        if any(m.id == msg_id for m in group_messages):
                            continue
                        try:
                            potential_msg = await client.get_messages(entity, ids=msg_id)
                            if potential_msg and hasattr(potential_msg, 'grouped_id') and potential_msg.grouped_id == target_grouped_id:
                                if not any(m.id == potential_msg.id for m in group_messages):
                                    group_messages.append(potential_msg)
                        except Exception:
                            continue
                    
                    if not group_messages:
                        group_messages = [tg_msg]
                    
                    group_messages.sort(key=lambda x: x.id)
                    logger.info(f"Found {len(group_messages)} messages in group {target_grouped_id} (IDs: {[m.id for m in group_messages]})")
                    
                    # Download each media in the group
                    for grouped_msg in group_messages:
                        if grouped_msg.media:
                            try:
                                if grouped_msg.photo:
                                    filename = f"{message.channel_id}_{grouped_msg.id}.jpg"
                                    media_type = "photo"
                                elif grouped_msg.video:
                                    filename = f"{message.channel_id}_{grouped_msg.id}.mp4"
                                    media_type = "video"
                                elif grouped_msg.document:
                                    ext = grouped_msg.document.mime_type.split('/')[-1] if grouped_msg.document.mime_type else 'bin'
                                    filename = f"{message.channel_id}_{grouped_msg.id}.{ext}"
                                    media_type = "document"
                                else:
                                    continue
                                
                                file_path = os.path.join(media_dir, filename)
                                if not os.path.exists(file_path):
                                    # Downloading media (removed verbose logging)
                                    await client.download_media(grouped_msg, file=file_path)
                                    if os.path.exists(file_path):
                                        # Downloaded successfully (removed verbose logging)
                                        pass
                                    else:
                                        logger.error(f"❌ File {filename} was not created")
                                        continue
                                
                                media_files.append(MediaFile(
                                    path=f"/static/media/{filename}",
                                    type=media_type
                                ))
                            except Exception as e:
                                logger.error(f"Error downloading grouped media {grouped_msg.id}: {e}")
                                continue
                    
                    message.grouped_id = tg_msg.grouped_id
                else:
                    # Single media file
                    if tg_msg.media:
                        try:
                            if tg_msg.photo:
                                filename = f"{message.channel_id}_{message.id}.jpg"
                                media_type = "photo"
                            elif tg_msg.video:
                                filename = f"{message.channel_id}_{message.id}.mp4"
                                media_type = "video"
                            elif tg_msg.document:
                                ext = tg_msg.document.mime_type.split('/')[-1] if tg_msg.document.mime_type else 'bin'
                                filename = f"{message.channel_id}_{message.id}.{ext}"
                                media_type = "document"
                            else:
                                continue
                            
                            file_path = os.path.join(media_dir, filename)
                            if not os.path.exists(file_path):
                                # Downloading media (removed verbose logging)
                                await client.download_media(tg_msg, file=file_path)
                                if os.path.exists(file_path):
                                    # Downloaded successfully (removed verbose logging)
                                    pass
                                else:
                                    logger.error(f"❌ File {filename} was not created")
                                    continue
                            
                            media_files.append(MediaFile(
                                path=f"/static/media/{filename}",
                                type=media_type
                            ))
                        except Exception as e:
                            logger.error(f"Error downloading media for message {message.id}: {e}")
                            continue
                
                # Update message with media files
                if media_files:
                    message.media_files = media_files
                    await message_service.update_message(message)
                    updated_count += 1
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing message {message.id}: {e}", exc_info=True)
                continue
        
        logger.info(f"Redownload completed: {updated_count} updated, {skipped_count} skipped, {error_count} errors")
        return {
            "status": "success",
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "message": f"Re-downloaded media for {updated_count} messages ({skipped_count} skipped, {error_count} errors)"
        }
        
    except Exception as e:
        logger.error(f"Error in redownload_media: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/document-text/{file_path:path}")
async def get_document_text(file_path: str):
    """
    Extract text from PDF or DOCX document.
    file_path should be relative to /static/media/ (e.g., '120363304781973950_ACF4E5999285AA7DF35734AAE887B547.pdf')
    """
    try:
        # Sanitize file path
        file_path = file_path.lstrip('/')
        if '..' in file_path:
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Construct full path - file_path is relative to /static/media/
        # Remove leading /static/media/ if present
        if file_path.startswith('static/media/'):
            file_path = file_path.replace('static/media/', '', 1)
        if file_path.startswith('/static/media/'):
            file_path = file_path.replace('/static/media/', '', 1)
        
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        full_path = os.path.join(BASE_DIR, "app", "static", "media", file_path)
        
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        
        if ext == '.pdf':
            try:
                import PyPDF2
                with open(full_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    text_parts = []
                    for page_num, page in enumerate(pdf_reader.pages):
                        try:
                            page_text = page.extract_text()
                            if page_text:
                                text_parts.append(f"--- Страница {page_num + 1} ---\n{page_text}")
                        except Exception as e:
                            logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                            continue
                    text = "\n\n".join(text_parts)
            except ImportError:
                raise HTTPException(status_code=500, detail="PyPDF2 library not installed")
            except Exception as e:
                logger.error(f"Error reading PDF: {e}")
                raise HTTPException(status_code=500, detail=f"Error reading PDF: {str(e)}")
        
        elif ext in ['.doc', '.docx']:
            try:
                from docx import Document
                doc = Document(full_path)
                text_parts = []
                for para in doc.paragraphs:
                    if para.text.strip():
                        text_parts.append(para.text)
                text = "\n".join(text_parts)
            except ImportError:
                raise HTTPException(status_code=500, detail="python-docx library not installed")
            except Exception as e:
                logger.error(f"Error reading DOCX: {e}")
                raise HTTPException(status_code=500, detail=f"Error reading DOCX: {str(e)}")
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        
        return {
            "file_path": file_path,
            "text": text,
            "preview": text[:500] + "..." if len(text) > 500 else text
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
