"""
Обработчики команд для личного кабинета организатора.
"""
import logging
import sys
import os
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

# Добавляем путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from cabinet_service import get_cabinet_service, CabinetService
    from cabinet_formatter import CabinetFormatter
except ImportError:
    from telegram_bot.cabinet_service import get_cabinet_service, CabinetService
    from telegram_bot.cabinet_formatter import CabinetFormatter

logger = logging.getLogger(__name__)

# Создаём роутер для кабинета
cabinet_router = Router()


class CabinetStates(StatesGroup):
    """FSM состояния для личного кабинета"""
    MAIN = State()           # Главный экран "Мои турниры"
    TOURNAMENT = State()     # Карточка турнира
    ANALYTICS = State()      # Аналитика турнира
    PROMOTION = State()      # Управление продвижением


def get_service(backend_client=None) -> CabinetService:
    """Получает сервис кабинета"""
    # Импортируем backend_client из bot.py если не передан
    if backend_client is None:
        try:
            from backend_client import BackendClient
            backend_client = BackendClient()
        except ImportError:
            from telegram_bot.backend_client import BackendClient
            backend_client = BackendClient()
    return get_cabinet_service(backend_client)


@cabinet_router.message(Command("cabinet", "org"))
async def cmd_cabinet(message: Message, state: FSMContext) -> None:
    """
    Обработчик команд /cabinet и /org.
    Показывает главный экран личного кабинета.
    """
    user_id = message.from_user.id
    logger.info(f"User {user_id} opened cabinet")
    
    # Получаем contact_id из FSM
    data = await state.get_data()
    contact_id = data.get("contact_id")
    
    if not contact_id:
        await message.answer(
            "❌ Для доступа к личному кабинету необходимо зарегистрироваться.\n"
            "Используйте команду /start"
        )
        return
    
    # Получаем турниры организатора
    service = get_service()
    tournaments, campaigns = await service.get_tournaments_with_campaigns(contact_id)
    
    if not tournaments:
        await message.answer(
            "📋 У вас нет турниров в системе\n\n"
            "Чтобы добавить турнир, обратитесь к администратору или "
            "создайте турнир через бота (функция в разработке)."
        )
        return
    
    # Форматируем и отправляем список турниров
    text = CabinetFormatter.format_tournaments_list(tournaments, campaigns)
    
    # Создаём клавиатуру для первого турнира
    first_tournament_id = tournaments[0].get("id")
    keyboard = CabinetFormatter.build_tournament_keyboard(first_tournament_id)
    
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(CabinetStates.MAIN)
    await state.update_data(current_tournament_id=first_tournament_id)


@cabinet_router.callback_query(F.data.startswith("cabinet_analytics_"))
async def show_analytics(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Показывает аналитику турнира.
    """
    tournament_id = int(callback.data.split("_")[-1])
    
    # Получаем contact_id для проверки владения
    data = await state.get_data()
    contact_id = data.get("contact_id")
    
    service = get_service()
    
    # Проверяем владение турниром
    if not await service.verify_tournament_ownership(tournament_id, contact_id):
        await callback.answer("❌ Турнир не найден", show_alert=True)
        return
    
    # Получаем аналитику
    analytics = await service.get_tournament_analytics(tournament_id)
    text = CabinetFormatter.format_analytics(analytics.to_dict(), tournament_id)
    
    # Кнопка "Назад"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад к турниру", callback_data=f"cabinet_tournament_{tournament_id}")
    builder.button(text="🏠 К списку турниров", callback_data="cabinet_back")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()
    await state.set_state(CabinetStates.ANALYTICS)


@cabinet_router.callback_query(F.data.startswith("cabinet_promotion_"))
async def show_promotion(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Показывает экран управления продвижением.
    """
    tournament_id = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    contact_id = data.get("contact_id")
    
    service = get_service()
    
    # Проверяем владение
    if not await service.verify_tournament_ownership(tournament_id, contact_id):
        await callback.answer("❌ Турнир не найден", show_alert=True)
        return
    
    # Получаем турнир
    tournament = await service.get_tournament_by_id(tournament_id)
    if not tournament:
        await callback.answer("❌ Турнир не найден", show_alert=True)
        return
    
    # Получаем кампанию
    campaign = await service.get_promo_campaign(tournament_id)
    
    # Форматируем карточку
    campaign_progress = service.promo_service.format_progress(campaign) if campaign else None
    text = CabinetFormatter.format_tournament_card(tournament, campaign_progress)
    text = f"⚙️ Управление продвижением\n\n{text}"
    
    # Проверяем доступность премиума
    availability = service.check_premium_availability(tournament)
    keyboard = CabinetFormatter.build_promotion_keyboard(tournament_id, availability)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
    await state.set_state(CabinetStates.PROMOTION)


@cabinet_router.callback_query(F.data.startswith("cabinet_tournament_"))
async def show_tournament_card(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Показывает карточку турнира.
    """
    tournament_id = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    contact_id = data.get("contact_id")
    
    service = get_service()
    
    if not await service.verify_tournament_ownership(tournament_id, contact_id):
        await callback.answer("❌ Турнир не найден", show_alert=True)
        return
    
    tournament = await service.get_tournament_by_id(tournament_id)
    if not tournament:
        await callback.answer("❌ Турнир не найден", show_alert=True)
        return
    
    campaign = await service.get_promo_campaign(tournament_id)
    campaign_progress = service.promo_service.format_progress(campaign) if campaign else None
    
    text = CabinetFormatter.format_tournament_card(tournament, campaign_progress)
    keyboard = CabinetFormatter.build_tournament_keyboard(tournament_id)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
    await state.set_state(CabinetStates.TOURNAMENT)


@cabinet_router.callback_query(F.data == "cabinet_back")
async def back_to_list(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Возврат к списку турниров.
    """
    data = await state.get_data()
    contact_id = data.get("contact_id")
    
    if not contact_id:
        await callback.answer("❌ Сессия истекла", show_alert=True)
        return
    
    service = get_service()
    tournaments, campaigns = await service.get_tournaments_with_campaigns(contact_id)
    
    if not tournaments:
        await callback.message.edit_text("📋 У вас нет турниров в системе")
        await callback.answer()
        return
    
    text = CabinetFormatter.format_tournaments_list(tournaments, campaigns)
    first_tournament_id = tournaments[0].get("id")
    keyboard = CabinetFormatter.build_tournament_keyboard(first_tournament_id)
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
    await state.set_state(CabinetStates.MAIN)


@cabinet_router.callback_query(F.data.startswith("cabinet_copy_utm_"))
async def copy_utm_link(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Генерирует и отправляет UTM-ссылку.
    """
    tournament_id = int(callback.data.split("_")[-1])
    
    service = get_service()
    utm_link = service.generate_utm_link(tournament_id)
    
    await callback.message.answer(
        f"🔗 Ссылка с UTM-метками:\n\n`{utm_link}`\n\n"
        "Скопируйте ссылку для отслеживания переходов.",
        parse_mode="Markdown"
    )
    await callback.answer("Ссылка сгенерирована!")


@cabinet_router.callback_query(F.data.startswith("cabinet_open_card_"))
async def open_tournament_card(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Отправляет ссылку на карточку турнира.
    """
    tournament_id = int(callback.data.split("_")[-1])
    
    service = get_service()
    link = f"http://127.0.0.1:8000/tournaments/{tournament_id}"
    
    await callback.message.answer(
        f"🔗 Карточка турнира:\n{link}"
    )
    await callback.answer()


# Заглушки для кнопок покупки (будут реализованы позже)
@cabinet_router.callback_query(F.data.startswith("cabinet_buy_premium_"))
async def buy_premium(callback: CallbackQuery, state: FSMContext) -> None:
    """Покупка премиума (заглушка)"""
    await callback.answer("💎 Функция покупки премиума в разработке", show_alert=True)


@cabinet_router.callback_query(F.data.startswith("cabinet_extend_premium_"))
async def extend_premium(callback: CallbackQuery, state: FSMContext) -> None:
    """Продление премиума (заглушка)"""
    await callback.answer("🔄 Функция продления премиума в разработке", show_alert=True)


@cabinet_router.callback_query(F.data.startswith("cabinet_add_day_"))
async def add_premium_day(callback: CallbackQuery, state: FSMContext) -> None:
    """Добавление дня премиума (заглушка)"""
    await callback.answer("➕ Функция добавления дня в разработке", show_alert=True)


@cabinet_router.callback_query(F.data.startswith("cabinet_buy_rating_"))
async def buy_rating(callback: CallbackQuery, state: FSMContext) -> None:
    """Покупка рейтинга (заглушка)"""
    await callback.answer("⭐ Функция покупки рейтинга в разработке", show_alert=True)


@cabinet_router.callback_query(F.data.startswith("cabinet_buy_native_"))
async def buy_native(callback: CallbackQuery, state: FSMContext) -> None:
    """Покупка нативных упоминаний (заглушка)"""
    await callback.answer("📢 Функция заказа нативных упоминаний в разработке", show_alert=True)


@cabinet_router.callback_query(F.data == "cabinet_exit")
async def exit_cabinet(callback: CallbackQuery, state: FSMContext) -> None:
    """Выход из личного кабинета"""
    user_id = callback.from_user.id
    logger.info(f"User {user_id} exited cabinet")
    
    # Сохраняем contact_id перед очисткой состояния
    data = await state.get_data()
    contact_id = data.get("contact_id")
    message_history = data.get("message_history", [])
    
    # Очищаем состояние кабинета
    await state.clear()
    
    # Восстанавливаем данные для основного бота
    from bot import UserStates
    await state.set_state(UserStates.ACTIVATED)
    await state.update_data(contact_id=contact_id, message_history=message_history)
    
    await callback.message.edit_text(
        "🚪 Вы вышли из личного кабинета.\n\n"
        "Теперь можете задавать вопросы о турнирах или использовать команды:\n"
        "• /cabinet - вернуться в кабинет\n"
        "• /tournaments - список турниров\n"
        "• /help - справка"
    )
    await callback.answer()


@cabinet_router.message(CabinetStates.MAIN)
@cabinet_router.message(CabinetStates.TOURNAMENT)
@cabinet_router.message(CabinetStates.ANALYTICS)
@cabinet_router.message(CabinetStates.PROMOTION)
async def handle_text_in_cabinet(message: Message, state: FSMContext) -> None:
    """
    Обработчик текстовых сообщений в состояниях кабинета.
    Выходит из кабинета и обрабатывает вопрос через LLM консультанта.
    """
    user_id = message.from_user.id
    logger.info(f"User {user_id} sent message in cabinet state, processing with LLM")
    
    # Сохраняем contact_id перед очисткой состояния
    data = await state.get_data()
    contact_id = data.get("contact_id")
    message_history = data.get("message_history", [])
    
    # Очищаем состояние кабинета, но сохраняем важные данные
    await state.clear()
    
    # Восстанавливаем данные для основного бота
    # Импортируем UserStates из bot.py
    from bot import UserStates
    
    await state.set_state(UserStates.ACTIVATED)
    await state.update_data(contact_id=contact_id, message_history=message_history)
    
    # Отправляем сообщение о выходе из кабинета
    await message.answer("📤 Вышел из личного кабинета. Обрабатываю ваш вопрос...")
    
    # Обрабатываем сообщение через LLM напрямую (без circular import)
    try:
        from llm_consultant import LLMConsultant
    except ImportError:
        from telegram_bot.llm_consultant import LLMConsultant
    
    llm_consultant = LLMConsultant()
    
    try:
        response = await llm_consultant.process_message(
            message.text,
            user_id=user_id,
            contact_id=contact_id,
            message_history=message_history
        )
        
        # Отправляем ответ с картинкой если есть
        text = response.get("text", "")
        image_path = response.get("image_path")
        
        if image_path and os.path.exists(image_path):
            # Отправляем фото с подписью
            from aiogram.types import FSInputFile
            photo = FSInputFile(image_path)
            # Telegram ограничивает caption до 1024 символов
            if len(text) <= 1024:
                await message.answer_photo(photo=photo, caption=text)
            else:
                # Отправляем фото отдельно, потом текст
                await message.answer_photo(photo=photo)
                if len(text) > 4000:
                    parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                    for part in parts:
                        await message.answer(part, parse_mode="HTML")
                else:
                    await message.answer(text, parse_mode="HTML")
        elif text:
            # Разбиваем длинные сообщения
            if len(text) > 4000:
                parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                for part in parts:
                    await message.answer(part, parse_mode="HTML")
            else:
                await message.answer(text, parse_mode="HTML")
        
        # Обновляем историю сообщений
        message_history.append({"role": "user", "content": message.text})
        message_history.append({"role": "assistant", "content": response.get("text", "")})
        if len(message_history) > 10:
            message_history = message_history[-10:]
        await state.update_data(message_history=message_history)
        
    except Exception as e:
        logger.error(f"Error processing message in cabinet: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке запроса.\n\n"
            "Попробуйте:\n"
            "• /tournaments - посмотреть турниры\n"
            "• /help - получить помощь"
        )
