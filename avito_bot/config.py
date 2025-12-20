"""
Конфигурация Avito Bot
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AvitoConfig:
    """Конфигурация Avito бота"""
    
    # Avito API
    AVITO_CLIENT_ID: str = os.getenv("AVITO_CLIENT_ID", "")
    AVITO_CLIENT_SECRET: str = os.getenv("AVITO_CLIENT_SECRET", "")
    AVITO_USER_ID: str = os.getenv("AVITO_USER_ID", "")
    
    # MegaLLM
    MEGALLM_API_KEY: str = os.getenv("MEGALLM_API_KEY", "")
    MEGALLM_BASE_URL: str = os.getenv("MEGALLM_BASE_URL", "https://api.mega-llm.ru/v1")
    MEGALLM_MODEL: str = os.getenv("MEGALLM_MODEL", "gpt-4o-mini")
    
    # Timeouts
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))
    AVITO_POLLING_INTERVAL: int = int(os.getenv("AVITO_POLLING_INTERVAL", "10"))
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # CRM
    CRM_API_URL: str = os.getenv("CRM_API_URL", "http://localhost:8000/api/leads")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Webhook
    WEBHOOK_SECRET: str = os.getenv("AVITO_WEBHOOK_SECRET", "")
    
    @property
    def is_configured(self) -> bool:
        """Проверка наличия обязательных настроек"""
        return bool(
            self.AVITO_CLIENT_ID and 
            self.AVITO_CLIENT_SECRET and
            self.MEGALLM_API_KEY
        )


config = AvitoConfig()
