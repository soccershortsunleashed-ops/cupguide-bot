"""
Автопостер - отправка объявлений в группы через личный аккаунт
"""
import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, List, Dict

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, 
    ChatWriteForbiddenError,
    ChannelPrivateError,
    UserBannedInChannelError,
    SlowModeWaitError,
    ChatAdminRequiredError
)

from .config import (
    TELEGRAM_API_ID, 
    TELEGRAM_API_HASH, 
    SESSION_PATH,
    POST_DELAY_SECONDS,
    MAX_POSTS_PER_HOUR,
    QUIET_HOURS_START,
    QUIET_HOURS_END
)
from .message import get_post_message, get_short_post_message
from .groups import get_active_groups

logger = logging.getLogger(__name__)

# Файл для логирования постов
POSTS_LOG_FILE = os.path.join(os.path.dirname(__file__), "posts_log.json")

# Картинка для объявления
POST_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "post_image.png")


class AutoPoster:
    """Автопостер объявлений в Telegram группы"""
    
    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.posts_log: List[Dict] = []
        self._load_posts_log()
    
    def _load_posts_log(self):
        """Загружает лог постов"""
        if os.path.exists(POSTS_LOG_FILE):
            try:
                with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
                    self.posts_log = json.load(f)
            except Exception as e:
                logger.error(f"Error loading posts log: {e}")
                self.posts_log = []
    
    def _save_posts_log(self):
        """Сохраняет лог постов"""
        try:
            with open(POSTS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.posts_log, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving posts log: {e}")
    
    def _is_quiet_hours(self) -> bool:
        """Проверяет, сейчас тихие часы"""
        hour = datetime.now().hour
        if QUIET_HOURS_START > QUIET_HOURS_END:
            # Например 23:00 - 08:00
            return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END
        else:
            return QUIET_HOURS_START <= hour < QUIET_HOURS_END
    
    def _was_posted_today(self, group_id) -> bool:
        """Проверяет, был ли УСПЕШНЫЙ пост в эту группу сегодня"""
        today = datetime.now().date().isoformat()
        for log in self.posts_log:
            if (log.get("group_id") == str(group_id) and 
                log.get("date") == today and 
                log.get("success") == True):
                return True
        return False
    
    async def connect(self) -> bool:
        """Подключается к Telegram"""
        if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
            logger.error("❌ TELEGRAM_API_ID или TELEGRAM_API_HASH не заданы!")
            return False
        
        try:
            self.client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)
            await self.client.start()
            
            me = await self.client.get_me()
            logger.info(f"✅ Подключено как: {me.first_name} (@{me.username})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    async def disconnect(self):
        """Отключается от Telegram"""
        if self.client:
            await self.client.disconnect()
            logger.info("📴 Отключено от Telegram")
    
    async def _resolve_entity(self, group_id):
        """Резолвит entity по ID или username"""
        # Если это @username - используем напрямую
        if isinstance(group_id, str) and group_id.startswith("@"):
            return await self.client.get_entity(group_id)
        
        # Если это числовой ID (строка или int)
        try:
            numeric_id = int(group_id)
            # Ищем в диалогах
            async for dialog in self.client.iter_dialogs():
                if dialog.id == numeric_id:
                    return dialog.entity
            # Если не нашли в диалогах, пробуем напрямую
            return await self.client.get_entity(numeric_id)
        except (ValueError, TypeError):
            # Не числовой ID, пробуем как есть
            return await self.client.get_entity(group_id)
    
    async def post_to_group(self, group: Dict, use_short: bool = False) -> Dict:
        """
        Отправляет пост в одну группу.
        Возвращает результат: {"success": bool, "error": str, "message_id": int}
        """
        group_id = group.get("id")
        group_name = group.get("name", str(group_id))
        
        result = {
            "group_id": str(group_id),
            "group_name": group_name,
            "success": False,
            "error": None,
            "message_id": None,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().date().isoformat()
        }
        
        try:
            # Резолвим entity
            entity = await self._resolve_entity(group_id)
            
            # Получаем текст сообщения
            if use_short:
                message = get_short_post_message(group_id if isinstance(group_id, int) else None)
            else:
                message = get_post_message(group_id if isinstance(group_id, int) else None)
            
            # Отправляем с картинкой если есть (лимит caption - 1024 символа)
            sent = None
            if os.path.exists(POST_IMAGE_PATH):
                # Строго обрезаем caption до лимита
                caption = message[:1024] if len(message) > 1024 else message
                
                try:
                    sent = await self.client.send_file(
                        entity, 
                        POST_IMAGE_PATH, 
                        caption=caption
                    )
                    logger.info(f"✅ Пост с картинкой отправлен в {group_name}")
                except Exception as photo_err:
                    # Если нельзя отправить фото - отправляем только текст
                    if "PHOTO" in str(photo_err).upper() or "MEDIA" in str(photo_err).upper():
                        logger.warning(f"📷 Фото запрещено в {group_name}, отправляем только текст")
                        sent = await self.client.send_message(entity, message, link_preview=True)
                        logger.info(f"✅ Пост (только текст) отправлен в {group_name}")
                    else:
                        raise photo_err
            else:
                # link_preview=True - включаем превью ссылок
                sent = await self.client.send_message(entity, message, link_preview=True)
                logger.info(f"✅ Пост отправлен в {group_name}")
            
            if sent:
                result["success"] = True
                result["message_id"] = sent.id
            else:
                result["error"] = "Сообщение не отправлено (sent=None)"
            
        except FloodWaitError as e:
            result["error"] = f"FloodWait: ждать {e.seconds} сек"
            logger.warning(f"⏳ FloodWait в {group_name}: ждать {e.seconds} сек")
            
        except SlowModeWaitError as e:
            result["error"] = f"SlowMode: ждать {e.seconds} сек"
            logger.warning(f"🐢 SlowMode в {group_name}: ждать {e.seconds} сек")
            
        except ChatWriteForbiddenError:
            result["error"] = "Нет прав на отправку"
            logger.error(f"🚫 Нет прав в {group_name}")
            
        except ChannelPrivateError:
            result["error"] = "Канал приватный/недоступен"
            logger.error(f"🔒 Канал {group_name} недоступен")
            
        except UserBannedInChannelError:
            result["error"] = "Забанен в канале"
            logger.error(f"🚷 Забанен в {group_name}")
            
        except ChatAdminRequiredError:
            result["error"] = "Нужны права админа"
            logger.error(f"👑 Нужны права админа в {group_name}")
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"❌ Ошибка в {group_name}: {e}")
        
        # Логируем результат
        self.posts_log.append(result)
        self._save_posts_log()
        
        return result
    
    async def post_to_all_groups(self, use_short: bool = False, skip_posted_today: bool = True) -> Dict:
        """
        Постит во все активные группы.
        Возвращает сводку: {"total": N, "success": N, "failed": N, "skipped": N}
        """
        if self._is_quiet_hours():
            logger.info(f"🌙 Тихие часы ({QUIET_HOURS_START}:00 - {QUIET_HOURS_END}:00), постинг отложен")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "reason": "quiet_hours"}
        
        groups = get_active_groups()
        
        if not groups:
            logger.warning("⚠️ Нет активных групп для постинга")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "reason": "no_groups"}
        
        stats = {"total": len(groups), "success": 0, "failed": 0, "skipped": 0}
        
        for i, group in enumerate(groups):
            # Проверяем лимит
            if stats["success"] >= MAX_POSTS_PER_HOUR:
                logger.warning(f"⚠️ Достигнут лимит {MAX_POSTS_PER_HOUR} постов в час")
                stats["skipped"] += len(groups) - i
                break
            
            # Проверяем, был ли пост сегодня
            if skip_posted_today and self._was_posted_today(group.get("id")):
                logger.info(f"⏭️ Пропуск {group.get('name')} - уже постили сегодня")
                stats["skipped"] += 1
                continue
            
            # Постим
            result = await self.post_to_group(group, use_short)
            
            if result["success"]:
                stats["success"] += 1
            else:
                stats["failed"] += 1
            
            # Задержка между постами
            if i < len(groups) - 1:
                logger.info(f"⏳ Ждём {POST_DELAY_SECONDS} сек...")
                await asyncio.sleep(POST_DELAY_SECONDS)
        
        logger.info(f"📊 Итого: {stats['success']} успешно, {stats['failed']} ошибок, {stats['skipped']} пропущено")
        return stats
    
    async def list_my_groups(self) -> List[Dict]:
        """Получает список групп/каналов в которых состоит аккаунт"""
        groups = []
        
        async for dialog in self.client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                groups.append({
                    "id": dialog.id,
                    "name": dialog.name,
                    "is_channel": dialog.is_channel,
                    "is_group": dialog.is_group,
                    "username": getattr(dialog.entity, "username", None)
                })
        
        return groups


# Singleton
auto_poster = AutoPoster()
