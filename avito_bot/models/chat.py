"""
AvitoChat - модель диалога с клиентом на Авито
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ChatState(str, Enum):
    """Состояния диалога"""
    NEW = "new"
    QUALIFYING = "qualifying"  # Сбор вводных
    ACTIVE = "active"  # Активный диалог
    LEAD_CREATED = "lead_created"  # Лид создан в CRM
    CLOSED = "closed"  # Диалог закрыт


class AvitoChat(BaseModel):
    """Модель диалога Авито"""
    
    id: Optional[int] = None
    
    # Идентификаторы Авито
    chat_id: str  # ID чата в Авито
    user_id: str  # ID пользователя Авито
    item_id: Optional[str] = None  # ID объявления
    
    # Состояние диалога
    state: ChatState = ChatState.NEW
    state_json: Optional[Dict[str, Any]] = None  # Дополнительные данные состояния
    
    # Собранные слоты
    slots: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    # Скоринг
    current_score: Optional[str] = None  # A/B/C
    
    # Последние сообщения (для дедупликации)
    last_in_msg_id: Optional[str] = None
    last_out_msg_id: Optional[str] = None
    
    # Связь с CRM
    crm_lead_id: Optional[int] = None
    
    # Метаданные
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
