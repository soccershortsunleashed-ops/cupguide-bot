"""
API для автопостинга в Telegram группы
"""
import logging
import asyncio
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autopost", tags=["autopost"])

# Статус подключения и постинга
autopost_status = {
    "connected": False,
    "phone": None,
    "username": None,
    "last_post_time": None,
    "posts_today": 0,
    "is_posting": False,
    "auth_required": False,
    "auth_phone_sent": False,
}


class GroupConfig(BaseModel):
    id: str  # chat_id или @username
    name: str
    active: bool = True


class PostRequest(BaseModel):
    use_short: bool = False
    skip_posted_today: bool = True


class AuthPhoneRequest(BaseModel):
    phone: str


class AuthCodeRequest(BaseModel):
    code: str


class MessageRequest(BaseModel):
    message: str


# ============================================================
# STATUS
# ============================================================

@router.get("/status")
async def get_status():
    """Получить статус автопостинга"""
    # Если не подключены, пробуем восстановить сессию
    if not autopost_status["connected"]:
        try:
            from freelance_bot.autopost.poster import auto_poster
            
            # Пробуем подключиться с существующей сессией
            connected = await auto_poster.connect()
            if connected and auto_poster.client and await auto_poster.client.is_user_authorized():
                me = await auto_poster.client.get_me()
                autopost_status["connected"] = True
                autopost_status["auth_required"] = False
                autopost_status["username"] = me.username
                autopost_status["phone"] = me.phone
                logger.info(f"✅ Restored session for @{me.username}")
        except Exception as e:
            logger.debug(f"Could not restore session: {e}")
    
    return autopost_status


# ============================================================
# GROUPS
# ============================================================

@router.get("/groups")
async def get_groups():
    """Получить список групп для постинга"""
    try:
        from freelance_bot.autopost.groups import TARGET_GROUPS
        return {"groups": TARGET_GROUPS}
    except Exception as e:
        logger.error(f"Error getting groups: {e}")
        return {"groups": [], "error": str(e)}


def normalize_group_id(group_id: str) -> str:
    """Конвертирует URL в username"""
    group_id = group_id.strip()
    # https://t.me/username -> @username
    if group_id.startswith("https://t.me/"):
        return "@" + group_id.replace("https://t.me/", "").split("/")[0]
    if group_id.startswith("http://t.me/"):
        return "@" + group_id.replace("http://t.me/", "").split("/")[0]
    if group_id.startswith("t.me/"):
        return "@" + group_id.replace("t.me/", "").split("/")[0]
    return group_id


def sanitize_string(s: str) -> str:
    """Санитизация строки для безопасной записи в Python файл"""
    # Удаляем опасные символы
    return s.replace('"', '\\"').replace("'", "\\'").replace("\n", " ").replace("\r", "").replace("\\", "\\\\")


@router.post("/groups")
async def save_groups(groups: List[GroupConfig]):
    """Сохранить список групп"""
    try:
        # Нормализуем ID групп
        for g in groups:
            g.id = normalize_group_id(g.id)
        
        # Обновляем файл groups.py
        groups_content = '''"""
Список групп для автопостинга.
"""

TARGET_GROUPS = [
'''
        for g in groups:
            # Санитизируем данные перед записью
            safe_name = sanitize_string(g.name)[:100]  # Ограничиваем длину
            safe_id = sanitize_string(g.id)[:100]
            groups_content += f'    {{"name": "{safe_name}", "id": "{safe_id}", "active": {str(g.active)}}},\n'
        
        groups_content += ''']

def get_active_groups() -> list:
    """Возвращает список активных групп для постинга"""
    return [g for g in TARGET_GROUPS if g.get("active", True)]
'''
        
        import os
        groups_file = os.path.join(os.path.dirname(__file__), "..", "..", "freelance_bot", "autopost", "groups.py")
        with open(groups_file, "w", encoding="utf-8") as f:
            f.write(groups_content)
        
        return {"success": True, "count": len(groups)}
    except Exception as e:
        logger.error(f"Error saving groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# MY GROUPS (from Telegram account)
# ============================================================

@router.get("/my-groups")
async def get_my_groups(folders_only: bool = False, no_folders: bool = False):
    """Получить список групп из аккаунта Telegram
    
    Args:
        folders_only: Вернуть только папки с группами
        no_folders: Вернуть только группы без папок
    """
    try:
        from freelance_bot.autopost.poster import auto_poster
        from telethon.tl.functions.messages import GetDialogFiltersRequest
        
        if not autopost_status["connected"]:
            # Пробуем подключиться
            connected = await auto_poster.connect()
            if not connected:
                return {"groups": [], "folders": [], "error": "Не подключено к Telegram", "auth_required": True}
            
            me = await auto_poster.client.get_me()
            autopost_status["connected"] = True
            autopost_status["username"] = me.username
            autopost_status["phone"] = me.phone
        
        # Получаем папки (фильтры диалогов)
        folders = []
        folder_chat_ids = set()
        
        try:
            filters = await auto_poster.client(GetDialogFiltersRequest())
            for f in filters.filters:
                if hasattr(f, 'title') and hasattr(f, 'include_peers'):
                    folder_info = {
                        "id": f.id,
                        "title": f.title,
                        "groups": []
                    }
                    for peer in f.include_peers:
                        if hasattr(peer, 'channel_id'):
                            folder_chat_ids.add(-1000000000000 - peer.channel_id)
                            folder_info["groups"].append({
                                "id": -1000000000000 - peer.channel_id,
                                "type": "channel"
                            })
                        elif hasattr(peer, 'chat_id'):
                            folder_chat_ids.add(-peer.chat_id)
                            folder_info["groups"].append({
                                "id": -peer.chat_id,
                                "type": "chat"
                            })
                    if folder_info["groups"]:
                        folders.append(folder_info)
        except Exception as e:
            logger.warning(f"Could not get folders: {e}")
        
        # Получаем все группы
        all_groups = await auto_poster.list_my_groups()
        
        # Обогащаем папки названиями групп
        group_map = {g["id"]: g for g in all_groups}
        logger.info(f"Found {len(folders)} folders, {len(all_groups)} groups")
        
        enriched_folders = []
        for folder in folders:
            enriched_groups = []
            for fg in folder["groups"]:
                if fg["id"] in group_map:
                    enriched_groups.append(group_map[fg["id"]])
            
            # Сохраняем папку даже если в ней нет групп (для отладки)
            folder["groups"] = enriched_groups
            folder["count"] = len(enriched_groups)
            
            # Добавляем только папки с группами
            if enriched_groups:
                enriched_folders.append(folder)
                logger.info(f"Folder '{folder.get('title', 'Unknown')}': {len(enriched_groups)} groups")
        
        if folders_only:
            return {"folders": enriched_folders}
        
        if no_folders:
            # Группы которые не в папках
            groups_without_folders = [g for g in all_groups if g["id"] not in folder_chat_ids]
            return {"groups": groups_without_folders}
        
        return {"groups": all_groups, "folders": enriched_folders}
        
    except Exception as e:
        logger.error(f"Error getting my groups: {e}")
        if "not authorized" in str(e).lower() or "auth" in str(e).lower():
            autopost_status["auth_required"] = True
            return {"groups": [], "folders": [], "error": "Требуется авторизация", "auth_required": True}
        return {"groups": [], "folders": [], "error": str(e)}


@router.delete("/groups")
async def clear_groups():
    """Очистить список групп"""
    try:
        import os
        groups_file = os.path.join(os.path.dirname(__file__), "..", "..", "freelance_bot", "autopost", "groups.py")
        
        groups_content = '''"""
Список групп для автопостинга.
"""

TARGET_GROUPS = []

def get_active_groups() -> list:
    """Возвращает список активных групп для постинга"""
    return [g for g in TARGET_GROUPS if g.get("active", True)]
'''
        with open(groups_file, "w", encoding="utf-8") as f:
            f.write(groups_content)
        
        return {"success": True, "message": "Список групп очищен"}
    except Exception as e:
        logger.error(f"Error clearing groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/groups/banned")
async def delete_banned_groups():
    """Удалить группы, в которых пользователь забанен"""
    try:
        from freelance_bot.autopost.poster import auto_poster
        from freelance_bot.autopost.groups import TARGET_GROUPS
        
        # Получаем логи постинга
        logs = auto_poster.posts_log or []
        
        if not logs:
            return {"success": True, "deleted_count": 0, "deleted_groups": [], "message": "Нет логов постинга. Сначала запустите постинг."}
        
        # Находим группы с ошибками доступа (бан, нет прав, приватный канал)
        banned_group_ids = set()
        banned_group_names = []
        
        access_errors = [
            "Забанен в канале",
            "Нет прав на отправку",
            "Канал приватный/недоступен",
            "Нужны права админа",
            "Chat admin privileges are required",
            "ChatWriteForbiddenError",
            "ChatAdminRequiredError",
        ]
        
        for log in logs:
            error = log.get("error", "") or ""
            # Проверяем на любую из ошибок доступа
            if any(err in error for err in access_errors):
                group_id = log.get("group_id")
                group_name = log.get("group_name", str(group_id))
                if group_id:
                    banned_group_ids.add(str(group_id))
                    if group_name not in banned_group_names:
                        banned_group_names.append(group_name)
        
        if not banned_group_ids:
            return {"success": True, "deleted_count": 0, "deleted_groups": [], "message": "Забаненных групп не найдено"}
        
        # Фильтруем группы, убирая забаненные
        new_groups = [g for g in TARGET_GROUPS if str(g.get("id", "")).lstrip("-") not in banned_group_ids and str(g.get("id", "")) not in banned_group_ids]
        
        deleted_count = len(TARGET_GROUPS) - len(new_groups)
        
        # Сохраняем обновлённый список
        import os
        groups_file = os.path.join(os.path.dirname(__file__), "..", "..", "freelance_bot", "autopost", "groups.py")
        
        groups_content = '''"""
Список групп для автопостинга.
"""

TARGET_GROUPS = [
'''
        for g in new_groups:
            safe_name = sanitize_string(g.get("name", ""))[:100]
            safe_id = sanitize_string(str(g.get("id", "")))[:100]
            active = g.get("active", True)
            groups_content += f'    {{"name": "{safe_name}", "id": "{safe_id}", "active": {str(active)}}},\n'
        
        groups_content += ''']

def get_active_groups() -> list:
    """Возвращает список активных групп для постинга"""
    return [g for g in TARGET_GROUPS if g.get("active", True)]
'''
        
        with open(groups_file, "w", encoding="utf-8") as f:
            f.write(groups_content)
        
        return {
            "success": True, 
            "deleted_count": deleted_count, 
            "deleted_groups": banned_group_names,
            "remaining_count": len(new_groups)
        }
        
    except Exception as e:
        logger.error(f"Error deleting banned groups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# AUTH
# ============================================================

@router.post("/auth/send-code")
async def send_auth_code(request: AuthPhoneRequest):
    """Отправить код авторизации на телефон"""
    try:
        from freelance_bot.autopost.poster import auto_poster
        from freelance_bot.autopost.config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSION_PATH
        from telethon import TelegramClient
        
        # Создаём клиент если нет
        if not auto_poster.client:
            auto_poster.client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)
        
        await auto_poster.client.connect()
        
        # Отправляем код
        result = await auto_poster.client.send_code_request(request.phone)
        
        autopost_status["auth_phone_sent"] = True
        autopost_status["phone"] = request.phone
        
        return {"success": True, "phone_code_hash": result.phone_code_hash}
        
    except Exception as e:
        logger.error(f"Error sending auth code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/verify-code")
async def verify_auth_code(request: AuthCodeRequest):
    """Подтвердить код авторизации"""
    try:
        from freelance_bot.autopost.poster import auto_poster
        
        if not auto_poster.client:
            raise HTTPException(status_code=400, detail="Сначала отправьте код")
        
        # Авторизуемся
        await auto_poster.client.sign_in(autopost_status["phone"], request.code)
        
        me = await auto_poster.client.get_me()
        
        autopost_status["connected"] = True
        autopost_status["auth_required"] = False
        autopost_status["auth_phone_sent"] = False
        autopost_status["username"] = me.username
        
        return {"success": True, "username": me.username}
        
    except Exception as e:
        logger.error(f"Error verifying auth code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# POSTING
# ============================================================

@router.post("/post")
async def run_posting(request: PostRequest, background_tasks: BackgroundTasks):
    """Запустить постинг в группы"""
    if autopost_status["is_posting"]:
        raise HTTPException(status_code=400, detail="Постинг уже запущен")
    
    try:
        from freelance_bot.autopost.poster import auto_poster
        from freelance_bot.autopost.groups import get_active_groups
        
        groups = get_active_groups()
        if not groups:
            raise HTTPException(status_code=400, detail="Нет активных групп для постинга")
        
        # Проверяем подключение
        if not autopost_status["connected"]:
            connected = await auto_poster.connect()
            if not connected:
                raise HTTPException(status_code=400, detail="Не удалось подключиться к Telegram")
            
            me = await auto_poster.client.get_me()
            autopost_status["connected"] = True
            autopost_status["username"] = me.username
        
        # Запускаем постинг в фоне
        autopost_status["is_posting"] = True
        
        async def do_posting():
            try:
                stats = await auto_poster.post_to_all_groups(
                    use_short=request.use_short,
                    skip_posted_today=request.skip_posted_today
                )
                autopost_status["last_post_time"] = datetime.now().isoformat()
                autopost_status["posts_today"] += stats.get("success", 0)
                return stats
            finally:
                autopost_status["is_posting"] = False
        
        # Запускаем асинхронно
        stats = await do_posting()
        
        return {"success": True, "stats": stats}
        
    except Exception as e:
        autopost_status["is_posting"] = False
        logger.error(f"Error posting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_post_logs():
    """Получить логи постинга"""
    try:
        from freelance_bot.autopost.poster import auto_poster
        return {"logs": auto_poster.posts_log[-50:]}  # Последние 50 записей
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        return {"logs": [], "error": str(e)}


@router.get("/message-preview")
async def get_message_preview(short: bool = False):
    """Получить превью сообщения для постинга"""
    try:
        from freelance_bot.autopost.message import get_post_message, get_short_post_message
        
        if short:
            message = get_short_post_message()
        else:
            message = get_post_message()
        
        return {"message": message}
    except Exception as e:
        logger.error(f"Error getting message preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message")
async def save_message(request: MessageRequest, short: bool = False):
    """Сохранить текст сообщения"""
    try:
        import os
        from pathlib import Path
        
        message = request.message
        
        # Валидация длины сообщения
        if len(message) > 4096:
            raise HTTPException(status_code=400, detail="Сообщение слишком длинное (макс 4096 символов)")
        
        if len(message) < 10:
            raise HTTPException(status_code=400, detail="Сообщение слишком короткое")
        
        message_file = Path(__file__).parent.parent.parent / "freelance_bot" / "autopost" / "message.py"
        
        # Читаем текущий файл
        with open(message_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Экранируем кавычки в сообщении (безопасно)
        escaped_message = message.replace('\\', '\\\\').replace('"""', '\\"\\"\\"').replace("'''", "\\'\\'\\'")
        
        if short:
            # Заменяем короткую версию
            import re
            pattern = r'(def get_short_post_message\(group_id: int = None\) -> str:.*?return f""")(.*?)(""")'
            replacement = f'\\1{escaped_message}\\3'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        else:
            # Заменяем полную версию
            import re
            pattern = r'(def get_post_message\(group_id: int = None\) -> str:.*?message = f""")(.*?)(""")'
            replacement = f'\\1{escaped_message}\\3'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        with open(message_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Перезагружаем модуль
        import importlib
        import freelance_bot.autopost.message as msg_module
        importlib.reload(msg_module)
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Error saving message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group-info")
async def get_group_info(group_id: str):
    """Получить информацию о группе по ID или username"""
    try:
        from freelance_bot.autopost.poster import auto_poster
        
        # Нормализуем ID
        group_id = normalize_group_id(group_id)
        
        # Проверяем подключение
        if not autopost_status["connected"]:
            connected = await auto_poster.connect()
            if not connected:
                return {"error": "Не подключено к Telegram", "auth_required": True}
            
            me = await auto_poster.client.get_me()
            autopost_status["connected"] = True
            autopost_status["username"] = me.username
        
        # Получаем информацию о группе
        try:
            entity = await auto_poster.client.get_entity(group_id)
            
            return {
                "id": entity.id,
                "name": getattr(entity, "title", None) or getattr(entity, "first_name", group_id),
                "username": getattr(entity, "username", None),
                "is_channel": hasattr(entity, "broadcast") and entity.broadcast,
                "is_group": hasattr(entity, "megagroup") and entity.megagroup,
                "participants_count": getattr(entity, "participants_count", None)
            }
        except Exception as e:
            logger.error(f"Error getting entity {group_id}: {e}")
            return {"error": f"Группа не найдена: {group_id}", "name": group_id}
        
    except Exception as e:
        logger.error(f"Error getting group info: {e}")
        return {"error": str(e)}
