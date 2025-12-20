"""
Polling Service - резервный режим получения сообщений
Используется когда webhook недоступен
"""
import logging
import asyncio
from typing import Dict, Set, Optional
from datetime import datetime

from avito_bot.config import config
from avito_bot.services.avito_client import avito_client
from avito_bot.services.dialog_orchestrator import dialog_orchestrator
from avito_bot.services.crm_connector import crm_connector
from avito_bot.models.chat import AvitoChat, ChatState
from avito_bot.models.message import AvitoMessage, MessageDirection

logger = logging.getLogger(__name__)


class PollingService:
    """Сервис polling для получения сообщений"""
    
    def __init__(self):
        self._running = False
        self._processed_messages: Set[str] = set()  # Для дедупликации
        self._chats: Dict[str, AvitoChat] = {}
        self._messages: Dict[str, list] = {}
        self._max_processed_cache = 10000
    
    async def start(self):
        """Запускает polling"""
        if self._running:
            logger.warning("⚠️ Polling already running")
            return
        
        self._running = True
        logger.info("🚀 Starting Avito polling...")
        
        while self._running:
            try:
                await self._poll_messages()
            except Exception as e:
                logger.error(f"❌ Polling error: {e}", exc_info=True)
            
            await asyncio.sleep(config.AVITO_POLLING_INTERVAL)
    
    async def stop(self):
        """Останавливает polling"""
        self._running = False
        logger.info("🛑 Avito polling stopped")
    
    async def _poll_messages(self):
        """Проверяет новые сообщения"""
        try:
            # Получаем чаты с непрочитанными сообщениями
            chats = await avito_client.get_chats(unread_only=True)
            
            for chat_data in chats:
                chat_id = chat_data.get("id")
                if not chat_id:
                    continue
                
                # Получаем сообщения
                messages = await avito_client.get_messages(chat_id, limit=10)
                
                for msg in messages:
                    await self._process_message(chat_id, chat_data, msg)
                
                # Помечаем как прочитанное
                await avito_client.mark_as_read(chat_id)
                
        except Exception as e:
            logger.error(f"❌ Poll messages error: {e}")
    
    async def _process_message(
        self, 
        chat_id: str, 
        chat_data: Dict, 
        msg: Dict
    ):
        """Обрабатывает одно сообщение"""
        msg_id = msg.get("id")
        
        # Дедупликация
        if msg_id in self._processed_messages:
            return
        
        # Пропускаем исходящие
        direction = msg.get("direction", "")
        if direction == "out":
            self._processed_messages.add(msg_id)
            return
        
        # Получаем или создаём чат
        chat = self._get_or_create_chat(chat_id, chat_data)
        
        # Извлекаем текст
        content = msg.get("content", {})
        text = content.get("text", "")
        
        if not text:
            self._processed_messages.add(msg_id)
            return
        
        logger.info(f"📩 New message in {chat_id}: {text[:50]}...")
        
        # Сохраняем входящее
        self._save_message(chat_id, text, MessageDirection.IN, msg_id)
        
        # Обрабатываем
        await self._handle_message(chat, text)
        
        # Добавляем в обработанные
        self._processed_messages.add(msg_id)
        self._cleanup_cache()
    
    def _get_or_create_chat(self, chat_id: str, chat_data: Dict) -> AvitoChat:
        """Получает или создаёт чат"""
        if chat_id not in self._chats:
            self._chats[chat_id] = AvitoChat(
                chat_id=chat_id,
                user_id=chat_data.get("user_id", ""),
                item_id=chat_data.get("context", {}).get("value", {}).get("id"),
                state=ChatState.NEW
            )
            self._messages[chat_id] = []
        return self._chats[chat_id]
    
    def _save_message(
        self, 
        chat_id: str, 
        text: str, 
        direction: MessageDirection,
        msg_id: Optional[str] = None
    ):
        """Сохраняет сообщение"""
        message = AvitoMessage(
            chat_id=chat_id,
            direction=direction,
            text=text,
            platform_message_id=msg_id
        )
        
        if chat_id not in self._messages:
            self._messages[chat_id] = []
        
        self._messages[chat_id].append(message)
        
        # Ограничиваем историю
        if len(self._messages[chat_id]) > 100:
            self._messages[chat_id] = self._messages[chat_id][-50:]
    
    async def _handle_message(self, chat: AvitoChat, text: str):
        """Обрабатывает сообщение через оркестратор"""
        try:
            # Контекст
            context = []
            for msg in self._messages.get(chat.chat_id, [])[-10:]:
                context.append({
                    "direction": msg.direction,
                    "text": msg.text
                })
            
            # Обрабатываем
            result = await dialog_orchestrator.process_message(
                chat=chat,
                user_message=text,
                context_messages=context
            )
            
            # Обновляем чат
            chat.current_score = result.score_abc
            chat.slots = result.slots
            chat.state = ChatState.ACTIVE
            
            # Создаём лид если нужно
            if result.should_create_lead and result.lead_payload:
                crm_result = await crm_connector.create_lead(result.lead_payload)
                
                if crm_result.success:
                    chat.crm_lead_id = crm_result.crm_lead_id
                    chat.state = ChatState.LEAD_CREATED
                else:
                    # Fallback
                    fallback = dialog_orchestrator.handle_crm_error(chat)
                    result = fallback
            
            # Отправляем ответ
            await avito_client.send_message(chat.chat_id, result.reply)
            
            # Сохраняем исходящее
            self._save_message(chat.chat_id, result.reply, MessageDirection.OUT)
            
            logger.info(f"📤 Reply sent to {chat.chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Handle message error: {e}", exc_info=True)
    
    def _cleanup_cache(self):
        """Очищает кэш обработанных сообщений"""
        if len(self._processed_messages) > self._max_processed_cache:
            # Удаляем половину старых
            to_remove = list(self._processed_messages)[:self._max_processed_cache // 2]
            for msg_id in to_remove:
                self._processed_messages.discard(msg_id)


# Singleton
polling_service = PollingService()
