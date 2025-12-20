"""
Lead Model - модель лида для фриланс-воронки
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class LeadStatus(str, Enum):
    """Статусы лида"""
    NEW = "NEW"
    IN_REVIEW = "IN_REVIEW"
    CONTACTED = "CONTACTED"
    WON = "WON"
    LOST = "LOST"
    TRASHED = "TRASHED"
    NURTURE = "NURTURE"  # Для TRASH_SOFT - "Я уточню и вернусь"


class LeadGrade(str, Enum):
    """Грейды лида (A/B/TRASH)"""
    A = "A"
    B = "B"
    TRASH = "TRASH"


class LeadRoute(str, Enum):
    """Маршруты воронки"""
    A_FLOW = "A_FLOW"
    B_FLOW = "B_FLOW"
    TRASH_FLOW = "TRASH_FLOW"


class SourceType(str, Enum):
    """Типы источников лида"""
    AUTOPOST = "autopost"
    DIRECT = "direct"
    REFERRAL = "referral"
    KEYWORD = "keyword"  # Вход по слову "БОТ"


class LeadGoal(str, Enum):
    """Цели лида (Q1)"""
    SALES = "sales"  # 💰 Продажи
    LEADS = "leads"  # 📥 Заявки
    BASE = "base"  # 🧲 Лиды/база
    SUPPORT = "support"  # 🧰 Поддержка/сервис
    JUST_BOT = "just_bot"  # 🤷 Просто "чтоб был бот"


class LeadPain(str, Enum):
    """Боли лида (Q2)"""
    TRAFFIC = "traffic"  # 🚪 Вход/трафик
    DIALOG = "dialog"  # 💬 Диалог есть — результата нет
    PAYMENT = "payment"  # 💳 До оплаты не доходят
    INTEGRATION = "integration"  # 🔁 Нужна автоматизация/интеграции
    CHAOS = "chaos"  # 🧨 Всё в хаосе


class LeadContext(str, Enum):
    """Контекст лида (Q3)"""
    FROM_SCRATCH = "from_scratch"  # 🆕 С нуля
    AFTER_CONSTRUCTOR = "after_constructor"  # 🧱 Был конструктор — надо нормально
    HAS_BOT = "has_bot"  # 🤖 Есть бот — нужно переписать/усилить
    HAS_CRM = "has_crm"  # 🧩 Есть CRM/сервисы — надо связать


class Lead(BaseModel):
    """Модель лида для фриланс-воронки"""
    
    id: Optional[int] = None
    
    # Telegram данные
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Источник
    source_type: SourceType = SourceType.DIRECT
    source_channel_id: Optional[int] = None
    source_post_id: Optional[int] = None
    
    # Скрининг (Q1/Q2/Q3)
    goal: Optional[str] = None  # LeadGoal value
    pain: Optional[str] = None  # LeadPain value
    context: Optional[str] = None  # LeadContext value
    niche_text: Optional[str] = None  # Ниша + продукт + чек
    
    # Детерминированный скоринг
    deterministic_score: Optional[int] = None
    deterministic_grade: Optional[str] = None  # LeadGrade value
    
    # LLM скоринг
    llm_grade: Optional[str] = None  # LeadGrade value (A/B/TRASH)
    llm_score: Optional[int] = None  # 0-100
    llm_reason: Optional[str] = None  # Краткое объяснение
    llm_json: Optional[str] = None  # Полный JSON ответ LLM
    llm_must_have: Optional[List[str]] = None  # Требования (до 6 пунктов)
    llm_next_questions: Optional[List[str]] = None  # Вопросы (до 4)
    llm_bot_reply: Optional[str] = None  # Сгенерированный ответ бота
    
    # Маршрутизация
    final_route: Optional[str] = None  # LeadRoute value
    status: LeadStatus = LeadStatus.NEW
    priority: str = "MEDIUM"  # HIGH/MEDIUM/LOW
    
    # Контактные данные (форма заявки)
    contact_phone: Optional[str] = None
    contact_link: Optional[str] = None  # Ссылка на проект/сайт/канал
    contact_preferred: Optional[str] = None  # @username / телефон
    bot_platform: Optional[str] = None  # TG/сайт/везде
    start_window: Optional[str] = None  # Когда запуск
    
    # Ручная обработка
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    owner_action: Optional[str] = None  # Действие владельца
    
    # FSM состояние
    current_fsm_state: Optional[str] = None
    last_bot_message_id: Optional[int] = None
    
    # Метаданные
    started_at: datetime = Field(default_factory=datetime.now)
    last_seen_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Связь с контактом
    contact_id: Optional[int] = None  # ID в contacts.json
    
    class Config:
        use_enum_values = True


class LeadEvent(BaseModel):
    """Событие лида для аналитики"""
    
    id: Optional[int] = None
    lead_id: int
    event_type: str  # bot_started, keyword_entry, screen_answered, etc.
    payload: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.now)


class LeadConversation(BaseModel):
    """Сообщение в диалоге с лидом"""
    
    id: Optional[int] = None
    lead_id: int
    message_id: Optional[int] = None  # Telegram message_id
    direction: str  # IN/OUT
    text: str
    button_data: Optional[str] = None  # Данные нажатой кнопки
    created_at: datetime = Field(default_factory=datetime.now)


class LeadApplication(BaseModel):
    """Заявка от лида"""
    
    id: Optional[int] = None
    lead_id: int
    
    # Данные заявки
    contact_preferred: str  # @username / телефон
    project_link: Optional[str] = None
    bot_platform: str  # TG/сайт/везде
    start_window: Optional[str] = None
    
    # Мини-бриф (для A_FLOW)
    traffic_source: Optional[str] = None  # Канал входа
    payment_crm: Optional[str] = None  # Оплата/CRM
    steps_count: Optional[str] = None  # Сколько шагов до результата
    
    # Для B_FLOW
    main_product: Optional[str] = None  # Один главный продукт
    main_objection: Optional[str] = None  # Самое частое возражение
    final_goal: Optional[str] = None  # Заявка или оплата
    selected_package: Optional[str] = None  # Прототип / Боевой
    
    # Статус
    status: str = "NEW"  # NEW/PROCESSED/PAID
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
