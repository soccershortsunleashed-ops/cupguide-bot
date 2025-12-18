"""
Сервис для управления промо-кампаниями (нативные упоминания) в личном кабинете организатора.
"""
import json
import os
import logging
from datetime import datetime
from typing import List, Optional

from app.models.promo_campaign import PromoCampaign, ScheduledPost

logger = logging.getLogger(__name__)

# Путь к файлу хранения кампаний
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CAMPAIGNS_FILE = os.path.join(DATA_DIR, "promo_campaigns.json")


class PromoCampaignService:
    """Сервис для управления промо-кампаниями турниров"""
    
    def __init__(self):
        self._ensure_data_dir()
        self._campaigns: List[PromoCampaign] = []
        self._load_campaigns()
    
    def _ensure_data_dir(self):
        """Создаёт директорию data если не существует"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
    
    def _load_campaigns(self):
        """Загружает кампании из файла"""
        if os.path.exists(CAMPAIGNS_FILE):
            try:
                with open(CAMPAIGNS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._campaigns = [PromoCampaign.from_dict(c) for c in data]
                logger.info(f"Loaded {len(self._campaigns)} promo campaigns")
            except Exception as e:
                logger.error(f"Error loading promo campaigns: {e}")
                self._campaigns = []
        else:
            self._campaigns = []
    
    def _save_campaigns(self):
        """Сохраняет кампании в файл"""
        try:
            with open(CAMPAIGNS_FILE, 'w', encoding='utf-8') as f:
                json.dump([c.to_dict() for c in self._campaigns], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving promo campaigns: {e}")
    
    def _get_next_id(self) -> int:
        """Генерирует следующий ID для кампании"""
        if not self._campaigns:
            return 1
        return max(c.id or 0 for c in self._campaigns) + 1
    
    async def get_campaign(self, tournament_id: int) -> Optional[PromoCampaign]:
        """
        Получает активную кампанию для турнира.
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            PromoCampaign или None если кампании нет
        """
        for campaign in self._campaigns:
            if campaign.tournament_id == tournament_id and campaign.status == "active":
                return campaign
        return None
    
    async def get_all_campaigns(self, tournament_id: int) -> List[PromoCampaign]:
        """
        Получает все кампании для турнира (включая завершённые).
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            Список кампаний
        """
        return [c for c in self._campaigns if c.tournament_id == tournament_id]
    
    async def create_campaign(
        self, 
        tournament_id: int, 
        campaign_type: str = "native_3",
        scheduled_dates: Optional[List[str]] = None
    ) -> PromoCampaign:
        """
        Создаёт новую промо-кампанию.
        
        Args:
            tournament_id: ID турнира
            campaign_type: Тип кампании (native_3)
            scheduled_dates: Список дат для постов (YYYY-MM-DD)
        
        Returns:
            Созданная кампания
        """
        # Создаём запланированные посты
        scheduled_posts = []
        if scheduled_dates:
            for date in scheduled_dates:
                scheduled_posts.append(ScheduledPost(date=date, status="pending"))
        
        campaign = PromoCampaign(
            id=self._get_next_id(),
            tournament_id=tournament_id,
            type=campaign_type,
            status="active",
            scheduled_posts=scheduled_posts,
            done_count=0,
            created_at=datetime.utcnow()
        )
        
        self._campaigns.append(campaign)
        self._save_campaigns()
        
        logger.info(f"Created promo campaign {campaign.id} for tournament {tournament_id}")
        return campaign
    
    async def update_post_status(
        self, 
        campaign_id: int, 
        post_index: int, 
        status: str,
        post_url: Optional[str] = None
    ) -> Optional[PromoCampaign]:
        """
        Обновляет статус поста в кампании.
        
        Args:
            campaign_id: ID кампании
            post_index: Индекс поста (0-based)
            status: Новый статус (pending/done)
            post_url: URL опубликованного поста
        
        Returns:
            Обновлённая кампания или None
        """
        for campaign in self._campaigns:
            if campaign.id == campaign_id:
                if 0 <= post_index < len(campaign.scheduled_posts):
                    campaign.scheduled_posts[post_index].status = status
                    if post_url:
                        campaign.scheduled_posts[post_index].post_url = post_url
                    
                    # Обновляем done_count
                    campaign.update_done_count()
                    
                    self._save_campaigns()
                    logger.info(f"Updated post {post_index} in campaign {campaign_id} to {status}")
                    return campaign
        return None
    
    async def cancel_campaign(self, campaign_id: int) -> Optional[PromoCampaign]:
        """
        Отменяет кампанию.
        
        Args:
            campaign_id: ID кампании
        
        Returns:
            Обновлённая кампания или None
        """
        for campaign in self._campaigns:
            if campaign.id == campaign_id:
                campaign.status = "cancelled"
                self._save_campaigns()
                logger.info(f"Cancelled campaign {campaign_id}")
                return campaign
        return None
    
    def format_progress(self, campaign: Optional[PromoCampaign]) -> str:
        """
        Форматирует прогресс кампании для отображения.
        
        Args:
            campaign: Кампания или None
        
        Returns:
            Строка прогресса: "🟢 Натив: 1/3 выполнено" или "Натив: не активен"
        """
        if not campaign:
            return "Натив: не активен"
        
        if campaign.is_completed:
            return "✅ Кампания завершена"
        
        return f"🟢 Натив: {campaign.progress_display} выполнено"
    
    def clear_campaigns(self):
        """Очищает все кампании (для тестирования)"""
        self._campaigns = []
        self._save_campaigns()


# Singleton instance
_promo_service: Optional[PromoCampaignService] = None


def get_promo_campaign_service() -> PromoCampaignService:
    """Получает singleton экземпляр сервиса промо-кампаний"""
    global _promo_service
    if _promo_service is None:
        _promo_service = PromoCampaignService()
    return _promo_service
