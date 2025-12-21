"""
API для поиска тематических чатов в Telegram
"""
import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()

# Пути к файлам
DATA_DIR = os.path.join(settings.DATA_DIR, "smart_poster")
CHATS_FILE = os.path.join(DATA_DIR, "it_freelance_chats.json")
KEYWORDS_FILE = os.path.join(DATA_DIR, "search_keywords.json")

os.makedirs(DATA_DIR, exist_ok=True)

# Статус поиска
search_status = {
    "status": "idle",  # idle, running, completed, error
    "progress": 0,
    "message": "",
    "current_keyword": "",
    "found": 0,
    "new": 0
}

# Дефолтные ключевые слова для футбольных турниров
DEFAULT_KEYWORDS = [
    "футбольный турнир", "детский футбол турнир", "юношеский футбол",
    "футбол соревнования", "кубок футбол",
    "футбол 2015", "футбол 2014", "футбол 2013", "футбол 2012", "футбол дети",
    "футбольная школа", "футбольная академия", "ДЮСШ футбол", "спортшкола футбол",
    "футбол Москва", "футбол Санкт-Петербург", "футбол Краснодар", "футбол Казань",
    "детский футбол", "юные футболисты", "футбол тренер", "футбольный лагерь"
]


class KeywordsRequest(BaseModel):
    keywords: List[str]


def load_chats() -> List[dict]:
    """Загрузка чатов из файла"""
    if os.path.exists(CHATS_FILE):
        with open(CHATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_chats(chats: List[dict]):
    """Сохранение чатов в файл"""
    with open(CHATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)


def load_keywords() -> List[str]:
    """Загрузка ключевых слов"""
    if os.path.exists(KEYWORDS_FILE):
        try:
            with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                keywords = data.get('keywords', [])
                if keywords:
                    return keywords
        except Exception as e:
            print(f"Error loading keywords: {e}")
    return DEFAULT_KEYWORDS.copy()


def save_keywords(keywords: List[str]):
    """Сохранение ключевых слов"""
    # Фильтруем пустые строки и дубликаты
    clean_keywords = list(dict.fromkeys([k.strip() for k in keywords if k.strip()]))
    
    with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'keywords': clean_keywords, 
            'updated_at': datetime.now().isoformat(),
            'count': len(clean_keywords)
        }, f, ensure_ascii=False, indent=2)
    
    return clean_keywords


@router.get("/chats")
async def get_chats():
    """Получение списка найденных чатов"""
    chats = load_chats()
    
    # Статистика
    total = len(chats)
    relevant = len([c for c in chats if c.get('relevance_level') in ['HIGH', 'MEDIUM']])
    joined = len([c for c in chats if c.get('is_joined')])
    
    # Сортировка по участникам
    chats_sorted = sorted(chats, key=lambda x: x.get('members_count') or 0, reverse=True)
    
    return {
        "chats": chats_sorted[:100],  # Первые 100
        "total": total,
        "relevant": relevant,
        "joined": joined
    }


@router.get("/keywords")
async def get_keywords():
    """Получение текущих ключевых слов"""
    keywords = load_keywords()
    return {"keywords": keywords}


@router.get("/keywords/default")
async def get_default_keywords():
    """Получение дефолтных ключевых слов"""
    return {"keywords": DEFAULT_KEYWORDS}


@router.post("/keywords")
async def set_keywords(request: KeywordsRequest):
    """Сохранение ключевых слов"""
    clean_keywords = save_keywords(request.keywords)
    return {"status": "ok", "count": len(clean_keywords), "keywords": clean_keywords}


@router.get("/status")
async def get_search_status():
    """Получение статуса поиска"""
    return search_status


@router.post("/start")
async def start_search(background_tasks: BackgroundTasks):
    """Запуск поиска чатов"""
    global search_status
    
    if search_status["status"] == "running":
        return {"status": "already_running", "message": "Поиск уже запущен"}
    
    search_status = {
        "status": "running",
        "progress": 0,
        "message": "Запуск поиска...",
        "current_keyword": "",
        "found": 0,
        "new": 0
    }
    
    background_tasks.add_task(run_search)
    return {"status": "started", "message": "Поиск запущен"}


async def run_search():
    """Фоновая задача поиска"""
    global search_status
    
    try:
        from app.services.telegram_service import telegram_service
        from telethon.tl.functions.contacts import SearchRequest
        from telethon.tl.types import Channel
        from telethon.errors import FloodWaitError
        
        client = await telegram_service.get_client()
        
        if not await client.is_user_authorized():
            search_status["status"] = "error"
            search_status["message"] = "Telegram не авторизован"
            return
        
        keywords = load_keywords()
        existing_chats = {c['tg_chat_id']: c for c in load_chats()}
        
        total_keywords = len(keywords)
        new_count = 0
        found_count = 0
        
        for i, keyword in enumerate(keywords):
            search_status["current_keyword"] = keyword
            search_status["progress"] = int((i / total_keywords) * 100)
            search_status["message"] = f"Поиск: {keyword}"
            
            try:
                result = await client(SearchRequest(q=keyword, limit=50))
                
                for chat in result.chats:
                    if isinstance(chat, Channel) and not chat.broadcast and chat.username:
                        found_count += 1
                        
                        if chat.id not in existing_chats:
                            new_chat = {
                                "id": len(existing_chats) + 1,
                                "tg_chat_id": chat.id,
                                "username": chat.username,
                                "title": chat.title,
                                "members_count": getattr(chat, 'participants_count', None),
                                "is_verified": getattr(chat, 'verified', False),
                                "relevance_level": "UNKNOWN",
                                "keywords_matched": [keyword],
                                "is_joined": False,
                                "discovered_at": datetime.now().isoformat()
                            }
                            existing_chats[chat.id] = new_chat
                            new_count += 1
                        else:
                            # Добавляем ключевое слово
                            kw_list = existing_chats[chat.id].get('keywords_matched', [])
                            if keyword not in kw_list:
                                kw_list.append(keyword)
                                existing_chats[chat.id]['keywords_matched'] = kw_list
                
                search_status["found"] = found_count
                search_status["new"] = new_count
                
                await asyncio.sleep(1.5)  # Задержка между запросами
                
            except FloodWaitError as e:
                search_status["message"] = f"Ожидание {e.seconds} сек..."
                await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                print(f"Error searching '{keyword}': {e}")
                await asyncio.sleep(2)
        
        # Сохраняем результаты
        save_chats(list(existing_chats.values()))
        
        search_status["status"] = "completed"
        search_status["progress"] = 100
        search_status["message"] = f"Готово! Найдено {found_count}, новых {new_count}"
        
    except Exception as e:
        search_status["status"] = "error"
        search_status["message"] = f"Ошибка: {str(e)}"


@router.post("/join/{chat_id}")
async def join_chat(chat_id: int):
    """Вступление в чат"""
    try:
        from app.services.telegram_service import telegram_service
        
        client = await telegram_service.get_client()
        
        # Находим чат
        chats = load_chats()
        chat = next((c for c in chats if c['tg_chat_id'] == chat_id), None)
        
        if not chat:
            raise HTTPException(status_code=404, detail="Чат не найден")
        
        # Вступаем
        from telethon.tl.functions.channels import JoinChannelRequest
        await client(JoinChannelRequest(chat['username']))
        
        # Обновляем статус
        chat['is_joined'] = True
        chat['joined_at'] = datetime.now().isoformat()
        save_chats(chats)
        
        return {"status": "ok", "message": f"Вступили в @{chat['username']}"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
