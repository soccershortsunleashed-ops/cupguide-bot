from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Contact(BaseModel):
    id: Optional[int] = None
    name: str
    phone: str
    group: str = "Общая"
    avatar_url: Optional[str] = None
    whatsapp_name: Optional[str] = None
    whatsapp_id: Optional[str] = None  # WhatsApp ID (например, "214237649621159@c.us" или "79095981637@c.us")
    # Дополнительная информация из Green API
    whatsapp_email: Optional[str] = None  # Email контакта (для бизнес-аккаунтов)
    whatsapp_category: Optional[str] = None  # Категория бизнеса
    whatsapp_description: Optional[str] = None  # Описание бизнеса/контакта
    whatsapp_is_business: Optional[bool] = None  # Является ли бизнес-аккаунтом
    whatsapp_last_seen: Optional[datetime] = None  # Последний раз онлайн
    whatsapp_products: Optional[str] = None  # JSON строка со списком продуктов (для бизнес-аккаунтов)
    whatsapp_is_registered: Optional[bool] = None  # Зарегистрирован ли номер в WhatsApp
    raw_text: Optional[str] = None
    created_at: datetime = datetime.now()
    last_sync_at: Optional[datetime] = None
    extracted_info: Optional[str] = None  # Обработанная структурированная информация о контакте (редактируется вручную)
    draft_info: Optional[str] = None  # Черновик информации - сырые данные из анализа сообщений
    analyzed_message_ids: Optional[List[str]] = None  # Список ID сообщений, которые уже были проанализированы
    
    # Telegram Bot fields
    telegram_user_id: Optional[int] = None  # Telegram user ID
    telegram_username: Optional[str] = None  # Telegram username
    consent_version: Optional[str] = None  # Version of consent given
    consent_given_at: Optional[datetime] = None  # When consent was given
    tags: Optional[List[dict]] = None  # User interest tags from LLM analysis

