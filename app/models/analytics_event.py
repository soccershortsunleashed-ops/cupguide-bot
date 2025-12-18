"""
Модель события аналитики для личного кабинета организатора.
Используется для логирования показов (impressions) и кликов (clicks) по турнирам.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class AnalyticsEvent(BaseModel):
    """
    Событие аналитики турнира.
    
    Типы событий:
    - impression: показ турнира в выдаче бота
    - click: переход по ссылке на карточку турнира
    """
    id: Optional[int] = Field(None, description="Уникальный идентификатор события")
    event_type: Literal["impression", "click"] = Field(..., description="Тип события")
    tournament_id: int = Field(..., description="ID турнира")
    
    # Контекст показа (для impression)
    context: Optional[str] = Field(
        None, 
        description="Контекст показа: search, tournaments_command"
    )
    
    # Источник клика (для click)
    source: Optional[str] = Field(
        None, 
        description="Источник клика: bot, channel, mailing"
    )
    
    # UTM-параметры (для click)
    utm_source: Optional[str] = Field(None, description="UTM source параметр")
    utm_medium: Optional[str] = Field(None, description="UTM medium параметр")
    utm_campaign: Optional[str] = Field(None, description="UTM campaign параметр")
    
    # Временная метка
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, 
        description="Время события"
    )
    
    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()}
    }
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для сериализации"""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "tournament_id": self.tournament_id,
            "context": self.context,
            "source": self.source,
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "utm_campaign": self.utm_campaign,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsEvent":
        """Создание из словаря (десериализация)"""
        if data.get("timestamp") and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
