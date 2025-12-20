"""
Модели данных для Avito Bot
"""
from .chat import AvitoChat
from .message import AvitoMessage
from .nlp_event import NLPEvent
from .lead import AvitoLead

__all__ = ["AvitoChat", "AvitoMessage", "NLPEvent", "AvitoLead"]
