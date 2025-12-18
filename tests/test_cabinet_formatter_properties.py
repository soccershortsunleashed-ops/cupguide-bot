"""
Property-based тесты для CabinetFormatter.

Тестирует:
- Property 5: Rating Status Display Correctness
- Property 6: Premium Status Display Correctness
- Property 7: Premium 24-Hour Restriction Display
- Property 4: Tournament Card Contains Required Fields
- Property 8: Premium Button Availability
"""
import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from telegram_bot.cabinet_formatter import CabinetFormatter, PremiumAvailability


# Стратегии для генерации дат
future_dates = st.dates(
    min_value=datetime.now().date() + timedelta(days=1),
    max_value=datetime.now().date() + timedelta(days=365)
)
past_dates = st.dates(
    min_value=datetime.now().date() - timedelta(days=365),
    max_value=datetime.now().date() - timedelta(days=1)
)


class TestRatingStatusDisplayCorrectness:
    """
    **Feature: organizer-cabinet, Property 5: Rating Status Display Correctness**
    **Validates: Requirements 7.1, 7.2**
    
    Для любого турнира, если rating_until — будущая дата, статус должен показывать
    "⭐ Рейтинг: Активен до [date]"; иначе "⭐ Рейтинг: Не активен".
    """
    
    @given(future_date=future_dates)
    @settings(max_examples=100)
    def test_rating_active_for_future_date(self, future_date):
        """
        Property: Будущая дата rating_until показывает "Активен до".
        
        **Feature: organizer-cabinet, Property 5: Rating Status Display Correctness**
        **Validates: Requirements 7.1**
        """
        date_str = future_date.strftime("%Y-%m-%d")
        result = CabinetFormatter.format_status_rating(date_str)
        
        assert "⭐ Рейтинг: Активен до" in result
        assert future_date.strftime("%d.%m.%Y") in result
    
    @given(past_date=past_dates)
    @settings(max_examples=100)
    def test_rating_inactive_for_past_date(self, past_date):
        """
        Property: Прошедшая дата rating_until показывает "Не активен".
        
        **Feature: organizer-cabinet, Property 5: Rating Status Display Correctness**
        **Validates: Requirements 7.2**
        """
        date_str = past_date.strftime("%Y-%m-%d")
        result = CabinetFormatter.format_status_rating(date_str)
        
        assert result == "⭐ Рейтинг: Не активен"
    
    def test_rating_inactive_for_none(self):
        """
        Property: None rating_until показывает "Не активен".
        
        **Feature: organizer-cabinet, Property 5: Rating Status Display Correctness**
        **Validates: Requirements 7.2**
        """
        result = CabinetFormatter.format_status_rating(None)
        assert result == "⭐ Рейтинг: Не активен"


class TestPremiumStatusDisplayCorrectness:
    """
    **Feature: organizer-cabinet, Property 6: Premium Status Display Correctness**
    **Validates: Requirements 7.3, 7.4**
    
    Для любого турнира, если premium_until — будущая дата, статус должен показывать
    "🔝 Премиум: Активен до [date]"; иначе "🔝 Премиум: Не активен".
    """
    
    @given(future_date=future_dates)
    @settings(max_examples=100)
    def test_premium_active_for_future_date(self, future_date):
        """
        Property: Будущая дата premium_until показывает "Активен до".
        
        **Feature: organizer-cabinet, Property 6: Premium Status Display Correctness**
        **Validates: Requirements 7.3**
        """
        date_str = future_date.strftime("%Y-%m-%d")
        result = CabinetFormatter.format_status_premium(date_str)
        
        assert "🔝 Премиум: Активен до" in result
        assert future_date.strftime("%d.%m.%Y") in result
    
    @given(past_date=past_dates)
    @settings(max_examples=100)
    def test_premium_inactive_for_past_date(self, past_date):
        """
        Property: Прошедшая дата premium_until показывает "Не активен".
        
        **Feature: organizer-cabinet, Property 6: Premium Status Display Correctness**
        **Validates: Requirements 7.4**
        """
        date_str = past_date.strftime("%Y-%m-%d")
        result = CabinetFormatter.format_status_premium(date_str)
        
        assert "🔝 Премиум: Не активен" in result
    
    def test_premium_inactive_for_none(self):
        """
        Property: None premium_until показывает "Не активен".
        
        **Feature: organizer-cabinet, Property 6: Premium Status Display Correctness**
        **Validates: Requirements 7.4**
        """
        result = CabinetFormatter.format_status_premium(None)
        assert result == "🔝 Премиум: Не активен"


class TestPremium24HourRestrictionDisplay:
    """
    **Feature: organizer-cabinet, Property 7: Premium 24-Hour Restriction Display**
    **Validates: Requirements 7.5, 4.3**
    
    Для любого турнира, где premium_last_ended в пределах 24 часов от текущего времени,
    система должна показывать "Доступно для покупки через [remaining_time]".
    """
    
    @given(hours_ago=st.integers(min_value=1, max_value=23))
    @settings(max_examples=100)
    def test_restriction_shown_within_24_hours(self, hours_ago):
        """
        Property: Если premium_last_ended < 24 часов назад, показывается ограничение.
        
        **Feature: organizer-cabinet, Property 7: Premium 24-Hour Restriction Display**
        **Validates: Requirements 7.5, 4.3**
        """
        last_ended = datetime.now() - timedelta(hours=hours_ago)
        last_ended_str = last_ended.strftime("%Y-%m-%d %H:%M:%S")
        
        result = CabinetFormatter.format_status_premium(None, last_ended_str)
        
        assert "Доступно для покупки через" in result
    
    @given(hours_ago=st.integers(min_value=25, max_value=100))
    @settings(max_examples=100)
    def test_no_restriction_after_24_hours(self, hours_ago):
        """
        Property: Если premium_last_ended > 24 часов назад, ограничение не показывается.
        
        **Feature: organizer-cabinet, Property 7: Premium 24-Hour Restriction Display**
        **Validates: Requirements 7.5**
        """
        last_ended = datetime.now() - timedelta(hours=hours_ago)
        last_ended_str = last_ended.strftime("%Y-%m-%d %H:%M:%S")
        
        result = CabinetFormatter.format_status_premium(None, last_ended_str)
        
        assert "Доступно для покупки через" not in result
        assert result == "🔝 Премиум: Не активен"


class TestTournamentCardContainsRequiredFields:
    """
    **Feature: organizer-cabinet, Property 4: Tournament Card Contains Required Fields**
    **Validates: Requirements 3.2**
    
    Для любого турнира в списке кабинета, отрендеренный вывод должен содержать
    название турнира, дату и город.
    """
    
    @given(
        title=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S'))),
        city=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=('L',))),
        date=st.dates(min_value=datetime(2020, 1, 1).date(), max_value=datetime(2030, 12, 31).date())
    )
    @settings(max_examples=100)
    def test_card_contains_title_date_city(self, title, city, date):
        """
        Property: Карточка турнира содержит title, date и city.
        
        **Feature: organizer-cabinet, Property 4: Tournament Card Contains Required Fields**
        **Validates: Requirements 3.2**
        """
        tournament = {
            "title": title,
            "city": city,
            "start_date": date.strftime("%Y-%m-%d")
        }
        
        result = CabinetFormatter.format_tournament_card(tournament)
        
        # Проверяем наличие обязательных полей
        assert title in result
        assert city in result
        assert date.strftime("%d.%m.%Y") in result


class TestPremiumButtonAvailability:
    """
    **Feature: organizer-cabinet, Property 8: Premium Button Availability**
    **Validates: Requirements 4.4, 4.5**
    
    Для любого турнира:
    - Если премиум не активен и нет 24ч ограничения → показывать "Купить премиум 7 дней"
    - Если премиум активен → показывать "Продлить 7 дней" и "+1 день"
    """
    
    @given(future_date=future_dates)
    @settings(max_examples=100)
    def test_extend_buttons_when_premium_active(self, future_date):
        """
        Property: При активном премиуме доступны кнопки продления.
        
        **Feature: organizer-cabinet, Property 8: Premium Button Availability**
        **Validates: Requirements 4.5**
        """
        date_str = future_date.strftime("%Y-%m-%d")
        availability = CabinetFormatter.check_premium_availability(date_str)
        
        assert availability.is_active is True
        assert availability.can_extend is True
        assert availability.can_buy is False
    
    def test_buy_button_when_premium_inactive_no_restriction(self):
        """
        Property: При неактивном премиуме без ограничения доступна кнопка покупки.
        
        **Feature: organizer-cabinet, Property 8: Premium Button Availability**
        **Validates: Requirements 4.4**
        """
        availability = CabinetFormatter.check_premium_availability(None, None)
        
        assert availability.is_active is False
        assert availability.can_buy is True
        assert availability.can_extend is False
    
    @given(hours_ago=st.integers(min_value=1, max_value=23))
    @settings(max_examples=100)
    def test_no_buy_button_during_restriction(self, hours_ago):
        """
        Property: Во время 24ч ограничения кнопка покупки недоступна.
        
        **Feature: organizer-cabinet, Property 8: Premium Button Availability**
        **Validates: Requirements 4.4**
        """
        last_ended = datetime.now() - timedelta(hours=hours_ago)
        last_ended_str = last_ended.strftime("%Y-%m-%d %H:%M:%S")
        
        availability = CabinetFormatter.check_premium_availability(None, last_ended_str)
        
        assert availability.can_buy is False
        assert availability.restriction_ends_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
