"""
Webhook API - приём сообщений от Авито
"""
import logging
import hashlib
import hmac
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Header, Request, BackgroundTasks
from pydantic import BaseModel

from avito_bot.config import config
from avito_bot.services.dialog_orchestrator import dialog_orchestrator
from avito_bot.services.crm_connector import crm_connector
from avito_bot.models.chat import AvitoChat, ChatState
from avito_bot.models.message import AvitoMessage, MessageDirection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook/avito", tags=["Avito Webhook"])


# In-memory storage (для MVP, потом заменить на Postgres)
_chats: Dict[str, AvitoChat] = {}
_messages: Dict[str, list] = {}  # chat_id -> list of messages


class AvitoWebhookPayload(BaseModel):
    """Payload от Авито webhook"""
    type: str  # message, etc.
    chat_id: str
    user_id: str
    item_id: Optional[str] = None
    message: Optional[Dict[str, Any]] = None
    timestamp: Optional[int] = None


class WebhookResponse(BaseModel):
    """Ответ на webhook"""
    status: str
    message_id: Optional[str] = None


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Проверяет подпись webhook"""
    if not secret:
        return True  # Если секрет не настроен, пропускаем проверку
    
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


@router.post("/", response_model=WebhookResponse)
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_avito_signature: Optional[str] = Header(None)
):
    """
    Обработка входящих webhook от Авито
    
    Поток:
    1. Проверка подписи
    2. Дедупликация
    3. Сохранение сообщения
    4. Обработка в фоне
    """
    try:
        # Получаем тело запроса
        body = await request.body()
        
        # Проверяем подпись (если настроена)
        if config.WEBHOOK_SECRET and x_avito_signature:
            if not verify_signature(body, x_avito_signature, config.WEBHOOK_SECRET):
                logger.warning("❌ Invalid webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Парсим payload
        import json
        data = json.loads(body)
        payload = AvitoWebhookPayload(**data)
        
        # Пропускаем не-сообщения
        if payload.type != "message":
            return WebhookResponse(status="ignored")
        
        # Получаем или создаём чат
        chat = await _get_or_create_chat(payload)
        
        # Дедупликация
        message_data = payload.message or {}
        message_id = message_data.get("id")
        
        if message_id and chat.last_in_msg_id == message_id:
            logger.debug(f"⚠️ Duplicate message: {message_id}")
            return WebhookResponse(status="duplicate", message_id=message_id)
        
        # Антипетля: не отвечаем на свои сообщения
        if message_data.get("direction") == "out":
            return WebhookResponse(status="ignored")
        
        # Сохраняем сообщение
        text = message_data.get("text", "")
        await _save_message(chat.chat_id, text, MessageDirection.IN, message_id)
        
        # Обновляем last_in_msg_id
        chat.last_in_msg_id = message_id
        
        # Обрабатываем в фоне
        background_tasks.add_task(
            process_message_async,
            chat,
            text
        )
        
        return WebhookResponse(status="accepted", message_id=message_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _get_or_create_chat(payload: AvitoWebhookPayload) -> AvitoChat:
    """Получает или создаёт чат"""
    chat_id = payload.chat_id
    
    if chat_id not in _chats:
        _chats[chat_id] = AvitoChat(
            chat_id=chat_id,
            user_id=payload.user_id,
            item_id=payload.item_id,
            state=ChatState.NEW
        )
        _messages[chat_id] = []
        logger.info(f"📝 New chat created: {chat_id}")
    
    return _chats[chat_id]


async def _save_message(
    chat_id: str, 
    text: str, 
    direction: MessageDirection,
    platform_message_id: Optional[str] = None
):
    """Сохраняет сообщение"""
    message = AvitoMessage(
        chat_id=chat_id,
        direction=direction,
        text=text,
        platform_message_id=platform_message_id
    )
    
    if chat_id not in _messages:
        _messages[chat_id] = []
    
    _messages[chat_id].append(message)
    
    # Ограничиваем историю
    if len(_messages[chat_id]) > 100:
        _messages[chat_id] = _messages[chat_id][-50:]


async def process_message_async(chat: AvitoChat, text: str):
    """Асинхронная обработка сообщения"""
    try:
        # Получаем контекст
        context = []
        for msg in _messages.get(chat.chat_id, [])[-10:]:
            context.append({
                "direction": msg.direction,
                "text": msg.text
            })
        
        # Обрабатываем через оркестратор
        result = await dialog_orchestrator.process_message(
            chat=chat,
            user_message=text,
            context_messages=context
        )
        
        # Обновляем состояние чата
        chat.current_score = result.score_abc
        chat.slots = result.slots
        chat.state = ChatState.ACTIVE
        
        # Создаём лид если нужно
        if result.should_create_lead and result.lead_payload:
            crm_result = await crm_connector.create_lead(result.lead_payload)
            
            if crm_result.success:
                chat.crm_lead_id = crm_result.crm_lead_id
                chat.state = ChatState.LEAD_CREATED
                logger.info(f"✅ Lead created: {crm_result.crm_lead_id}")
            else:
                # Fallback при ошибке CRM
                logger.warning(f"⚠️ CRM error: {crm_result.error}")
                fallback = dialog_orchestrator.handle_crm_error(chat)
                result = fallback
        
        # Сохраняем ответ
        await _save_message(chat.chat_id, result.reply, MessageDirection.OUT)
        
        # TODO: Отправить ответ в Авито через API
        logger.info(f"📤 Reply for {chat.chat_id}: {result.reply[:100]}...")
        
    except Exception as e:
        logger.error(f"❌ Process message error: {e}", exc_info=True)


@router.get("/health")
async def health_check():
    """Проверка статуса"""
    return {
        "status": "ok",
        "configured": config.is_configured,
        "chats_count": len(_chats)
    }


@router.post("/polling/start")
async def start_polling(background_tasks: BackgroundTasks):
    """Запускает polling режим (альтернатива webhook)"""
    from avito_bot.services.polling import polling_service
    
    background_tasks.add_task(polling_service.start)
    return {"status": "polling_started"}


@router.post("/polling/stop")
async def stop_polling():
    """Останавливает polling режим"""
    from avito_bot.services.polling import polling_service
    
    await polling_service.stop()
    return {"status": "polling_stopped"}
