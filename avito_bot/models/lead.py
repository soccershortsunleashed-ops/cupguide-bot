"""
AvitoLead - модель лида для CRM
Минимальный payload из ТЗ раздел 9
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class LeadStatus(str, Enum):
    """Статусы лида"""
    PENDING = "pending"  # Ожидает создания в CRM
    CREATED = "created"  # Создан в CRM
    FAILED = "failed"  # Ошибка создания
    DUPLICATE = "duplicate"  # Дубликат


class AvitoLead(BaseModel):
    """Модель лида Авито для CRM
    
    Минимальный payload (из ТЗ раздел 9):
    - service_group
    - service_id (если есть)
    - deadline (если есть)
    - integrations
    - summary (1–2 предложения)
    - score_abc (A/B/C)
    - comment (подсказка владельцу)
    """
    
    id: Optional[int] = None
    
    # Связь с чатом
    chat_id: str  # ID чата в Авито
    
    # ID лида в CRM (после создания)
    crm_lead_id: Optional[int] = None
    
    # Payload для CRM
    payload_json: dict = Field(default_factory=lambda: {
        "service_group": None,
        "service_id": None,
        "deadline": None,
        "integrations": [],
        "summary": None,
        "score_abc": None,
        "comment": None
    })
    
    # Источник
    source: str = "avito"
    item_id: Optional[str] = None  # ID объявления
    
    # Статус
    status: LeadStatus = LeadStatus.PENDING
    error_text: Optional[str] = None
    
    # Метаданные
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


class LeadPayload(BaseModel):
    """Структура payload для создания лида в CRM"""
    
    service_group: Optional[str] = None  # Программирование / CRM-системы
    service_id: Optional[str] = None  # ID конкретной услуги
    deadline: Optional[str] = None  # Срок (если есть)
    integrations: List[str] = Field(default_factory=list)  # Список интеграций
    summary: str  # 1-2 предложения: что нужно клиенту
    score_abc: str  # A/B/C
    comment: Optional[str] = None  # Подсказка владельцу
    
    # Дополнительные поля
    source: str = "avito"
    chat_id: str
    item_id: Optional[str] = None
