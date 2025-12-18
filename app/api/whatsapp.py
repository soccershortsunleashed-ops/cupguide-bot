from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.whatsapp_service import whatsapp_service
import logging

router = APIRouter(tags=["whatsapp"])
logger = logging.getLogger(__name__)

class WhatsAppStatus(BaseModel):
    authenticated: bool
    qr_code: str | None = None

@router.get("/status", response_model=WhatsAppStatus)
async def get_whatsapp_status():
    """Get WhatsApp authentication status"""
    try:
        if whatsapp_service.authenticated:
            return WhatsAppStatus(authenticated=True, qr_code=None)
        else:
            # Try to get QR code
            qr_code = await whatsapp_service.get_qr_code()
            return WhatsAppStatus(authenticated=False, qr_code=qr_code)
    except Exception as e:
        logger.error(f"Error getting WhatsApp status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/connect")
async def connect_whatsapp():
    """Initialize WhatsApp connection"""
    try:
        await whatsapp_service.connect()
        return {"status": "connecting", "message": "Scan QR code to authenticate"}
    except Exception as e:
        logger.error(f"Error connecting to WhatsApp: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chats")
async def get_whatsapp_chats():
    """Get all WhatsApp chats"""
    try:
        chats = await whatsapp_service.get_all_chats()
        return chats
    except Exception as e:
        logger.error(f"Error getting WhatsApp chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MonitoredChat(BaseModel):
    chat_id: str

@router.post("/monitored-chats")
async def add_monitored_chat_endpoint(chat: MonitoredChat):
    """Add a chat to the monitored chats list."""
    try:
        chat_id = chat.chat_id.strip()
        
        # If it's a group ID (ends with @g.us), try to get group name
        chat_name = chat_id
        if chat_id.endswith('@g.us'):
            from app.services.green_api_service import green_api_service
            try:
                group_data = await green_api_service.get_group_data(chat_id)
                if group_data and isinstance(group_data, dict) and group_data.get('name'):
                    chat_name = group_data.get('name')
                    logger.info(f"Found group name '{chat_name}' for ID {chat_id}")
                else:
                    # Если не удалось получить название, используем ID
                    logger.warning(f"Could not get group name for {chat_id}, using ID as name")
                    chat_name = chat_id
            except Exception as e:
                # При ошибке используем ID как название
                logger.warning(f"Error getting group name for {chat_id}: {e}, using ID as name")
                chat_name = chat_id
        else:
            # Для не-групп используем ID как есть
            chat_name = chat_id
        
        # Проверяем, не добавлен ли уже чат с таким ID или названием
        existing_chats = await whatsapp_service.get_monitored_chats()
        # Проверяем по ID (если это группа) и по названию
        if chat_id in existing_chats or chat_name in existing_chats:
            return {
                "status": "already_exists", 
                "message": f"Chat '{chat_name}' (ID: {chat_id}) is already being monitored", 
                "chat_name": chat_name,
                "chat_id": chat_id
            }
        
        success = await whatsapp_service.add_monitored_chat(chat_name)
        if success:
            # Также сохраняем ID для удобства (можно использовать для синхронизации)
            logger.info(f"Successfully added chat '{chat_name}' (ID: {chat_id}) to monitored chats")
            return {
                "status": "success", 
                "message": f"Added '{chat_name}' to monitored chats", 
                "chat_name": chat_name,
                "chat_id": chat_id
            }
        else:
            return {
                "status": "already_exists", 
                "message": f"Chat '{chat_name}' is already being monitored", 
                "chat_name": chat_name,
                "chat_id": chat_id
            }
    except Exception as e:
        logger.error(f"Error adding monitored chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/monitored-chats/{chat_id}")
async def remove_monitored_chat_endpoint(chat_id: str):
    """Remove a chat from the monitored chats list."""
    try:
        success = await whatsapp_service.remove_monitored_chat(chat_id)
        if success:
            return {"status": "success", "message": f"Removed '{chat_id}' from monitored chats"}
        else:
            return {"status": "not_found", "message": f"Chat '{chat_id}' was not in monitored chats"}
    except Exception as e:
        logger.error(f"Error removing monitored chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitored-chats")
async def get_monitored_chats_endpoint():
    """Get the list of monitored chats."""
    try:
        chats = await whatsapp_service.get_monitored_chats()
        return {"monitored_chats": chats}
    except Exception as e:
        logger.error(f"Error getting monitored chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monitored-chats/{chat_name}/sync")
async def sync_chat_history(chat_name: str, days: int = 30):
    """
    Synchronize chat history - extract and save messages from WhatsApp.
    
    Args:
        chat_name: Name of the chat to sync
        days: Number of days of history to sync (default 30)
    """
    try:
        from app.services.whatsapp_message_service import whatsapp_message_service
        from app.models.whatsapp_message import WhatsAppMessage
        
        logger.info(f"Starting sync for chat '{chat_name}'")
        
        # Extract messages from WhatsApp
        messages_data = await whatsapp_service.get_messages_from_chat(chat_name, days)
        
        # Save to database
        saved_count = 0
        for msg_data in messages_data:
            # Create WhatsAppMessage object
            wa_message = WhatsAppMessage(
                chat_name=chat_name,
                sender=msg_data.get('sender'),
                text=msg_data.get('text', ''),
                date=msg_data.get('date'),
                message_id="",  # Will be auto-generated
                media_type=msg_data.get('media_type'),
                media_path=None,
                media_files=msg_data.get('media_files')
            )
            
            await whatsapp_message_service.save_message(wa_message)
            saved_count += 1
        
        logger.info(f"Synced {saved_count} messages from '{chat_name}'")
        return {
            "status": "success",
            "chat_name": chat_name,
            "messages_synced": saved_count,
            "messages_total": len(messages_data)
        }
    except Exception as e:
        logger.error(f"Error syncing chat '{chat_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monitored-chats/{chat_name}/messages")
async def get_chat_messages(chat_name: str, limit: int = 100):
    """
    Get stored messages from a monitored chat.
    
    Args:
        chat_name: Name of the chat
        limit: Maximum number of messages to return (default 100)
    """
    try:
        from app.services.whatsapp_message_service import whatsapp_message_service
        
        messages = await whatsapp_message_service.get_messages(chat_name=chat_name)
        
        # Limit results
        messages = messages[:limit]
        
        return {
            "chat_name": chat_name,
            "count": len(messages),
            "messages": [msg.dict() for msg in messages]
        }
    except Exception as e:
        logger.error(f"Error getting messages for '{chat_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

class SendMessageRequest(BaseModel):
    phone: str
    message: str

@router.post("/send-message")
async def send_whatsapp_message(request: SendMessageRequest):
    """Send a WhatsApp message to a contact using Green API"""
    try:
        from app.services.green_api_service import green_api_service
        result = await green_api_service.send_message(request.phone, request.message)
        if result:
            return {"status": "success", "message": "Message sent successfully", "result": result}
        else:
            raise HTTPException(status_code=500, detail="Failed to send message")
    except Exception as e:
        logger.error(f"Error sending message to {request.phone}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BroadcastRequest(BaseModel):
    group: str
    message: str

@router.post("/broadcast")
async def broadcast_to_group(request: BroadcastRequest):
    """Send a broadcast message to all contacts in a group using Green API"""
    try:
        from app.services.contact_service import contact_service
        from app.services.green_api_service import green_api_service
        
        # Get all contacts in the group
        all_contacts = await contact_service.get_contacts()
        group_contacts = [c for c in all_contacts if c.group == request.group]
        
        if not group_contacts:
            raise HTTPException(status_code=404, detail=f"No contacts found in group '{request.group}'")
        
        sent_count = 0
        failed_count = 0
        
        for contact in group_contacts:
            try:
                # Use Green API instead of Selenium
                # Use WhatsApp ID if available, otherwise use phone number
                contact_id = contact.whatsapp_id if contact.whatsapp_id else contact.phone
                result = await green_api_service.send_message(contact_id, request.message)
                if result:
                    sent_count += 1
                    logger.info(f"✅ Sent message to {contact.name} ({contact.phone}) via Green API")
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Error sending to {contact.phone}: {e}")
                failed_count += 1
        
        return {
            "status": "completed",
            "sent": sent_count,
            "failed": failed_count,
            "total": len(group_contacts)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error broadcasting to group '{request.group}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Message Synchronization Endpoints ==============

@router.post("/sync")
async def sync_all_whatsapp_messages():
    """
    Manually trigger message sync for all contacts.
    Returns sync job status.
    """
    from app.services.message_sync_service import message_sync_service
    
    try:
        # Run sync and return results
        result = await message_sync_service.sync_all_contacts()
        
        return {
            "status": "completed",
            "result": result
        }
    except Exception as e:
        logger.error(f"Error syncing messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/{contact_id}")
async def sync_contact_messages(contact_id: int, full_sync: bool = False):
    """
    Sync messages for a single contact.
    Query param full_sync=true to fetch all messages instead of incremental.
    """
    from app.services.message_sync_service import message_sync_service
    
    try:
        result = await message_sync_service.sync_contact_messages(contact_id, full_sync=full_sync)
        
        return {
            "status": "success",
            "contact_id": contact_id,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error syncing contact {contact_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages/{contact_id}")
async def get_contact_messages(
    contact_id: int,
    limit: int = 50,
    since: str = None
):
    """
    Get message history for a contact.
    Query params:
    - limit: max number of messages to return
    - since: ISO datetime string to filter messages after this date
    """
    from app.services.contact_message_service import contact_message_service
    from datetime import datetime
    
    try:
        since_dt = None
        if since:
            since_dt = datetime.fromisoformat(since)
        
        messages = await contact_message_service.get_messages_by_contact(
            contact_id,
            limit=limit,
            since=since_dt
        )
        
        return {
            "contact_id": contact_id,
            "count": len(messages),
            "messages": [m.dict() for m in messages]
        }
    except Exception as e:
        logger.error(f"Error getting messages for contact {contact_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
