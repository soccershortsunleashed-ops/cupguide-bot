"""
Сервис для личного кабинета организатора.
Бизнес-логика для работы с турнирами, аналитикой и промо-кампаниями.
"""
import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.analytics_service import get_analytics_service, AnalyticsData
from app.services.promo_campaign_service import get_promo_campaign_service
from app.models.promo_campaign import PromoCampaign
from telegram_bot.cabinet_formatter import CabinetFormatter, PremiumAvailability

logger = logging.getLogger(__name__)


class CabinetService:
    """Сервис для работы с личным кабинетом организатора"""
    
    def __init__(self, backend_client=None):
        """
        Args:
            backend_client: Клиент для работы с backend API
        """
        self.backend_client = backend_client
        self.analytics_service = get_analytics_service()
        self.promo_service = get_promo_campaign_service()
    
    async def get_organizer_tournaments(self, contact_id: int) -> List[Dict[str, Any]]:
        """
        Получает список турниров организатора.
        
        Args:
            contact_id: ID контакта организатора
        
        Returns:
            Список турниров с organizer_contact_id == contact_id
        """
        if not self.backend_client:
            logger.warning("Backend client not configured")
            return []
        
        try:
            # Пробуем получить турниры через специальный endpoint
            try:
                tournaments = await self.backend_client.get_organizer_tournaments(contact_id)
                if tournaments:
                    logger.info(f"Found {len(tournaments)} tournaments for organizer {contact_id} via API")
                    return tournaments
            except Exception as e:
                logger.warning(f"Organizer endpoint failed, falling back to filter: {e}")
            
            # Fallback: получаем все турниры и фильтруем по organizer_contact_id
            tournaments = await self.backend_client.get_tournaments()
            
            if not tournaments:
                return []
            
            # Фильтруем по organizer_contact_id
            organizer_tournaments = [
                t for t in tournaments
                if t.get("organizer_contact_id") == contact_id
            ]
            
            logger.info(f"Found {len(organizer_tournaments)} tournaments for organizer {contact_id}")
            return organizer_tournaments
            
        except Exception as e:
            logger.error(f"Error getting organizer tournaments: {e}")
            return []
    
    async def get_tournament_by_id(self, tournament_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает турнир по ID.
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            Данные турнира или None
        """
        if not self.backend_client:
            return None
        
        try:
            return await self.backend_client.get_tournament(tournament_id)
        except Exception as e:
            logger.error(f"Error getting tournament {tournament_id}: {e}")
            return None
    
    async def get_tournament_analytics(self, tournament_id: int) -> AnalyticsData:
        """
        Получает аналитику турнира.
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            AnalyticsData с агрегированными данными
        """
        return await self.analytics_service.get_tournament_analytics(tournament_id)
    
    async def get_promo_campaign(self, tournament_id: int) -> Optional[PromoCampaign]:
        """
        Получает активную промо-кампанию турнира.
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            PromoCampaign или None
        """
        return await self.promo_service.get_campaign(tournament_id)
    
    def check_premium_availability(self, tournament: Dict[str, Any]) -> PremiumAvailability:
        """
        Проверяет доступность премиума для турнира.
        
        Args:
            tournament: Данные турнира
        
        Returns:
            PremiumAvailability с информацией о доступных действиях
        """
        return CabinetFormatter.check_premium_availability(
            tournament.get("premium_until"),
            tournament.get("premium_last_ended")
        )
    
    def generate_utm_link(
        self, 
        tournament_id: int, 
        base_url: str = "http://127.0.0.1:8000",
        source: str = "telegram",
        medium: str = "cabinet",
        campaign: Optional[str] = None
    ) -> str:
        """
        Генерирует ссылку на турнир с UTM-метками.
        
        Args:
            tournament_id: ID турнира
            base_url: Базовый URL сайта
            source: UTM source
            medium: UTM medium
            campaign: UTM campaign (по умолчанию tournament_{id})
        
        Returns:
            URL с UTM-параметрами
        """
        if not campaign:
            campaign = f"tournament_{tournament_id}"
        
        utm_params = {
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": campaign
        }
        
        url = f"{base_url}/tournaments/{tournament_id}"
        return f"{url}?{urlencode(utm_params)}"
    
    async def get_tournaments_with_campaigns(
        self, 
        contact_id: int
    ) -> tuple[List[Dict[str, Any]], Dict[int, str]]:
        """
        Получает турниры организатора с прогрессом кампаний.
        
        Args:
            contact_id: ID контакта организатора
        
        Returns:
            Tuple (список турниров, словарь {tournament_id: progress_string})
        """
        tournaments = await self.get_organizer_tournaments(contact_id)
        campaigns = {}
        
        for t in tournaments:
            tournament_id = t.get("id")
            if tournament_id:
                campaign = await self.get_promo_campaign(tournament_id)
                if campaign:
                    campaigns[tournament_id] = self.promo_service.format_progress(campaign)
        
        return tournaments, campaigns
    
    async def verify_tournament_ownership(
        self, 
        tournament_id: int, 
        contact_id: int
    ) -> bool:
        """
        Проверяет, принадлежит ли турнир организатору.
        
        Args:
            tournament_id: ID турнира
            contact_id: ID контакта организатора
        
        Returns:
            True если турнир принадлежит организатору
        """
        tournament = await self.get_tournament_by_id(tournament_id)
        if not tournament:
            return False
        
        return tournament.get("organizer_contact_id") == contact_id


# Singleton instance
_cabinet_service: Optional[CabinetService] = None


def get_cabinet_service(backend_client=None) -> CabinetService:
    """Получает singleton экземпляр сервиса кабинета"""
    global _cabinet_service
    if _cabinet_service is None:
        _cabinet_service = CabinetService(backend_client)
    elif backend_client and _cabinet_service.backend_client is None:
        _cabinet_service.backend_client = backend_client
    return _cabinet_service
