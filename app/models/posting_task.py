"""
Posting Task Model - модели для автопостинга в Telegram-каналы
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class PostingStatus(str, Enum):
    """Статусы задачи постинга"""
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # Уже отправлено в этом часовом окне


class ChannelStatus(str, Enum):
    """Статусы канала"""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    NO_ACCESS = "NO_ACCESS"  # Нет прав на публикацию
    BANNED = "BANNED"  # Забанен


class AutopostChannel(BaseModel):
    """Канал для автопостинга"""
    
    id: Optional[int] = None
    
    # Telegram данные
    tg_chat_id: int  # ID чата/канала в Telegram
    tg_username: Optional[str] = None  # @username канала
    title: str  # Название канала
    
    # Статус
    is_active: bool = True
    can_post: bool = True  # Есть ли права на публикацию
    status: ChannelStatus = ChannelStatus.ACTIVE
    
    # Ограничения
    rate_limit_seconds: int = 2  # Задержка между постами
    max_posts_per_hour: int = 1  # Максимум постов в час
    
    # Статистика
    last_post_at: Optional[datetime] = None
    total_posts: int = 0
    successful_posts: int = 0
    failed_posts: int = 0
    
    # Метаданные
    added_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    notes: Optional[str] = None


class AutopostMessage(BaseModel):
    """Сообщение для автопостинга"""
    
    id: Optional[int] = None
    
    # Контент
    message_text: str  # Текст объявления
    message_hash: Optional[str] = None  # Хэш для дедупликации
    
    # Настройки
    schedule_type: str = "HOURLY"  # HOURLY/DAILY/MANUAL
    is_active: bool = True
    
    # Deep-link настройки
    include_button: bool = True  # Добавлять inline-кнопку
    button_text: str = "👉 Написать боту"
    bot_username: Optional[str] = None  # Для формирования deep-link
    
    # Метаданные
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PostingBatch(BaseModel):
    """Пакет задач постинга (создаётся каждый час)"""
    
    id: Optional[int] = None
    
    # Связи
    message_id: int  # ID сообщения для постинга
    
    # Статус
    total_channels: int = 0
    sent_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    
    # Время
    scheduled_for: datetime  # Запланированное время
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.now)


class PostingTask(BaseModel):
    """Задача постинга в конкретный канал"""
    
    id: Optional[int] = None
    
    # Связи
    batch_id: int  # ID пакета
    channel_id: int  # ID канала
    message_id: int  # ID сообщения
    
    # Статус
    status: PostingStatus = PostingStatus.PENDING
    attempt_count: int = 0
    max_attempts: int = 3
    
    # Результат
    sent_message_id: Optional[int] = None  # ID отправленного сообщения в Telegram
    last_error: Optional[str] = None
    retry_after: Optional[int] = None  # Секунды до повтора (при 429)
    
    # Время
    scheduled_for: datetime
    sent_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PostingLog(BaseModel):
    """Лог попытки постинга"""
    
    id: Optional[int] = None
    task_id: int
    
    # Результат
    success: bool
    error_code: Optional[str] = None  # 403, 400, 429, timeout
    error_message: Optional[str] = None
    retry_after: Optional[int] = None
    
    # Метаданные
    attempt_number: int
    created_at: datetime = Field(default_factory=datetime.now)
