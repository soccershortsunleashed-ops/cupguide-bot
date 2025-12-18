"""
Configuration for Telegram Bot
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings

class BotConfig(BaseSettings):
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str
    
    # Backend API
    BACKEND_URL: str = "http://127.0.0.1:8000"
    
    # WebApp Cabinet URL (for Telegram Mini App)
    WEBAPP_CABINET_URL: Optional[str] = None
    
    # MegaLLM
    MEGALLM_API_KEY: str
    MEGALLM_BASE_URL: str = "https://ai.megallm.io/v1"
    
    # Consent
    CONSENT_VERSION: str = "1.1"
    CONSENT_TEXT: str = """
🛡 **Политика конфиденциальности**

Используя Бота, вы соглашаетесь на обработку минимального набора данных:
• Telegram ID и имя
• Сообщения и запросы
• Параметры поиска (город, возраст, сезон)

Данные используются исключительно для подбора турниров и улучшения сервиса.

Мы **не передаём** данные третьим лицам и соблюдаем конфиденциальность.

📄 Полная версия: /privacy

Согласны ли вы на обработку персональных данных?
    """
    
    # Redis (optional)
    REDIS_URL: Optional[str] = None
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env

# Global config instance
config = BotConfig()