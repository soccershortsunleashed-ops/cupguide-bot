"""
Модели для промо-кампаний (нативные упоминания) в личном кабинете организатора.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class ScheduledPost(BaseModel):
    """
    Запланированный пост в рамках нативной кампании.
    """
    date: str = Field(..., description="Дата публикации (YYYY-MM-DD)")
    status: Literal["pending", "done"] = Field(
        "pending", 
        description="Статус поста: pending (ожидает), done (опубликован)"
    )
    post_url: Optional[str] = Field(
        None, 
        description="URL опубликованного поста"
    )
    
    def to_dict(self) -> dict:
        """Преобразование в словарь"""
        return {
            "date": self.date,
            "status": self.status,
            "post_url": self.post_url
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledPost":
        """Создание из словаря"""
        return cls(**data)


class PromoCampaign(BaseModel):
    """
    Промо-кампания для турнира.
    
    Типы кампаний:
    - native_3: пакет из 3 нативных упоминаний
    """
    id: Optional[int] = Field(None, description="Уникальный идентификатор кампании")
    tournament_id: int = Field(..., description="ID турнира")
    type: Literal["native_3"] = Field(
        "native_3", 
        description="Тип кампании"
    )
    status: Literal["active", "completed", "cancelled"] = Field(
        "active", 
        description="Статус кампании"
    )
    scheduled_posts: List[ScheduledPost] = Field(
        default_factory=list, 
        description="Список запланированных постов"
    )
    done_count: int = Field(
        0, 
        description="Количество выполненных упоминаний"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, 
        description="Дата создания кампании"
    )
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для сериализации"""
        return {
            "id": self.id,
            "tournament_id": self.tournament_id,
            "type": self.type,
            "status": self.status,
            "scheduled_posts": [post.to_dict() for post in self.scheduled_posts],
            "done_count": self.done_count,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PromoCampaign":
        """Создание из словаря (десериализация)"""
        if data.get("created_at") and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        
        if data.get("scheduled_posts"):
            data["scheduled_posts"] = [
                ScheduledPost.from_dict(post) if isinstance(post, dict) else post
                for post in data["scheduled_posts"]
            ]
        
        return cls(**data)
    
    def calculate_done_count(self) -> int:
        """Вычисляет количество выполненных постов"""
        return sum(1 for post in self.scheduled_posts if post.status == "done")
    
    def update_done_count(self) -> None:
        """Обновляет done_count на основе статусов постов"""
        self.done_count = self.calculate_done_count()
        
        # Автоматически завершаем кампанию если все посты выполнены
        if self.type == "native_3" and self.done_count >= 3:
            self.status = "completed"
    
    @property
    def progress_display(self) -> str:
        """Отображение прогресса для UI: '1/3', '2/3', '3/3'"""
        total = 3 if self.type == "native_3" else len(self.scheduled_posts)
        return f"{self.done_count}/{total}"
    
    @property
    def is_completed(self) -> bool:
        """Проверка завершённости кампании"""
        return self.status == "completed" or (
            self.type == "native_3" and self.done_count >= 3
        )
