"""
Property-based тесты для модели AnalyticsEvent.

**Feature: organizer-cabinet, Property 14: Analytics Event Round-Trip**
**Validates: Requirements 9.3**

Для любого валидного AnalyticsEvent, сериализация в JSON и десериализация обратно
должна производить эквивалентное событие со всеми сохранёнными полями.
"""
import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.analytics_event import AnalyticsEvent


# Стратегии для генерации данных
event_types = st.sampled_from(["impression", "click"])
contexts = st.sampled_from([None, "search", "tournaments_command"])
sources = st.sampled_from([None, "bot", "channel", "mailing"])
utm_values = st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))))

# Стратегия для datetime (в пределах разумного диапазона)
timestamps = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31)
)


@st.composite
def analytics_events(draw):
    """Генератор случайных AnalyticsEvent"""
    event_type = draw(event_types)
    tournament_id = draw(st.integers(min_value=1, max_value=1000000))
    timestamp = draw(timestamps)
    
    # Контекст только для impression
    context = draw(contexts) if event_type == "impression" else None
    
    # Источник и UTM только для click
    if event_type == "click":
        source = draw(sources)
        utm_source = draw(utm_values)
        utm_medium = draw(utm_values)
        utm_campaign = draw(utm_values)
    else:
        source = None
        utm_source = None
        utm_medium = None
        utm_campaign = None
    
    return AnalyticsEvent(
        id=draw(st.one_of(st.none(), st.integers(min_value=1, max_value=1000000))),
        event_type=event_type,
        tournament_id=tournament_id,
        context=context,
        source=source,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        timestamp=timestamp
    )


class TestAnalyticsEventRoundTrip:
    """
    **Feature: organizer-cabinet, Property 14: Analytics Event Round-Trip**
    **Validates: Requirements 9.3**
    """
    
    @given(event=analytics_events())
    @settings(max_examples=100)
    def test_round_trip_to_dict_from_dict(self, event: AnalyticsEvent):
        """
        Property: to_dict() -> from_dict() должен сохранять все поля.
        
        **Feature: organizer-cabinet, Property 14: Analytics Event Round-Trip**
        **Validates: Requirements 9.3**
        """
        # Сериализуем в dict
        serialized = event.to_dict()
        
        # Десериализуем обратно
        deserialized = AnalyticsEvent.from_dict(serialized)
        
        # Проверяем эквивалентность всех полей
        assert deserialized.id == event.id
        assert deserialized.event_type == event.event_type
        assert deserialized.tournament_id == event.tournament_id
        assert deserialized.context == event.context
        assert deserialized.source == event.source
        assert deserialized.utm_source == event.utm_source
        assert deserialized.utm_medium == event.utm_medium
        assert deserialized.utm_campaign == event.utm_campaign
        
        # Для timestamp проверяем с точностью до секунды (из-за ISO формата)
        assert abs((deserialized.timestamp - event.timestamp).total_seconds()) < 1
    
    @given(event=analytics_events())
    @settings(max_examples=100)
    def test_round_trip_json_serialization(self, event: AnalyticsEvent):
        """
        Property: JSON serialization -> deserialization должен сохранять все поля.
        
        **Feature: organizer-cabinet, Property 14: Analytics Event Round-Trip**
        **Validates: Requirements 9.3**
        """
        # Сериализуем в JSON строку
        json_str = json.dumps(event.to_dict())
        
        # Десериализуем из JSON
        data = json.loads(json_str)
        deserialized = AnalyticsEvent.from_dict(data)
        
        # Проверяем эквивалентность
        assert deserialized.event_type == event.event_type
        assert deserialized.tournament_id == event.tournament_id
        assert deserialized.context == event.context
        assert deserialized.source == event.source
        assert deserialized.utm_source == event.utm_source
        assert deserialized.utm_medium == event.utm_medium
        assert deserialized.utm_campaign == event.utm_campaign
    
    @given(event=analytics_events())
    @settings(max_examples=100)
    def test_serialized_dict_contains_all_fields(self, event: AnalyticsEvent):
        """
        Property: to_dict() должен содержать все обязательные поля.
        
        **Feature: organizer-cabinet, Property 14: Analytics Event Round-Trip**
        **Validates: Requirements 9.3**
        """
        serialized = event.to_dict()
        
        # Проверяем наличие всех ключей
        required_keys = {
            "id", "event_type", "tournament_id", "context", 
            "source", "utm_source", "utm_medium", "utm_campaign", "timestamp"
        }
        assert set(serialized.keys()) == required_keys
        
        # Проверяем что event_type и tournament_id не None
        assert serialized["event_type"] is not None
        assert serialized["tournament_id"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
