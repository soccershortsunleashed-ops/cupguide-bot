from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class ContactMessage(BaseModel):
    """Model for storing WhatsApp messages from contact dialogs"""
    
    id: Optional[int] = Field(default=None, description="Auto-increment ID")
    contact_id: int = Field(..., description="ID of the contact")
    direction: Literal["in", "out"] = Field(..., description="Message direction: incoming or outgoing")
    message: str = Field(..., description="Text content of the message")
    timestamp: datetime = Field(..., description="When the message was sent/received")
    whatsapp_msg_id: Optional[str] = Field(default=None, description="Original WhatsApp message ID")
    loaded_via: str = Field(default="greenapi", description="Source of the message")
    sender_name: Optional[str] = Field(default=None, description="Name of sender (for group chats)")
    
    # Media fields
    media_type: Optional[Literal["image", "video", "document", "audio", "sticker"]] = Field(
        default=None, 
        description="Type of media attachment"
    )
    media_path: Optional[str] = Field(default=None, description="Local path to downloaded media file")
    media_url: Optional[str] = Field(default=None, description="Original URL from Green API")
    media_filename: Optional[str] = Field(default=None, description="Original filename")
    media_mime_type: Optional[str] = Field(default=None, description="MIME type of the media file")

    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
