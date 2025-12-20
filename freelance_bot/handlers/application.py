"""
Application Handler - форма заявки
"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from freelance_bot.states import FreelanceStates
from freelance_bot.keyboards.inline import (
    get_platform_keyboard,
    get_skip_keyboard,
    get_a_flow_order_keyboard,
    get_contact_keyboard,
    get_remove_keyboard,
)
from aiogram.types import FSInputFile
from freelance_bot.texts.messages import (
    MSG_APPLICATION_INTRO, MSG_APPLICATION_CONTACT, MSG_APPLICATION_LINK,
    MSG_APPLICATION_PLATFORM, MSG_APPLICATION_START_WINDOW, MSG_APPLICATION_DONE,
    CB_FIX_ORDER, CB_PREPAY, CB_CALL,
    CB_PLATFORM_TG, CB_PLATFORM_WEB, CB_PLATFORM_ALL,
    PLATFORM_MAP,
)

# Путь к картинке "Done"
import os
DONE_IMAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "done.png")

logger = logging.getLogger(__name__)

application_router = Router(name="application")


async def start_application(message: Message, state: FSMContext) -> None:
    """Начало формы заявки"""
    await state.set_state(FreelanceStates.APPLICATION_CONTACT)
    await message.answer(
        MSG_APPLICATION_CONTACT + "\n\nИли нажми кнопку ниже 👇",
        reply_markup=get_contact_keyboard()
    )


# ============================================================
# A_FLOW ORDER BUTTONS
# ============================================================

@application_router.callback_query(
    FreelanceStates.APPLICATION_FORM,
    F.data.in_([CB_FIX_ORDER, CB_PREPAY, CB_CALL])
)
async def cb_a_flow_action(callback: CallbackQuery, state: FSMContext) -> None:
    """A_FLOW: Выбор действия (заказ/предоплата/созвон)"""
    await callback.answer()
    
    action_map = {
        CB_FIX_ORDER: ("fix_order", "Зафиксировать заказ"),
        CB_PREPAY: ("prepay", "Внести предоплату"),
        CB_CALL: ("call", "Созвон 15 минут"),
    }
    
    action_key, action_label = action_map.get(callback.data, ("unknown", "Неизвестно"))
    
    logger.info(f"✅ A_FLOW action: {action_label} from user {callback.from_user.id}")
    
    await state.update_data(a_action=action_key, a_action_label=action_label)
    
    await callback.message.edit_text(
        f"Выбрано: {action_label}\n\n{MSG_APPLICATION_INTRO}"
    )
    
    # Переходим к сбору контакта с кнопкой "Поделиться контактом"
    await state.set_state(FreelanceStates.APPLICATION_CONTACT)
    await callback.message.answer(
        MSG_APPLICATION_CONTACT + "\n\nИли нажми кнопку ниже 👇",
        reply_markup=get_contact_keyboard()
    )


# ============================================================
# APPLICATION FORM STEPS
# ============================================================

@application_router.message(FreelanceStates.APPLICATION_CONTACT, F.contact)
async def handle_contact_shared(message: Message, state: FSMContext) -> None:
    """Обработка контакта через кнопку "Поделиться контактом" """
    contact = message.contact
    phone = contact.phone_number
    
    # Форматируем телефон
    if not phone.startswith("+"):
        phone = "+" + phone
    
    logger.info(f"📱 Contact shared: {phone} from user {message.from_user.id}")
    
    await state.update_data(
        contact_preferred=phone,
        contact_phone=phone,
        contact_first_name=contact.first_name,
        contact_last_name=contact.last_name
    )
    await state.set_state(FreelanceStates.APPLICATION_LINK)
    
    await message.answer(
        f"✅ Контакт получен: {phone}\n\n{MSG_APPLICATION_LINK}",
        reply_markup=get_remove_keyboard()  # Убираем Reply клавиатуру
    )
    await message.answer(
        "Есть ссылка на проект?",
        reply_markup=get_skip_keyboard("fl_skip_link")
    )


@application_router.message(FreelanceStates.APPLICATION_CONTACT, F.text == "✍️ Ввести вручную")
async def handle_contact_manual_choice(message: Message, state: FSMContext) -> None:
    """Пользователь выбрал ввести контакт вручную"""
    await message.answer(
        "Хорошо, введи @username или номер телефона:",
        reply_markup=get_remove_keyboard()
    )


@application_router.message(FreelanceStates.APPLICATION_CONTACT)
async def handle_contact_text(message: Message, state: FSMContext) -> None:
    """Сбор контакта текстом (@username / телефон)"""
    if not message.text:
        await message.answer(
            "Нажми кнопку 'Поделиться контактом' или введи @username / телефон:",
            reply_markup=get_contact_keyboard()
        )
        return
    
    contact = message.text.strip()
    
    # Базовая валидация
    if len(contact) < 3:
        await message.answer(
            "Слишком короткий контакт. Укажи @username или телефон:",
            reply_markup=get_contact_keyboard()
        )
        return
    
    logger.info(f"📞 Contact text: {contact} from user {message.from_user.id}")
    
    await state.update_data(contact_preferred=contact)
    await state.set_state(FreelanceStates.APPLICATION_LINK)
    
    await message.answer(
        MSG_APPLICATION_LINK,
        reply_markup=get_remove_keyboard()
    )
    await message.answer(
        "Есть ссылка?",
        reply_markup=get_skip_keyboard("fl_skip_link")
    )


@application_router.callback_query(F.data == "fl_skip_link")
async def cb_skip_link(callback: CallbackQuery, state: FSMContext) -> None:
    """Пропуск ссылки на проект"""
    await callback.answer()
    await state.update_data(contact_link=None)
    await state.set_state(FreelanceStates.APPLICATION_PLATFORM)
    await callback.message.edit_text(MSG_APPLICATION_PLATFORM)
    await callback.message.answer(
        "Где будет бот?",
        reply_markup=get_platform_keyboard()
    )


@application_router.message(FreelanceStates.APPLICATION_LINK)
async def handle_link(message: Message, state: FSMContext) -> None:
    """Сбор ссылки на проект"""
    link = message.text.strip()
    
    logger.info(f"🔗 Link: {link} from user {message.from_user.id}")
    
    await state.update_data(contact_link=link)
    await state.set_state(FreelanceStates.APPLICATION_PLATFORM)
    
    await message.answer(
        MSG_APPLICATION_PLATFORM,
        reply_markup=get_platform_keyboard()
    )


@application_router.callback_query(
    FreelanceStates.APPLICATION_PLATFORM,
    F.data.in_([CB_PLATFORM_TG, CB_PLATFORM_WEB, CB_PLATFORM_ALL])
)
async def cb_platform(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор платформы"""
    await callback.answer()
    
    platform_key, platform_label = PLATFORM_MAP.get(callback.data, ("unknown", "Неизвестно"))
    
    logger.info(f"📱 Platform: {platform_label} from user {callback.from_user.id}")
    
    await state.update_data(bot_platform=platform_key, bot_platform_label=platform_label)
    await state.set_state(FreelanceStates.APPLICATION_START_WINDOW)
    
    await callback.message.edit_text(f"Платформа: {platform_label}")
    await callback.message.answer(MSG_APPLICATION_START_WINDOW)


@application_router.message(FreelanceStates.APPLICATION_PLATFORM)
async def handle_platform_text(message: Message, state: FSMContext) -> None:
    """Текстовый ввод платформы"""
    await message.answer(
        "Выбери платформу кнопкой 👆",
        reply_markup=get_platform_keyboard()
    )


@application_router.message(FreelanceStates.APPLICATION_START_WINDOW)
async def handle_start_window(message: Message, state: FSMContext) -> None:
    """Сбор окна старта - завершение заявки"""
    start_window = message.text.strip()
    
    logger.info(f"📅 Start window: {start_window} from user {message.from_user.id}")
    
    await state.update_data(
        start_window=start_window,
        application_completed_at=datetime.now().isoformat()
    )
    
    # Переходим в состояние DONE
    await state.set_state(FreelanceStates.DONE)
    
    # Получаем все данные для сохранения
    data = await state.get_data()
    
    # Отправляем клиенту ТОЛЬКО короткое подтверждение с картинкой (без сводки!)
    if os.path.exists(DONE_IMAGE_PATH):
        await message.answer_photo(
            photo=FSInputFile(DONE_IMAGE_PATH),
            caption=MSG_APPLICATION_DONE
        )
    else:
        await message.answer(MSG_APPLICATION_DONE)
    
    # Сохраняем заявку в backend
    try:
        import aiohttp
        from freelance_bot.config import config
        
        # Формируем данные для API
        lead_data = {
            "telegram_user_id": message.from_user.id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "source_type": data.get("source_type", "direct"),
            "source_channel_id": data.get("source_channel_id"),
            "source_post_id": data.get("source_post_id"),
            "goal": data.get("goal"),
            "pain": data.get("pain"),
            "context": data.get("context"),
            "niche_text": data.get("niche_text"),
            "llm_grade": data.get("llm_grade"),
            "llm_score": data.get("llm_score"),
            "llm_reason": data.get("llm_reason"),
            "final_route": data.get("final_route"),
            "deterministic_score": data.get("deterministic_score"),
            "deterministic_grade": data.get("deterministic_grade"),
            "contact_preferred": data.get("contact_preferred"),
            "contact_link": data.get("contact_link"),
            "bot_platform": data.get("bot_platform"),
            "start_window": start_window,
            "status": "NEW",
            # A_FLOW бриф
            "a_traffic": data.get("a_traffic"),
            "a_payment": data.get("a_payment"),
            "a_steps": data.get("a_steps"),
            # B_FLOW бриф
            "b_product": data.get("b_product"),
            "b_objection": data.get("b_objection"),
            "b_goal": data.get("b_goal"),
            "b_package": data.get("b_package"),
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{config.BACKEND_URL}/api/leads/",
                json=lead_data
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"✅ Lead saved to backend: id={result.get('id')}")
                else:
                    logger.error(f"❌ Failed to save lead: {resp.status}")
                    
    except Exception as e:
        logger.error(f"❌ Error saving lead to backend: {e}")
    
    # Отправляем уведомление владельцу
    try:
        from freelance_bot.services.notification_service import notification_service
        await notification_service.notify_new_lead(message.bot, data)
    except Exception as e:
        logger.error(f"❌ Error sending notification: {e}")
    
    logger.info(f"✅ Application completed for user {message.from_user.id}")


def format_application_summary(data: dict) -> str:
    """Форматирует сводку заявки"""
    lines = []
    
    # Основные данные
    if data.get("goal_label"):
        lines.append(f"🎯 Цель: {data['goal_label']}")
    if data.get("pain_label"):
        lines.append(f"💔 Проблема: {data['pain_label']}")
    if data.get("context_label"):
        lines.append(f"📦 Контекст: {data['context_label']}")
    if data.get("niche_text"):
        lines.append(f"📝 Ниша: {data['niche_text'][:100]}")
    
    lines.append("")  # Пустая строка
    
    # Скоринг
    if data.get("llm_grade"):
        lines.append(f"📊 Оценка: {data['llm_grade']} ({data.get('llm_score', '?')}/100)")
    if data.get("final_route"):
        route_labels = {
            "A_FLOW": "A (взрослый лид)",
            "B_FLOW": "B (прототип)",
            "TRASH_FLOW": "TRASH"
        }
        lines.append(f"🚦 Маршрут: {route_labels.get(data['final_route'], data['final_route'])}")
    
    lines.append("")
    
    # Контакты
    if data.get("contact_preferred"):
        lines.append(f"📞 Контакт: {data['contact_preferred']}")
    if data.get("contact_link"):
        lines.append(f"🔗 Ссылка: {data['contact_link']}")
    if data.get("bot_platform_label"):
        lines.append(f"📱 Платформа: {data['bot_platform_label']}")
    if data.get("start_window"):
        lines.append(f"📅 Старт: {data['start_window']}")
    
    # A_FLOW бриф
    if data.get("a_traffic"):
        lines.append("")
        lines.append("📋 Бриф A:")
        lines.append(f"  • Трафик: {data['a_traffic']}")
        if data.get("a_payment"):
            lines.append(f"  • Оплата/CRM: {data['a_payment']}")
        if data.get("a_steps"):
            lines.append(f"  • Шаги: {data['a_steps']}")
    
    # B_FLOW бриф
    if data.get("b_product"):
        lines.append("")
        lines.append("📋 Бриф B:")
        lines.append(f"  • Продукт: {data['b_product']}")
        if data.get("b_objection"):
            lines.append(f"  • Возражение: {data['b_objection']}")
        if data.get("b_goal"):
            lines.append(f"  • Финал: {data['b_goal']}")
        if data.get("b_package_label"):
            lines.append(f"  • Пакет: {data['b_package_label']}")
    
    return "\n".join(lines)
