from pydantic import BaseModel
from typing import Optional, List, Union
from datetime import datetime
from enum import Enum

class MessageStatus(str, Enum):
    NEW = "new"
    PROCESSED = "processed"
    PUBLISHED = "published"

class MediaFile(BaseModel):
    path: str
    type: str  # 'photo', 'video', etc.

class Message(BaseModel):
    id: Union[int, str]
    channel_id: Union[int, str]
    channel_title: str
    text: str
    date: datetime
    url: Optional[str] = None
    status: MessageStatus = MessageStatus.NEW
    media_files: List[MediaFile] = []
    grouped_id: Optional[int] = None  # To identify albums
    summary: Optional[str] = None
    rewrite: Optional[str] = None
    sender: Optional[str] = None  # Автор сообщения (для WhatsApp групп)
    author_contact_id: Optional[int] = None  # ID контакта автора (для открытия карточки контакта)
    
    # Legacy fields for backward compatibility
    @property
    def media_path(self) -> Optional[str]:
        return self.media_files[0].path if self.media_files else None
    
    @property
    def media_type(self) -> Optional[str]:
        return self.media_files[0].type if self.media_files else None
