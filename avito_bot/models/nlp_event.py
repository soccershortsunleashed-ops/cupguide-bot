"""
NLPEvent - результат NLP-анализа сообщения
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class Intent(str, Enum):
    """Интенты из ТЗ раздел 8.1"""
    GENERAL_INTEREST = "general_interest"  # "расскажите подробнее"
    PRICING = "pricing"  # "сколько стоит"
    SERVICE_QUESTION = "service_question"  # вопрос по услуге
    COMPARISON = "comparison"  # "бот за 2к vs продающий"
    OBJECTION = "objection"  # "дорого", "справитесь?", "пример"
    REQUEST_EXAMPLES = "request_examples"  # "покажите кейс/портфолио"
    HANDOFF_REQUEST = "handoff_request"  # "давайте созвон/оформим"
    OFFTOPIC = "offtopic"
    ABUSE = "abuse"


class ScoreABC(str, Enum):
    """Скоринг A/B/C"""
    A = "A"  # Горячий
    B = "B"  # Тёплый
    C = "C"  # Холодный


class NextAction(str, Enum):
    """Следующее действие бота"""
    ASK_QUALIFYING_QUESTIONS = "ask_qualifying_questions"
    GIVE_PRICE_FROM_AND_EXPLAIN = "give_price_from_and_explain"
    CREATE_CRM_LEAD = "create_crm_lead"
    HANDOFF_MANAGER = "handoff_manager"
    REQUEST_BACKUP_CONTACT = "request_backup_contact"
    CLOSE = "close"


class ServiceGroup(str, Enum):
    """Группы услуг"""
    PROGRAMMING = "Программирование"
    CRM_SYSTEMS = "CRM-системы"
    UNKNOWN = "unknown"


class NLPEvent(BaseModel):
    """Результат NLP-анализа сообщения"""
    
    id: Optional[int] = None
    
    # Связь с сообщением
    message_id: int
    
    # Результаты анализа
    intent: Intent
    score_abc: ScoreABC
    
    # Слоты (из ТЗ раздел 8.2)
    slots_json: Optional[Dict[str, Any]] = Field(default_factory=lambda: {
        "service_group": "unknown",
        "service_id": None,
        "deadline": None,
        "integrations": [],
        "budget_hint": None,
        "scope_hint": None  # low/medium/high
    })
    
    # Действие
    next_action: NextAction
    
    # Сгенерированный ответ
    reply: Optional[str] = None
    
    # Payload для лида (если next_action = create_crm_lead)
    lead_payload: Optional[Dict[str, Any]] = None
    
    # Метаданные LLM
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    raw_response: Optional[str] = None
    
    # Метаданные
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
