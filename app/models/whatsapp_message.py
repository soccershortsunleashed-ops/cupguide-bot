from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class WhatsAppMessageStatus(str, Enum):
    NEW = "new"
    PROCESSED = "processed"

class WhatsAppMessage(BaseModel):
    id: Optional[int] = None
    chat_name: str
    sender: Optional[str] = None  # For group chats (display name)
    sender_id: Optional[str] = None  # WhatsApp ID автора (например, "214237649621159@c.us")
    text: str
    date: datetime
    message_id: str  # Unique identifier (hash of chat+sender+text+date)
    media_type: Optional[str] = None  # photo, video, document, etc.
    media_path: Optional[str] = None
    media_files: Optional[List[dict]] = None # List of {type: str, path: str}
    status: WhatsAppMessageStatus = WhatsAppMessageStatus.NEW
    created_at: datetime = datetime.utcnow()
