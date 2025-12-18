import os
import asyncio
import aiofiles
import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.api import auth, channels, messages, contacts, green_api, groups, webhooks, tournaments, dashboard, admin, tournament_extract, extract, logs, teletype, whatsapp, premium
from app.services.monitoring_service import monitoring_service

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Telegram News Monitor & Rewriter API"
)

# Увеличиваем максимальный размер загружаемых файлов до 20МБ
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class FileSizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 20 * 1024 * 1024):  # 20MB
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_size:
                return Response("File too large", status_code=413)
        return await call_next(request)

app.add_middleware(FileSizeMiddleware, max_size=20 * 1024 * 1024)  # 20MB

# Mount static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

media_dir = os.path.join(settings.DATA_DIR, "media")
os.makedirs(media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")

# Templates
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Добавляем кастомный фильтр для форматирования дат
def format_date_dd_mm_yyyy(date_string):
    """Форматирует дату в ДД.ММ.ГГГГ"""
    if not date_string:
        return ''
    
    try:
        from datetime import datetime
        date_str = str(date_string)
        
        # Пробуем разные форматы входных данных
        formats_to_try = [
            '%Y-%m-%d',    # YYYY-MM-DD
            '%d.%m.%Y',    # DD.MM.YYYY
            '%d/%m/%Y',    # DD/MM/YYYY
            '%d-%m-%Y',    # DD-MM-YYYY
            '%d/%m/%y',    # DD/MM/YY
        ]
        
        date_obj = None
        for fmt in formats_to_try:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        
        if date_obj:
            # Возвращаем в формате ДД.ММ.ГГГГ (full year with dots)
            return date_obj.strftime('%d.%m.%Y')
        else:
            # Если не удалось распарсить, возвращаем исходную строку
            return date_str
            
    except (ValueError, TypeError) as e:
        logger.warning(f"Error formatting date {date_string}: {e}")
        return str(date_string)

# Регистрируем фильтр в Jinja2
templates.env.filters['format_date'] = format_date_dd_mm_yyyy

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(channels.router, prefix="/channels", tags=["Channels"])
app.include_router(messages.router, prefix="/messages", tags=["Messages"])
app.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp"])
app.include_router(contacts.router, prefix="/contacts", tags=["Contacts"])
app.include_router(green_api.router, prefix="/green-api", tags=["Green API"])
app.include_router(groups.router, prefix="/groups", tags=["Groups"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
# Tournament routes
try:
    print("🔧 [DEBUG] Attempting to include tournament router...")
    logger.info(f"🔧 Attempting to include tournament router...")
    print(f"   [DEBUG] Router object: {tournaments.router}")
    print(f"   [DEBUG] Router routes count: {len(tournaments.router.routes)}")
    logger.info(f"   Router object: {tournaments.router}")
    logger.info(f"   Router routes count: {len(tournaments.router.routes)}")
    
    app.include_router(tournaments.router, prefix="/api/tournaments", tags=["Tournaments"])
    
    # Premium router
    app.include_router(premium.router, prefix="/api/tournaments", tags=["Premium"])
    print("✅ [DEBUG] Premium router included")
    
    # Analytics router (для личного кабинета организатора)
    from app.api import analytics
    app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
    print("✅ [DEBUG] Analytics router included")
    
    # Cabinet WebApp router (личный кабинет как WebApp)
    from app.api import cabinet
    app.include_router(cabinet.router, prefix="/api", tags=["Cabinet"])
    print("✅ [DEBUG] Cabinet WebApp router included")
    
    print("✅ [DEBUG] Tournament router included")
    logger.info(f"✅ Tournament router included with prefix /api/tournaments")
    logger.info(f"   Total routes in router: {len(tournaments.router.routes)}")
    
    # Логируем все роуты турниров для отладки
    for route in tournaments.router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"   [DEBUG] Route: /api/tournaments{route.path} - {list(route.methods)}")
            logger.info(f"   Route: /api/tournaments{route.path} - {list(route.methods)}")
    
    # Проверяем, что роуты действительно зарегистрированы в приложении
    tournament_routes_in_app = [
        r for r in app.routes 
        if hasattr(r, 'path') and '/api/tournaments' in str(r.path)
    ]
    print(f"   [DEBUG] Tournament routes registered in app: {len(tournament_routes_in_app)}")
    logger.info(f"   Tournament routes registered in app: {len(tournament_routes_in_app)}")
    for route in tournament_routes_in_app:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"   [DEBUG] App route: {route.path} - {list(route.methods)}")
            logger.info(f"   App route: {route.path} - {list(route.methods)}")
            
except Exception as e:
    print(f"❌ [DEBUG] Error including tournament router: {e}")
    import traceback
    print(f"   [DEBUG] Traceback: {traceback.format_exc()}")
    logger.error(f"❌ Error including tournament router: {e}", exc_info=True)
    logger.error(f"   Traceback: {traceback.format_exc()}")
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# Admin router with debug
try:
    print("🔧 [DEBUG] Adding admin router...")
    print(f"   [DEBUG] Admin router has {len(admin.router.routes)} routes")
    
    # Check for extract endpoint specifically
    extract_routes = [r for r in admin.router.routes if hasattr(r, 'path') and 'extract' in r.path]
    print(f"   [DEBUG] Extract routes found: {len(extract_routes)}")
    for route in extract_routes:
        if hasattr(route, 'methods'):
            print(f"   [DEBUG] Extract route: {route.path} - {list(route.methods)}")
    
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    print("✅ [DEBUG] Admin router included successfully")
    
    # Verify routes were added to app
    admin_routes_in_app = [r for r in app.routes if hasattr(r, 'path') and r.path.startswith('/admin')]
    print(f"   [DEBUG] Admin routes in app: {len(admin_routes_in_app)}")
    
    extract_routes_in_app = [r for r in app.routes if hasattr(r, 'path') and 'extract' in r.path]
    print(f"   [DEBUG] Extract routes in app: {len(extract_routes_in_app)}")
    for route in extract_routes_in_app:
        if hasattr(route, 'methods'):
            print(f"   [DEBUG] App extract route: {route.path} - {list(route.methods)}")
            
except Exception as e:
    print(f"❌ [DEBUG] Error including admin router: {e}")
    import traceback
    print(f"   [DEBUG] Traceback: {traceback.format_exc()}")
    logger.error(f"❌ Error including admin router: {e}", exc_info=True)

# Простой endpoint для извлечения данных турнира
from fastapi import HTTPException
from pydantic import BaseModel
import json

class ExtractRequest(BaseModel):
    text: str

# Tournament Extract router
try:
    print("🔧 [DEBUG] Adding tournament extract router...")
    app.include_router(tournament_extract.router, prefix="/api/tournament-extract", tags=["Tournament Extract"])
    print("✅ [DEBUG] Tournament extract router added successfully")
    
    # Log routes
    for route in tournament_extract.router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"   [DEBUG] Extract route: /api/tournament-extract{route.path} - {list(route.methods)}")
            
except Exception as e:
    print(f"❌ [DEBUG] Error adding tournament extract router: {e}")
    import traceback
    print(f"   [DEBUG] Traceback: {traceback.format_exc()}")

# Logs router
try:
    print("🔧 [DEBUG] Adding logs router...")
    app.include_router(logs.router, prefix="/api/logs", tags=["Logs"])
    print("✅ [DEBUG] Logs router added successfully")
    
    print("🔧 [DEBUG] Adding teletype router...")
    app.include_router(teletype.router, prefix="/api/teletype", tags=["Teletype"])
    print("✅ [DEBUG] Teletype router added successfully")
    
except Exception as e:
    print(f"❌ [DEBUG] Error adding logs router: {e}")
    import traceback
    print(f"   [DEBUG] Traceback: {traceback.format_exc()}")

# Добавляем простой endpoint для извлечения данных
@app.post("/admin/extract-tournament-data")
async def extract_tournament_data_simple(request: ExtractRequest):
    """Простое извлечение данных турнира"""
    try:
        from app.services.llm_service import llm_service
        
        if not llm_service.configured:
            await llm_service.refresh_client()
            if not llm_service.configured:
                raise HTTPException(status_code=500, detail="LLM service not configured")
        
        # Простой промпт
        prompt = f"""Извлеки данные из текста о турнире:

{request.text}

Верни JSON:
{{
    "city": "город или null",
    "region": "регион или null",
    "start_date": "YYYY-MM-DD или null",
    "end_date": "YYYY-MM-DD или null", 
    "birth_years": "года рождения или null",
    "format": "формат турнира или null",
    "entry_fee": "взнос или null",
    "organizer_name": "организатор или null",
    "contact": "телефон или null"
}}"""

        response = await llm_service.generate_content_async(prompt, timeout=30)
        
        if not response:
            return {
                "city": None, "region": None, "start_date": None, "end_date": None,
                "birth_years": None, "format": None, "entry_fee": None, 
                "organizer_name": None, "contact": None
            }
        
        # Парсим JSON
        try:
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            result = json.loads(clean_response)
            
            # Очищаем данные
            for key, value in result.items():
                if value and str(value).strip() and str(value).lower() != 'null':
                    result[key] = str(value).strip()
                else:
                    result[key] = None
            
            return result
            
        except:
            # Если не удалось распарсить, возвращаем пустые данные
            return {
                "city": None, "region": None, "start_date": None, "end_date": None,
                "birth_years": None, "format": None, "entry_fee": None, 
                "organizer_name": None, "contact": None
            }
            
    except Exception as e:
        logger.error(f"Error in extract: {e}")
        return {
            "city": None, "region": None, "start_date": None, "end_date": None,
            "birth_years": None, "format": None, "entry_fee": None, 
            "organizer_name": None, "contact": None
        }

@app.on_event("startup")
async def startup_event():
    from app.core.logging_config import setup_logging
    from app.core.scheduler import start_scheduler
    setup_logging()
    asyncio.create_task(monitoring_service.start())
    # Start message sync scheduler
    await start_scheduler()
    # Temporarily disabled WhatsApp monitoring due to dependency issues
    import logging
    startup_logger = logging.getLogger(__name__)
    startup_logger.info("WhatsApp monitoring temporarily disabled due to dependency issues")
    
    # Запускаем фоновую задачу для анализа авторов сообщений
    startup_logger.info("Starting author analysis task...")
    asyncio.create_task(start_author_analysis())

async def start_whatsapp_monitoring():
    """Background task to monitor WhatsApp chats for new messages"""
    import logging
    from app.services.whatsapp_service import whatsapp_service
    from app.services.whatsapp_message_service import whatsapp_message_service
    from app.models.whatsapp_message import WhatsAppMessage
    from datetime import datetime, timedelta, timezone
    
    logger = logging.getLogger(__name__)
    logger.info("WhatsApp monitoring task started")
    
    # Log initial monitored chats
    monitored_chats = await whatsapp_service.get_monitored_chats()
    logger.info(f"WhatsApp monitoring: Loaded {len(monitored_chats)} monitored chats: {monitored_chats}")
    
    await asyncio.sleep(10)  # Wait for app to fully start
    
    while True:
        try:
            # Get list of monitored chats
            monitored_chats = await whatsapp_service.get_monitored_chats()
            
            if not monitored_chats:
                logger.debug("No WhatsApp chats being monitored")
                await asyncio.sleep(60)
                continue
            
            logger.debug(f"WhatsApp monitoring: Checking {len(monitored_chats)} monitored chats")
            
            # Check each monitored chat for new messages
            for chat_name in monitored_chats:
                try:
                    logger.info(f"Checking monitored chat: '{chat_name}'")
                    
                    # Check if it's a group ID (ends with @g.us) or find group by name
                    group_id = None
                    if chat_name.endswith('@g.us'):
                        # Already a group ID
                        group_id = chat_name
                        logger.info(f"✅ Using group ID directly: {group_id}")
                        
                        # Get group name for display (optional, for logging)
                        try:
                            from app.services.green_api_service import green_api_service
                            group_data = await green_api_service.get_group_data(group_id)
                            if group_data and isinstance(group_data, dict) and group_data.get('name'):
                                display_name = group_data.get('name')
                                logger.info(f"Group display name: {display_name}")
                        except Exception as e:
                            logger.debug(f"Could not get group name for {group_id}: {e}")
                    else:
                        # Try to find group ID by name
                        from app.services.green_api_service import green_api_service
                        logger.info(f"Looking for group ID by name: '{chat_name}'")
                        try:
                            chats = await green_api_service.get_chats()
                            logger.debug(f"Retrieved {len(chats)} chats from Green API")
                            
                            # Try exact match first
                            for chat in chats:
                                if chat.get('type') == 'group':
                                    chat_name_from_api = chat.get('name', '')
                                    chat_id = chat.get('id', '')
                                    if chat_name_from_api == chat_name:
                                        group_id = chat_id
                                        logger.info(f"✅ Found group ID {group_id} for '{chat_name}' (exact match)")
                                        break
                            
                            # If not found, try partial match
                            if not group_id:
                                for chat in chats:
                                    if chat.get('type') == 'group':
                                        chat_name_from_api = chat.get('name', '')
                                        chat_id = chat.get('id', '')
                                        if chat_name.lower() in chat_name_from_api.lower() or chat_name_from_api.lower() in chat_name.lower():
                                            group_id = chat_id
                                            logger.info(f"✅ Found group ID {group_id} for '{chat_name}' (partial match: '{chat_name_from_api}')")
                                            break
                            
                            if not group_id:
                                logger.warning(f"❌ Group '{chat_name}' not found in Green API chats list")
                                # Log available groups for debugging
                                available_groups = [(c.get('name'), c.get('id')) for c in chats if c.get('type') == 'group']
                                logger.warning(f"Available groups ({len(available_groups)}): {available_groups[:20]}")  # Log first 20 with IDs
                                
                                # Try to find by ID if we know it
                                known_group_id = "120363304781973950@g.us"
                                for chat in chats:
                                    if chat.get('id') == known_group_id:
                                        group_id = known_group_id
                                        logger.info(f"✅ Found group by known ID: {group_id} (name: {chat.get('name', 'Unknown')})")
                                        break
                        except Exception as e:
                            logger.error(f"Error finding group by name '{chat_name}': {e}", exc_info=True)
                    
                    if group_id:
                        # Use Green API for groups
                        from app.services.green_api_service import green_api_service
                        
                        # Get group name for display (if we have ID but not name)
                        # Initialize display_name with chat_name as fallback
                        display_name = chat_name
                        
                        if group_id == chat_name:
                            # We have ID, try to get name for display
                            try:
                                logger.debug(f"Attempting to get group name for {group_id}...")
                                
                                # Method 1: Try get_chats() first - it's more reliable
                                chats = await green_api_service.get_chats()
                                for chat in chats:
                                    if chat.get('id') == group_id and chat.get('type') == 'group':
                                        display_name = chat.get('name', group_id)
                                        logger.info(f"✅ Got group name '{display_name}' from get_chats()")
                                        break
                                
                                # Method 2: If not found, try get_group_data()
                                if display_name == group_id:
                                    logger.debug(f"Group not found in get_chats(), trying get_group_data()...")
                                    group_data = await green_api_service.get_group_data(group_id)
                                    logger.debug(f"Group data received: {type(group_data)}, keys: {list(group_data.keys()) if isinstance(group_data, dict) else 'not a dict'}")
                                    
                                    if group_data and isinstance(group_data, dict):
                                        # Try different possible field names for group name
                                        group_name = (group_data.get('name') or 
                                                     group_data.get('title') or
                                                     group_data.get('subject') or
                                                     group_data.get('groupName'))
                                        if group_name:
                                            display_name = group_name
                                            logger.info(f"✅ Got group name: {display_name}")
                                        else:
                                            logger.warning(f"Group data exists but no name field found. Keys: {list(group_data.keys())}")
                                            display_name = group_id
                                    else:
                                        logger.warning(f"Group data is not a dict: {type(group_data)}")
                                        display_name = group_id
                            except Exception as e:
                                logger.error(f"Error getting group name for {group_id}: {e}", exc_info=True)
                                display_name = group_id  # Fallback to ID if name not available
                        
                        logger.info(f"Using Green API for group: {group_id} (display: {display_name})")
                        
                        # Get recent messages from group (last 50 messages)
                        try:
                            # Get chat history using Green API
                            logger.debug(f"Fetching chat history for group {group_id}...")
                            history = await green_api_service.get_chat_history(group_id, count=50)
                            logger.info(f"Retrieved {len(history) if history else 0} messages from group {group_id}")
                            
                            # Log sender information from first few messages
                            if history and len(history) > 0:
                                for i, msg in enumerate(history[:3]):  # Check first 3 messages
                                    sender_name = msg.get('senderName') or msg.get('senderContactName') or 'Not found'
                                    logger.info(f"Message {i+1} senderName: {msg.get('senderName')}, senderContactName: {msg.get('senderContactName')}, senderId: {msg.get('senderId')}, extracted: {sender_name}")
                            
                            if history:
                                # For first load, save all messages from history (last 24 hours)
                                # For subsequent checks, only save new messages (last 5 minutes)
                                # Check if we already have messages from this group
                                from app.services.whatsapp_message_service import whatsapp_message_service
                                existing_messages = await whatsapp_message_service.get_messages(chat_name=group_id)
                                
                                if len(existing_messages) == 0:
                                    # First load - save all messages from last 24 hours
                                    recent_cutoff = datetime.now().astimezone() - timedelta(hours=24)
                                    logger.info(f"First load for group {group_id}, saving messages from last 24 hours")
                                else:
                                    # Subsequent check - only save new messages from last 5 minutes
                                    recent_cutoff = datetime.now().astimezone() - timedelta(minutes=5)
                                    logger.debug(f"Subsequent check for group {group_id}, saving only new messages")
                                
                                saved = 0
                                
                                for msg_data in history:
                                    # Parse timestamp - Green API uses different field names
                                    # Try multiple possible field names
                                    timestamp = (msg_data.get('timestamp') or 
                                                msg_data.get('timestampMessage') or
                                                msg_data.get('timestampMessage') or
                                                msg_data.get('date'))
                                    if timestamp:
                                        if isinstance(timestamp, int):
                                            if timestamp > 1000000000000:
                                                msg_date = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                                            else:
                                                msg_date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                                        else:
                                            msg_date = datetime.now(timezone.utc)
                                    else:
                                        msg_date = datetime.now(timezone.utc)
                                    
                                    # Skip reaction messages - они бесполезны
                                    type_message_check = msg_data.get('typeMessage', '')
                                    if 'reaction' in type_message_check.lower() or type_message_check == 'reactionMessage':
                                        logger.debug(f"Skipping reaction message: {msg_data.get('idMessage', 'unknown')}")
                                        continue
                                    
                                    # Check if message is within time window
                                    is_recent = msg_date >= recent_cutoff
                                    
                                    # Check if message has media - process media even if message is old (for first load)
                                    has_media_check = (msg_data.get('typeMessage') in ['imageMessage', 'videoMessage', 'documentMessage', 'audioMessage', 'stickerMessage'] or
                                                      msg_data.get('downloadUrl') or
                                                      msg_data.get('body', {}).get('downloadUrl'))
                                    
                                    # Process message if it's recent OR if it has media (for first load, we want to download all media)
                                    should_process = is_recent or has_media_check
                                    
                                    if should_process:
                                        # Extract text - Green API uses different field names
                                        text = (msg_data.get('textMessage') or 
                                               msg_data.get('extendedTextMessageData', {}).get('text') or
                                               msg_data.get('message') or
                                               msg_data.get('body', {}).get('textMessageData', {}).get('textMessage') or
                                               msg_data.get('caption') or
                                               '')
                                        
                                        # Extract sender - Green API structure
                                        # Green API provides senderName and senderContactName directly in message
                                        sender = (msg_data.get('senderName') or 
                                                 msg_data.get('senderContactName') or
                                                 None)
                                        
                                        # Fallback: try senderData if available
                                        if not sender:
                                            sender_data = msg_data.get('senderData') or msg_data.get('sender') or {}
                                            if isinstance(sender_data, dict):
                                                sender = (sender_data.get('senderName') or 
                                                         sender_data.get('name') or
                                                         sender_data.get('sender') or
                                                         None)
                                            elif sender_data:
                                                sender = str(sender_data) if sender_data else None
                                        
                                        # Last fallback: try to find contact by WhatsApp ID in database, then Green API
                                        if not sender or sender.strip() == '':
                                            sender_id = msg_data.get('senderId', '')
                                            if sender_id and '@c.us' in sender_id:
                                                # First, try to find contact in database by WhatsApp ID
                                                try:
                                                    from app.services.contact_service import contact_service
                                                    contacts = await contact_service.get_contacts()
                                                    
                                                    # Search by WhatsApp ID
                                                    for contact in contacts:
                                                        if contact.whatsapp_id == sender_id:
                                                            sender = contact.name or contact.whatsapp_name or contact.phone or None
                                                            if sender:
                                                                logger.info(f"✅ Found contact name '{sender}' by WhatsApp ID {sender_id} from database")
                                                                break
                                                    
                                                    # If not found by WhatsApp ID, try by phone number
                                                    if not sender or sender.strip() == '':
                                                        phone = sender_id.replace('@c.us', '').replace('@g.us', '').replace('@', '')
                                                        is_phone_number = (phone.isdigit() and 
                                                                           (phone.startswith('7') or phone.startswith('8')) and 
                                                                           10 <= len(phone) <= 11)
                                                        
                                                        if is_phone_number:
                                                            # Search by phone (with or without +)
                                                            phone_variants = [phone, f"+{phone}", phone[1:] if phone.startswith('+') else phone]
                                                            for contact in contacts:
                                                                contact_phone_clean = contact.phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                                                                phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
                                                                if contact_phone_clean == phone_clean or contact.phone in phone_variants or phone in phone_variants:
                                                                    sender = contact.name or contact.whatsapp_name or None
                                                                    if sender:
                                                                        logger.info(f"✅ Found contact name '{sender}' for phone {phone} from database")
                                                                        break
                                                except Exception as e:
                                                    logger.warning(f"Error looking up contact for {sender_id}: {e}")
                                                
                                                # If not found in database, try Green API as last resort
                                                if not sender or sender.strip() == '':
                                                    try:
                                                        contact_info = await green_api_service.get_contact_info(sender_id)
                                                        logger.debug(f"Green API getContactInfo response for {sender_id}: {contact_info}")
                                                        if contact_info.get("exists") and contact_info.get("name"):
                                                            contact_name = contact_info["name"]
                                                            # Don't use phone number as name - if name is just digits, it's likely a phone number
                                                            phone = sender_id.replace('@c.us', '').replace('@g.us', '').replace('@', '')
                                                            is_phone_number = (phone.isdigit() and 
                                                                               (phone.startswith('7') or phone.startswith('8')) and 
                                                                               10 <= len(phone) <= 11)
                                                            # If contact_name is the same as phone number, don't use it
                                                            if contact_name and contact_name != phone and not (is_phone_number and contact_name == phone):
                                                                sender = contact_name
                                                                logger.info(f"✅ Got contact name '{sender}' from Green API for {sender_id}")
                                                            else:
                                                                logger.debug(f"Green API returned phone number '{contact_name}' instead of name for {sender_id}, skipping")
                                                    except Exception as e:
                                                        logger.warning(f"Error getting contact info from Green API for {sender_id}: {e}", exc_info=True)
                                        
                                        # If still no sender, use Unknown (don't use numeric ID)
                                        if not sender or sender.strip() == '':
                                            sender = None  # Will be saved as None, not 'Unknown'
                                        
                                        # Log sender extraction for debugging
                                        if msg_data.get('idMessage'):
                                            logger.info(f"Message {msg_data.get('idMessage', 'unknown')} sender extraction: senderName={msg_data.get('senderName')}, senderContactName={msg_data.get('senderContactName')}, senderId={msg_data.get('senderId')}, extracted={sender}")
                                        
                                        # Extract and download media if present
                                        media_type = None
                                        media_path = None
                                        media_files = None
                                        
                                        # Check for media in message
                                        # Green API getChatHistory might have different structure than incoming notifications
                                        # Check multiple possible locations for typeMessage
                                        type_message = (msg_data.get('typeMessage') or 
                                                      msg_data.get('type') or
                                                      msg_data.get('body', {}).get('typeMessage') or
                                                      '')
                                        
                                        # Removed verbose message processing log
                                        
                                        # Also check for media-related fields directly
                                        has_media = (type_message in ['imageMessage', 'videoMessage', 'documentMessage', 'audioMessage', 'stickerMessage'] or
                                                    msg_data.get('downloadUrl') or
                                                    msg_data.get('body', {}).get('downloadUrl') or
                                                    msg_data.get('imageMessageData') or
                                                    msg_data.get('videoMessageData') or
                                                    msg_data.get('documentMessageData') or
                                                    msg_data.get('body', {}).get('imageMessageData') or
                                                    msg_data.get('body', {}).get('videoMessageData') or
                                                    msg_data.get('body', {}).get('documentMessageData'))
                                        
                                        download_url_check = msg_data.get('downloadUrl') or msg_data.get('body', {}).get('downloadUrl')
                                        # Removed verbose media logging - only log errors
                                        
                                        media_type_map = {
                                            'imageMessage': 'photo',
                                            'videoMessage': 'video',
                                            'documentMessage': 'document',
                                            'audioMessage': 'audio',
                                            'stickerMessage': 'sticker'
                                        }
                                        
                                        # Process media if present
                                        if has_media:
                                            # Try to determine media type from available fields if typeMessage is not set
                                            if not type_message or type_message not in media_type_map:
                                                # Try to infer from available data
                                                if msg_data.get('imageMessageData') or msg_data.get('body', {}).get('imageMessageData'):
                                                    type_message = 'imageMessage'
                                                elif msg_data.get('videoMessageData') or msg_data.get('body', {}).get('videoMessageData'):
                                                    type_message = 'videoMessage'
                                                elif msg_data.get('documentMessageData') or msg_data.get('body', {}).get('documentMessageData'):
                                                    type_message = 'documentMessage'
                                                elif msg_data.get('audioMessageData') or msg_data.get('body', {}).get('audioMessageData'):
                                                    type_message = 'audioMessage'
                                                elif msg_data.get('stickerMessageData') or msg_data.get('body', {}).get('stickerMessageData'):
                                                    type_message = 'stickerMessage'
                                                elif msg_data.get('downloadUrl') or msg_data.get('body', {}).get('downloadUrl'):
                                                    # Has downloadUrl but no typeMessage - default to image
                                                    type_message = 'imageMessage'
                                                    # Inferring imageMessage from downloadUrl
                                            
                                            # Process if we have a valid type
                                            if type_message in media_type_map:
                                                media_type = media_type_map[type_message]
                                                message_id = msg_data.get('idMessage', '')
                                                
                                                if not message_id:
                                                    logger.error(f"Media message found but no idMessage: {msg_data}")
                                                else:
                                                    # Found media message
                                                    
                                                    try:
                                                        # Determine file extension from type or mimeType (before downloading)
                                                        mime_type = (msg_data.get('mimeType') or 
                                                                   msg_data.get('imageMessageData', {}).get('mimeType') or
                                                                   msg_data.get('videoMessageData', {}).get('mimeType') or
                                                                   msg_data.get('documentMessageData', {}).get('mimeType') or
                                                                   'image/jpeg')
                                                        
                                                        # Map MIME type to extension
                                                        ext_map = {
                                                            'image/jpeg': '.jpg',
                                                            'image/png': '.png',
                                                            'image/gif': '.gif',
                                                            'image/webp': '.webp',
                                                            'video/mp4': '.mp4',
                                                            'video/quicktime': '.mov',
                                                            'application/pdf': '.pdf',
                                                            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                                                            'application/msword': '.doc',
                                                            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
                                                            'application/vnd.ms-excel': '.xls',
                                                            'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
                                                            'application/vnd.ms-powerpoint': '.ppt',
                                                            'application/zip': '.zip',
                                                            'application/x-rar-compressed': '.rar',
                                                            'text/plain': '.txt',
                                                            'text/csv': '.csv'
                                                        }
                                                        # Try to get filename from documentMessageData if available
                                                        ext = None
                                                        doc_filename = None
                                                        if type_message == 'documentMessage':
                                                            doc_data = msg_data.get('documentMessageData') or msg_data.get('body', {}).get('documentMessageData') or {}
                                                            doc_filename = doc_data.get('fileName') or doc_data.get('filename')
                                                            if doc_filename and '.' in doc_filename:
                                                                # Extract extension from filename
                                                                ext_from_filename = '.' + doc_filename.rsplit('.', 1)[1].lower()
                                                                if ext_from_filename in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.zip', '.rar']:
                                                                    ext = ext_from_filename
                                                                    # Using extension from filename
                                                        if not ext or ext == '.bin':
                                                            ext = ext_map.get(mime_type, '.pdf' if media_type == 'document' else '.jpg' if media_type == 'photo' else '.mp4' if media_type == 'video' else '.bin')
                                                        
                                                        # Prepare file path - use BASE_DIR to match static files mount
                                                        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
                                                        media_dir = os.path.join(BASE_DIR, "static", "media")
                                                        os.makedirs(media_dir, exist_ok=True)
                                                        
                                                        safe_group_id = group_id.replace('@g.us', '').replace('@', '_')
                                                        filename = f"{safe_group_id}_{message_id}{ext}"
                                                        file_path = os.path.join(media_dir, filename)
                                                        
                                                        # Check if downloadUrl is available - prefer it over download_file_by_id
                                                        download_url = msg_data.get('downloadUrl') or msg_data.get('body', {}).get('downloadUrl')
                                                        if download_url:
                                                            # Use downloadUrl directly - it's more reliable for groups
                                                            success = await green_api_service.download_media_file(download_url, file_path)
                                                            if success:
                                                                # Check file size
                                                                file_size = os.path.getsize(file_path)
                                                                if file_size < 1000:
                                                                    logger.warning(f"⚠️ File downloaded via downloadUrl is still small ({file_size} bytes): {filename}")
                                                                media_path = f"/static/media/{filename}"
                                                                media_files = [{"type": media_type, "path": media_path}]
                                                            else:
                                                                logger.error(f"❌ Failed to download via downloadUrl for message {message_id}")
                                                                # Try download_file_by_id as fallback
                                                                # Trying download_file_by_id as fallback
                                                                file_data = await green_api_service.download_file_by_id(group_id, message_id)
                                                                if file_data and len(file_data) >= 1000:
                                                                    async with aiofiles.open(file_path, 'wb') as f:
                                                                        await f.write(file_data)
                                                                    media_path = f"/static/media/{filename}"
                                                                    media_files = [{"type": media_type, "path": media_path}]
                                                                    # Downloaded via download_file_by_id fallback
                                                        else:
                                                            # No downloadUrl - use download_file_by_id
                                                            # Attempting to download media via download_file_by_id
                                                            file_data = await green_api_service.download_file_by_id(group_id, message_id)
                                                            
                                                            # Check if file_data is valid before saving
                                                            if file_data and len(file_data) >= 1000:
                                                                # Save to app/static/media (same as Telegram)
                                                                async with aiofiles.open(file_path, 'wb') as f:
                                                                    await f.write(file_data)
                                                                
                                                                media_path = f"/static/media/{filename}"
                                                                media_files = [{"type": media_type, "path": media_path}]
                                                                
                                                                # Downloaded and saved media successfully
                                                            elif file_data:
                                                                # File is too small - might be error response
                                                                file_size = len(file_data)
                                                                logger.warning(f"⚠️ Downloaded media file is very small ({file_size} bytes) - might be thumbnail or error. Message: {message_id}")
                                                                # Try to check if it's JSON error
                                                                try:
                                                                    import json
                                                                    error_data = json.loads(file_data.decode('utf-8'))
                                                                    logger.error(f"❌ Green API returned error instead of file: {error_data}")
                                                                except:
                                                                    logger.warning(f"File data is not JSON, but size is suspicious: {file_size} bytes")
                                                                # Will try downloadUrl below
                                                            else:
                                                                logger.warning(f"❌ download_file_by_id returned None or empty for message {message_id}")
                                                            
                                                            # If file is too small or None, try downloadUrl method
                                                            if not file_data or (file_data and len(file_data) < 1000):
                                                                download_url = msg_data.get('downloadUrl') or msg_data.get('body', {}).get('downloadUrl')
                                                                if download_url:
                                                                    # File too small or None, trying downloadUrl method
                                                                    try:
                                                                        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
                                                                        media_dir = os.path.join(BASE_DIR, "static", "media")
                                                                        os.makedirs(media_dir, exist_ok=True)
                                                                        
                                                                        safe_group_id = group_id.replace('@g.us', '').replace('@', '_')
                                                                        # Determine extension from mimeType or media_type
                                                                        if not ext:
                                                                            mime_type = (msg_data.get('mimeType') or 
                                                                                       msg_data.get('imageMessageData', {}).get('mimeType') or
                                                                                       msg_data.get('videoMessageData', {}).get('mimeType') or
                                                                                       msg_data.get('documentMessageData', {}).get('mimeType') or
                                                                                       'image/jpeg')
                                                                            ext_map = {
                                                                                'image/jpeg': '.jpg',
                                                                                'image/png': '.png',
                                                                                'image/gif': '.gif',
                                                                                'image/webp': '.webp',
                                                                                'video/mp4': '.mp4',
                                                                                'video/quicktime': '.mov',
                                                                                'application/pdf': '.pdf',
                                                                                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                                                                                'application/msword': '.doc',
                                                                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
                                                                                'application/vnd.ms-excel': '.xls',
                                                                                'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
                                                                                'application/vnd.ms-powerpoint': '.ppt',
                                                                                'application/zip': '.zip',
                                                                                'application/x-rar-compressed': '.rar',
                                                                                'text/plain': '.txt',
                                                                                'text/csv': '.csv'
                                                                            }
                                                                            # Try to get filename from documentMessageData if available
                                                                            ext = None
                                                                            if type_message == 'documentMessage':
                                                                                doc_data = msg_data.get('documentMessageData') or msg_data.get('body', {}).get('documentMessageData') or {}
                                                                                doc_filename = doc_data.get('fileName') or doc_data.get('filename')
                                                                                if doc_filename and '.' in doc_filename:
                                                                                    # Extract extension from filename
                                                                                    ext_from_filename = '.' + doc_filename.rsplit('.', 1)[1].lower()
                                                                                    if ext_from_filename in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.zip', '.rar']:
                                                                                        ext = ext_from_filename
                                                                                        # Using extension from filename
                                                                            if not ext or ext == '.bin':
                                                                                ext = ext_map.get(mime_type, '.pdf' if media_type == 'document' else '.jpg' if media_type == 'photo' else '.mp4' if media_type == 'video' else '.bin')
                                                                        
                                                                        filename = f"{safe_group_id}_{message_id}{ext}"
                                                                        file_path = os.path.join(media_dir, filename)
                                                                        
                                                                        success = await green_api_service.download_media_file(download_url, file_path)
                                                                        if success:
                                                                            # Check file size
                                                                            file_size = os.path.getsize(file_path)
                                                                            if file_size < 1000:
                                                                                logger.warning(f"⚠️ File downloaded via downloadUrl is still small ({file_size} bytes): {filename}")
                                                                            media_path = f"/static/media/{filename}"
                                                                            media_files = [{"type": media_type, "path": media_path}]
                                                                            # Downloaded media via downloadUrl successfully
                                                                            file_data = b"success"  # Mark as successful
                                                                        else:
                                                                            logger.error(f"❌ Failed to download via downloadUrl for message {message_id}")
                                                                    except Exception as e2:
                                                                        logger.error(f"Error downloading via downloadUrl: {e2}", exc_info=True)
                                                            else:
                                                                logger.warning(f"❌ No downloadUrl available for message {message_id}, file_data size: {len(file_data) if file_data else 0} bytes")
                                                    except Exception as e:
                                                        logger.error(f"Error downloading media for message {message_id}: {e}", exc_info=True)
                                        else:
                                            # Log if message might have media but typeMessage is not set
                                            if msg_data.get('downloadUrl') or msg_data.get('body', {}).get('downloadUrl'):
                                                logger.warning(f"Message {msg_data.get('idMessage', 'unknown')} has downloadUrl but typeMessage is '{type_message}'")
                                        
                                        # Save message if it's recent OR if it has media (to display media in UI)
                                        if is_recent or (has_media_check and (media_path or media_files)):
                                            # Create WhatsApp message
                                            # Store both ID and display name - use ID for channel_id matching
                                            final_sender = sender if sender and sender != 'Unknown' else None
                                            # Saving message
                                            # Извлекаем senderId для сохранения
                                            sender_id = msg_data.get('senderId', '')
                                            
                                            wa_message = WhatsAppMessage(
                                                chat_name=group_id,  # Use group ID for channel_id matching
                                                sender=final_sender,  # Save None instead of 'Unknown'
                                                sender_id=sender_id if sender_id and '@c.us' in sender_id else None,  # Сохраняем WhatsApp ID автора
                                                text=text,
                                                date=msg_date,
                                                message_id=msg_data.get('idMessage', ''),
                                                media_type=media_type,
                                                media_path=media_path,
                                                media_files=media_files
                                            )
                                            await whatsapp_message_service.save_message(wa_message)
                                            saved += 1
                                            
                                            # Триггерим анализ автора если есть sender или sender_id
                                            # Это позволяет анализировать сообщения даже без имени отправителя (например, только изображения)
                                            if final_sender or (sender_id and '@c.us' in sender_id):
                                                logger.info(f"✅ Saved message {msg_data.get('idMessage', 'unknown')} from sender: {final_sender or 'Unknown'} (ID: {sender_id})")
                                                
                                                # Триггерим анализ автора сразу после сохранения сообщения
                                                # Запускаем в фоне, чтобы не блокировать сохранение
                                                try:
                                                    from app.services.author_analysis_service import author_analysis_service
                                                    
                                                    # ВАЖНО: Используем senderName из Green API (например, "anofcfinist") 
                                                    # как приоритетное имя, если оно есть
                                                    # Это позволяет сохранить ник пользователя в контакте
                                                    green_api_sender_name = msg_data.get('senderName') or msg_data.get('senderContactName')
                                                    if green_api_sender_name and green_api_sender_name.strip() and green_api_sender_name != 'Unknown':
                                                        analysis_sender_name = green_api_sender_name
                                                        logger.info(f"📝 Using Green API senderName '{analysis_sender_name}' for analysis")
                                                    else:
                                                        # Fallback: используем final_sender или sender_id
                                                        analysis_sender_name = final_sender or sender_id or 'Unknown'
                                                    
                                                    async def run_analysis_with_error_handling():
                                                        try:
                                                            await author_analysis_service.analyze_author_immediately(
                                                                sender_name=analysis_sender_name,
                                                                sender_id=sender_id if sender_id and '@c.us' in sender_id else None,
                                                                group_id=group_id,
                                                                group_name=display_name
                                                            )
                                                        except Exception as e:
                                                            logger.error(f"Error in background author analysis for {analysis_sender_name}: {e}", exc_info=True)
                                                    
                                                    asyncio.create_task(run_analysis_with_error_handling())
                                                    logger.info(f"Triggered immediate analysis for author: {analysis_sender_name} (ID: {sender_id})")
                                                except Exception as e:
                                                    logger.error(f"Could not trigger immediate author analysis: {e}", exc_info=True)
                                            
                                            if not is_recent:
                                                # Saved old message with media to display in UI
                                                pass
                                
                                # Check saved count after processing all messages in the loop
                                if saved > 0:
                                    logger.info(f"✅ Saved {saved} new messages from group '{display_name}' (ID: {group_id}) via Green API")
                                else:
                                    logger.debug(f"No new messages from group '{display_name}' (checked {len(history)} messages)")
                            else:
                                logger.debug(f"No messages found for group '{display_name}'")
                        except Exception as e:
                            logger.error(f"Error getting messages from group '{display_name}' (ID: {group_id}) via Green API: {e}", exc_info=True)
                            continue
                    else:
                        # Group not found or it's a regular chat (not a group)
                        # Skip if we were looking for a group but didn't find it
                        if not chat_name.endswith('@g.us'):
                            logger.warning(f"⚠️ Group '{chat_name}' not found. Skipping Selenium check (groups should be found via Green API).")
                            continue
                        
                        # Use Selenium for regular chats (by name) - only for non-group chats
                        logger.debug(f"Using Selenium for regular chat: {chat_name}")
                        messages_data = await whatsapp_service.get_messages_from_chat(chat_name, days=1)
                        
                        # Filter to only last 5 minutes
                        recent_cutoff = datetime.now().astimezone() - timedelta(minutes=5)
                        recent_messages = [
                            msg for msg in messages_data 
                            if msg.get('date', datetime.now().astimezone()) >= recent_cutoff
                        ]
                        
                        # Save new messages
                        saved = 0
                        for msg_data in recent_messages:
                            wa_message = WhatsAppMessage(
                                chat_name=chat_name,
                                sender=msg_data.get('sender'),
                                text=msg_data.get('text', ''),
                                date=msg_data.get('date'),
                                message_id="",
                                media_type=msg_data.get('media_type'),
                                media_path=None,
                                media_files=msg_data.get('media_files')
                            )
                            await whatsapp_message_service.save_message(wa_message)
                            saved += 1
                        
                        if saved > 0:
                            logger.info(f"Saved {saved} new messages from '{chat_name}'")
                        
                except Exception as e:
                    logger.error(f"Error monitoring chat '{chat_name}': {e}", exc_info=True)
                    continue
            
        except Exception as e:
            logger.error(f"Error in WhatsApp monitoring loop: {e}")
        
        # Check every 60 seconds
        await asyncio.sleep(60)

async def start_author_analysis():
    """Фоновая задача для периодического анализа авторов сообщений"""
    from app.services.author_analysis_service import author_analysis_service
    from app.services.pending_analysis_service import pending_analysis_service
    import asyncio
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("Author analysis task started")
    
    while True:
        try:
            await asyncio.sleep(300)  # Каждые 5 минут
            
            # Сначала обрабатываем отложенные анализы (если квота восстановилась)
            pending_count = pending_analysis_service.get_pending_count()
            if pending_count > 0:
                logger.info(f"🔄 Found {pending_count} pending analyses, processing...")
                await author_analysis_service.process_pending_analyses()
            
            # Затем анализируем новых авторов
            await author_analysis_service.analyze_new_authors()
        except Exception as e:
            logger.error(f"Error in author analysis task: {e}", exc_info=True)
            await asyncio.sleep(60)  # При ошибке ждем минуту перед повтором

@app.on_event("shutdown")
async def shutdown_event():
    from app.core.scheduler import stop_scheduler
    await stop_scheduler()
    await monitoring_service.stop()
    from app.services.telegram_service import telegram_service
    # Temporarily disabled WhatsApp service due to dependency issues
    # from app.services.whatsapp_service import whatsapp_service
    await telegram_service.disconnect()
    # await whatsapp_service.disconnect()

AVAILABLE_TABS = {"messages", "channels", "contacts", "tournaments", "group-data"}

def render_dashboard(request: Request, initial_tab: str = "messages"):
    if initial_tab not in AVAILABLE_TABS:
        initial_tab = "messages"
    return templates.TemplateResponse("index.html", {
        "request": request,
        "initial_tab": initial_tab
    })

@app.get("/")
async def root(request: Request):
    tab = request.query_params.get("tab")
    initial_tab = tab if tab in AVAILABLE_TABS else "messages"
    return render_dashboard(request, initial_tab)

@app.get("/messages", include_in_schema=False)
async def messages_page(request: Request):
    return render_dashboard(request, "messages")

@app.get("/channels", include_in_schema=False)
async def channels_page(request: Request):
    return render_dashboard(request, "channels")

@app.get("/contacts", include_in_schema=False)
async def contacts_page(request: Request):
    return render_dashboard(request, "contacts")

@app.get("/tournaments", include_in_schema=False)
async def tournaments_tab_page(request: Request):
    return render_dashboard(request, "tournaments")

@app.get("/group-data", include_in_schema=False)
async def group_data_page(request: Request):
    return render_dashboard(request, "group-data")

@app.get("/admin", include_in_schema=False)
async def admin_page(request: Request):
    """Страница админ-панели"""
    from datetime import datetime
    return templates.TemplateResponse("admin_panel.html", {
        "request": request,
        "timestamp": int(datetime.now().timestamp())
    })

@app.get("/tournaments/create")
async def tournament_create_page(request: Request):
    """Страница создания турнира"""
    return templates.TemplateResponse("tournament_create.html", {
        "request": request
    })


@app.get("/t/{tournament_id}")
async def short_tournament_redirect(
    request: Request, 
    tournament_id: int,
    utm_source: str = None,
    utm_medium: str = None,
    utm_campaign: str = None
):
    """
    Короткая ссылка на турнир с логированием клика и UTM параметрами.
    Редиректит на Telegraph если есть, иначе на страницу турнира.
    
    Формат: /t/14?utm_source=telegram&utm_medium=bot&utm_campaign=search
    """
    from fastapi.responses import RedirectResponse
    from app.services.tournament_service import tournament_service
    
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        return RedirectResponse(url="/", status_code=302)
    
    # Определяем источник из UTM или referer
    source = utm_source or "short_link"
    if not utm_source:
        referer = request.headers.get("referer", "")
        if "t.me" in referer or "telegram" in referer.lower():
            source = "telegram"
        elif "channel" in referer.lower():
            source = "channel"
    
    # Логируем клик с UTM параметрами
    try:
        from app.services.analytics_service import get_analytics_service
        analytics_service = get_analytics_service()
        await analytics_service.log_click(tournament_id, source, {
            "utm_source": utm_source or source,
            "utm_medium": utm_medium or "telegraph",
            "utm_campaign": utm_campaign or f"tournament_{tournament_id}"
        })
        logger.info(f"📊 Logged click for tournament {tournament_id}: source={source}, utm_source={utm_source}")
    except Exception as e:
        logger.warning(f"Failed to log click: {e}")
    
    # Редирект на Telegraph если есть, иначе на страницу турнира
    teletype_url = getattr(tournament, 'teletype_url', None)
    if teletype_url:
        return RedirectResponse(url=teletype_url, status_code=302)
    else:
        return RedirectResponse(url=f"/tournaments/{tournament_id}", status_code=302)


@app.get("/tournaments/{tournament_id}")
async def tournament_page(request: Request, tournament_id: int):
    """Страница турнира"""
    from app.services.tournament_service import tournament_service
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=404)
    
    # Логируем клик если есть UTM-параметры (переход из бота/канала)
    utm_source = request.query_params.get("utm_source")
    utm_medium = request.query_params.get("utm_medium")
    utm_campaign = request.query_params.get("utm_campaign")
    
    if utm_source or utm_medium or utm_campaign:
        try:
            from app.services.analytics_service import get_analytics_service
            analytics_service = get_analytics_service()
            
            # Определяем источник по utm_source/utm_medium
            if utm_source == "telegraph" or utm_medium == "article":
                source = "telegraph"
            elif utm_medium == "bot":
                source = "bot_search"
            elif utm_medium == "channel":
                source = "tg_channel"
            elif utm_medium == "mailing":
                source = "mailing"
            else:
                source = "unknown"
            
            utm_params = {}
            if utm_source:
                utm_params["utm_source"] = utm_source
            if utm_medium:
                utm_params["utm_medium"] = utm_medium
            if utm_campaign:
                utm_params["utm_campaign"] = utm_campaign
            
            await analytics_service.log_click(tournament_id, source, utm_params)
            logger.info(f"📊 Logged click for tournament {tournament_id} from {source}")
        except Exception as e:
            logger.warning(f"Failed to log click for tournament {tournament_id}: {e}")
    
    # Получаем извлеченные данные если есть
    extracted_data = await tournament_service.get_extracted_data(tournament_id)
    
    # Всегда используем новый шаблон карточки
    return templates.TemplateResponse("tournament_card.html", {
        "request": request,
        "tournament": tournament,
        "extracted_data": extracted_data
    })

@app.get("/tournaments/{tournament_id}/edit")
async def tournament_edit_page(request: Request, tournament_id: int):
    """Страница редактирования турнира"""
    from app.services.tournament_service import tournament_service
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/tournaments", status_code=404)
    
    # Получаем извлеченные данные если есть
    extracted_data = await tournament_service.get_extracted_data(tournament_id)
    
    return templates.TemplateResponse("tournament_edit.html", {
        "request": request,
        "tournament": tournament,
        "extracted_data": extracted_data
    })

@app.get("/login")
async def login_page(request: Request):
    from app.core.config import settings
    return templates.TemplateResponse("login.html", {"request": request, "phone": settings.TELEGRAM_PHONE})
