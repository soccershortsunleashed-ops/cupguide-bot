"""
Screening Handler - обработка скрининга (Q1/Q2/Q3) и сбора niche_text
"""
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from freelance_bot.states import FreelanceStates
from freelance_bot.keyboards.inline import (
    get_q1_goal_keyboard,
    get_q2_pain_keyboard,
    get_q3_context_keyboard,
)
from freelance_bot.texts.messages import (
    MSG_Q1_GOAL, MSG_Q2_PAIN, MSG_Q3_CONTEXT, MSG_COLLECT_NICHE,
    MSG_DEMO_INTRO, MSG_DEMO_TEMPLATE, MSG_ANTI_DUMPING,
    # Q1 callbacks
    CB_GOAL_SALES, CB_GOAL_LEADS, CB_GOAL_BASE, CB_GOAL_SUPPORT, CB_GOAL_JUST_BOT,
    # Q2 callbacks
    CB_PAIN_TRAFFIC, CB_PAIN_DIALOG, CB_PAIN_PAYMENT, CB_PAIN_INTEGRATION, CB_PAIN_CHAOS,
    # Q3 callbacks
    CB_CONTEXT_SCRATCH, CB_CONTEXT_CONSTRUCTOR, CB_CONTEXT_HAS_BOT, CB_CONTEXT_HAS_CRM,
    # Maps
    GOAL_MAP, PAIN_MAP, CONTEXT_MAP,
)
from freelance_bot.services.llm_scoring import llm_scoring_service
from freelance_bot.services.deterministic_scoring import deterministic_scoring
from freelance_bot.handlers.entry import is_price_question

logger = logging.getLogger(__name__)

screening_router = Router(name="screening")


# ============================================================
# Q1: ЦЕЛЬ
# ============================================================

@screening_router.callback_query(
    FreelanceStates.SCREEN_Q1_GOAL,
    F.data.in_([CB_GOAL_SALES, CB_GOAL_LEADS, CB_GOAL_BASE, CB_GOAL_SUPPORT, CB_GOAL_JUST_BOT])
)
async def cb_q1_goal(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка ответа на Q1: Цель"""
    await callback.answer()
    
    # Получаем значение из маппинга
    goal_key, goal_label = GOAL_MAP.get(callback.data, ("unknown", "Неизвестно"))
    
    logger.info(f"🎯 Q1 Goal: {goal_label} from user {callback.from_user.id}")
    
    # Сохраняем в FSM
    await state.update_data(goal=goal_key, goal_label=goal_label)
    
    # Переходим к Q2
    await state.set_state(FreelanceStates.SCREEN_Q2_PAIN)
    
    await callback.message.edit_text(
        MSG_Q2_PAIN,
        reply_markup=get_q2_pain_keyboard()
    )


@screening_router.message(FreelanceStates.SCREEN_Q1_GOAL)
async def handle_q1_text(message: Message, state: FSMContext) -> None:
    """Обработка текста в Q1"""
    if is_price_question(message.text):
        await message.answer(MSG_ANTI_DUMPING)
        return
    
    await message.answer(
        "Выбери один из вариантов 👆",
        reply_markup=get_q1_goal_keyboard()
    )


# ============================================================
# Q2: БОЛЬ
# ============================================================

@screening_router.callback_query(
    FreelanceStates.SCREEN_Q2_PAIN,
    F.data.in_([CB_PAIN_TRAFFIC, CB_PAIN_DIALOG, CB_PAIN_PAYMENT, CB_PAIN_INTEGRATION, CB_PAIN_CHAOS])
)
async def cb_q2_pain(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка ответа на Q2: Боль"""
    await callback.answer()
    
    # Получаем значение из маппинга
    pain_key, pain_label = PAIN_MAP.get(callback.data, ("unknown", "Неизвестно"))
    
    logger.info(f"💔 Q2 Pain: {pain_label} from user {callback.from_user.id}")
    
    # Сохраняем в FSM
    await state.update_data(pain=pain_key, pain_label=pain_label)
    
    # Переходим к Q3
    await state.set_state(FreelanceStates.SCREEN_Q3_CONTEXT)
    
    await callback.message.edit_text(
        MSG_Q3_CONTEXT,
        reply_markup=get_q3_context_keyboard()
    )


@screening_router.message(FreelanceStates.SCREEN_Q2_PAIN)
async def handle_q2_text(message: Message, state: FSMContext) -> None:
    """Обработка текста в Q2"""
    if is_price_question(message.text):
        await message.answer(MSG_ANTI_DUMPING)
        return
    
    await message.answer(
        "Выбери один из вариантов 👆",
        reply_markup=get_q2_pain_keyboard()
    )


# ============================================================
# Q3: КОНТЕКСТ
# ============================================================

@screening_router.callback_query(
    FreelanceStates.SCREEN_Q3_CONTEXT,
    F.data.in_([CB_CONTEXT_SCRATCH, CB_CONTEXT_CONSTRUCTOR, CB_CONTEXT_HAS_BOT, CB_CONTEXT_HAS_CRM])
)
async def cb_q3_context(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка ответа на Q3: Контекст"""
    await callback.answer()
    
    # Получаем значение из маппинга
    context_key, context_label = CONTEXT_MAP.get(callback.data, ("unknown", "Неизвестно"))
    
    logger.info(f"📦 Q3 Context: {context_label} from user {callback.from_user.id}")
    
    # Сохраняем в FSM
    await state.update_data(context=context_key, context_label=context_label)
    
    # Переходим к сбору niche_text
    await state.set_state(FreelanceStates.COLLECT_NICHE_TEXT)
    
    await callback.message.edit_text(MSG_COLLECT_NICHE)


@screening_router.message(FreelanceStates.SCREEN_Q3_CONTEXT)
async def handle_q3_text(message: Message, state: FSMContext) -> None:
    """Обработка текста в Q3"""
    if is_price_question(message.text):
        await message.answer(MSG_ANTI_DUMPING)
        return
    
    await message.answer(
        "Выбери один из вариантов 👆",
        reply_markup=get_q3_context_keyboard()
    )


# ============================================================
# СБОР NICHE_TEXT
# ============================================================

@screening_router.message(FreelanceStates.COLLECT_NICHE_TEXT)
async def handle_niche_text(message: Message, state: FSMContext) -> None:
    """Обработка ввода ниша+продукт+чек"""
    
    # Проверяем на вопрос о цене
    if is_price_question(message.text):
        await message.answer(MSG_ANTI_DUMPING)
        await message.answer(MSG_COLLECT_NICHE)
        return
    
    niche_text = message.text.strip()
    
    # Проверяем минимальную длину
    if len(niche_text) < 5:
        await message.answer(
            "Слишком коротко. Напиши хотя бы: ниша, продукт, примерный чек.\n"
            "Пример: \"онлайн-школа, курс, 20 000\""
        )
        return
    
    logger.info(f"📝 Niche text from user {message.from_user.id}: {niche_text[:50]}...")
    
    # Сохраняем в FSM
    await state.update_data(niche_text=niche_text)
    
    # Получаем все данные для скоринга
    data = await state.get_data()
    goal = data.get("goal", "")
    pain = data.get("pain", "")
    context = data.get("context", "")
    
    # Показываем "товар лицом" - демонстрацию структуры
    goal_label = data.get("goal_label", goal)
    pain_label = data.get("pain_label", pain)
    
    demo_text = MSG_DEMO_INTRO + "\n\n" + MSG_DEMO_TEMPLATE.format(
        goal=goal_label,
        pain=pain_label
    )
    await message.answer(demo_text)
    
    # Переходим к LLM скорингу
    await state.set_state(FreelanceStates.LLM_SCORING)
    
    # Показываем индикатор "думаю"
    thinking_msg = await message.answer("🧠 Анализирую твою задачу...")
    
    try:
        # Запускаем LLM скоринг
        llm_result = await llm_scoring_service.score_lead(
            goal=goal,
            pain=pain,
            context=context,
            niche_text=niche_text
        )
        
        # Запускаем детерминированный скоринг для сравнения
        det_result = deterministic_scoring.calculate(
            goal=goal,
            pain=pain,
            context=context,
            niche_text=niche_text
        )
        
        # Сравниваем результаты
        match, comparison_note = deterministic_scoring.compare_with_llm(
            det_result.grade,
            llm_result.grade
        )
        
        if not match:
            logger.warning(f"⚠️ Scoring mismatch: {comparison_note}")
        
        # Сохраняем результаты в FSM
        await state.update_data(
            llm_grade=llm_result.grade,
            llm_score=llm_result.score,
            llm_reason=llm_result.reason,
            llm_must_have=llm_result.must_have,
            llm_next_questions=llm_result.next_questions,
            llm_bot_reply=llm_result.bot_reply,
            llm_route=llm_result.route,
            llm_raw_json=llm_result.raw_json,
            deterministic_score=det_result.score,
            deterministic_grade=det_result.grade,
            final_route=llm_result.route,  # Используем LLM route
        )
        
        # Удаляем сообщение "думаю"
        await thinking_msg.delete()
        
        # Переходим к маршрутизации
        from freelance_bot.handlers.routing import route_lead
        await route_lead(message, state, llm_result)
        
    except Exception as e:
        logger.error(f"❌ Scoring error: {e}")
        await thinking_msg.edit_text(
            "⚠️ Произошла ошибка при анализе. Попробуем ещё раз.\n"
            "Напиши свою нишу, продукт и средний чек:"
        )
        await state.set_state(FreelanceStates.COLLECT_NICHE_TEXT)
