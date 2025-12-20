"""
Конфигурация фриланс-бота
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class FreelanceBotConfig:
    """Конфигурация бота"""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("FREELANCE_BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("FREELANCE_BOT_USERNAME", "freelance_dev_bot")
    
    # Owner для уведомлений
    OWNER_TELEGRAM_ID: int = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
    OWNER_USERNAME: str = os.getenv("OWNER_USERNAME", "")
    
    # LLM (MegaLLM) - используем тот же ключ что и в telegram_bot
    MEGALLM_API_KEY: str = os.getenv("MEGALLM_API_KEY", "sk-mega-799f59581da118a313a37622c51bcbc22a5067beedf050aa20444c56ab5f6a79")
    MEGALLM_BASE_URL: str = os.getenv("MEGALLM_BASE_URL", "https://ai.megallm.io/v1")
    LLM_MODEL: str = "llama3-8b-instruct"
    LLM_TIMEOUT: int = 45
    
    # Backend API
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    
    # Автопостинг
    AUTOPOST_INTERVAL_HOURS: int = 1
    AUTOPOST_DELAY_BETWEEN_CHANNELS: float = 2.0  # секунды
    AUTOPOST_MAX_RETRIES: int = 3
    
    # FSM
    FSM_TTL_DAYS: int = 30  # Время жизни состояния
    
    # Уведомления
    NOTIFY_ON_A_LEAD: bool = True
    NOTIFY_ON_B_LEAD: bool = True
    NOTIFY_ON_TRASH: bool = False
    QUIET_HOURS_START: int = 23  # Тишина с 23:00
    QUIET_HOURS_END: int = 8  # до 08:00
    
    # Группа контактов
    FREELANCE_CONTACT_GROUP: str = "Фриланс"
    FREELANCE_CONTACT_GROUP_KEY: str = "freelance"
    
    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = FreelanceBotConfig()
