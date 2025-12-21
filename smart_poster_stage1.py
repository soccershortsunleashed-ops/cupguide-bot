"""
Smart Poster - Этап 1: Поиск и база данных

✅ Поиск чатов по ключевым словам
✅ Фильтрация только открытых групп
✅ Исключение приватных и закрытых чатов
✅ Сохранение найденных чатов в базу данных
✅ Дедупликация чатов по ID / username
✅ Обновление данных при повторном сканировании
✅ Логирование источника и даты добавления чата
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Set, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel
from telethon.errors import FloodWaitError

from app.core.config import settings


# Конфигурация
DATA_DIR = os.path.join(settings.DATA_DIR, "smart_poster")
CHATS_FILE = os.path.join(DATA_DIR, "it_freelance_chats.json")
SEARCH_LOG_FILE = os.path.join(DATA_DIR, "it_freelance_search_log.json")
KEYWORDS_FILE = os.path.join(DATA_DIR, "search_keywords.json")

# Создаём директорию
os.makedirs(DATA_DIR, exist_ok=True)


def load_keywords_from_file() -> List[str]:
    """Загружает ключевые слова из файла настроек"""
    if os.path.exists(KEYWORDS_FILE):
        try:
            with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                keywords = data.get('keywords', [])
                if keywords:
                    return keywords
        except Exception as e:
            print(f"⚠️ Ошибка загрузки ключевых слов: {e}")
    
    # Возвращаем дефолтные если файл пуст
    return DEFAULT_KEYWORDS.copy()


def load_existing_chats() -> Dict[int, dict]:
    """Загружает существующие чаты из базы"""
    if os.path.exists(CHATS_FILE):
        with open(CHATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {chat['tg_chat_id']: chat for chat in data}
    return {}


def save_chats(chats: Dict[int, dict]):
    """Сохраняет чаты в базу"""
    # Сортируем по количеству участников
    sorted_chats = sorted(
        chats.values(),
        key=lambda x: x.get('members_count') or 0,
        reverse=True
    )
    with open(CHATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(sorted_chats, f, ensure_ascii=False, indent=2, default=str)


def log_search(keyword: str, found: int, new: int, updated: int):
    """Логирует результаты поиска"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "keyword": keyword,
        "found": found,
        "new": new,
        "updated": updated
    }
    
    # Загружаем существующий лог
    log_data = []
    if os.path.exists(SEARCH_LOG_FILE):
        with open(SEARCH_LOG_FILE, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
    
    log_data.append(log_entry)
    
    # Храним последние 1000 записей
    if len(log_data) > 1000:
        log_data = log_data[-1000:]
    
    with open(SEARCH_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)


# Дефолтные ключевые слова (используются если файл пуст)
DEFAULT_KEYWORDS = [
    "футбольный турнир", "детский футбол турнир", "юношеский футбол",
    "футбол соревнования", "кубок футбол", "футбольная школа",
    "футбольная академия", "ДЮСШ футбол", "детский футбол"
]


async def search_chats(client: TelegramClient, keyword: str, limit: int = 50) -> List[dict]:
    """
    Поиск открытых групп по ключевому слову
    
    Фильтрует:
    - Только megagroup (не broadcast каналы)
    - Только с публичным username
    - Исключает restricted чаты
    """
    try:
        result = await client(SearchRequest(q=keyword, limit=limit))
        
        found_chats = []
        for chat in result.chats:
            if isinstance(chat, Channel):
                # ❌ Исключаем broadcast каналы (там нельзя писать)
                if chat.broadcast:
                    continue
                
                # ❌ Исключаем приватные чаты без username
                if not chat.username:
                    continue
                
                # ❌ Исключаем restricted чаты
                if getattr(chat, 'restricted', False):
                    continue
                
                chat_info = {
                    "tg_chat_id": chat.id,
                    "username": chat.username,
                    "title": chat.title,
                    "chat_type": "megagroup",
                    "members_count": getattr(chat, 'participants_count', None),
                    "is_verified": getattr(chat, 'verified', False),
                }
                found_chats.append(chat_info)
        
        return found_chats
        
    except FloodWaitError as e:
        print(f"⏳ FloodWait: ждём {e.seconds} секунд...")
        await asyncio.sleep(e.seconds + 5)
        return []
    except Exception as e:
        print(f"❌ Ошибка: {str(e)[:50]}")
        return []


async def main():
    print("=" * 70)
    print("🔍 Smart Poster - Этап 1: Поиск чатов")
    print("=" * 70)
    
    # Загружаем ключевые слова из файла
    keywords = load_keywords_from_file()
    
    if not keywords:
        print("\n❌ Ключевые слова не найдены!")
        print(f"   Добавьте их через веб-интерфейс или в файл: {KEYWORDS_FILE}")
        return
    
    print(f"\n📋 Загружено ключевых слов: {len(keywords)}")
    
    # Загружаем существующие чаты
    existing_chats = load_existing_chats()
    print(f"📂 Существующих чатов в базе: {len(existing_chats)}")
    
    # Подключаемся к Telegram
    print("\n📱 Подключение к Telegram...")
    
    client = TelegramClient(
        settings.TELEGRAM_SESSION_PATH,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH
    )
    
    await client.connect()
    
    if not await client.is_user_authorized():
        print("❌ Telegram не авторизован")
        await client.disconnect()
        return
    
    me = await client.get_me()
    print(f"✅ Авторизован как: @{me.username}")
    
    # Статистика
    stats = {
        "total_found": 0,
        "new_added": 0,
        "updated": 0,
        "duplicates": 0,
        "errors": 0
    }
    
    now = datetime.now()
    
    # Поиск по всем ключевым словам
    for i, keyword in enumerate(keywords, 1):
        print(f"\n[{i}/{len(keywords)}] 🔍 '{keyword}'", end=" ")
        
        try:
            found = await search_chats(client, keyword)
            stats["total_found"] += len(found)
            
            new_count = 0
            updated_count = 0
            
            for chat_data in found:
                tg_id = chat_data["tg_chat_id"]
                
                if tg_id in existing_chats:
                    # Обновляем существующий чат
                    existing = existing_chats[tg_id]
                    
                    # Добавляем ключевое слово если новое
                    keywords_matched = existing.get("keywords_matched", [])
                    if keyword not in keywords_matched:
                        keywords_matched.append(keyword)
                        existing["keywords_matched"] = keywords_matched
                    
                    # Обновляем данные
                    existing["members_count"] = chat_data.get("members_count") or existing.get("members_count")
                    existing["last_scanned_at"] = now.isoformat()
                    existing["updated_at"] = now.isoformat()
                    
                    existing_chats[tg_id] = existing
                    updated_count += 1
                    stats["duplicates"] += 1
                else:
                    # Добавляем новый чат
                    next_id = max([c.get("id", 0) for c in existing_chats.values()], default=0) + 1
                    
                    new_chat = {
                        "id": next_id,
                        "tg_chat_id": tg_id,
                        "username": chat_data["username"],
                        "title": chat_data["title"],
                        "chat_type": chat_data["chat_type"],
                        "members_count": chat_data.get("members_count"),
                        "is_verified": chat_data.get("is_verified", False),
                        
                        # Релевантность (будет заполнено на Этапе 2)
                        "relevance_score": 0.0,
                        "relevance_level": "UNKNOWN",
                        "relevance_reason": None,
                        "keywords_matched": [keyword],
                        
                        # Статус
                        "status": "DISCOVERED",
                        "is_joined": False,
                        "can_post": True,
                        
                        # Статистика
                        "posts_count": 0,
                        "successful_posts": 0,
                        "failed_posts": 0,
                        
                        # Метаданные - логирование источника и даты
                        "discovered_at": now.isoformat(),
                        "discovered_via_keyword": keyword,
                        "source": "search",
                        "last_scanned_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                        
                        # Дополнительно
                        "is_active": True,
                        "notes": None
                    }
                    
                    existing_chats[tg_id] = new_chat
                    new_count += 1
                    stats["new_added"] += 1
            
            # Логируем результат поиска
            log_search(keyword, len(found), new_count, updated_count)
            
            if new_count > 0:
                print(f"→ +{new_count} новых", end="")
            if updated_count > 0:
                print(f" | {updated_count} обновлено", end="")
            if new_count == 0 and updated_count == 0:
                print(f"→ 0", end="")
            print()
            
            # Сохраняем после каждого ключевого слова (на случай прерывания)
            save_chats(existing_chats)
            
            # Задержка между запросами
            await asyncio.sleep(1.5)
            
        except Exception as e:
            print(f"→ ❌ {str(e)[:30]}")
            stats["errors"] += 1
            await asyncio.sleep(3)
    
    await client.disconnect()
    
    # Финальное сохранение
    save_chats(existing_chats)
    
    # Итоги
    print("\n" + "=" * 70)
    print("📊 ИТОГИ ЭТАПА 1")
    print("=" * 70)
    print(f"✅ Всего найдено чатов: {stats['total_found']}")
    print(f"➕ Новых добавлено: {stats['new_added']}")
    print(f"🔄 Обновлено существующих: {stats['duplicates']}")
    print(f"❌ Ошибок: {stats['errors']}")
    print(f"\n📂 Всего чатов в базе: {len(existing_chats)}")
    print(f"💾 Сохранено в: {CHATS_FILE}")
    print(f"📝 Лог поиска: {SEARCH_LOG_FILE}")
    
    # Показываем ТОП-20 по участникам
    sorted_chats = sorted(
        existing_chats.values(),
        key=lambda x: x.get('members_count') or 0,
        reverse=True
    )
    
    print("\n🏆 ТОП-20 чатов по участникам:\n")
    for i, chat in enumerate(sorted_chats[:20], 1):
        title = chat['title'][:35] + "..." if len(chat['title']) > 35 else chat['title']
        members = chat.get('members_count') or '?'
        kw_count = len(chat.get('keywords_matched', []))
        print(f"{i:2}. {title}")
        print(f"    @{chat['username']} | {members} уч. | {kw_count} ключ.слов")
    
    print("\n✅ Этап 1 завершён!")


if __name__ == "__main__":
    asyncio.run(main())
