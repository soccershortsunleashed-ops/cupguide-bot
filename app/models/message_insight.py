from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class MessageInsight(BaseModel):
    """Извлеченная информация из сообщения автора"""
    
    # Основная информация
    group_name: Optional[str] = Field(None, description="Название группы, в которой публикуется")
    role: Optional[str] = Field(None, description="Роль автора (например, 'Администратор группы', 'Организатор турниров')")
    
    # Информация о турнирах/событиях
    tournament_name: Optional[str] = Field(None, description="Название турнира или УТС")
    tournament_type: Optional[str] = Field(None, description="Тип события (турнир, УТС, сборы и т.д.)")
    city: Optional[str] = Field(None, description="Город проведения")
    dates: Optional[str] = Field(None, description="Даты проведения")
    age_categories: Optional[List[str]] = Field(None, description="Возрастные категории")
    birth_years: Optional[List[str]] = Field(None, description="Годы рождения спортсменов, для которых организуются турниры/УТС")
    tournaments_organized: Optional[List[str]] = Field(None, description="Список названий турниров, которые организует автор")
    
    # Дополнительная информация
    organization: Optional[str] = Field(None, description="Организация или клуб")
    contact_info: Optional[str] = Field(None, description="Контактная информация")
    email: Optional[str] = Field(None, description="Email адрес (если обнаружен в сообщениях)")
    website: Optional[str] = Field(None, description="Веб-сайт или ссылка")
    social_media: Optional[List[str]] = Field(None, description="Социальные сети")
    
    # Детали
    description: Optional[str] = Field(None, description="Подробное описание деятельности")
    specializations: Optional[List[str]] = Field(None, description="Специализации (например, 'детский футбол', 'юношеские турниры')")
    
    # Метаданные
    confidence: Optional[float] = Field(None, description="Уверенность в извлеченной информации (0-1)")
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="Когда была извлечена информация")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }



