from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ContactInsight(BaseModel):
    """Model for AI-generated contact insights"""
    contact_id: int = Field(..., description="ID of the contact")
    summary: str = Field(default="", description="AI-generated summary of customer needs and interests")
    tags: List[str] = Field(default_factory=list, description="Tags for segmentation")
    from_dialogs: str = Field(default="", description="Brief history of key requests from dialogs")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last analysis timestamp")
    manually_edited: bool = Field(default=False, description="Flag if summary was manually edited")

    class Config:
        json_schema_extra = {
            "example": {
                "contact_id": 1,
                "summary": "Ищет футбольные сборы в Сочи для ребенка 2011 г.р.",
                "tags": ["Сочи", "сборы", "футбол", "2011"],
                "from_dialogs": "Интересовался сборами в январе, спрашивал про даты и стоимость",
                "updated_at": "2025-11-25T06:00:00",
                "manually_edited": False
            }
        }
