"""
Property-based тесты для PromoCampaignService.

**Feature: organizer-cabinet, Property 13: Native Campaign Progress Display**
**Validates: Requirements 8.1**
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.promo_campaign_service import PromoCampaignService
from app.models.promo_campaign import PromoCampaign, ScheduledPost


# Стратегии для генерации данных
tournament_ids = st.integers(min_value=1, max_value=10000)
done_counts = st.integers(min_value=0, max_value=3)


@pytest.fixture
def promo_service(tmp_path, monkeypatch):
    """Создаёт изолированный сервис для тестов"""
    test_file = str(tmp_path / "test_campaigns.json")
    monkeypatch.setattr("app.services.promo_campaign_service.CAMPAIGNS_FILE", test_file)
    monkeypatch.setattr("app.services.promo_campaign_service.DATA_DIR", str(tmp_path))
    
    service = PromoCampaignService()
    service.clear_campaigns()
    return service


class TestNativeCampaignProgressDisplay:
    """
    **Feature: organizer-cabinet, Property 13: Native Campaign Progress Display**
    **Validates: Requirements 8.1**
    
    Для любой promo_campaign с типом "native_3", отображение прогресса
    должно показывать "[done_count]/3", где done_count — количество постов со статусом "done".
    """
    
    @given(
        tournament_id=tournament_ids,
        done_count=done_counts
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_progress_display_matches_done_count(
        self, promo_service, tournament_id, done_count
    ):
        """
        Property: progress_display показывает корректное соотношение done_count/3.
        
        **Feature: organizer-cabinet, Property 13: Native Campaign Progress Display**
        **Validates: Requirements 8.1**
        """
        # Очищаем перед каждой итерацией
        promo_service.clear_campaigns()
        
        # Создаём кампанию с 3 постами
        scheduled_dates = ["2025-01-01", "2025-01-15", "2025-02-01"]
        campaign = asyncio.run(promo_service.create_campaign(
            tournament_id=tournament_id,
            campaign_type="native_3",
            scheduled_dates=scheduled_dates
        ))
        
        # Помечаем done_count постов как выполненные
        for i in range(done_count):
            asyncio.run(promo_service.update_post_status(
                campaign_id=campaign.id,
                post_index=i,
                status="done",
                post_url=f"https://example.com/post{i}"
            ))
        
        # Получаем обновлённую кампанию
        updated_campaign = asyncio.run(promo_service.get_campaign(tournament_id))
        
        # Проверяем progress_display
        if done_count < 3:
            assert updated_campaign.progress_display == f"{done_count}/3"
            assert updated_campaign.done_count == done_count
        else:
            # При done_count == 3 кампания завершается
            # Нужно получить из всех кампаний, т.к. активная может быть None
            all_campaigns = asyncio.run(promo_service.get_all_campaigns(tournament_id))
            completed_campaign = all_campaigns[0]
            assert completed_campaign.done_count == 3
            assert completed_campaign.progress_display == "3/3"
    
    @given(tournament_id=tournament_ids)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_format_progress_for_completed_campaign(self, promo_service, tournament_id):
        """
        Property: format_progress показывает "✅ Кампания завершена" когда все 3 поста выполнены.
        
        **Feature: organizer-cabinet, Property 13: Native Campaign Progress Display**
        **Validates: Requirements 8.4**
        """
        # Очищаем перед каждой итерацией
        promo_service.clear_campaigns()
        
        # Создаём и завершаем кампанию
        scheduled_dates = ["2025-01-01", "2025-01-15", "2025-02-01"]
        campaign = asyncio.run(promo_service.create_campaign(
            tournament_id=tournament_id,
            campaign_type="native_3",
            scheduled_dates=scheduled_dates
        ))
        
        # Помечаем все 3 поста как выполненные
        for i in range(3):
            asyncio.run(promo_service.update_post_status(
                campaign_id=campaign.id,
                post_index=i,
                status="done"
            ))
        
        # Получаем кампанию (может быть None если статус completed)
        all_campaigns = asyncio.run(promo_service.get_all_campaigns(tournament_id))
        completed_campaign = all_campaigns[0]
        
        # Проверяем format_progress
        progress_text = promo_service.format_progress(completed_campaign)
        assert progress_text == "✅ Кампания завершена"
    
    @given(tournament_id=tournament_ids)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_format_progress_for_no_campaign(self, promo_service, tournament_id):
        """
        Property: format_progress показывает "Натив: не активен" когда кампании нет.
        
        **Feature: organizer-cabinet, Property 13: Native Campaign Progress Display**
        **Validates: Requirements 8.1**
        """
        # Очищаем перед каждой итерацией
        promo_service.clear_campaigns()
        
        # Проверяем format_progress для None
        progress_text = promo_service.format_progress(None)
        assert progress_text == "Натив: не активен"
    
    @given(
        tournament_id=tournament_ids,
        done_count=st.integers(min_value=0, max_value=2)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_format_progress_for_active_campaign(self, promo_service, tournament_id, done_count):
        """
        Property: format_progress показывает "🟢 Натив: X/3 выполнено" для активной кампании.
        
        **Feature: organizer-cabinet, Property 13: Native Campaign Progress Display**
        **Validates: Requirements 8.1**
        """
        # Очищаем перед каждой итерацией
        promo_service.clear_campaigns()
        
        # Создаём кампанию
        scheduled_dates = ["2025-01-01", "2025-01-15", "2025-02-01"]
        campaign = asyncio.run(promo_service.create_campaign(
            tournament_id=tournament_id,
            campaign_type="native_3",
            scheduled_dates=scheduled_dates
        ))
        
        # Помечаем done_count постов как выполненные
        for i in range(done_count):
            asyncio.run(promo_service.update_post_status(
                campaign_id=campaign.id,
                post_index=i,
                status="done"
            ))
        
        # Получаем обновлённую кампанию
        updated_campaign = asyncio.run(promo_service.get_campaign(tournament_id))
        
        # Проверяем format_progress
        progress_text = promo_service.format_progress(updated_campaign)
        assert progress_text == f"🟢 Натив: {done_count}/3 выполнено"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
