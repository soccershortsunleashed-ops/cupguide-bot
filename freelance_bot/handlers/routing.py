"""
Routing Handler - маршрутизация A/B/TRASH и обработка каждого flow
"""
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from freelance_bot.states import FreelanceStates
from freelance_bot.keyboards.inline import (
    get_trash_keyboard,
    get_a_flow_order_keyboard,
    get_b_flow_package_keyboard,
)
from freelance_bot.texts.messages import (
    MSG_A_FLOW_INTRO, MSG_A_BRIEF_TRAFFIC, MSG_A_BRIEF_PAYMENT, MSG_A_BRIEF_STEPS,
    MSG_B_FLOW_INTRO, MSG_B_BRIEF_PRODUCT, MSG_B_BRIEF_OBJECTION, MSG_B_BRIEF_GOAL,
    MSG_B_PACKAGE_SELECT,
    MSG_TRASH_FLOW, MSG_TRASH_CHECKLIST,
    CB_TRASH_RETURN, CB_TRASH_CHECKLIST,
    CB_PACKAGE_PROTOTYPE, CB_PACKAGE_BATTLE,
)
from freelance_bot.services.llm_scoring import ScoringResult

logger = logging.getLogger(__name__)

routing_router = Router(name="routing")


async def route_lead(message: Message, state: FSMContext, scoring: ScoringResult) -> None:
    """
    Маршрутизация лида по результатам скоринга
    
    A_FLOW (70-100): взрослые лиды
    B_FLOW (40-69): можно спасти
    TRASH_FLOW (<40): вежливо выносим
    """
    route = scoring.route
    
    logger.info(f"🚦 Routing user {message.from_user.id}: {route} (score={scoring.score})")
    
    if route == "A_FLOW":
        await handle_a_flow(message, state, scoring)
    elif route == "B_FLOW":
        await handle_b_flow(message, state, scoring)
    else:  # TRASH_FLOW
        await handle_trash_flow(message, state, scoring)


# ============================================================
# A_FLOW - "ВЗРОСЛЫЕ ДЕНЬГИ"
# ============================================================

async def handle_a_flow(message: Message, state: FSMContext, scoring: ScoringResult) -> None:
    """Обработка A_FLOW - взрослые лиды"""
    
    data = await state.get_data()
    goal_label = data.get("goal_label", "результат")
    pain_label = data.get("pain_label", "текущая ситуация")
    
    # Используем ТОЛЬКО фиксированные тексты из ТЗ (НЕ bot_reply от LLM!)
    response_text = MSG_A_FLOW_INTRO.format(
        pain=pain_label,
        goal=goal_label
    )
    
    await state.set_state(FreelanceStates.ROUTE_A)
    await message.answer(response_text)
    
    # Переходим к мини-брифу
    await state.set_state(FreelanceStates.A_BRIEF_TRAFFIC)
    await message.answer(MSG_A_BRIEF_TRAFFIC)


async def handle_b_flow(message: Message, state: FSMContext, scoring: ScoringResult) -> None:
    """Обработка B_FLOW - можно спасти"""
    
    # Используем ТОЛЬКО фиксированные тексты из ТЗ (НЕ bot_reply от LLM!)
    response_text = MSG_B_FLOW_INTRO
    
    await state.set_state(FreelanceStates.ROUTE_B)
    await message.answer(response_text)
    
    # Переходим к уточнению
    await state.set_state(FreelanceStates.B_BRIEF_PRODUCT)
    await message.answer(MSG_B_BRIEF_PRODUCT)


async def handle_trash_flow(message: Message, state: FSMContext, scoring: ScoringResult) -> None:
    """Обработка TRASH_FLOW - вежливо выносим"""
    
    # Используем ТОЛЬКО фиксированные тексты из ТЗ (НЕ bot_reply от LLM!)
    response_text = MSG_TRASH_FLOW
    
    await state.set_state(FreelanceStates.ROUTE_TRASH)
    await message.answer(
        response_text,
        reply_markup=get_trash_keyboard()
    )


# ============================================================
# A_FLOW BRIEF HANDLERS
# ============================================================

@routing_router.message(FreelanceStates.A_BRIEF_TRAFFIC)
async def handle_a_traffic(message: Message, state: FSMContext) -> None:
    """A_FLOW: Канал входа"""
    await state.update_data(a_traffic=message.text.strip())
    await state.set_state(FreelanceStates.A_BRIEF_PAYMENT)
    await message.answer(MSG_A_BRIEF_PAYMENT)


@routing_router.message(FreelanceStates.A_BRIEF_PAYMENT)
async def handle_a_payment(message: Message, state: FSMContext) -> None:
    """A_FLOW: Оплата/CRM"""
    await state.update_data(a_payment=message.text.strip())
    await state.set_state(FreelanceStates.A_BRIEF_STEPS)
    await message.answer(MSG_A_BRIEF_STEPS)


@routing_router.message(FreelanceStates.A_BRIEF_STEPS)
async def handle_a_steps(message: Message, state: FSMContext) -> None:
    """A_FLOW: Шаги до результата - переход к заявке"""
    await state.update_data(a_steps=message.text.strip())
    
    # Переходим к форме заявки
    await state.set_state(FreelanceStates.APPLICATION_FORM)
    
    # Показываем кнопки действий
    await message.answer(
        "Отлично, картину собрал. Выбери следующий шаг:",
        reply_markup=get_a_flow_order_keyboard()
    )


# ============================================================
# B_FLOW BRIEF HANDLERS
# ============================================================

@routing_router.message(FreelanceStates.B_BRIEF_PRODUCT)
async def handle_b_product(message: Message, state: FSMContext) -> None:
    """B_FLOW: Главный продукт"""
    await state.update_data(b_product=message.text.strip())
    await state.set_state(FreelanceStates.B_BRIEF_OBJECTION)
    await message.answer(MSG_B_BRIEF_OBJECTION)


@routing_router.message(FreelanceStates.B_BRIEF_OBJECTION)
async def handle_b_objection(message: Message, state: FSMContext) -> None:
    """B_FLOW: Главное возражение"""
    await state.update_data(b_objection=message.text.strip())
    await state.set_state(FreelanceStates.B_BRIEF_GOAL)
    await message.answer(MSG_B_BRIEF_GOAL)


@routing_router.message(FreelanceStates.B_BRIEF_GOAL)
async def handle_b_goal(message: Message, state: FSMContext) -> None:
    """B_FLOW: Финал (заявка/оплата) - переход к выбору пакета"""
    await state.update_data(b_goal=message.text.strip())
    await state.set_state(FreelanceStates.B_PACKAGE_SELECT)
    await message.answer(
        MSG_B_PACKAGE_SELECT,
        reply_markup=get_b_flow_package_keyboard()
    )


@routing_router.callback_query(
    FreelanceStates.B_PACKAGE_SELECT,
    F.data.in_([CB_PACKAGE_PROTOTYPE, CB_PACKAGE_BATTLE])
)
async def cb_b_package(callback: CallbackQuery, state: FSMContext) -> None:
    """B_FLOW: Выбор пакета"""
    await callback.answer()
    
    package = "prototype" if callback.data == CB_PACKAGE_PROTOTYPE else "battle"
    package_label = "Прототип" if package == "prototype" else "Боевой"
    
    logger.info(f"📦 B_FLOW package: {package_label} from user {callback.from_user.id}")
    
    await state.update_data(b_package=package, b_package_label=package_label)
    
    # Переходим к форме заявки
    await state.set_state(FreelanceStates.APPLICATION_FORM)
    
    await callback.message.edit_text(
        f"Выбран пакет: {package_label}\n\n"
        "Теперь оставь контакты для связи."
    )
    
    # Импортируем и вызываем начало формы заявки
    from freelance_bot.handlers.application import start_application
    await start_application(callback.message, state)


# ============================================================
# TRASH_FLOW HANDLERS
# ============================================================

@routing_router.callback_query(FreelanceStates.ROUTE_TRASH, F.data == CB_TRASH_RETURN)
async def cb_trash_return(callback: CallbackQuery, state: FSMContext) -> None:
    """TRASH: Я уточню и вернусь"""
    await callback.answer("Буду ждать!")
    
    logger.info(f"🔁 TRASH return: user {callback.from_user.id}")
    
    await state.update_data(trash_action="return")
    await state.set_state(FreelanceStates.DONE)
    
    await callback.message.edit_text(
        "Хорошо, возвращайся когда будет:\n"
        "• Понятная ниша\n"
        "• Конкретная цель\n"
        "• Примерный чек\n\n"
        "Напиши /start когда будешь готов."
    )


@routing_router.callback_query(FreelanceStates.ROUTE_TRASH, F.data == CB_TRASH_CHECKLIST)
async def cb_trash_checklist(callback: CallbackQuery, state: FSMContext) -> None:
    """TRASH: Что нужно подготовить?"""
    await callback.answer()
    
    logger.info(f"📋 TRASH checklist: user {callback.from_user.id}")
    
    await state.update_data(trash_action="checklist")
    await state.set_state(FreelanceStates.TRASH_CHECKLIST)
    
    await callback.message.edit_text(MSG_TRASH_CHECKLIST)


@routing_router.message(FreelanceStates.ROUTE_TRASH)
async def handle_trash_text(message: Message, state: FSMContext) -> None:
    """Обработка текста в TRASH_FLOW"""
    await message.answer(
        "Выбери один из вариантов 👆",
        reply_markup=get_trash_keyboard()
    )
