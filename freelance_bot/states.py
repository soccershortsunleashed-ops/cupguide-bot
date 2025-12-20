"""
FSM States - состояния конечного автомата для фриланс-воронки

Переходы:
ENTRY → (Поехали) → Q1 → Q2 → Q3 → NICHE_TEXT → LLM_SCORING → ROUTE_* → APPLICATION_FORM → DONE
ENTRY → (Сразу цена) → ENTRY_PRICE_GUARD → (Поехали) → Q1…
"""
from aiogram.fsm.state import State, StatesGroup


class FreelanceStates(StatesGroup):
    """Состояния FSM для фриланс-воронки"""
    
    # === ВХОД ===
    ENTRY = State()  # Вход/первое сообщение + кнопки (Поехали/Сразу цена/Посмотреть)
    ENTRY_PRICE_GUARD = State()  # Ветка "Сразу цена" - отсечка демпинга
    
    # === СКРИНИНГ (3 вопроса) ===
    SCREEN_Q1_GOAL = State()  # Вопрос 1: Что бот должен принести?
    SCREEN_Q2_PAIN = State()  # Вопрос 2: Где сейчас всё разваливается?
    SCREEN_Q3_CONTEXT = State()  # Вопрос 3: Что уже есть?
    
    # === СБОР ДАННЫХ ===
    COLLECT_NICHE_TEXT = State()  # Сбор "ниша+продукт+чек" (текст)
    
    # === LLM СКОРИНГ ===
    LLM_SCORING = State()  # Вызов LLM + детерминированная проверка
    
    # === МАРШРУТИЗАЦИЯ ===
    ROUTE_A = State()  # A_FLOW - взрослые лиды (70-100)
    ROUTE_B = State()  # B_FLOW - можно спасти (40-69)
    ROUTE_TRASH = State()  # TRASH_FLOW - мусор (<40)
    
    # === A_FLOW: Мини-бриф ===
    A_BRIEF_TRAFFIC = State()  # Канал входа: трафик откуда?
    A_BRIEF_PAYMENT = State()  # Оплата/CRM: что используешь?
    A_BRIEF_STEPS = State()  # Сколько шагов до результата?
    
    # === B_FLOW: Уточнение ===
    B_BRIEF_PRODUCT = State()  # Один главный продукт?
    B_BRIEF_OBJECTION = State()  # Самое частое возражение?
    B_BRIEF_GOAL = State()  # Куда ведём: заявка или оплата?
    B_PACKAGE_SELECT = State()  # Выбор пакета (Прототип/Боевой)
    
    # === TRASH_FLOW ===
    TRASH_CHOICE = State()  # Выбор: "Я уточню" / "Что подготовить?"
    TRASH_CHECKLIST = State()  # Показ чек-листа
    
    # === ЗАЯВКА ===
    APPLICATION_FORM = State()  # Сбор заявки (контакт, ссылка, платформа, окно старта)
    APPLICATION_CONTACT = State()  # Контакт: @username / телефон
    APPLICATION_LINK = State()  # Ссылка на проект/сайт/канал
    APPLICATION_PLATFORM = State()  # Где будет бот: TG/сайт/везде
    APPLICATION_START_WINDOW = State()  # Окно старта: когда запуск
    
    # === ЗАВЕРШЕНИЕ ===
    DONE = State()  # Завершение/фиксация
    
    # === СПЕЦИАЛЬНЫЕ ===
    ANTI_DUMPING = State()  # Анти-демпинг ответ (при "сколько стоит?")


# Маппинг состояний на названия для логирования
STATE_NAMES = {
    FreelanceStates.ENTRY: "entry",
    FreelanceStates.ENTRY_PRICE_GUARD: "entry_price_guard",
    FreelanceStates.SCREEN_Q1_GOAL: "screen_q1_goal",
    FreelanceStates.SCREEN_Q2_PAIN: "screen_q2_pain",
    FreelanceStates.SCREEN_Q3_CONTEXT: "screen_q3_context",
    FreelanceStates.COLLECT_NICHE_TEXT: "collect_niche_text",
    FreelanceStates.LLM_SCORING: "llm_scoring",
    FreelanceStates.ROUTE_A: "route_a",
    FreelanceStates.ROUTE_B: "route_b",
    FreelanceStates.ROUTE_TRASH: "route_trash",
    FreelanceStates.A_BRIEF_TRAFFIC: "a_brief_traffic",
    FreelanceStates.A_BRIEF_PAYMENT: "a_brief_payment",
    FreelanceStates.A_BRIEF_STEPS: "a_brief_steps",
    FreelanceStates.B_BRIEF_PRODUCT: "b_brief_product",
    FreelanceStates.B_BRIEF_OBJECTION: "b_brief_objection",
    FreelanceStates.B_BRIEF_GOAL: "b_brief_goal",
    FreelanceStates.B_PACKAGE_SELECT: "b_package_select",
    FreelanceStates.TRASH_CHOICE: "trash_choice",
    FreelanceStates.TRASH_CHECKLIST: "trash_checklist",
    FreelanceStates.APPLICATION_FORM: "application_form",
    FreelanceStates.APPLICATION_CONTACT: "application_contact",
    FreelanceStates.APPLICATION_LINK: "application_link",
    FreelanceStates.APPLICATION_PLATFORM: "application_platform",
    FreelanceStates.APPLICATION_START_WINDOW: "application_start_window",
    FreelanceStates.DONE: "done",
    FreelanceStates.ANTI_DUMPING: "anti_dumping",
}
