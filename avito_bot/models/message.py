"""
AvitoMessage - модель сообщения в диалоге
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class MessageDirection(str, Enum):
    """Направление сообщения"""
    IN = "in"  # Входящее от клиента
    OUT = "out"  # Исходящее от бота


class AvitoMessage(BaseModel):
    """Модель сообщения Авито"""
    
    id: Optional[int] = None
    
    # Связь с чатом
    chat_id: str  # ID чата в Авито
    
    # Данные сообщения
    direction: MessageDirection
    text: str
    
    # Идентификаторы
    platform_message_id: Optional[str] = None  # ID сообщения в Авито
    
    # Сырые данные (для отладки)
    raw_json: Optional[Dict[str, Any]] = None
    
    # Метаданные
    ts: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
