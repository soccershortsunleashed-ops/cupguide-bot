"""
Autopost Service - сервис автопостинга в Telegram-каналы
"""
import json
import os
import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib

import aiofiles
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest

from app.core.config import settings
from app.models.posting_task import (
    AutopostChannel, AutopostMessage, PostingBatch, PostingTask, PostingLog,
    PostingStatus, ChannelStatus
)

logger = logging.getLogger(__name__)


class AutopostService:
    """Сервис автопостинга в Telegram-каналы"""
    
    def __init__(self):
        self.channels_file = os.path.join(settings.DATA_DIR, "channels_autopost.json")
        self.messages_file = os.path.join(settings.DATA_DIR, "autopost_messages.json")
        self.batches_file = os.path.join(settings.DATA_DIR, "posting_batches.json")
        self.tasks_file = os.path.join(settings.DATA_DIR, "posting_tasks.json")
        self.logs_file = os.path.join(settings.DATA_DIR, "posting_logs.json")
        self._ensure_files_exist()
        
        # Настройки
        self.delay_between_channels = 2.0  # секунды
        self.max_retries = 3
    
    def _ensure_files_exist(self):
        """Создаёт файлы если не существуют"""
        os.makedirs(os.path.dirname(self.channels_file), exist_ok=True)
        
        for file_path in [self.channels_file, self.messages_file, 
                          self.batches_file, self.tasks_file, self.logs_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([], f)
    
    # ============================================================
    # CHANNELS
    # ============================================================
    
    async def get_channels(self, active_only: bool = True) -> List[AutopostChannel]:
        """Получает список каналов для автопостинга"""
        async with aiofiles.open(self.channels_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            
            data = json.loads(content)
            channels = [AutopostChannel(**item) for item in data]
        
        if active_only:
            channels = [c for c in channels if c.is_active and c.can_post]
        
        return channels
    
    async def add_channel(self, channel_data: Dict[str, Any]) -> AutopostChannel:
        """Добавляет канал для автопостинга"""
        channels = await self.get_channels(active_only=False)
        
        # Проверяем дубликат
        tg_chat_id = channel_data.get("tg_chat_id")
        for ch in channels:
            if ch.tg_chat_id == tg_chat_id:
                logger.warning(f"Channel {tg_chat_id} already exists")
                return ch
        
        next_id = max([c.id for c in channels if c.id], default=0) + 1
        
        channel = AutopostChannel(
            id=next_id,
            **channel_data
        )
        
        channels.append(channel)
        await self._save_channels(channels)
        
        logger.info(f"✅ Added autopost channel: {channel.title} ({channel.tg_chat_id})")
        return channel
    
    async def update_channel(self, channel_id: int, update_data: Dict[str, Any]) -> Optional[AutopostChannel]:
        """Обновляет канал"""
        channels = await self.get_channels(active_only=False)
        
        for i, ch in enumerate(channels):
            if ch.id == channel_id:
                for key, value in update_data.items():
                    if hasattr(ch, key):
                        setattr(ch, key, value)
                ch.updated_at = datetime.now()
                channels[i] = ch
                await self._save_channels(channels)
                return ch
        
        return None
    
    async def _save_channels(self, channels: List[AutopostChannel]):
        """Сохраняет каналы"""
        data = [c.model_dump() for c in channels]
        async with aiofiles.open(self.channels_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    
    # ============================================================
    # MESSAGES
    # ============================================================
    
    async def get_active_message(self) -> Optional[AutopostMessage]:
        """Получает активное сообщение для постинга"""
        async with aiofiles.open(self.messages_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return None
            
            data = json.loads(content)
            messages = [AutopostMessage(**item) for item in data]
        
        for msg in messages:
            if msg.is_active:
                return msg
        
        return None
    
    async def set_message(self, message_text: str, bot_username: str) -> AutopostMessage:
        """Устанавливает сообщение для автопостинга"""
        async with aiofiles.open(self.messages_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            messages = json.loads(content) if content.strip() else []
        
        # Деактивируем все предыдущие
        for msg in messages:
            msg["is_active"] = False
        
        next_id = max([m.get("id", 0) for m in messages], default=0) + 1
        
        message = AutopostMessage(
            id=next_id,
            message_text=message_text,
            message_hash=hashlib.md5(message_text.encode()).hexdigest(),
            bot_username=bot_username,
            is_active=True
        )
        
        messages.append(message.model_dump())
        
        async with aiofiles.open(self.messages_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(messages, ensure_ascii=False, indent=2, default=str))
        
        logger.info(f"✅ Set autopost message (id={message.id})")
        return message
    
    # ============================================================
    # POSTING
    # ============================================================
    
    async def create_posting_batch(self) -> Optional[PostingBatch]:
        """Создаёт пакет задач постинга (вызывается планировщиком каждый час)"""
        
        # Получаем активное сообщение
        message = await self.get_active_message()
        if not message:
            logger.warning("No active message for autoposting")
            return None
        
        # Получаем активные каналы
        channels = await self.get_channels(active_only=True)
        if not channels:
            logger.warning("No active channels for autoposting")
            return None
        
        # Создаём batch
        async with aiofiles.open(self.batches_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            batches = json.loads(content) if content.strip() else []
        
        next_id = max([b.get("id", 0) for b in batches], default=0) + 1
        
        batch = PostingBatch(
            id=next_id,
            message_id=message.id,
            total_channels=len(channels),
            scheduled_for=datetime.now()
        )
        
        batches.append(batch.model_dump())
        
        async with aiofiles.open(self.batches_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(batches, ensure_ascii=False, indent=2, default=str))
        
        # Создаём задачи для каждого канала
        await self._create_posting_tasks(batch.id, message.id, channels)
        
        logger.info(f"✅ Created posting batch {batch.id} with {len(channels)} tasks")
        return batch
    
    async def _create_posting_tasks(self, batch_id: int, message_id: int, 
                                     channels: List[AutopostChannel]):
        """Создаёт задачи постинга для каждого канала"""
        async with aiofiles.open(self.tasks_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            tasks = json.loads(content) if content.strip() else []
        
        next_id = max([t.get("id", 0) for t in tasks], default=0) + 1
        
        for channel in channels:
            # Проверяем, не было ли уже поста в этом часовом окне
            if await self._was_posted_this_hour(channel.id):
                logger.info(f"Skipping channel {channel.title} - already posted this hour")
                continue
            
            task = PostingTask(
                id=next_id,
                batch_id=batch_id,
                channel_id=channel.id,
                message_id=message_id,
                scheduled_for=datetime.now()
            )
            
            tasks.append(task.model_dump())
            next_id += 1
        
        async with aiofiles.open(self.tasks_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(tasks, ensure_ascii=False, indent=2, default=str))
    
    async def _was_posted_this_hour(self, channel_id: int) -> bool:
        """Проверяет, был ли пост в канал в текущем часовом окне"""
        channels = await self.get_channels(active_only=False)
        
        for ch in channels:
            if ch.id == channel_id and ch.last_post_at:
                hour_ago = datetime.now() - timedelta(hours=1)
                if ch.last_post_at > hour_ago:
                    return True
        
        return False
    
    async def execute_posting_batch(self, bot: Bot, batch_id: int) -> Dict[str, int]:
        """Выполняет пакет постинга"""
        
        # Получаем задачи
        async with aiofiles.open(self.tasks_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            all_tasks = json.loads(content) if content.strip() else []
        
        tasks = [PostingTask(**t) for t in all_tasks if t.get("batch_id") == batch_id]
        pending_tasks = [t for t in tasks if t.status == PostingStatus.PENDING]
        
        if not pending_tasks:
            logger.info(f"No pending tasks for batch {batch_id}")
            return {"sent": 0, "failed": 0, "skipped": 0}
        
        # Получаем сообщение
        message = await self.get_active_message()
        if not message:
            logger.error("No active message!")
            return {"sent": 0, "failed": 0, "skipped": 0}
        
        # Получаем каналы
        channels = await self.get_channels(active_only=False)
        channels_map = {c.id: c for c in channels}
        
        stats = {"sent": 0, "failed": 0, "skipped": 0}
        
        for task in pending_tasks:
            channel = channels_map.get(task.channel_id)
            if not channel:
                logger.warning(f"Channel {task.channel_id} not found")
                stats["skipped"] += 1
                continue
            
            # Выполняем отправку
            success = await self._send_to_channel(bot, task, channel, message)
            
            if success:
                stats["sent"] += 1
            else:
                stats["failed"] += 1
            
            # Задержка между каналами
            await asyncio.sleep(self.delay_between_channels)
        
        logger.info(f"✅ Batch {batch_id} completed: {stats}")
        return stats
    
    async def _send_to_channel(self, bot: Bot, task: PostingTask, 
                                channel: AutopostChannel, 
                                message: AutopostMessage) -> bool:
        """Отправляет сообщение в канал"""
        try:
            # Формируем текст с deep-link кнопкой
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            # Deep-link: ?start=src_ch_{channelId}_p_{postId}
            deep_link = f"https://t.me/{message.bot_username}?start=src_ch_{channel.tg_chat_id}_p_{task.id}"
            
            keyboard = None
            if message.include_button:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=message.button_text, url=deep_link)]
                ])
            
            # Отправляем
            sent_message = await bot.send_message(
                chat_id=channel.tg_chat_id,
                text=message.message_text,
                reply_markup=keyboard
            )
            
            # Обновляем задачу
            await self._update_task_status(task.id, PostingStatus.SENT, 
                                           sent_message_id=sent_message.message_id)
            
            # Обновляем канал
            await self.update_channel(channel.id, {
                "last_post_at": datetime.now(),
                "total_posts": channel.total_posts + 1,
                "successful_posts": channel.successful_posts + 1
            })
            
            # Логируем
            await self._log_posting(task.id, True)
            
            logger.info(f"✅ Posted to {channel.title}")
            return True
            
        except TelegramRetryAfter as e:
            # Rate limit - ждём и повторяем
            logger.warning(f"⏳ Rate limit for {channel.title}, retry after {e.retry_after}s")
            await self._update_task_status(task.id, PostingStatus.PENDING,
                                           retry_after=e.retry_after,
                                           error=f"429 retry_after={e.retry_after}")
            await self._log_posting(task.id, False, "429", str(e))
            return False
            
        except TelegramForbiddenError as e:
            # Нет прав
            logger.error(f"❌ No access to {channel.title}: {e}")
            await self._update_task_status(task.id, PostingStatus.FAILED, error="403 forbidden")
            await self.update_channel(channel.id, {
                "can_post": False,
                "status": ChannelStatus.NO_ACCESS
            })
            await self._log_posting(task.id, False, "403", str(e))
            return False
            
        except TelegramBadRequest as e:
            # Канал не найден или другая ошибка
            logger.error(f"❌ Bad request for {channel.title}: {e}")
            await self._update_task_status(task.id, PostingStatus.FAILED, error=f"400 {str(e)}")
            await self._log_posting(task.id, False, "400", str(e))
            return False
            
        except Exception as e:
            logger.error(f"❌ Error posting to {channel.title}: {e}")
            await self._update_task_status(task.id, PostingStatus.FAILED, error=str(e))
            await self._log_posting(task.id, False, "error", str(e))
            return False
    
    async def _update_task_status(self, task_id: int, status: PostingStatus,
                                   sent_message_id: Optional[int] = None,
                                   retry_after: Optional[int] = None,
                                   error: Optional[str] = None):
        """Обновляет статус задачи"""
        async with aiofiles.open(self.tasks_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            tasks = json.loads(content) if content.strip() else []
        
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = status.value
                task["updated_at"] = datetime.now().isoformat()
                
                if sent_message_id:
                    task["sent_message_id"] = sent_message_id
                    task["sent_at"] = datetime.now().isoformat()
                
                if retry_after:
                    task["retry_after"] = retry_after
                    task["next_retry_at"] = (datetime.now() + timedelta(seconds=retry_after)).isoformat()
                
                if error:
                    task["last_error"] = error
                    task["attempt_count"] = task.get("attempt_count", 0) + 1
                
                break
        
        async with aiofiles.open(self.tasks_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(tasks, ensure_ascii=False, indent=2, default=str))
    
    async def _log_posting(self, task_id: int, success: bool, 
                           error_code: Optional[str] = None,
                           error_message: Optional[str] = None):
        """Логирует попытку постинга"""
        async with aiofiles.open(self.logs_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            logs = json.loads(content) if content.strip() else []
        
        # Считаем номер попытки
        attempt_number = len([l for l in logs if l.get("task_id") == task_id]) + 1
        
        next_id = max([l.get("id", 0) for l in logs], default=0) + 1
        
        log = PostingLog(
            id=next_id,
            task_id=task_id,
            success=success,
            error_code=error_code,
            error_message=error_message,
            attempt_number=attempt_number
        )
        
        logs.append(log.model_dump())
        
        async with aiofiles.open(self.logs_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(logs, ensure_ascii=False, indent=2, default=str))


# Singleton instance
autopost_service = AutopostService()
