"""
Freelance Bot - главный файл бота
FSM воронка для фриланс-лидов с LLM скорингом
"""
import asyncio
import logging
import sys
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

# Добавляем путь к корню проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from freelance_bot.config import config
from freelance_bot.handlers import main_router

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('freelance_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Запуск бота"""
    
    # Проверяем токен
    if not config.BOT_TOKEN:
        logger.error("❌ FREELANCE_BOT_TOKEN not set in environment!")
        logger.info("Set it in .env file or environment variables")
        return
    
    logger.info("🚀 Starting Freelance Bot...")
    logger.info(f"📊 LLM Model: {config.LLM_MODEL}")
    logger.info(f"🔗 Backend URL: {config.BACKEND_URL}")
    
    # Создаём бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Создаём диспетчер с хранилищем состояний
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключаем роутеры
    dp.include_router(main_router)
    
    # Запускаем polling
    try:
        logger.info("✅ Bot started successfully!")
        logger.info(f"🤖 Bot username: @{config.BOT_USERNAME}")
        
        # Удаляем webhook если был
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Устанавливаем команды меню
        # Кнопка "БОТ" внизу чата, которая запускает /start
        commands = [
            BotCommand(command="start", description="БОТ"),
        ]
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("📋 Bot menu commands set: /start = 'БОТ'")
        
        # Запускаем polling
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        raise
    finally:
        await bot.session.close()
        logger.info("👋 Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
