"""
Property-based тесты для AnalyticsService.

Тестирует:
- Property 11: Event Logging Completeness
- Property 9: Analytics Aggregation Correctness
- Property 10: Clicks Aggregation by Source
- Property 12: Analytics Anonymization
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from datetime import datetime, timedelta
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.analytics_service import AnalyticsService, AnalyticsData
from app.models.analytics_event import AnalyticsEvent


# Стратегии для генерации данных
tournament_ids = st.integers(min_value=1, max_value=10000)
contexts = st.sampled_from(["search", "tournaments_command"])
sources = st.sampled_from(["bot", "channel", "mailing"])
utm_values = st.one_of(st.none(), st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"))


@pytest.fixture
def analytics_service(tmp_path, monkeypatch):
    """Создаёт изолированный сервис аналитики для тестов"""
    # Переопределяем путь к файлу данных
    test_file = str(tmp_path / "test_analytics.json")
    monkeypatch.setattr("app.services.analytics_service.ANALYTICS_FILE", test_file)
    monkeypatch.setattr("app.services.analytics_service.DATA_DIR", str(tmp_path))
    
    service = AnalyticsService()
    service.clear_events()
    return service


class TestEventLoggingCompleteness:
    """
    **Feature: organizer-cabinet, Property 11: Event Logging Completeness**
    **Validates: Requirements 6.1**
    
    Для любого турнира, появляющегося в результатах поиска, событие impression
    должно быть залогировано с заполненными полями tournament_id, context и timestamp.
    """
    
    @given(tournament_id=tournament_ids, context=contexts)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_impression_logging_completeness(self, analytics_service, tournament_id, context):
        """
        Property: log_impression создаёт событие со всеми обязательными полями.
        
        **Feature: organizer-cabinet, Property 11: Event Logging Completeness**
        **Validates: Requirements 6.1**
        """
        # Логируем impression
        event = asyncio.run(analytics_service.log_impression(tournament_id, context))
        
        # Проверяем что все обязательные поля заполнены
        assert event.tournament_id == tournament_id
        assert event.context == context
        assert event.timestamp is not None
        assert event.event_type == "impression"
        assert event.id is not None
    
    @given(tournament_id=tournament_ids, source=sources)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_click_logging_completeness(self, analytics_service, tournament_id, source):
        """
        Property: log_click создаёт событие со всеми обязательными полями.
        
        **Feature: organizer-cabinet, Property 11: Event Logging Completeness**
        **Validates: Requirements 6.2**
        """
        # Логируем click
        event = asyncio.run(analytics_service.log_click(tournament_id, source))
        
        # Проверяем что все обязательные поля заполнены
        assert event.tournament_id == tournament_id
        assert event.source == source
        assert event.timestamp is not None
        assert event.event_type == "click"
        assert event.id is not None


class TestAnalyticsAggregationCorrectness:
    """
    **Feature: organizer-cabinet, Property 9: Analytics Aggregation Correctness**
    **Validates: Requirements 5.1, 6.4**
    
    Для любого набора impression событий для турнира за период,
    количество показов должно равняться количеству событий с matching tournament_id
    и timestamp в пределах периода.
    """
    
    @given(
        tournament_id=tournament_ids,
        num_impressions=st.integers(min_value=0, max_value=50)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_impressions_count_matches_logged_events(
        self, analytics_service, tournament_id, num_impressions
    ):
        """
        Property: get_impressions возвращает точное количество залогированных событий.
        
        **Feature: organizer-cabinet, Property 9: Analytics Aggregation Correctness**
        **Validates: Requirements 5.1, 6.4**
        """
        # Очищаем перед каждой итерацией
        analytics_service.clear_events()
        
        # Логируем заданное количество impressions
        for _ in range(num_impressions):
            asyncio.run(analytics_service.log_impression(tournament_id, "search"))
        
        # Проверяем что count совпадает
        count = asyncio.run(analytics_service.get_impressions(tournament_id, 7))
        assert count == num_impressions
    
    @given(
        tournament_id=tournament_ids,
        num_clicks=st.integers(min_value=0, max_value=50)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_clicks_count_matches_logged_events(
        self, analytics_service, tournament_id, num_clicks
    ):
        """
        Property: get_clicks возвращает точное количество залогированных событий.
        
        **Feature: organizer-cabinet, Property 9: Analytics Aggregation Correctness**
        **Validates: Requirements 5.2, 6.4**
        """
        # Очищаем перед каждой итерацией
        analytics_service.clear_events()
        
        # Логируем заданное количество clicks
        for _ in range(num_clicks):
            asyncio.run(analytics_service.log_click(tournament_id, "bot"))
        
        # Проверяем что count совпадает
        count = asyncio.run(analytics_service.get_clicks(tournament_id, 7))
        assert count == num_clicks


class TestClicksAggregationBySource:
    """
    **Feature: organizer-cabinet, Property 10: Clicks Aggregation by Source**
    **Validates: Requirements 5.3**
    
    Для любого набора click событий для турнира, разбивка кликов по источникам
    должна корректно группировать и считать события по полю source.
    """
    
    @given(
        tournament_id=tournament_ids,
        bot_clicks=st.integers(min_value=0, max_value=20),
        channel_clicks=st.integers(min_value=0, max_value=20),
        mailing_clicks=st.integers(min_value=0, max_value=20)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_clicks_by_source_grouping(
        self, analytics_service, tournament_id, bot_clicks, channel_clicks, mailing_clicks
    ):
        """
        Property: get_clicks_by_source корректно группирует клики по источникам.
        
        **Feature: organizer-cabinet, Property 10: Clicks Aggregation by Source**
        **Validates: Requirements 5.3**
        """
        # Очищаем перед каждой итерацией
        analytics_service.clear_events()
        
        # Логируем клики с разными источниками
        for _ in range(bot_clicks):
            asyncio.run(analytics_service.log_click(tournament_id, "bot"))
        for _ in range(channel_clicks):
            asyncio.run(analytics_service.log_click(tournament_id, "channel"))
        for _ in range(mailing_clicks):
            asyncio.run(analytics_service.log_click(tournament_id, "mailing"))
        
        # Получаем разбивку
        breakdown = asyncio.run(analytics_service.get_clicks_by_source(tournament_id, 7))
        
        # Проверяем что группировка корректна
        assert breakdown.get("bot_search", 0) == bot_clicks
        assert breakdown.get("tg_channel", 0) == channel_clicks
        assert breakdown.get("mailing", 0) == mailing_clicks
        
        # Проверяем что сумма равна общему количеству
        total = bot_clicks + channel_clicks + mailing_clicks
        assert sum(breakdown.values()) == total


class TestAnalyticsAnonymization:
    """
    **Feature: organizer-cabinet, Property 12: Analytics Anonymization**
    **Validates: Requirements 6.3**
    
    Для любых данных аналитики, возвращаемых организатору,
    данные НЕ должны содержать поля user_id или contact_id.
    """
    
    @given(tournament_id=tournament_ids)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_analytics_data_does_not_contain_user_identifiers(
        self, analytics_service, tournament_id
    ):
        """
        Property: AnalyticsData не содержит user_id или contact_id.
        
        **Feature: organizer-cabinet, Property 12: Analytics Anonymization**
        **Validates: Requirements 6.3**
        """
        # Очищаем перед каждой итерацией
        analytics_service.clear_events()
        
        # Логируем несколько событий
        asyncio.run(analytics_service.log_impression(tournament_id, "search"))
        asyncio.run(analytics_service.log_click(tournament_id, "bot"))
        
        # Получаем аналитику
        analytics = asyncio.run(analytics_service.get_tournament_analytics(tournament_id))
        analytics_dict = analytics.to_dict()
        
        # Проверяем отсутствие идентификаторов пользователей
        assert "user_id" not in analytics_dict
        assert "contact_id" not in analytics_dict
        
        # Проверяем что в событиях тоже нет идентификаторов
        events = analytics_service.get_events_for_tournament(tournament_id)
        for event in events:
            event_dict = event.to_dict()
            assert "user_id" not in event_dict
            assert "contact_id" not in event_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
