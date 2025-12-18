"""
Premium Handlers для Telegram Bot
Обработчики для управления Премиум-размещением турниров
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

# Создаём роутер для Premium
premium_router = Router()

# Константы цен
PREMIUM_PRICE = 3000  # ₽
PREMIUM_EXTEND_PRICE = 2000  # ₽
PREMIUM_DAY_PRICE = 500  # ₽
PREMIUM_DURATION_DAYS = 7
COOLDOWN_HOURS = 24


class PremiumBotService:
    """Сервис для работы с Premium в боте"""
    
    def __init__(self, backend_client):
        self.backend = backend_client
    
    async def get_premium_status(self, tournament_id: int) -> Dict[str, Any]:
        """Получает статус Premium через API"""
        try:
            url = f"{self.backend.base_url}/api/tournaments/premium/{tournament_id}/status"
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Error getting premium status: {response.status_code}")
                    return {"error": "Не удалось получить статус"}
        except Exception as e:
            logger.error(f"Error getting premium status: {e}")
            return {"error": str(e)}
    
    async def premium_action(self, tournament_id: int, action: str) -> Dict[str, Any]:
        """Выполняет действие с Premium через API"""
        try:
            url = f"{self.backend.base_url}/api/tournaments/premium/{tournament_id}/action"
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={"action": action})
                if response.status_code == 200:
                    return response.json()
                else:
                    error_detail = response.json().get("detail", "Ошибка")
                    return {"success": False, "error": error_detail}
        except Exception as e:
            logger.error(f"Error performing premium action: {e}")
            return {"success": False, "error": str(e)}


def format_premium_status_message(status: Dict[str, Any]) -> str:
    """Форматирует сообщение о статусе Premium"""
    if status.get("error"):
        return f"❌ Ошибка: {status['error']}"
    
    tournament_title = status.get("tournament_title", "Турнир")
    is_active = status.get("is_active", False)
    premium_until_display = status.get("premium_until_display")
    status_type = status.get("status", "inactive")
    
    lines = [f"🏆 **{tournament_title}**", ""]
    
    if is_active:
        lines.append("🔝 **Премиум-размещение активно**")
        lines.append(f"📅 Действует до: {premium_until_display}")
        lines.append("")
        lines.append("Вы можете продлить размещение или докупить дополнительный день.")
    elif status_type == "cooldown":
        lines.append("⏳ **Премиум-размещение недавно завершилось**")
        lines.append("")
        lines.append("Новая покупка будет доступна через 24 часа после окончания предыдущего периода.")
        if status.get("can_buy_reason") == "cooldown":
            available_at = status.get("available_at_display")
            if available_at:
                lines.append(f"📅 Доступно с: {available_at}")
    else:
        lines.append("ℹ️ **Премиум-размещение не активно**")
        lines.append("")
        lines.append("Вы можете приобрести Премиум для повышения видимости турнира.")
    
    return "\n".join(lines)


def build_premium_keyboard(status: Dict[str, Any], tournament_id: int) -> InlineKeyboardBuilder:
    """Создаёт клавиатуру для Premium действий"""
    builder = InlineKeyboardBuilder()
    
    is_active = status.get("is_active", False)
    can_buy = status.get("can_buy", False)
    
    if is_active:
        # Премиум активен - показываем кнопки продления
        builder.button(
            text=f"🔄 Продлить на 7 дней ({PREMIUM_EXTEND_PRICE} ₽)",
            callback_data=f"premium_extend7_{tournament_id}"
        )
        builder.button(
            text=f"➕ Докупить 1 день ({PREMIUM_DAY_PRICE} ₽)",
            callback_data=f"premium_extend1_{tournament_id}"
        )
    elif can_buy:
        # Премиум не активен, но можно купить
        builder.button(
            text=f"🔝 Купить Премиум ({PREMIUM_PRICE} ₽)",
            callback_data=f"premium_buy_{tournament_id}"
        )
    
    # Кнопка статуса всегда доступна
    builder.button(
        text="ℹ️ Статус Премиума",
        callback_data=f"premium_status_{tournament_id}"
    )
    
    builder.adjust(1)  # По одной кнопке в ряд
    return builder


# ========== Обработчики команд ==========

@premium_router.callback_query(F.data.startswith("premium_status_"))
async def handle_premium_status(callback: CallbackQuery, state: FSMContext):
    """Показывает статус Premium для турнира"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        from backend_client import BackendClient
        backend = BackendClient()
        premium_service = PremiumBotService(backend)
        
        status = await premium_service.get_premium_status(tournament_id)
        
        message_text = format_premium_status_message(status)
        keyboard = build_premium_keyboard(status, tournament_id)
        
        await callback.answer()
        await callback.message.edit_text(
            message_text,
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in premium_status handler: {e}")
        await callback.answer("Ошибка при получении статуса", show_alert=True)


@premium_router.callback_query(F.data.startswith("premium_buy_"))
async def handle_premium_buy(callback: CallbackQuery, state: FSMContext):
    """Покупка Premium (7 дней)"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        from backend_client import BackendClient
        backend = BackendClient()
        premium_service = PremiumBotService(backend)
        
        # Показываем подтверждение
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"✅ Подтвердить покупку ({PREMIUM_PRICE} ₽)",
            callback_data=f"premium_confirm_buy_{tournament_id}"
        )
        builder.button(
            text="❌ Отмена",
            callback_data=f"premium_status_{tournament_id}"
        )
        builder.adjust(1)
        
        await callback.answer()
        await callback.message.edit_text(
            f"🔝 **Покупка Премиум-размещения**\n\n"
            f"💰 Стоимость: {PREMIUM_PRICE} ₽\n"
            f"📅 Срок: {PREMIUM_DURATION_DAYS} дней\n\n"
            f"Премиум-размещение повышает видимость турнира в поиске.\n\n"
            f"Подтвердите покупку:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in premium_buy handler: {e}")
        await callback.answer("Ошибка", show_alert=True)


@premium_router.callback_query(F.data.startswith("premium_confirm_buy_"))
async def handle_premium_confirm_buy(callback: CallbackQuery, state: FSMContext):
    """Подтверждение покупки Premium"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        from backend_client import BackendClient
        backend = BackendClient()
        premium_service = PremiumBotService(backend)
        
        result = await premium_service.premium_action(tournament_id, "activate")
        
        if result.get("success"):
            await callback.answer("✅ Премиум активирован!", show_alert=True)
            
            # Показываем обновлённый статус
            status = await premium_service.get_premium_status(tournament_id)
            message_text = format_premium_status_message(status)
            keyboard = build_premium_keyboard(status, tournament_id)
            
            await callback.message.edit_text(
                f"✅ **Премиум успешно активирован!**\n\n{message_text}",
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
        else:
            error = result.get("error", "Неизвестная ошибка")
            await callback.answer(f"❌ {error}", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in premium_confirm_buy handler: {e}")
        await callback.answer("Ошибка при активации", show_alert=True)


@premium_router.callback_query(F.data.startswith("premium_extend7_"))
async def handle_premium_extend7(callback: CallbackQuery, state: FSMContext):
    """Продление Premium на 7 дней"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        # Показываем подтверждение
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"✅ Подтвердить ({PREMIUM_EXTEND_PRICE} ₽)",
            callback_data=f"premium_confirm_ext7_{tournament_id}"
        )
        builder.button(
            text="❌ Отмена",
            callback_data=f"premium_status_{tournament_id}"
        )
        builder.adjust(1)
        
        await callback.answer()
        await callback.message.edit_text(
            f"🔄 **Продление Премиума на 7 дней**\n\n"
            f"💰 Стоимость: {PREMIUM_EXTEND_PRICE} ₽\n\n"
            f"Срок действия будет увеличен на 7 дней от текущей даты окончания.\n\n"
            f"Подтвердите продление:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in premium_extend7 handler: {e}")
        await callback.answer("Ошибка", show_alert=True)


@premium_router.callback_query(F.data.startswith("premium_confirm_ext7_"))
async def handle_premium_confirm_ext7(callback: CallbackQuery, state: FSMContext):
    """Подтверждение продления на 7 дней"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        from backend_client import BackendClient
        backend = BackendClient()
        premium_service = PremiumBotService(backend)
        
        result = await premium_service.premium_action(tournament_id, "extend_7days")
        
        if result.get("success"):
            await callback.answer("✅ Премиум продлён!", show_alert=True)
            
            status = await premium_service.get_premium_status(tournament_id)
            message_text = format_premium_status_message(status)
            keyboard = build_premium_keyboard(status, tournament_id)
            
            await callback.message.edit_text(
                f"✅ **Премиум успешно продлён!**\n\n{message_text}",
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
        else:
            error = result.get("error", "Неизвестная ошибка")
            await callback.answer(f"❌ {error}", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in premium_confirm_ext7 handler: {e}")
        await callback.answer("Ошибка при продлении", show_alert=True)


@premium_router.callback_query(F.data.startswith("premium_extend1_"))
async def handle_premium_extend1(callback: CallbackQuery, state: FSMContext):
    """Докупка 1 дня Premium"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"✅ Подтвердить ({PREMIUM_DAY_PRICE} ₽)",
            callback_data=f"premium_confirm_ext1_{tournament_id}"
        )
        builder.button(
            text="❌ Отмена",
            callback_data=f"premium_status_{tournament_id}"
        )
        builder.adjust(1)
        
        await callback.answer()
        await callback.message.edit_text(
            f"➕ **Докупка 1 дня Премиума**\n\n"
            f"💰 Стоимость: {PREMIUM_DAY_PRICE} ₽\n\n"
            f"Срок действия будет увеличен на 1 день.\n\n"
            f"Подтвердите докупку:",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in premium_extend1 handler: {e}")
        await callback.answer("Ошибка", show_alert=True)


@premium_router.callback_query(F.data.startswith("premium_confirm_ext1_"))
async def handle_premium_confirm_ext1(callback: CallbackQuery, state: FSMContext):
    """Подтверждение докупки 1 дня"""
    try:
        tournament_id = int(callback.data.split("_")[-1])
        
        from backend_client import BackendClient
        backend = BackendClient()
        premium_service = PremiumBotService(backend)
        
        result = await premium_service.premium_action(tournament_id, "extend_1day")
        
        if result.get("success"):
            await callback.answer("✅ День добавлен!", show_alert=True)
            
            status = await premium_service.get_premium_status(tournament_id)
            message_text = format_premium_status_message(status)
            keyboard = build_premium_keyboard(status, tournament_id)
            
            await callback.message.edit_text(
                f"✅ **День успешно добавлен!**\n\n{message_text}",
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
        else:
            error = result.get("error", "Неизвестная ошибка")
            await callback.answer(f"❌ {error}", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error in premium_confirm_ext1 handler: {e}")
        await callback.answer("Ошибка при докупке", show_alert=True)


# ========== Вспомогательные функции для интеграции ==========

def get_premium_info_text(is_premium: bool, premium_until: Optional[str]) -> str:
    """Возвращает текст о Premium статусе для карточки турнира"""
    if not is_premium:
        return ""
    
    if premium_until:
        try:
            dt = datetime.fromisoformat(premium_until.replace('Z', '+00:00'))
            date_str = dt.strftime('%d.%m.%Y')
            return f"🔝 Премиум до {date_str}"
        except:
            return "🔝 Премиум"
    
    return "🔝 Премиум"


def add_premium_button_to_tournament(
    builder: InlineKeyboardBuilder, 
    tournament_id: int,
    is_organizer: bool = False
) -> InlineKeyboardBuilder:
    """Добавляет кнопку Premium к клавиатуре турнира (только для организаторов)"""
    if is_organizer:
        builder.button(
            text="🔝 Премиум-размещение",
            callback_data=f"premium_status_{tournament_id}"
        )
    return builder
