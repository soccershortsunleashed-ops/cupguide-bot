"""
Форматтер для личного кабинета организатора.
Форматирует данные турниров, статусов и аналитики для отображения в Telegram.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


class PremiumAvailability:
    """Информация о доступности премиума для покупки"""
    def __init__(
        self,
        can_buy: bool = False,
        can_extend: bool = False,
        restriction_ends_at: Optional[datetime] = None,
        is_active: bool = False,
        active_until: Optional[datetime] = None
    ):
        self.can_buy = can_buy
        self.can_extend = can_extend
        self.restriction_ends_at = restriction_ends_at
        self.is_active = is_active
        self.active_until = active_until


class CabinetFormatter:
    """Форматирование данных для личного кабинета организатора"""
    
    @staticmethod
    def format_status_rating(rating_until: Optional[str]) -> str:
        """
        Форматирует статус рейтинга турнира.
        
        Args:
            rating_until: Дата окончания рейтинга (YYYY-MM-DD) или None
        
        Returns:
            Строка статуса: "⭐ Рейтинг: Активен до DD.MM.YYYY" или "⭐ Рейтинг: Не активен"
        """
        if not rating_until:
            return "⭐ Рейтинг: Не активен"
        
        try:
            end_date = datetime.strptime(rating_until, "%Y-%m-%d")
            if end_date > datetime.now():
                formatted_date = end_date.strftime("%d.%m.%Y")
                return f"⭐ Рейтинг: Активен до {formatted_date}"
            else:
                return "⭐ Рейтинг: Не активен"
        except ValueError:
            return "⭐ Рейтинг: Не активен"
    
    @staticmethod
    def format_status_premium(
        premium_until: Optional[str], 
        premium_last_ended: Optional[str] = None
    ) -> str:
        """
        Форматирует статус премиума турнира.
        
        Args:
            premium_until: Дата окончания премиума (YYYY-MM-DD) или None
            premium_last_ended: Дата окончания предыдущего премиума (для 24ч ограничения)
        
        Returns:
            Строка статуса с информацией о доступности
        """
        now = datetime.now()
        
        # Проверяем активный премиум
        if premium_until:
            try:
                end_date = datetime.strptime(premium_until, "%Y-%m-%d")
                if end_date > now:
                    formatted_date = end_date.strftime("%d.%m.%Y")
                    return f"🔝 Премиум: Активен до {formatted_date}"
            except ValueError:
                pass
        
        # Премиум не активен - проверяем 24-часовое ограничение
        if premium_last_ended:
            try:
                last_ended = datetime.strptime(premium_last_ended, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    last_ended = datetime.strptime(premium_last_ended, "%Y-%m-%d")
                except ValueError:
                    return "🔝 Премиум: Не активен"
            
            restriction_ends = last_ended + timedelta(hours=24)
            if restriction_ends > now:
                # Ещё действует ограничение
                remaining = restriction_ends - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return f"🔝 Премиум: Не активен\n⏳ Доступно для покупки через {hours}ч {minutes}мин"
        
        return "🔝 Премиум: Не активен"
    
    @staticmethod
    def check_premium_availability(
        premium_until: Optional[str],
        premium_last_ended: Optional[str] = None
    ) -> PremiumAvailability:
        """
        Проверяет доступность премиума для покупки/продления.
        
        Args:
            premium_until: Дата окончания премиума
            premium_last_ended: Дата окончания предыдущего премиума
        
        Returns:
            PremiumAvailability с информацией о доступных действиях
        """
        now = datetime.now()
        result = PremiumAvailability()
        
        # Проверяем активный премиум
        if premium_until:
            try:
                end_date = datetime.strptime(premium_until, "%Y-%m-%d")
                if end_date > now:
                    result.is_active = True
                    result.active_until = end_date
                    result.can_extend = True
                    return result
            except ValueError:
                pass
        
        # Премиум не активен - проверяем 24-часовое ограничение
        if premium_last_ended:
            try:
                last_ended = datetime.strptime(premium_last_ended, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    last_ended = datetime.strptime(premium_last_ended, "%Y-%m-%d")
                except ValueError:
                    result.can_buy = True
                    return result
            
            restriction_ends = last_ended + timedelta(hours=24)
            if restriction_ends > now:
                result.restriction_ends_at = restriction_ends
                result.can_buy = False
            else:
                result.can_buy = True
        else:
            result.can_buy = True
        
        return result
    
    @staticmethod
    def format_tournament_card(
        tournament: Dict[str, Any],
        campaign_progress: Optional[str] = None
    ) -> str:
        """
        Форматирует карточку турнира для списка "Мои турниры".
        
        Args:
            tournament: Данные турнира
            campaign_progress: Строка прогресса нативной кампании
        
        Returns:
            Отформатированная строка карточки
        """
        title = tournament.get("title", "Турнир")
        city = tournament.get("city", "")
        start_date = tournament.get("start_date", "")
        
        # Форматируем дату
        date_str = ""
        if start_date:
            try:
                date_obj = datetime.strptime(start_date, "%Y-%m-%d")
                date_str = date_obj.strftime("%d.%m.%Y")
            except ValueError:
                date_str = start_date
        
        # Статусы
        rating_status = CabinetFormatter.format_status_rating(
            tournament.get("rating_until")
        )
        premium_status = CabinetFormatter.format_status_premium(
            tournament.get("premium_until"),
            tournament.get("premium_last_ended")
        )
        
        # Формируем карточку
        lines = [
            f"🏆 {title}",
            f"📅 {date_str}" if date_str else "",
            f"📍 {city}" if city else "",
            "",
            rating_status,
            premium_status,
        ]
        
        if campaign_progress:
            lines.append(campaign_progress)
        
        return "\n".join(line for line in lines if line)
    
    @staticmethod
    def format_tournaments_list(
        tournaments: List[Dict[str, Any]],
        campaigns: Optional[Dict[int, str]] = None
    ) -> str:
        """
        Форматирует список турниров организатора.
        
        Args:
            tournaments: Список турниров
            campaigns: Словарь {tournament_id: progress_string}
        
        Returns:
            Отформатированный список
        """
        if not tournaments:
            return "У вас нет турниров в системе"
        
        campaigns = campaigns or {}
        
        lines = [f"📋 Мои турниры ({len(tournaments)})\n"]
        
        for i, t in enumerate(tournaments, 1):
            tournament_id = t.get("id")
            campaign_progress = campaigns.get(tournament_id)
            
            card = CabinetFormatter.format_tournament_card(t, campaign_progress)
            lines.append(f"━━━ {i} ━━━")
            lines.append(card)
            lines.append("")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_analytics(analytics_data: Dict[str, Any], tournament_id: int = None) -> str:
        """
        Форматирует аналитику турнира.
        
        Args:
            analytics_data: Агрегированные данные аналитики
            tournament_id: ID турнира для короткой ссылки
        
        Returns:
            Отформатированная строка аналитики
        """
        impressions_7d = analytics_data.get("impressions_7d", 0)
        impressions_30d = analytics_data.get("impressions_30d", 0)
        clicks_7d = analytics_data.get("clicks_7d", 0)
        clicks_30d = analytics_data.get("clicks_30d", 0)
        clicks_by_source = analytics_data.get("clicks_by_source", {})
        utm_breakdown = analytics_data.get("utm_breakdown", [])
        
        if impressions_30d == 0 and clicks_30d == 0:
            return "📊 Данные аналитики пока недоступны"
        
        lines = [
            "📊 Аналитика турнира\n",
        ]
        
        # Добавляем короткую ссылку если есть tournament_id
        if tournament_id:
            # TODO: заменить на реальный домен в продакшене
            short_url = f"http://127.0.0.1:8000/t/{tournament_id}"
            lines.append(f"🔗 Короткая ссылка: {short_url}")
            lines.append("")
        
        lines.extend([
            "👁 Показы:",
            f"   За 7 дней: {impressions_7d}",
            f"   За 30 дней: {impressions_30d}",
            "",
            "🖱 Клики:",
            f"   За 7 дней: {clicks_7d}",
            f"   За 30 дней: {clicks_30d}",
            "",
            "📍 Источники кликов (30 дней):",
        ])
        
        for source, count in clicks_by_source.items():
            source_name = {
                "bot_search": "Поиск в боте",
                "tg_channel": "Telegram канал",
                "mailing": "Рассылка",
                "telegraph": "Telegraph страница"
            }.get(source, source)
            lines.append(f"   {source_name}: {count}")
        
        if utm_breakdown:
            lines.append("")
            lines.append("🏷 UTM-кампании:")
            for utm in utm_breakdown[:5]:  # Топ 5
                campaign = utm.get("utm_campaign", "-")
                clicks = utm.get("clicks", 0)
                lines.append(f"   {campaign}: {clicks} кликов")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_native_progress(campaign: Optional[Dict[str, Any]]) -> str:
        """
        Форматирует прогресс нативной кампании.
        
        Args:
            campaign: Данные кампании или None
        
        Returns:
            Строка прогресса
        """
        if not campaign:
            return "Натив: не активен"
        
        status = campaign.get("status", "active")
        done_count = campaign.get("done_count", 0)
        
        if status == "completed" or done_count >= 3:
            return "✅ Кампания завершена"
        
        return f"🟢 Натив: {done_count}/3 выполнено"
    
    @staticmethod
    def build_tournament_keyboard(tournament_id: int) -> InlineKeyboardMarkup:
        """
        Строит клавиатуру для карточки турнира в списке.
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            InlineKeyboardMarkup с кнопками
        """
        builder = InlineKeyboardBuilder()
        builder.button(
            text="📊 Открыть аналитику",
            callback_data=f"cabinet_analytics_{tournament_id}"
        )
        builder.button(
            text="⚙️ Управлять продвижением",
            callback_data=f"cabinet_promotion_{tournament_id}"
        )
        builder.button(
            text="🚪 Выйти из кабинета",
            callback_data="cabinet_exit"
        )
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def build_promotion_keyboard(
        tournament_id: int,
        availability: PremiumAvailability
    ) -> InlineKeyboardMarkup:
        """
        Строит клавиатуру для управления продвижением.
        
        Args:
            tournament_id: ID турнира
            availability: Информация о доступности премиума
        
        Returns:
            InlineKeyboardMarkup с кнопками покупки/продления
        """
        builder = InlineKeyboardBuilder()
        
        if availability.can_buy:
            builder.button(
                text="💎 Купить премиум 7 дней",
                callback_data=f"cabinet_buy_premium_{tournament_id}"
            )
        
        if availability.can_extend:
            builder.button(
                text="🔄 Продлить 7 дней",
                callback_data=f"cabinet_extend_premium_{tournament_id}"
            )
            builder.button(
                text="➕ +1 день",
                callback_data=f"cabinet_add_day_{tournament_id}"
            )
        
        builder.button(
            text="⭐ Купить рейтинг 45 дней",
            callback_data=f"cabinet_buy_rating_{tournament_id}"
        )
        builder.button(
            text="📢 Заказать 3 нативных упоминания",
            callback_data=f"cabinet_buy_native_{tournament_id}"
        )
        builder.button(
            text="🔗 Открыть карточку турнира",
            callback_data=f"cabinet_open_card_{tournament_id}"
        )
        builder.button(
            text="📋 Скопировать ссылку с UTM",
            callback_data=f"cabinet_copy_utm_{tournament_id}"
        )
        builder.button(
            text="◀️ Назад",
            callback_data="cabinet_back"
        )
        
        builder.adjust(1)
        return builder.as_markup()
