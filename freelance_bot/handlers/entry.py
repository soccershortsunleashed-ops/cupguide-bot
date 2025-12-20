"""
Entry Handler - обработка входа в воронку
Триггеры: /start, слово "БОТ", deep-link из автопостинга
"""
import re
import logging
from datetime import datetime
from typing import Optional

import os
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile

from freelance_bot.states import FreelanceStates
from freelance_bot.keyboards.inline import (
    get_entry_keyboard,
    get_price_guard_keyboard,
    get_q1_goal_keyboard,
)
from freelance_bot.texts.messages import (
    MSG_ENTRY, MSG_PRICE_GUARD, MSG_Q1_GOAL, MSG_ANTI_DUMPING,
    CB_START, CB_PRICE, CB_DEMO,
)

logger = logging.getLogger(__name__)

entry_router = Router(name="entry")


def parse_deep_link(start_param: str) -> dict:
    """
    Парсит deep-link параметр из /start
    Формат: src_ch_{channelId}_p_{postId}
    
    Returns:
        {"source_type": "autopost", "channel_id": int, "post_id": int}
        или {"source_type": "direct"} если не распознано
    """
    if not start_param:
        return {"source_type": "direct"}
    
    # Паттерн: src_ch_123456_p_789
    match = re.match(r'src_ch_(\d+)_p_(\d+)', start_param)
    if match:
        return {
            "source_type": "autopost",
            "channel_id": int(match.group(1)),
            "post_id": int(match.group(2)),
        }
    
    return {"source_type": "direct", "raw_param": start_param}


def is_keyword_entry(text: str) -> bool:
    """Проверяет, является ли сообщение входом по ключевому слову "БОТ" """
    if not text:
        return False
    normalized = text.strip().upper()
    return normalized == "БОТ"


def is_price_question(text: str) -> bool:
    """Проверяет, спрашивает ли пользователь о цене (анти-демпинг)"""
    if not text:
        return False
    
    price_patterns = [
        r'сколько\s*стоит',
        r'какая\s*цена',
        r'почём',
        r'по\s*чём',
        r'подешевле',
        r'дёшево',
        r'дешево',
        r'скидк',
        r'бюджет',
    ]
    
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in price_patterns)


@entry_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """
    Обработка /start команды
    Может содержать deep-link параметр из автопостинга
    """
    user_id = message.from_user.id
    
    # Парсим deep-link если есть
    start_param = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""
    source_info = parse_deep_link(start_param)
    
    logger.info(f"👤 /start from user {user_id}, source: {source_info}")
    
    # Сохраняем данные в FSM
    await state.update_data(
        telegram_user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        source_type=source_info.get("source_type", "direct"),
        source_channel_id=source_info.get("channel_id"),
        source_post_id=source_info.get("post_id"),
        started_at=datetime.now().isoformat(),
    )
    
    # Устанавливаем состояние ENTRY
    await state.set_state(FreelanceStates.ENTRY)
    
    # Отправляем приветственное сообщение с картинкой
    welcome_image = os.path.join(os.path.dirname(__file__), "..", "welcome.png")
    if os.path.exists(welcome_image):
        photo = FSInputFile(welcome_image)
        await message.answer_photo(
            photo=photo,
            caption=MSG_ENTRY,
            reply_markup=get_entry_keyboard()
        )
    else:
        await message.answer(
            MSG_ENTRY,
            reply_markup=get_entry_keyboard()
        )


@entry_router.message(F.text.upper() == "БОТ")
async def keyword_entry(message: Message, state: FSMContext) -> None:
    """
    Обработка входа по ключевому слову "БОТ"
    Основной триггер из объявления
    """
    user_id = message.from_user.id
    
    logger.info(f"👤 Keyword entry 'БОТ' from user {user_id}")
    
    # Сохраняем данные в FSM
    await state.update_data(
        telegram_user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        source_type="keyword",
        started_at=datetime.now().isoformat(),
    )
    
    # Устанавливаем состояние ENTRY
    await state.set_state(FreelanceStates.ENTRY)
    
    # Отправляем приветственное сообщение с картинкой
    welcome_image = os.path.join(os.path.dirname(__file__), "..", "welcome.png")
    if os.path.exists(welcome_image):
        photo = FSInputFile(welcome_image)
        await message.answer_photo(
            photo=photo,
            caption=MSG_ENTRY,
            reply_markup=get_entry_keyboard()
        )
    else:
        await message.answer(
            MSG_ENTRY,
            reply_markup=get_entry_keyboard()
        )


@entry_router.callback_query(F.data == CB_START)
async def cb_start_funnel(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка кнопки "Поехали" - переход к Q1"""
    await callback.answer()
    
    logger.info(f"▶️ User {callback.from_user.id} clicked 'Поехали'")
    
    # Переходим к первому вопросу скрининга
    await state.set_state(FreelanceStates.SCREEN_Q1_GOAL)
    
    # Если сообщение с фото - удаляем и отправляем новое, иначе редактируем
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(
                MSG_Q1_GOAL,
                reply_markup=get_q1_goal_keyboard()
            )
        else:
            await callback.message.edit_text(
                MSG_Q1_GOAL,
                reply_markup=get_q1_goal_keyboard()
            )
    except Exception as e:
        logger.warning(f"Edit failed, sending new message: {e}")
        await callback.message.answer(
            MSG_Q1_GOAL,
            reply_markup=get_q1_goal_keyboard()
        )


@entry_router.callback_query(F.data == CB_PRICE)
async def cb_price_guard(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка кнопки "Сразу цена" - отсечка демпинга"""
    await callback.answer()
    
    logger.info(f"💸 User {callback.from_user.id} clicked 'Сразу цена'")
    
    # Переходим в состояние PRICE_GUARD
    await state.set_state(FreelanceStates.ENTRY_PRICE_GUARD)
    
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(
                MSG_PRICE_GUARD,
                reply_markup=get_price_guard_keyboard()
            )
        else:
            await callback.message.edit_text(
                MSG_PRICE_GUARD,
                reply_markup=get_price_guard_keyboard()
            )
    except Exception as e:
        logger.warning(f"Edit failed: {e}")
        await callback.message.answer(
            MSG_PRICE_GUARD,
            reply_markup=get_price_guard_keyboard()
        )


@entry_router.callback_query(F.data == CB_DEMO)
async def cb_demo(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка кнопки "Посмотреть как работает" - переход к Q1"""
    await callback.answer()
    
    logger.info(f"🧪 User {callback.from_user.id} clicked 'Посмотреть как работает'")
    
    # Переходим к первому вопросу (демо = прохождение воронки)
    await state.set_state(FreelanceStates.SCREEN_Q1_GOAL)
    
    try:
        if callback.message.photo:
            await callback.message.delete()
            await callback.message.answer(
                MSG_Q1_GOAL,
                reply_markup=get_q1_goal_keyboard()
            )
        else:
            await callback.message.edit_text(
                MSG_Q1_GOAL,
                reply_markup=get_q1_goal_keyboard()
            )
    except Exception as e:
        logger.warning(f"Edit failed: {e}")
        await callback.message.answer(
            MSG_Q1_GOAL,
            reply_markup=get_q1_goal_keyboard()
        )


@entry_router.message(FreelanceStates.ENTRY)
async def handle_entry_text(message: Message, state: FSMContext) -> None:
    """Обработка текстовых сообщений в состоянии ENTRY"""
    
    # Проверяем на вопрос о цене
    if is_price_question(message.text):
        logger.info(f"💸 Price question detected from user {message.from_user.id}")
        await message.answer(
            MSG_ANTI_DUMPING,
            reply_markup=get_entry_keyboard()
        )
        return
    
    # Иначе напоминаем о кнопках
    await message.answer(
        "Нажми одну из кнопок выше 👆",
        reply_markup=get_entry_keyboard()
    )


@entry_router.message(FreelanceStates.ENTRY_PRICE_GUARD)
async def handle_price_guard_text(message: Message, state: FSMContext) -> None:
    """Обработка текста в состоянии PRICE_GUARD"""
    
    # Проверяем на вопрос о цене
    if is_price_question(message.text):
        await message.answer(
            MSG_ANTI_DUMPING,
            reply_markup=get_price_guard_keyboard()
        )
        return
    
    # Напоминаем о кнопке
    await message.answer(
        "Жми «Поехали» — и за 60 секунд поймём, ты клиент или турист.",
        reply_markup=get_price_guard_keyboard()
    )
