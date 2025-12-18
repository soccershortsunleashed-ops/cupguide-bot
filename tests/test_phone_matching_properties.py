"""
Property-based тесты для матчинга телефона организатора к контакту.

**Feature: organizer-cabinet, Property 2: Phone-to-Contact Matching**
**Validates: Requirements 1.3**
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# Стратегии для генерации телефонов
phone_digits = st.text(alphabet="0123456789", min_size=10, max_size=11)


@pytest.fixture
def tournament_service(tmp_path, monkeypatch):
    """Создаёт изолированный сервис для тестов"""
    from app.services.tournament_service import TournamentService
    
    # Создаём временные файлы
    tournaments_file = tmp_path / "tournaments.json"
    contacts_file = tmp_path / "contacts.json"
    
    tournaments_file.write_text("[]")
    contacts_file.write_text("[]")
    
    service = TournamentService()
    service.file_path = str(tournaments_file)
    service.contacts_file_path = str(contacts_file)
    
    return service, contacts_file


class TestPhoneToContactMatching:
    """
    **Feature: organizer-cabinet, Property 2: Phone-to-Contact Matching**
    **Validates: Requirements 1.3**
    
    Для любого турнира с organizer_phone и без organizer_contact_id,
    если существует контакт с matching phone, система должна найти contact_id.
    """
    
    @given(
        contact_id=st.integers(min_value=1, max_value=10000),
        phone_base=st.text(alphabet="0123456789", min_size=10, max_size=10)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_matching_phone_returns_contact_id(self, tournament_service, contact_id, phone_base):
        """
        Property: Если контакт с таким телефоном существует, возвращается его contact_id.
        
        **Feature: organizer-cabinet, Property 2: Phone-to-Contact Matching**
        **Validates: Requirements 1.3**
        """
        service, contacts_file = tournament_service
        
        # Формируем телефон в формате 7XXXXXXXXXX
        phone = "7" + phone_base
        
        # Создаём контакт с этим телефоном
        contacts = [{"id": contact_id, "phone": phone, "name": "Test"}]
        contacts_file.write_text(json.dumps(contacts))
        
        # Проверяем матчинг
        result = asyncio.run(service.match_organizer_phone_to_contact(phone))
        
        assert result == contact_id
    
    @given(
        contact_id=st.integers(min_value=1, max_value=10000),
        phone_base=st.text(alphabet="0123456789", min_size=10, max_size=10)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_matching_with_8_prefix_normalization(self, tournament_service, contact_id, phone_base):
        """
        Property: Телефон с префиксом 8 нормализуется к 7 и матчится.
        
        **Feature: organizer-cabinet, Property 2: Phone-to-Contact Matching**
        **Validates: Requirements 1.3**
        """
        service, contacts_file = tournament_service
        
        # Контакт с телефоном 7XXXXXXXXXX
        phone_7 = "7" + phone_base
        contacts = [{"id": contact_id, "phone": phone_7, "name": "Test"}]
        contacts_file.write_text(json.dumps(contacts))
        
        # Ищем по телефону 8XXXXXXXXXX
        phone_8 = "8" + phone_base
        result = asyncio.run(service.match_organizer_phone_to_contact(phone_8))
        
        assert result == contact_id
    
    @given(
        phone_base=st.text(alphabet="0123456789", min_size=10, max_size=10)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_no_match_returns_none(self, tournament_service, phone_base):
        """
        Property: Если контакт не найден, возвращается None.
        
        **Feature: organizer-cabinet, Property 2: Phone-to-Contact Matching**
        **Validates: Requirements 1.3**
        """
        service, contacts_file = tournament_service
        
        # Создаём контакт с другим телефоном
        contacts = [{"id": 1, "phone": "79991234567", "name": "Test"}]
        contacts_file.write_text(json.dumps(contacts))
        
        # Ищем по несуществующему телефону
        phone = "7" + phone_base
        if phone == "79991234567":
            phone = "79991234568"
        
        result = asyncio.run(service.match_organizer_phone_to_contact(phone))
        
        # Если телефон не совпадает, должен вернуться None
        if phone != "79991234567":
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
