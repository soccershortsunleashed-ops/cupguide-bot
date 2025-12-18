from pydantic import BaseModel
from typing import Optional, Union
from enum import Enum

class ChannelType(str, Enum):
    SOURCE = "source"
    TARGET = "target"

class Platform(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"

class Channel(BaseModel):
    id: Union[int, str]
    title: str
    username: Optional[str] = None
    type: ChannelType
    platform: Platform = Platform.TELEGRAM
