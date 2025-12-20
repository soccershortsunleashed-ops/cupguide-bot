"""Обработчики для фриланс-бота"""
from aiogram import Router

from .entry import entry_router
from .screening import screening_router
from .routing import routing_router
from .application import application_router

# Главный роутер, объединяющий все обработчики
main_router = Router(name="freelance_main")
main_router.include_router(entry_router)
main_router.include_router(screening_router)
main_router.include_router(routing_router)
main_router.include_router(application_router)
