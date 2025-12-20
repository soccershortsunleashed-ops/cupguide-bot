"""
API endpoints для Avito Bot
"""
from .webhook import router as webhook_router
from .admin import router as admin_router

__all__ = ["webhook_router", "admin_router"]
