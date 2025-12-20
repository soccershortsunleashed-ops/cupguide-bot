"""
Inline клавиатуры для фриланс-бота
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from freelance_bot.texts.messages import (
    # Buttons
    BTN_START, BTN_PRICE, BTN_DEMO,
    BTN_GOAL_SALES, BTN_GOAL_LEADS, BTN_GOAL_BASE, BTN_GOAL_SUPPORT, BTN_GOAL_JUST_BOT,
    BTN_PAIN_TRAFFIC, BTN_PAIN_DIALOG, BTN_PAIN_PAYMENT, BTN_PAIN_INTEGRATION, BTN_PAIN_CHAOS,
    BTN_CONTEXT_SCRATCH, BTN_CONTEXT_CONSTRUCTOR, BTN_CONTEXT_HAS_BOT, BTN_CONTEXT_HAS_CRM,
    BTN_TRASH_RETURN, BTN_TRASH_CHECKLIST,
    BTN_FIX_ORDER, BTN_PREPAY, BTN_CALL,
    BTN_PACKAGE_PROTOTYPE, BTN_PACKAGE_BATTLE,
    BTN_PLATFORM_TG, BTN_PLATFORM_WEB, BTN_PLATFORM_ALL,
    # Callbacks
    CB_START, CB_PRICE, CB_DEMO,
    CB_GOAL_SALES, CB_GOAL_LEADS, CB_GOAL_BASE, CB_GOAL_SUPPORT, CB_GOAL_JUST_BOT,
    CB_PAIN_TRAFFIC, CB_PAIN_DIALOG, CB_PAIN_PAYMENT, CB_PAIN_INTEGRATION, CB_PAIN_CHAOS,
    CB_CONTEXT_SCRATCH, CB_CONTEXT_CONSTRUCTOR, CB_CONTEXT_HAS_BOT, CB_CONTEXT_HAS_CRM,
    CB_TRASH_RETURN, CB_TRASH_CHECKLIST,
    CB_FIX_ORDER, CB_PREPAY, CB_CALL,
    CB_PACKAGE_PROTOTYPE, CB_PACKAGE_BATTLE,
    CB_PLATFORM_TG, CB_PLATFORM_WEB, CB_PLATFORM_ALL,
)


def get_entry_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура входа в воронку"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_START, callback_data=CB_START)
    builder.button(text=BTN_PRICE, callback_data=CB_PRICE)
    builder.button(text=BTN_DEMO, callback_data=CB_DEMO)
    builder.adjust(1)  # По одной кнопке в ряд
    return builder.as_markup()


def get_price_guard_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после "Сразу цена" """
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_START, callback_data=CB_START)
    builder.adjust(1)
    return builder.as_markup()


def get_q1_goal_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура Q1: Что бот должен принести?"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_GOAL_SALES, callback_data=CB_GOAL_SALES)
    builder.button(text=BTN_GOAL_LEADS, callback_data=CB_GOAL_LEADS)
    builder.button(text=BTN_GOAL_BASE, callback_data=CB_GOAL_BASE)
    builder.button(text=BTN_GOAL_SUPPORT, callback_data=CB_GOAL_SUPPORT)
    builder.button(text=BTN_GOAL_JUST_BOT, callback_data=CB_GOAL_JUST_BOT)
    builder.adjust(1)
    return builder.as_markup()


def get_q2_pain_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура Q2: Где сейчас всё разваливается?"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_PAIN_TRAFFIC, callback_data=CB_PAIN_TRAFFIC)
    builder.button(text=BTN_PAIN_DIALOG, callback_data=CB_PAIN_DIALOG)
    builder.button(text=BTN_PAIN_PAYMENT, callback_data=CB_PAIN_PAYMENT)
    builder.button(text=BTN_PAIN_INTEGRATION, callback_data=CB_PAIN_INTEGRATION)
    builder.button(text=BTN_PAIN_CHAOS, callback_data=CB_PAIN_CHAOS)
    builder.adjust(1)
    return builder.as_markup()


def get_q3_context_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура Q3: Что уже есть?"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_CONTEXT_SCRATCH, callback_data=CB_CONTEXT_SCRATCH)
    builder.button(text=BTN_CONTEXT_CONSTRUCTOR, callback_data=CB_CONTEXT_CONSTRUCTOR)
    builder.button(text=BTN_CONTEXT_HAS_BOT, callback_data=CB_CONTEXT_HAS_BOT)
    builder.button(text=BTN_CONTEXT_HAS_CRM, callback_data=CB_CONTEXT_HAS_CRM)
    builder.adjust(1)
    return builder.as_markup()


def get_trash_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура TRASH_FLOW"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_TRASH_RETURN, callback_data=CB_TRASH_RETURN)
    builder.button(text=BTN_TRASH_CHECKLIST, callback_data=CB_TRASH_CHECKLIST)
    builder.adjust(1)
    return builder.as_markup()


def get_a_flow_order_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура A_FLOW: Зафиксировать заказ"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_FIX_ORDER, callback_data=CB_FIX_ORDER)
    builder.button(text=BTN_PREPAY, callback_data=CB_PREPAY)
    builder.button(text=BTN_CALL, callback_data=CB_CALL)
    builder.adjust(1)
    return builder.as_markup()


def get_b_flow_package_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура B_FLOW: Выбор пакета"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_PACKAGE_PROTOTYPE, callback_data=CB_PACKAGE_PROTOTYPE)
    builder.button(text=BTN_PACKAGE_BATTLE, callback_data=CB_PACKAGE_BATTLE)
    builder.adjust(2)  # Две кнопки в ряд
    return builder.as_markup()


def get_platform_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора платформы"""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_PLATFORM_TG, callback_data=CB_PLATFORM_TG)
    builder.button(text=BTN_PLATFORM_WEB, callback_data=CB_PLATFORM_WEB)
    builder.button(text=BTN_PLATFORM_ALL, callback_data=CB_PLATFORM_ALL)
    builder.adjust(3)  # Три кнопки в ряд
    return builder.as_markup()


def get_deep_link_button(bot_username: str, channel_id: int, post_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт inline-кнопку с deep-link для автопостинга
    Deep-link: https://t.me/{bot_username}?start=src_ch_{channelId}_p_{postId}
    """
    deep_link = f"https://t.me/{bot_username}?start=src_ch_{channel_id}_p_{post_id}"
    builder = InlineKeyboardBuilder()
    builder.button(text="👉 Написать боту", url=deep_link)
    return builder.as_markup()


def get_skip_keyboard(callback_data: str = "fl_skip") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой "Пропустить" """
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data=callback_data)
    return builder.as_markup()


def get_contact_keyboard() -> ReplyKeyboardMarkup:
    """
    Reply клавиатура с кнопкой "Поделиться контактом"
    Позволяет получить реальный номер телефона пользователя
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Поделиться контактом", request_contact=True)
    builder.button(text="✍️ Ввести вручную")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_remove_keyboard() -> ReplyKeyboardRemove:
    """Убирает Reply клавиатуру"""
    return ReplyKeyboardRemove()
