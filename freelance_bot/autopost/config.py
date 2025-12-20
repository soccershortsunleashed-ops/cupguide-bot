"""
Конфигурация автопостинга
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env из корня проекта
ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

# Telegram MTProto API (для личного аккаунта)
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# Бот для ссылки в объявлении
BOT_USERNAME = "LeadRazor_bot"

# Настройки постинга
POST_DELAY_SECONDS = 40  # Задержка между постами (безопасно)
MAX_POSTS_PER_HOUR = 35  # Максимум постов в час
QUIET_HOURS_START = 2   # Не постить с 02:00
QUIET_HOURS_END = 6     # до 06:00 (сужено для тестирования)

# Путь к сессии Telethon
SESSION_NAME = "freelance_poster"
SESSION_PATH = os.path.join(os.path.dirname(__file__), SESSION_NAME)
