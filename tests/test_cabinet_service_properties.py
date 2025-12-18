"""
Property-based тесты для CabinetService.

**Feature: organizer-cabinet, Property 3: Tournament Retrieval by Organizer**
**Validates: Requirements 1.4**
"""
import pytest
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, MagicMock
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from telegram_bot.cabinet_service import CabinetService


# Стратегии для генерации данных
contact_ids = st.integers(min_value=1, max_value=10000)
tournament_ids = st.integers(min_value=1, max_value=10000)


@st.composite
def tournaments_with_organizers(draw, num_tournaments=st.integers(min_value=0, max_value=20)):
    """Генератор списка турниров с разными organizer_contact_id"""
    n = draw(num_tournaments)
    tournaments = []
    
    for i in range(n):
        organizer_id = draw(st.integers(min_value=1, max_value=100))
        tournaments.append({
            "id": i + 1,
            "title": f"Tournament {i + 1}",
            "organizer_contact_id": organizer_id,
            "city": "Moscow",
            "start_date": "2025-06-01"
        })
    
    return tournaments


class TestTournamentRetrievalByOrganizer:
    """
    **Feature: organizer-cabinet, Property 3: Tournament Retrieval by Organizer**
    **Validates: Requirements 1.4**
    
    Для любого организатора с contact_id, запрос его турниров должен вернуть
    ровно тот набор турниров, где organizer_contact_id равен этому contact_id.
    """
    
    @given(
        tournaments=tournaments_with_organizers(),
        target_contact_id=contact_ids
    )
    @settings(max_examples=100)
    def test_returns_only_organizer_tournaments(self, tournaments, target_contact_id):
        """
        Property: get_organizer_tournaments возвращает только турниры с matching organizer_contact_id.
        
        **Feature: organizer-cabinet, Property 3: Tournament Retrieval by Organizer**
        **Validates: Requirements 1.4**
        """
        # Создаём mock backend client
        mock_client = MagicMock()
        mock_client.get_tournaments = AsyncMock(return_value=tournaments)
        
        # Создаём сервис с mock client
        service = CabinetService(backend_client=mock_client)
        
        # Получаем турниры организатора
        result = asyncio.run(service.get_organizer_tournaments(target_contact_id))
        
        # Вычисляем ожидаемый результат
        expected = [
            t for t in tournaments 
            if t.get("organizer_contact_id") == target_contact_id
        ]
        
        # Проверяем что результат совпадает с ожидаемым
        assert len(result) == len(expected)
        
        # Проверяем что все возвращённые турниры принадлежат организатору
        for t in result:
            assert t.get("organizer_contact_id") == target_contact_id
    
    @given(
        tournaments=tournaments_with_organizers(num_tournaments=st.integers(min_value=5, max_value=20))
    )
    @settings(max_examples=100)
    def test_no_tournaments_from_other_organizers(self, tournaments):
        """
        Property: Результат не содержит турниры других организаторов.
        
        **Feature: organizer-cabinet, Property 3: Tournament Retrieval by Organizer**
        **Validates: Requirements 1.4**
        """
        if not tournaments:
            return
        
        # Выбираем первый турнир и его организатора
        target_contact_id = tournaments[0].get("organizer_contact_id")
        
        # Создаём mock backend client
        mock_client = MagicMock()
        mock_client.get_tournaments = AsyncMock(return_value=tournaments)
        
        service = CabinetService(backend_client=mock_client)
        result = asyncio.run(service.get_organizer_tournaments(target_contact_id))
        
        # Проверяем что нет турниров от других организаторов
        other_organizer_ids = {
            t.get("organizer_contact_id") 
            for t in tournaments 
            if t.get("organizer_contact_id") != target_contact_id
        }
        
        for t in result:
            assert t.get("organizer_contact_id") not in other_organizer_ids
    
    @given(contact_id=contact_ids)
    @settings(max_examples=100)
    def test_empty_result_for_non_organizer(self, contact_id):
        """
        Property: Для пользователя без турниров возвращается пустой список.
        
        **Feature: organizer-cabinet, Property 3: Tournament Retrieval by Organizer**
        **Validates: Requirements 1.4**
        """
        # Создаём турниры с другими organizer_contact_id
        tournaments = [
            {"id": 1, "title": "T1", "organizer_contact_id": contact_id + 1},
            {"id": 2, "title": "T2", "organizer_contact_id": contact_id + 2},
        ]
        
        mock_client = MagicMock()
        mock_client.get_tournaments = AsyncMock(return_value=tournaments)
        
        service = CabinetService(backend_client=mock_client)
        result = asyncio.run(service.get_organizer_tournaments(contact_id))
        
        assert result == []


class TestVerifyTournamentOwnership:
    """
    Тесты для проверки владения турниром.
    """
    
    @given(
        tournament_id=tournament_ids,
        owner_contact_id=contact_ids
    )
    @settings(max_examples=100)
    def test_ownership_verified_for_owner(self, tournament_id, owner_contact_id):
        """
        Property: verify_tournament_ownership возвращает True для владельца.
        """
        tournament = {
            "id": tournament_id,
            "title": "Test Tournament",
            "organizer_contact_id": owner_contact_id
        }
        
        mock_client = MagicMock()
        mock_client.get_tournament = AsyncMock(return_value=tournament)
        
        service = CabinetService(backend_client=mock_client)
        result = asyncio.run(service.verify_tournament_ownership(tournament_id, owner_contact_id))
        
        assert result is True
    
    @given(
        tournament_id=tournament_ids,
        owner_contact_id=contact_ids,
        other_contact_id=contact_ids
    )
    @settings(max_examples=100)
    def test_ownership_denied_for_non_owner(self, tournament_id, owner_contact_id, other_contact_id):
        """
        Property: verify_tournament_ownership возвращает False для не-владельца.
        """
        # Убеждаемся что contact_id разные
        if owner_contact_id == other_contact_id:
            other_contact_id = owner_contact_id + 1
        
        tournament = {
            "id": tournament_id,
            "title": "Test Tournament",
            "organizer_contact_id": owner_contact_id
        }
        
        mock_client = MagicMock()
        mock_client.get_tournament = AsyncMock(return_value=tournament)
        
        service = CabinetService(backend_client=mock_client)
        result = asyncio.run(service.verify_tournament_ownership(tournament_id, other_contact_id))
        
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
