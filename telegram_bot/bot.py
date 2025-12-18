"""
Main Telegram Bot Implementation
"""
import asyncio
import logging
import os
from typing import Any, Dict, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, 
    CallbackQuery, 
    Contact,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config
from backend_client import BackendClient
from llm_consultant import LLMConsultant
from llm_tagger import LLMTagger
from logging_client import LoggingClient

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FSM States
class UserStates(StatesGroup):
    NEW = State()           # Показ согласия
    CONSENTED = State()     # Запрос контакта
    ACTIVATED = State()     # Доступ к общению

# Initialize services
backend_client = BackendClient()
llm_consultant = LLMConsultant()
llm_tagger = LLMTagger()
logging_client = LoggingClient()

# Initialize analytics service for impression logging
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from app.services.analytics_service import get_analytics_service
    analytics_service = get_analytics_service()
except Exception as e:
    logger.warning(f"Analytics service not available: {e}")
    analytics_service = None

def _log_tournament_impressions_sync(tournaments: list, context: str = "search"):
    """Логирует показы турниров для аналитики (асинхронно, не блокирует)"""
    if not analytics_service or not tournaments:
        return
    
    import asyncio
    try:
        for t in tournaments:
            tournament_id = t.get("id")
            if tournament_id:
                asyncio.create_task(
                    analytics_service.log_impression(tournament_id, context)
                )
    except Exception as e:
        logger.warning(f"Error logging impressions: {e}")

# Create router
main_router = Router()

# Список GIF-анимаций поиска (чередуются случайным образом)
import random
SEARCH_ANIMATIONS = [
    os.path.join(os.path.dirname(__file__), "search.gif"),  # Основная GIF
    os.path.join(os.path.dirname(__file__), "search_vast.gif"),  # Vast scene
    os.path.join(os.path.dirname(__file__), "search_old.gif"),  # Old scene
    os.path.join(os.path.dirname(__file__), "search_soviet.gif"),  # Soviet scene
    os.path.join(os.path.dirname(__file__), "assets", "search_animation.gif"),
    os.path.join(os.path.dirname(__file__), "assets", "search_animation_2.gif"),
    os.path.join(os.path.dirname(__file__), "assets", "search_animation_3.gif"),
]
# Fallback URL если локальные файлы не найдены
SEARCH_ANIMATION_URL = "https://media.giphy.com/media/l0HlNQ03J5JxX6lva/giphy.gif"

# Фразы во время поиска турниров (случайный выбор)
SEARCH_CAPTIONS = [
    # Новые краткие фразы
    "🔍 Подбираю турниры по заданным параметрам…",
    "🧠 Сверяю сезон, город и возрастные категории.",
    "⚙️ Фильтрую турниры по формату игры.",
    "🏟️ Проверяю доступные турниры в выбранном городе.",
    "🔎 Ищу подходящие варианты — почти готово.",
    # Футбольные фразы
    "⚽ Заглядываю в футбольные архивы и тайные таблицы…",
    "🧠 Ухожу в Чертоги Разума — ищу турнир с точностью до финального свистка.",
    "🔍 Просматриваю календарь, как скаут перед дерби.",
    "� Анализирую данные, словно перед решающим матчем.",
    "🧩 Складываю турнирную сетку по кусочкам.",
    "🕵️‍♂️ Веду расследование — футбольные факты не скроются.",
    "⏱️ Беру тайм-аут, чтобы найти самое точное расписание.",
    "🌍 Облетаю футбольный мир в поисках нужного турнира.",
    "🧠 Подключаю футбольный интеллект высшей лиги.",
    "�  Листаю летопись великих турниров…",
    "⚙️ Настраиваю тактику поиска — играем по умному.",
    "🔎 Проверяю всё, как VAR в спорном моменте.",
    "🧠 Ищу ответ там, где рождаются футбольные инсайды.",
    "🏟️ Заглядываю за кулисы мирового футбола.",
    "🎙️ Готовлю аналитику, как перед матчем тура.",
]

# Фразы ответа на "Спасибо" (случайный выбор)
THANK_YOU_RESPONSES = [
    # Короткие и лёгкие
    "⚽ Всегда рад помочь — игра продолжается!",
    "🙌 Не за что, до следующего матча!",
    "🏟️ Обращайся — я всегда на скамейке запасных.",
    "🔥 Рад быть полезным, играем дальше.",
    "👌 Всегда в форме для новых запросов.",
    # Более «характерные»
    "⚽ Не за что — футбол объединяет.",
    "🧠 Обращайся, аналитика — мой второй тайм.",
    "🎙️ Рад помочь, как комментатор в финале.",
    "🏆 Для хорошего футбольного вопроса — всегда готов.",
    "⏱️ Всегда на связи до финального свистка.",
    # С юмором
    "😄 Не за что — даже пенальти без VAR.",
    "⚽ Рад помочь, без офсайдов и ошибок.",
    "🟥🟨 Спасибо принято, карточки не выдаю.",
    "😎 Работаю чётко, как гол в девятку.",
    "🏟️ Увидимся на футбольных полях!",
    # Чуть эпичнее
    "🏆 Служу футболу и хорошим вопросам.",
    "🌍 Всегда рад помочь фанатам игры номер один.",
    "🎯 Моя миссия — точные футбольные ответы.",
    "📊 Аналитика доставлена — до новых матчей!",
    "⚽ Футбол не ждёт — если что, зови.",
    # Тёплые и дружелюбные
    "🙌 Обращайся в любое время — я на дежурстве.",
    "😊 Рад, что был полезен.",
    "⚙️ Всегда готов к следующему запросу.",
    "🧠 Если появятся вопросы — знаешь, где меня найти.",
    "🎙️ Спасибо за доверие!",
    # С «характером бота»
    "🤖 Работа выполнена, бот доволен.",
    "⚽ Задача выполнена — матч сыгран.",
    "🔍 Рад помочь, поиск завершён.",
    "🏟️ До встречи на следующем турнире!",
    "🏆 Всегда к вашим футбольным услугам.",
]

# Фразы приветствия (случайный выбор) - для быстрых ответов на "привет"
GREETING_RESPONSES = [
    "👋 Привет! Подберу футбольные турниры в России. С чего начнём?",
    "⚽ Здравствуй! Ищем турнир по городу, сезону или году рождения?",
    "🏟️ Привет! Могу найти турнир по формату, сезону и возрасту.",
    "👋 На связи. Назови любой параметр — город, сезон или формат.",
    "⚙️ Привет! Давай подберём подходящий турнир.",
]

# Персонализированные приветствия для /start (возвращающиеся пользователи)
# {name} будет заменено на имя пользователя
RETURNING_USER_GREETINGS = [
    # Дружелюбное
    "Привет, {name}! 👋 Рад снова тебя видеть. Я помогу найти футбольный турнир по всей России — по городу, возрасту и формату. Начнём подбор?",
    # Коротко и динамично
    "{name}, снова на старте! ⚽ Подберу турнир для ребёнка по городу, возрасту и датам. Готов искать?",
    # Навигатор по турнирам
    "Добро пожаловать обратно, {name}! Я — твой навигатор по футбольным турнирам России 🇷🇺 Найду соревнование по городу, возрасту и формату.",
    # С акцентом на заботу
    "Рад тебя видеть, {name} 😊 Хочешь подобрать футбольный турнир для ребёнка? Я учту город, возраст и формат — всё просто и быстро.",
    # Экспертный
    "Привет, {name}! Я специализируюсь на подборе футбольных турниров по всей России. Сообщи город и возраст — начнём поиск.",
    # Мотивирующее
    "{name}, турнир уже ждёт ⚽ Подберу подходящее соревнование по городу, возрасту и формату. Давай начнём!",
    # Про возможности
    "С возвращением, {name}! Я могу:\n• найти турнир по городу\n• подобрать по возрасту ребёнка\n• учесть формат и сезон\nГотов приступить к подбору.",
    # Максимально тёплое
    "Привет, {name}! 👋 Рад снова помочь с поиском футбольного турнира — от города до формата соревнований. С чего начнём?",
    # Точное и деловое
    "Здравствуйте, {name}. Подберу футбольный турнир по России с учётом города, возраста и формата. Готов начать поиск.",
    # Универсальное
    "Привет, {name}! ⚽ Я помогу найти или подобрать футбольный турнир по всей России — быстро и удобно. Начнём?",
]

# Приветствия без имени (fallback)
RETURNING_USER_GREETINGS_NO_NAME = [
    "Привет! 👋 Рад снова тебя видеть. Я помогу найти футбольный турнир по всей России — по городу, возрасту и формату. Начнём подбор?",
    "Снова на старте! ⚽ Подберу турнир для ребёнка по городу, возрасту и датам. Готов искать?",
    "Добро пожаловать обратно! Я — твой навигатор по футбольным турнирам России 🇷🇺",
    "Рад тебя видеть 😊 Хочешь подобрать футбольный турнир для ребёнка?",
    "Привет! ⚽ Я помогу найти или подобрать футбольный турнир по всей России — быстро и удобно. Начнём?",
]

# Фразы прощания (случайный выбор)
GOODBYE_RESPONSES = [
    "👋 Удачи на поле и за его пределами!",
    "⚽ Рад был помочь. Возвращайся, если понадобится турнир.",
    "🏟️ До встречи! Если изменятся параметры — я на связи.",
    "🙌 Спасибо за обращение. Хорошего сезона!",
    "👋 Пока! Надеюсь, турнир найдётся быстро.",
]

# Фразы для выбора турнира (рандомный выбор)
TOURNAMENT_CHOICE_PROMPTS = [
    # Нейтрально-дружелюбные
    "Какой турнир вас заинтересовал?",
    "О каком турнире хотите узнать подробнее?",
    "Расскажите, какой турнир вам интересен",
    "Что из этого откликнулось больше всего?",
    "Какой вариант рассматриваете?",
    # Диалоговые
    "Давайте разберёмся — какой турнир вам ближе?",
    "Подскажите, на какой турнир смотрите 👀",
    "Интересует конкретный турнир или сравнить оба?",
    "О каком турнире поговорим подробнее?",
    "Что хотите узнать в первую очередь?",
    # Вовлекающие
    "Напишите, какой турнир вам откликнулся — расскажу детали",
    "Выберите турнир словами, а я подберу всю информацию",
    "Опишите, какой турнир ищете — помогу разобраться",
]

async def send_search_animation(message: Message) -> Message:
    """
    Отправляет случайную GIF-анимацию поиска с случайной подписью.
    Возвращает сообщение для последующего удаления.
    """
    caption = random.choice(SEARCH_CAPTIONS)
    
    try:
        # Выбираем случайную анимацию из доступных
        available_animations = [gif for gif in SEARCH_ANIMATIONS if os.path.exists(gif)]
        
        if available_animations:
            selected_gif = random.choice(available_animations)
            animation = FSInputFile(selected_gif)
            return await message.answer_animation(
                animation=animation,
                caption=caption
            )
        else:
            # Fallback: отправляем GIF по URL
            return await message.answer_animation(
                animation=SEARCH_ANIMATION_URL,
                caption=caption
            )
    except Exception as e:
        logger.warning(f"Не удалось отправить GIF-анимацию: {e}")
        # Fallback: простое текстовое сообщение
        return await message.answer(caption)

# Helper function for logging callback actions
async def log_callback_action(callback: CallbackQuery, contact_id: Optional[int], action: str, description: str):
    """Логирует нажатие кнопки в историю сообщений"""
    try:
        await logging_client.log_message(
            contact_id=contact_id,
            telegram_user_id=callback.from_user.id,
            direction="incoming",
            message_type="callback",
            text=f"[Кнопка] {description}",
            payload={"action": action, "callback_data": callback.data},
            timestamp=callback.message.date if callback.message else datetime.now()
        )
        logger.info(f"📱 Callback logged: {action} for user {callback.from_user.id}")
    except Exception as e:
        logger.error(f"Error logging callback: {e}")

# Helper functions for image handling and formatting
async def send_recommendation_with_image(message: Message, text: str, image_path: Optional[str] = None):
    """Отправляет рекомендацию с картинкой встроенной в сообщение как фото (НЕ документ)"""
    try:
        if image_path and os.path.exists(image_path):
            file_size = os.path.getsize(image_path)
            logger.info(f"📸 Отправляем изображение как ФОТО (не документ): {image_path} ({file_size} байт)")
            
            # Отправляем как ФОТО с подписью - это встраивает изображение в сообщение
            # НЕ используем answer_document - это отправляет как файл!
            photo = FSInputFile(image_path)
            await message.answer_photo(
                photo=photo,
                caption=text  # Без parse_mode - отправляем как обычный текст
            )
            
            logger.info(f"✅ Отправлена рекомендация с ФОТО: {image_path}")
        else:
            # Отправляем только текст
            await message.answer(text)
            logger.info(f"✅ Отправлена рекомендация без картинки")
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки рекомендации: {e}")
        # Fallback - пробуем отправить без форматирования
        try:
            if image_path and os.path.exists(image_path):
                photo = FSInputFile(image_path)
                await message.answer_photo(photo=photo, caption=text)
                logger.info(f"✅ Fallback: отправлено как фото")
            else:
                await message.answer(text)
                logger.info(f"✅ Fallback: отправлен только текст")
        except Exception as e2:
            logger.error(f"❌ Ошибка fallback отправки: {e2}")
            try:
                await message.answer("❌ Произошла ошибка при отправке рекомендации.")
            except:
                pass

def format_tournaments_hierarchical(tournaments: list, context: str = "tournaments_command") -> str:
    """
    Форматирует список турниров с иерархией: Рейтинг ⭐ > Премиум 🔝 > Обычные
    Соответствует формату из llm_consultant.py
    Показывает ВСЕ рейтинговые турниры (не ограничивает до 1)
    """
    if not tournaments:
        return "🔍 Турниры не найдены."
    
    # Логируем показы турниров для аналитики
    _log_tournament_impressions_sync(tournaments, context)
    
    # Разделяем турниры по категориям
    rating_tournaments = []
    premium_tournaments = []
    regular_tournaments = []
    
    for t in tournaments:
        if t.get('rating_active') or t.get('priority_rating'):
            rating_tournaments.append(t)
        elif t.get('premium_active') or t.get('is_premium'):
            premium_tournaments.append(t)
        else:
            regular_tournaments.append(t)
    
    lines = []
    start_num = 1
    
    # 1. Рейтинговые турниры ⭐ (показываем ВСЕ)
    if rating_tournaments:
        if len(rating_tournaments) == 1:
            lines.append("⭐ Рекомендуемый турнир")
            lines.append(_format_tournament_item(rating_tournaments[0], show_number=False))
        else:
            lines.append("⭐ Рекомендуемые турниры")
            for i, t in enumerate(rating_tournaments, 1):
                lines.append(_format_tournament_item(t, number=i))
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        start_num = len(rating_tournaments) + 1
    
    # 2. Премиум-турниры 🔝
    if premium_tournaments:
        lines.append("🔝 Премиум-турниры")
        for i, t in enumerate(premium_tournaments, start_num):
            lines.append(_format_tournament_item(t, number=i))
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        start_num += len(premium_tournaments)
    
    # 3. Обычные турниры
    if regular_tournaments:
        if rating_tournaments or premium_tournaments:
            lines.append("Другие подходящие турниры:")
        else:
            lines.append(f"🏆 Найдено турниров: {len(tournaments)}\n")
        for i, t in enumerate(regular_tournaments, start_num):
            lines.append(_format_tournament_item(t, number=i))
    
    return "\n".join(lines)


def split_long_message(text: str, max_length: int = 4000) -> list:
    """
    Разбивает длинное сообщение на части для Telegram (лимит ~4096 символов).
    Разбивает по разделителям секций или по строкам.
    """
    if len(text) <= max_length:
        return [text]
    
    messages = []
    current_part = ""
    
    # Пробуем разбить по секциям (━━━━━━━━━━━━━━)
    sections = text.split("━━━━━━━━━━━━━━")
    
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
            
        # Добавляем разделитель обратно (кроме последней секции)
        if i < len(sections) - 1:
            section += "\n━━━━━━━━━━━━━━\n"
        
        if len(current_part) + len(section) <= max_length:
            current_part += section
        else:
            if current_part:
                messages.append(current_part.strip())
            current_part = section
    
    if current_part:
        messages.append(current_part.strip())
    
    # Если секции не помогли - разбиваем по строкам
    if any(len(m) > max_length for m in messages):
        messages = []
        current_part = ""
        for line in text.split("\n"):
            if len(current_part) + len(line) + 1 <= max_length:
                current_part += line + "\n"
            else:
                if current_part:
                    messages.append(current_part.strip())
                current_part = line + "\n"
        if current_part:
            messages.append(current_part.strip())
    
    return messages if messages else [text]


def _format_tournament_item(t: dict, number: int = None, show_number: bool = True) -> str:
    """Форматирует один турнир для списка"""
    title = t.get('title', 'Турнир')
    city = t.get('city', '')
    start_date = t.get('start_date') or t.get('date_start', '')
    entry_fee = t.get('entry_fee', '')
    teletype_url = t.get('teletype_url')
    tournament_id = t.get('id')
    
    # Форматируем дату
    date_str = ''
    if start_date:
        try:
            from datetime import datetime as dt
            date_obj = dt.strptime(start_date, '%Y-%m-%d')
            date_str = date_obj.strftime('%d.%m.%Y')
        except:
            date_str = start_date
    
    # Формируем строку
    if show_number and number:
        result = f"{number}. {title}"
    else:
        result = f"   {title}"
    
    if date_str:
        result += f"\n   📅 {date_str}"
    if city:
        result += f"\n   📍 {city}"
    if entry_fee:
        result += f"\n   💰 {entry_fee}"
    
    # Ссылка - кликабельная надпись с HTML
    if teletype_url and tournament_id:
        # Короткая ссылка на Telegraph через наш сервер
        result += f'\n   <a href="http://127.0.0.1:8000/t/{tournament_id}">📖 Подробная информация</a>'
    elif tournament_id:
        # Ссылка на страницу турнира
        result += f'\n   <a href="http://127.0.0.1:8000/tournaments/{tournament_id}?utm_source=telegram&utm_medium=bot&utm_campaign=search">📖 Подробная информация</a>'
    
    result += "\n"
    return result


def format_tournament_full(tournament: Dict) -> str:
    """Полное форматирование турнира для Markdown"""
    title = tournament.get('title', 'Турнир')
    city = tournament.get('city', '')
    region = tournament.get('region', '')
    start_date = tournament.get('start_date', '')
    end_date = tournament.get('end_date', '')
    entry_fee = tournament.get('entry_fee', 'Уточняйте')
    contact = tournament.get('contact', 'Не указан')
    organizer = tournament.get('organizer_name', 'Не указан')
    teletype_url = tournament.get('teletype_url')
    
    # Форматируем даты
    try:
        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').strftime('%d.%m.%Y')
            end = datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')
            dates = f"{start} - {end}"
        else:
            dates = f"{start_date} - {end_date}" if start_date and end_date else "Даты уточняются"
    except:
        dates = f"{start_date} - {end_date}" if start_date and end_date else "Даты уточняются"
    
    # Извлекаем возраста
    birth_years = tournament.get('birth_years', [])
    if birth_years:
        if isinstance(birth_years, list):
            ages_str = ', '.join(str(year).strip("[]'\"") for year in birth_years)
        else:
            ages_str = str(birth_years).strip("[]'\"")
        ages_str = ages_str.replace("'", "").replace('"', '')
    else:
        ages_str = "Не указано"
    
    # Формируем ответ в Markdown формате (используем обычный текст без жирного для совместимости)
    response = f"""🏆 {title}

📅 Даты: {dates}
📍 Место: {city}{f', {region}' if region else ''}
⚽ Возраста: {ages_str}
💰 Взнос: {entry_fee}

👥 Организатор: {organizer}
📞 Контакт: {contact}"""

    # Добавляем ссылку на Teletype если есть
    if teletype_url:
        response += f"\n\n📰 Читать в Teletype: {teletype_url}"
    
    return response

def get_tournament_image_path(tournament: Dict) -> Optional[str]:
    """
    Получает путь к КВАДРАТНОМУ изображению турнира.
    Приоритет: квадратное изображение для Telegram (лучше смотрится в чате)
    """
    # Приоритет: квадратное изображение (лучше для Telegram)
    img_url = tournament.get('image_cover_square_url')
    
    # Если нет квадратного, пробуем оригинальное
    if not img_url:
        img_url = tournament.get('image_original_url')
    
    if not img_url:
        return None
    
    img_url = img_url.lstrip('/')
    
    # ВАЖНО: сначала проверяем app/static (правильная папка с реальными картинками)
    alt_paths = [
        f"../app/{img_url}",  # Приоритет: app/static
        f"app/{img_url}",
        f"../{img_url}",
        img_url,
    ]
    
    for alt_path in alt_paths:
        if os.path.exists(alt_path):
            logger.info(f"📸 Найдено ОРИГИНАЛЬНОЕ изображение: {alt_path}")
            return alt_path
    
    logger.warning(f"⚠️ Изображение не найдено: {img_url}")
    return None

@main_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command - check if user exists or show consent"""
    user_id = message.from_user.id
    
    # Log the interaction
    await logging_client.log_message(
        contact_id=None,
        telegram_user_id=user_id,
        direction="incoming",
        message_type="command",
        text="/start",
        payload={"command": "start"},
        timestamp=message.date
    )
    
    # Проверяем, есть ли уже зарегистрированный пользователь
    try:
        existing_contact = await backend_client.get_contact_by_telegram_id(user_id)
        
        if existing_contact and existing_contact.get("found"):
            # Пользователь уже зарегистрирован - пропускаем согласие и запрос контакта
            contact_id = existing_contact.get("contact_id")
            contact_name = existing_contact.get("name", "")
            
            logger.info(f"✅ Returning user found: {user_id} -> contact_id={contact_id}")
            
            # Сохраняем contact_id в FSM
            await state.update_data(contact_id=contact_id)
            await state.set_state(UserStates.ACTIVATED)
            
            # Приветствуем вернувшегося пользователя - персонализированное сообщение
            first_name = contact_name.split()[0] if contact_name else ""
            
            if first_name:
                # Используем персонализированное приветствие с именем
                welcome_template = random.choice(RETURNING_USER_GREETINGS)
                welcome_text = welcome_template.format(name=first_name)
            else:
                # Fallback без имени
                welcome_text = random.choice(RETURNING_USER_GREETINGS_NO_NAME)
            
            await message.answer(welcome_text)
            
            # Log outgoing message
            await logging_client.log_message(
                contact_id=contact_id,
                telegram_user_id=user_id,
                direction="outgoing",
                message_type="text",
                text=welcome_text,
                payload={"action": "returning_user_welcome", "contact_id": contact_id},
                timestamp=message.date
            )
            return
            
    except Exception as e:
        logger.warning(f"Error checking existing user {user_id}: {e}")
        # Продолжаем с обычным flow если ошибка
    
    # Новый пользователь - показываем согласие
    await state.set_state(UserStates.NEW)
    
    # Create consent keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Согласен", callback_data="consent_agree")
    builder.button(text="❌ Не согласен", callback_data="consent_disagree")
    builder.adjust(2)
    
    # Send consent message
    await message.answer(
        config.CONSENT_TEXT,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Log outgoing message
    await logging_client.log_message(
        contact_id=None,
        telegram_user_id=user_id,
        direction="outgoing",
        message_type="text",
        text=config.CONSENT_TEXT,
        payload={"action": "consent_request"},
        timestamp=message.date
    )

@main_router.callback_query(F.data == "consent_agree")
async def consent_agree(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle consent agreement"""
    user_id = callback.from_user.id
    
    # Log consent agreement
    await logging_client.log_message(
        contact_id=None,
        telegram_user_id=user_id,
        direction="incoming",
        message_type="callback",
        text="consent_agree",
        payload={"consent_version": config.CONSENT_VERSION},
        timestamp=callback.message.date
    )
    
    # Set state to CONSENTED
    await state.set_state(UserStates.CONSENTED)
    
    # Create contact request keyboard
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Поделиться номером", request_contact=True)
    builder.adjust(1)
    
    # Answer callback and request contact
    await callback.answer("Спасибо за согласие!")
    await callback.message.edit_text(
        "✅ Согласие получено!\n\n"
        "Теперь поделитесь своим номером телефона, чтобы я мог добавить вас в записную книжку и предоставить персонализированные рекомендации.",
        reply_markup=None
    )
    
    await callback.message.answer(
        "👇 Нажмите кнопку ниже, чтобы поделиться контактом:",
        reply_markup=builder.as_markup(
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Нажмите кнопку ниже"
        )
    )

@main_router.callback_query(F.data == "consent_disagree")
async def consent_disagree(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle consent disagreement"""
    user_id = callback.from_user.id
    
    # Log consent disagreement
    await logging_client.log_message(
        contact_id=None,
        telegram_user_id=user_id,
        direction="incoming",
        message_type="callback",
        text="consent_disagree",
        payload={"consent_refused": True},
        timestamp=callback.message.date
    )
    
    # Clear state
    await state.clear()
    
    await callback.answer("Понятно")
    await callback.message.edit_text(
        "❌ Без согласия на обработку данных продолжение работы невозможно.\n\n"
        "Если передумаете, используйте команду /start",
        reply_markup=None
    )

@main_router.callback_query(F.data == "open_cabinet")
async def open_cabinet_from_help(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cabinet button from /help"""
    from cabinet_handlers import cmd_cabinet
    # Создаём фейковое сообщение для вызова cmd_cabinet
    await cmd_cabinet(callback.message, state)
    await callback.answer()

@main_router.message(F.content_type == "contact")
async def handle_contact(message: Message, state: FSMContext) -> None:
    """Handle contact sharing"""
    user_id = message.from_user.id
    contact: Contact = message.contact
    
    # Verify this is user's own contact
    if contact.user_id != user_id:
        await message.answer(
            "❌ Пожалуйста, поделитесь своим собственным контактом, а не чужим.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # Log contact received
    await logging_client.log_message(
        contact_id=None,
        telegram_user_id=user_id,
        direction="incoming",
        message_type="contact",
        text=f"Contact: {contact.phone_number}",
        payload={
            "phone_number": contact.phone_number,
            "first_name": contact.first_name,
            "last_name": contact.last_name
        },
        timestamp=message.date
    )
    
    try:
        # Create/update contact in backend
        contact_data = await backend_client.upsert_contact(
            telegram_user_id=user_id,
            phone=contact.phone_number,
            first_name=contact.first_name or message.from_user.first_name,
            last_name=contact.last_name or message.from_user.last_name,
            username=message.from_user.username,
            consent_version=config.CONSENT_VERSION,
            consent_given_at=message.date
        )
        
        contact_id = contact_data["contact_id"]
        is_new = contact_data["is_new"]
        
        # Store contact_id in FSM data
        await state.update_data(contact_id=contact_id)
        
        # Set state to ACTIVATED
        await state.set_state(UserStates.ACTIVATED)
        
        # Send welcome message - простое сообщение без кнопок
        first_name = contact.first_name or message.from_user.first_name or ""
        if is_new:
            welcome_text = f"🎉 Добро пожаловать{', ' + first_name if first_name else ''}!\n\n⚽ Я подберу футбольные турниры в России по городу, сезону, году рождения или формату игры.\n\nПросто напиши, что тебя интересует!"
        else:
            welcome_text = random.choice([
                f"👋 С возвращением{', ' + first_name if first_name else ''}! Подберу футбольные турниры. С чего начнём?",
                f"⚽ Привет{', ' + first_name if first_name else ''}! Ищем турнир по городу, сезону или году рождения?",
            ])
        
        await message.answer(
            welcome_text,
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Log successful activation
        await logging_client.log_message(
            contact_id=contact_id,
            telegram_user_id=user_id,
            direction="outgoing",
            message_type="text",
            text=welcome_text,
            payload={
                "action": "user_activated",
                "is_new_contact": is_new,
                "contact_id": contact_id
            },
            timestamp=message.date
        )
        
    except Exception as e:
        logger.error(f"Error processing contact for user {user_id}: {e}", exc_info=True)
        
        # Try to continue without backend (fallback mode)
        try:
            # Store basic data in FSM
            await state.update_data(
                contact_id=user_id,  # Use telegram user_id as fallback
                phone=contact.phone_number,
                first_name=contact.first_name or message.from_user.first_name
            )
            
            # Set state to ACTIVATED
            await state.set_state(UserStates.ACTIVATED)
            
            await message.answer(
                "⚠️ Произошла временная ошибка с сервером, но вы можете пользоваться ботом.\n\n"
                "🔍 Попробуйте найти турниры или задать вопрос!",
                reply_markup=ReplyKeyboardRemove()
            )
            
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            await message.answer(
                "❌ Произошла ошибка при обработке контакта. Попробуйте команду /start снова.",
                reply_markup=ReplyKeyboardRemove()
            )

@main_router.message(UserStates.NEW)
@main_router.message(UserStates.CONSENTED)
async def handle_not_activated(message: Message, state: FSMContext) -> None:
    """Handle messages from non-activated users"""
    current_state = await state.get_state()
    
    if current_state == UserStates.NEW.state:
        await message.answer(
            "Пожалуйста, сначала дайте согласие на обработку данных. Используйте команду /start"
        )
    elif current_state == UserStates.CONSENTED.state:
        await message.answer(
            "Пожалуйста, поделитесь своим контактом, нажав кнопку ниже 👇",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )

@main_router.message(UserStates.ACTIVATED, ~Command("privacy"), ~Command("delete_me"), ~Command("help"), ~Command("start"), ~Command("tournaments"), ~Command("search"), ~Command("cabinet"), ~Command("org"))
async def handle_activated_message(message: Message, state: FSMContext) -> None:
    """Handle messages from activated users (excluding commands)"""
    user_id = message.from_user.id
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    message_history = user_data.get("message_history", [])
    
    # Log incoming message
    await logging_client.log_message(
        contact_id=contact_id,
        telegram_user_id=user_id,
        direction="incoming",
        message_type="text",
        text=message.text,
        payload={},
        timestamp=message.date
    )
    
    try:
        # Quick responses for common commands
        text_lower = message.text.lower()
        
        # Быстрые ответы без вызова LLM
        
        # Приветствия
        greeting_words = ["привет", "здравствуй", "здравствуйте", "хай", "hello", "hi", "добрый день", "доброе утро", "добрый вечер"]
        if any(word in text_lower for word in greeting_words) and len(text_lower) < 30:
            response = {"text": random.choice(GREETING_RESPONSES)}
        
        # Прощания - но НЕ если есть слова поиска турниров
        elif any(word in text_lower for word in ["пока", "до свидания", "bye", "goodbye"]) and len(text_lower) < 20 and not any(w in text_lower for w in ["турнир", "покажи", "найди", "поиск"]):
            response = {"text": random.choice(GOODBYE_RESPONSES)}
        
        # Благодарности - но только если нет запроса на поиск
        elif any(word in text_lower for word in ["спасибо", "благодарю", "благодарность", "круто", "отлично", 
                          "супер", "класс", "молодец", "здорово", "прекрасно", "замечательно",
                          "thanks", "thank you", "thx"]):
            # Проверяем, есть ли в сообщении год рождения или слова поиска
            import re
            has_birth_year = bool(re.search(r'\b(200[5-9]|201[0-9]|202[0-5])\b', text_lower))
            search_words = ["поищем", "поищи", "найди", "найти", "поиск", "турнир", "вариант", "года", "год", "г.р", "покажи", "подбери"]
            has_search_intent = any(word in text_lower for word in search_words)
            
            if has_birth_year or has_search_intent:
                # Это запрос на поиск, а не благодарность - отправляем в LLM
                status_msg = await send_search_animation(message)
                try:
                    response = await llm_consultant.process_message(
                        message.text,
                        user_id=user_id,
                        contact_id=contact_id,
                        message_history=message_history
                    )
                finally:
                    try:
                        await status_msg.delete()
                    except:
                        pass
            else:
                response = {"text": random.choice(THANK_YOU_RESPONSES)}
        
        elif any(word in text_lower for word in ["турнир", "найди", "поиск", "tournament", "расскажи", "подскажи", "информация", "покажи", "все турниры", "все варианты", "подбери"]):
            # Tournament search - use LLM with history
            # Отправляем GIF-анимацию поиска
            status_msg = await send_search_animation(message)
            
            try:
                response = await llm_consultant.process_message(
                    message.text,
                    user_id=user_id,
                    contact_id=contact_id,
                    message_history=message_history
                )
            finally:
                # Удаляем анимацию поиска
                try:
                    await status_msg.delete()
                except:
                    pass
        elif any(word in text_lower for word in ["помощь", "help", "что умеешь"]):
            # Help - quick response
            response = {
                "text": "🤖 **Я умею помогать с турнирами!**\n\n"
                       "🔍 Найти турниры: \"Найди турниры 2016 г.р. в январе\"\n"
                       "📋 Показать карточку: \"Покажи турнир Zenit Cup\"\n"
                       "❓ Ответить на вопросы: \"Сколько стоит?\", \"Где проходит?\"\n\n"
                       "Просто напишите свой вопрос!"
            }
        else:
            # General query - use LLM with timeout and history
            # Отправляем GIF-анимацию поиска
            status_msg = await send_search_animation(message)
            
            try:
                response = await asyncio.wait_for(
                    llm_consultant.process_message(
                        message.text,
                        user_id=user_id,
                        contact_id=contact_id,
                        message_history=message_history
                    ),
                    timeout=20.0
                )
            finally:
                # Удаляем анимацию
                try:
                    await status_msg.delete()
                except:
                    pass
        
        # Send response with image if available
        if response.get("image_path"):
            await send_recommendation_with_image(
                message, 
                response["text"], 
                response["image_path"]
            )
        elif response.get("reply_markup"):
            await message.answer(
                response["text"],
                reply_markup=response["reply_markup"],
                parse_mode=ParseMode.HTML
            )
        else:
            # Разбиваем длинные сообщения на части (лимит Telegram ~4096 символов)
            messages_to_send = split_long_message(response["text"])
            for i, msg_part in enumerate(messages_to_send):
                # HTML parse_mode для кликабельных ссылок
                await message.answer(msg_part, parse_mode=ParseMode.HTML)
        
        # Log outgoing message
        await logging_client.log_message(
            contact_id=contact_id,
            telegram_user_id=user_id,
            direction="outgoing",
            message_type="text",
            text=response["text"],
            payload=response.get("payload", {}),
            timestamp=message.date
        )
        
        # Update message history in FSM (keep last 10 messages)
        message_history.append({"role": "user", "content": message.text})
        message_history.append({"role": "assistant", "content": response["text"]})
        # Keep only last 10 messages to avoid memory issues
        if len(message_history) > 10:
            message_history = message_history[-10:]
        await state.update_data(message_history=message_history)
        
        # Process tags in background (don't wait)
        asyncio.create_task(
            process_tags_async(message.text, contact_id, user_id, message.message_id, message.date)
        )
        
        # Generate conversation summary every 6 messages (3 exchanges)
        if contact_id and len(message_history) >= 6 and len(message_history) % 6 == 0:
            asyncio.create_task(
                generate_summary_async(message_history, contact_id, user_id)
            )
        
    except asyncio.TimeoutError:
        logger.error(f"Message processing timeout for user {user_id}")
        await message.answer(
            "⏱️ Обработка запроса занимает слишком много времени.\n\n"
            "Попробуйте:\n"
            "• Задать более простой вопрос\n"
            "• Использовать команды: /tournaments, /help\n"
            "• Написать \"найди турниры\" для поиска"
        )
    except Exception as e:
        logger.error(f"Error processing message from user {user_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке запроса.\n\n"
            "Попробуйте:\n"
            "• /tournaments - посмотреть турниры\n"
            "• /help - получить помощь\n"
            "• Написать простой вопрос"
        )

async def generate_summary_async(message_history: list, contact_id: int, user_id: int) -> None:
    """Generate conversation summary asynchronously"""
    try:
        summary = await llm_consultant.generate_conversation_summary(message_history, contact_id)
        if summary:
            logger.info(f"📝 Generated summary for contact {contact_id}: {len(summary)} chars")
    except Exception as e:
        logger.error(f"Error generating summary for user {user_id}: {e}")

async def process_tags_async(text: str, contact_id: int, user_id: int, message_id: int, timestamp) -> None:
    """Process tags asynchronously"""
    try:
        tags_result = await llm_tagger.extract_tags(text, contact_id, user_id)
        
        if tags_result.get("add") or tags_result.get("remove"):
            await backend_client.merge_contact_tags(
                contact_id=contact_id,
                add_tags=tags_result.get("add", []),
                remove_tags=tags_result.get("remove", []),
                meta={
                    "telegram_user_id": user_id,
                    "message_id": message_id,
                    "timestamp": timestamp.isoformat()
                }
            )
            
    except Exception as e:
        logger.error(f"Error processing tags for user {user_id}: {e}")

# Command handlers
@main_router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    """Handle /help command"""
    
    # Часть 1 - Основная информация
    help_text_1 = """
📘 **Помощь**

Я — бот для подбора футбольных турниров по России ⚽
Помогаю быстро найти подходящие соревнования для команды или ребёнка.

🔍 **Что я умею**
• Подбирать турниры по городу, возрасту, сезону и формату
• Находить турниры по названию
• Показывать актуальную информацию по датам, условиям и контактам
• Рекомендовать турниры, которые лучше всего подходят под ваш запрос

🗣 **Как со мной общаться**
Просто напишите запрос обычным языком. Например:
• «Турниры в Москве для 2016 года весной»
• «Найди турнир в Сочи в апреле»
• «Ищу УТС для команды 2014 г.р.»
• «Кубок Юга»

Чем точнее запрос — тем лучше результат 👍
    """
    
    # Часть 2 - Метки и дополнительная информация
    help_text_2 = """
⭐ **Что означают метки в выдаче**
• ⭐ Рекомендуемый турнир — лучший вариант под ваш запрос по мнению сервиса
• 🔝 Премиум-турнир — турнир с повышенной видимостью в поиске

🏆 **Я показываю только актуальные турниры**
Если по вашему запросу ничего не найдено:
• Попробуйте изменить город или даты
• Уточните год рождения
• Напишите запрос по-другому

📩 **Для организаторов турниров**
Если вы организуете турниры или УТС, вы можете:
• Разместить свой турнир в базе
• Получить дополнительное продвижение
• Показывать турнир заинтересованной аудитории

Используйте команду /cabinet для доступа к личному кабинету организатора.

🔐 **Конфиденциальность**
Я обрабатываю только те данные, которые необходимы для работы сервиса.
Подробная политика: /privacy
    """
    
    # Создаём клавиатуру с кнопкой кабинета
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import WebAppInfo
    builder = InlineKeyboardBuilder()
    
    # Если настроен WebApp URL - используем WebApp кнопку, иначе callback
    if config.WEBAPP_CABINET_URL:
        builder.button(
            text="📋 Личный кабинет организатора", 
            web_app=WebAppInfo(url=config.WEBAPP_CABINET_URL)
        )
    else:
        builder.button(text="📋 Личный кабинет организатора", callback_data="open_cabinet")
    
    await message.answer(help_text_1, parse_mode=ParseMode.MARKDOWN)
    await message.answer(help_text_2, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)

@main_router.message(Command("tournaments"))
async def cmd_tournaments(message: Message, state: FSMContext) -> None:
    """Handle /tournaments command"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Log command
    await logging_client.log_message(
        contact_id=contact_id,
        telegram_user_id=message.from_user.id,
        direction="incoming",
        message_type="command",
        text="/tournaments",
        payload={"command": "tournaments"},
        timestamp=message.date
    )
    
    try:
        # Get upcoming tournaments
        tournaments = await backend_client.search_tournaments(
            limit=8,
            date_from="now"
        )
        
        if not tournaments:
            await message.answer(
                "🔍 Ближайшие турниры не найдены.\n\n"
                "Попробуйте:\n"
                "• /search - интерактивный поиск\n"
                "• Написать \"найди турниры в [город]\"\n"
                "• Указать конкретные критерии"
            )
            return
        
        # Format tournaments list с иерархией (Рейтинг > Премиум > Обычные)
        text = format_tournaments_hierarchical(tournaments)
        text += "\n" + random.choice(TOURNAMENT_CHOICE_PROMPTS)
        
        # Разбиваем на несколько сообщений если текст слишком длинный
        messages_to_send = split_long_message(text)
        for msg_part in messages_to_send:
            await message.answer(msg_part)
        
        # Log outgoing message
        await logging_client.log_message(
            contact_id=contact_id,
            telegram_user_id=message.from_user.id,
            direction="outgoing",
            message_type="text",
            text=text,
            payload={"tournaments_count": len(tournaments), "messages_sent": len(messages_to_send)},
            timestamp=message.date
        )
        
    except Exception as e:
        logger.error(f"Error in /tournaments command: {e}")
        await message.answer(
            "❌ Ошибка при загрузке турниров.\n\n"
            "Попробуйте:\n"
            "• Повторить команду позже\n"
            "• Написать \"найди турниры\"\n"
            "• Использовать /help для справки"
        )

@main_router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext) -> None:
    """Handle /search command - interactive search"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Log command
    await logging_client.log_message(
        contact_id=contact_id,
        telegram_user_id=message.from_user.id,
        direction="incoming",
        message_type="command",
        text="/search",
        payload={"command": "search"},
        timestamp=message.date
    )
    
    # Текстовый поиск без кнопок
    search_text = """🔍 Поиск турниров

Напишите свой запрос, например:

• найди турниры для 2016 года
• турниры в Санкт-Петербурге весной
• зимние турниры 2015-2016
• турниры в Сочи в январе

Я найду подходящие варианты!"""
    
    await message.answer(search_text)

@main_router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    """Handle /privacy command - полная политика конфиденциальности"""
    
    # Часть 1 - Общие положения и сбор данных
    privacy_text_1 = """
🛡 **Политика конфиденциальности**
Telegram-бота по подбору футбольных турниров

**1. Общие положения**
Настоящая Политика описывает порядок сбора, хранения и использования персональных данных пользователей Бота.
Используя Бота, пользователь подтверждает согласие с условиями настоящей Политики.

**2. Какие данные мы собираем**
• Telegram ID пользователя
• Имя и никнейм в Telegram
• Номер телефона (если предоставлен добровольно)
• Сообщения и запросы, отправляемые в Бот
• Параметры интересов (город, возраст, сезон, формат)
• Технические данные (дата и время обращений)

📌 Бот НЕ запрашивает паспортные данные, банковские реквизиты или иные чувствительные данные.
    """
    
    # Часть 2 - Цели и передача данных
    privacy_text_2 = """
**3. Цели обработки данных**
• Подбор и показ релевантных футбольных турниров
• Улучшение качества работы Бота
• Персонализация ответов и рекомендаций
• Связь с пользователем в рамках сервиса
• Формирование обезличенной статистики

**4. Передача данных третьим лицам**
Мы НЕ передаём персональные данные третьим лицам, за исключением:
• Выполнения требований законодательства РФ
• Технического обеспечения работы Бота (при соблюдении конфиденциальности)

**5. Хранение и защита данных**
• Данные хранятся в защищённых системах
• Принимаются меры для защиты от утраты и несанкционированного доступа
• Данные хранятся не дольше, чем необходимо для работы Бота
    """
    
    # Часть 3 - Права и контакты
    privacy_text_3 = """
**6. Аналитика**
В Боте могут использоваться UTM-метки для анализа эффективности.
Аналитика не используется для идентификации личности вне Бота.

**7. Права пользователя**
Вы имеете право:
• Запросить информацию о своих данных
• Отозвать согласие на обработку
• Прекратить использование Бота в любой момент
• Удалить свои данные командой /delete\\_me

**8. Изменения политики**
Администрация вправе вносить изменения в Политику.
Актуальная версия всегда доступна по команде /privacy

**9. Контакты**
По вопросам обработки данных свяжитесь с администратором через Telegram.

📋 Версия: """ + config.CONSENT_VERSION
    
    # Отправляем в 3 сообщения чтобы не превысить лимит Telegram
    await message.answer(privacy_text_1, parse_mode=ParseMode.MARKDOWN)
    await message.answer(privacy_text_2, parse_mode=ParseMode.MARKDOWN)
    await message.answer(privacy_text_3, parse_mode=ParseMode.MARKDOWN)

@main_router.message(Command("delete_me"))
async def cmd_delete_me(message: Message, state: FSMContext) -> None:
    """Handle /delete_me command"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    if not contact_id:
        await message.answer("У вас нет сохраненных данных для удаления.")
        return
    
    # Create confirmation keyboard
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"delete_confirm_{contact_id}")
    builder.button(text="❌ Отмена", callback_data="delete_cancel")
    builder.adjust(2)
    
    await message.answer(
        "⚠️ **Подтверждение удаления**\n\n"
        "Вы уверены, что хотите удалить все свои данные?\n"
        "Это действие необратимо и включает:\n\n"
        "• Контактную информацию\n"
        "• Историю переписки\n"
        "• Сохраненные интересы и теги\n\n"
        "После удаления вам потребуется заново пройти регистрацию.",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@main_router.callback_query(F.data.startswith("delete_confirm_"))
async def confirm_delete(callback: CallbackQuery, state: FSMContext) -> None:
    """Confirm data deletion"""
    contact_id = int(callback.data.split("_")[-1])
    
    try:
        # Delete contact data
        await backend_client.delete_contact(contact_id)
        
        # Clear FSM state
        await state.clear()
        
        await callback.answer("Данные удалены")
        await callback.message.edit_text(
            "✅ Ваши данные успешно удалены.\n\n"
            "Для повторного использования бота используйте команду /start",
            reply_markup=None
        )
        
    except Exception as e:
        logger.error(f"Error deleting contact {contact_id}: {e}")
        await callback.answer("Ошибка при удалении данных")
        await callback.message.edit_text(
            "❌ Произошла ошибка при удалении данных. Попробуйте позже.",
            reply_markup=None
        )

@main_router.callback_query(F.data == "delete_cancel")
async def cancel_delete(callback: CallbackQuery) -> None:
    """Cancel data deletion"""
    await callback.answer("Удаление отменено")
    await callback.message.edit_text(
        "❌ Удаление данных отменено.",
        reply_markup=None
    )

# Callback handlers for main menu
@main_router.callback_query(F.data == "tournaments_upcoming")
async def show_upcoming_tournaments(callback: CallbackQuery, state: FSMContext) -> None:
    """Show upcoming tournaments"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, "tournaments_upcoming", "Просмотр ближайших турниров")
    
    try:
        # Get upcoming tournaments
        tournaments = await backend_client.search_tournaments(
            limit=8,
            date_from="now"
        )
        
        if not tournaments:
            await callback.answer("Турниры не найдены")
            await callback.message.edit_text(
                "🔍 Ближайшие турниры не найдены.\n\n"
                "Попробуйте расширить критерии поиска или воспользуйтесь командой /search",
                reply_markup=None
            )
            return
        
        # Format tournaments list с иерархией (Рейтинг > Премиум > Обычные)
        text = format_tournaments_hierarchical(tournaments)
        text += "\n" + random.choice(TOURNAMENT_CHOICE_PROMPTS)
        
        await callback.answer()
        
        # Разбиваем на несколько сообщений если текст слишком длинный
        messages_to_send = split_long_message(text)
        if len(messages_to_send) == 1:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            # Удаляем старое сообщение и отправляем новые
            try:
                await callback.message.delete()
            except:
                pass
            for msg_part in messages_to_send:
                await callback.message.answer(msg_part, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error fetching upcoming tournaments: {e}")
        await callback.answer("Ошибка загрузки турниров")

# Interactive search handlers
@main_router.callback_query(F.data == "search_interactive")
async def start_interactive_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Start interactive search"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, "search_interactive", "Открыл интерактивный поиск")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙️ По городу", callback_data="search_by_city")
    builder.button(text="📅 По датам", callback_data="search_by_date")
    builder.button(text="⚽ По возрасту", callback_data="search_by_age")
    builder.button(text="🎮 По формату", callback_data="search_by_format")
    builder.button(text="🔍 Общий поиск", callback_data="search_general")
    builder.adjust(2)
    
    await callback.answer()
    await callback.message.edit_text(
        "🔍 **Поиск турниров**\n\n"
        "Выберите критерий поиска:",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@main_router.callback_query(F.data == "search_by_city")
async def search_by_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Search by city"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, "search_by_city", "Поиск по городу")
    
    builder = InlineKeyboardBuilder()
    cities = ["Санкт-Петербург", "Москва", "Сочи", "Краснодар", "Екатеринбург", "Казань"]
    
    for city in cities:
        builder.button(text=city, callback_data=f"city_{city}")
    
    builder.button(text="🔙 Назад", callback_data="search_interactive")
    builder.adjust(2)
    
    await callback.answer()
    await callback.message.edit_text(
        "🏙️ **Поиск по городу**\n\n"
        "Выберите город или напишите название:",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@main_router.callback_query(F.data == "search_by_age")
async def search_by_age(callback: CallbackQuery, state: FSMContext) -> None:
    """Search by age"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, "search_by_age", "Поиск по возрасту")
    
    builder = InlineKeyboardBuilder()
    ages = ["2010", "2011", "2012", "2013", "2014", "2015", "2016", "2017"]
    
    for age in ages:
        builder.button(text=f"{age} г.р.", callback_data=f"age_{age}")
    
    builder.button(text="🔙 Назад", callback_data="search_interactive")
    builder.adjust(4)
    
    await callback.answer()
    await callback.message.edit_text(
        "⚽ **Поиск по возрасту**\n\n"
        "Выберите год рождения:",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@main_router.callback_query(F.data == "search_by_date")
async def search_by_date(callback: CallbackQuery, state: FSMContext) -> None:
    """Search by date"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, "search_by_date", "Поиск по датам")
    
    builder = InlineKeyboardBuilder()
    periods = [
        ("Январь 2026", "2026-01"),
        ("Февраль 2026", "2026-02"),
        ("Март 2026", "2026-03"),
        ("Зима", "winter"),
        ("Весна", "spring"),
        ("Ближайшие", "now")
    ]
    
    for period_name, period_code in periods:
        builder.button(text=period_name, callback_data=f"date_{period_code}")
    
    builder.button(text="🔙 Назад", callback_data="search_interactive")
    builder.adjust(2)
    
    await callback.answer()
    await callback.message.edit_text(
        "📅 **Поиск по датам**\n\n"
        "Выберите период:",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@main_router.callback_query(F.data == "search_by_format")
async def search_by_format(callback: CallbackQuery, state: FSMContext) -> None:
    """Search by format"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, "search_by_format", "Поиск по формату")
    
    builder = InlineKeyboardBuilder()
    formats = [
        ("5x5", "5x5"),
        ("8x8", "8x8"), 
        ("11x11", "11x11"),
        ("Футзал", "futsal")
    ]
    
    for format_name, format_code in formats:
        builder.button(text=format_name, callback_data=f"format_{format_code}")
    
    builder.button(text="🔙 Назад", callback_data="search_interactive")
    builder.adjust(2)
    
    await callback.answer()
    await callback.message.edit_text(
        "🎮 **Поиск по формату**\n\n"
        "Выберите формат игры:",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

# Search result handlers
@main_router.callback_query(F.data.startswith("city_"))
async def handle_city_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle city search"""
    city = callback.data.split("_", 1)[1]
    await perform_search(callback, state, city=city)

@main_router.callback_query(F.data.startswith("age_"))
async def handle_age_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle age search"""
    age = callback.data.split("_", 1)[1]
    await perform_search(callback, state, age=age)

@main_router.callback_query(F.data.startswith("date_"))
async def handle_date_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle date search"""
    date_period = callback.data.split("_", 1)[1]
    
    if date_period == "now":
        await perform_search(callback, state, date_from="now")
    elif date_period in ["winter", "spring"]:
        await perform_search(callback, state, q=date_period)
    else:
        await perform_search(callback, state, date_from=date_period)

@main_router.callback_query(F.data.startswith("format_"))
async def handle_format_search(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle format search"""
    format_type = callback.data.split("_", 1)[1]
    await perform_search(callback, state, format=format_type)

async def perform_search(
    callback: CallbackQuery, 
    state: FSMContext, 
    **search_params
) -> None:
    """Perform tournament search with given parameters"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    
    try:
        # Perform search
        tournaments = await backend_client.search_tournaments(
            limit=8,
            **search_params
        )
        
        if not tournaments:
            await callback.answer("Турниры не найдены")
            await callback.message.edit_text(
                "🔍 По вашим критериям турниры не найдены.\n\n"
                "Попробуйте:\n"
                "• Изменить критерии поиска\n"
                "• Расширить диапазон дат\n"
                "• Написать общий запрос",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔙 Новый поиск", callback_data="search_interactive")
                ]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Format results
        search_desc = []
        if search_params.get("city"):
            search_desc.append(f"🏙️ {search_params['city']}")
        if search_params.get("age"):
            search_desc.append(f"⚽ {search_params['age']} г.р.")
        if search_params.get("format"):
            search_desc.append(f"🎮 {search_params['format']}")
        if search_params.get("date_from"):
            search_desc.append(f"📅 от {search_params['date_from']}")
        
        text = f"🔍 Результаты поиска\n"
        if search_desc:
            text += f"Критерии: {', '.join(search_desc)}\n\n"
        
        # Format tournaments list с иерархией (Рейтинг > Премиум > Обычные)
        text += format_tournaments_hierarchical(tournaments)
        text += "\n" + random.choice(TOURNAMENT_CHOICE_PROMPTS)
        
        await callback.answer()
        
        # Разбиваем на несколько сообщений если текст слишком длинный
        messages_to_send = split_long_message(text)
        if len(messages_to_send) == 1:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
        else:
            # Удаляем старое сообщение и отправляем новые
            try:
                await callback.message.delete()
            except:
                pass
            for msg_part in messages_to_send:
                await callback.message.answer(msg_part, parse_mode=ParseMode.HTML)
        
        # Log search
        await logging_client.log_message(
            contact_id=contact_id,
            telegram_user_id=callback.from_user.id,
            direction="outgoing",
            message_type="search_results",
            text=text,
            payload={
                "search_params": search_params,
                "results_count": len(tournaments),
                "messages_sent": len(messages_to_send)
            },
            timestamp=callback.message.date
        )
        
    except Exception as e:
        logger.error(f"Error performing search: {e}")
        await callback.answer("Ошибка поиска")
        await callback.message.edit_text(
            "❌ Произошла ошибка при поиске турниров.\n\n"
            "Попробуйте написать запрос текстом, например:\n"
            "• найди турниры для 2015 года\n"
            "• турниры весной в Сочи",
            parse_mode=None
        )

@main_router.callback_query(F.data.startswith("tournament_card_"))
async def show_tournament_card(callback: CallbackQuery, state: FSMContext) -> None:
    """Show tournament card"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    tournament_id = int(callback.data.split("_")[-1])
    
    # Логируем нажатие кнопки
    await log_callback_action(callback, contact_id, f"tournament_card_{tournament_id}", f"Просмотр карточки турнира #{tournament_id}")
    
    # Логируем клик для аналитики
    if analytics_service:
        try:
            await analytics_service.log_click(tournament_id, "bot_search")
            logger.debug(f"Logged click for tournament {tournament_id}")
        except Exception as e:
            logger.warning(f"Failed to log click: {e}")
    
    try:
        # Get tournament card
        card_data = await backend_client.get_tournament_card(tournament_id)
        
        if card_data["type"] == "url":
            # Отправляем ссылку без кнопок
            await callback.answer()
            await callback.message.edit_text(
                f"🏆 Карточка турнира\n\n"
                f"🔗 Подробнее: {card_data['url']}",
                parse_mode=None
            )
        elif card_data["type"] == "data" and card_data.get("card"):
            # Форматируем данные турнира
            tournament = card_data["card"]
            text = format_tournament_full(tournament)
            await callback.answer()
            await callback.message.edit_text(text, parse_mode=None)
        else:
            # Handle text or other formats
            await callback.answer()
            await callback.message.edit_text(
                card_data.get("text", "Карточка турнира недоступна"),
                parse_mode=None
            )
            
    except Exception as e:
        logger.error(f"Error fetching tournament card {tournament_id}: {e}")
        await callback.answer("Ошибка загрузки карточки")


@main_router.callback_query(F.data.startswith("open_tournament_"))
async def open_tournament_link(callback: CallbackQuery, state: FSMContext) -> None:
    """Open tournament link and log click for analytics"""
    user_data = await state.get_data()
    contact_id = user_data.get("contact_id")
    tournament_id = int(callback.data.split("_")[-1])
    
    # Логируем клик для аналитики
    if analytics_service:
        try:
            await analytics_service.log_click(tournament_id, "bot_search")
            logger.info(f"📊 Logged click for tournament {tournament_id} from bot")
        except Exception as e:
            logger.warning(f"Failed to log click: {e}")
    
    # Логируем действие
    await log_callback_action(callback, contact_id, f"open_tournament_{tournament_id}", f"Открытие ссылки на турнир #{tournament_id}")
    
    # Получаем данные турнира для ссылки
    try:
        tournament = await backend_client.get_tournament(tournament_id)
        teletype_url = tournament.get('teletype_url') if tournament else None
        
        if teletype_url:
            link = teletype_url
        else:
            link = f"http://127.0.0.1:8000/tournaments/{tournament_id}"
        
        await callback.answer()
        await callback.message.answer(
            f"🔗 Ссылка на турнир:\n{link}\n\n"
            f"Нажмите на ссылку для просмотра подробной информации."
        )
    except Exception as e:
        logger.error(f"Error getting tournament link {tournament_id}: {e}")
        await callback.answer("Ошибка получения ссылки")


async def main() -> None:
    """Main function to run the bot"""
    # Initialize Bot instance with default bot properties
    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Initialize Dispatcher with memory storage for FSM
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Include cabinet router FIRST (личный кабинет организатора)
    # Важно: cabinet_router должен быть зарегистрирован до main_router,
    # чтобы команды /cabinet и /org обрабатывались правильно
    from cabinet_handlers import cabinet_router
    dp.include_router(cabinet_router)
    
    # Include premium router
    from premium_handlers import premium_router
    dp.include_router(premium_router)
    
    # Include main router
    dp.include_router(main_router)
    
    # Set bot commands
    await bot.set_my_commands([
        {"command": "start", "description": "Начать работу с ботом"},
        {"command": "help", "description": "Помощь"},
        {"command": "cabinet", "description": "Личный кабинет организатора"},
        {"command": "privacy", "description": "Политика конфиденциальности"},
        {"command": "delete_me", "description": "Удалить мои данные"},
    ])
    
    logger.info("Bot starting...")
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())