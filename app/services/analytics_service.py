"""
Сервис аналитики для личного кабинета организатора.
Логирует показы (impressions) и клики (clicks) по турнирам.
Агрегирует данные для отображения в ЛК.
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from app.models.analytics_event import AnalyticsEvent

logger = logging.getLogger(__name__)

# Путь к файлу хранения событий
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
ANALYTICS_FILE = os.path.join(DATA_DIR, "analytics_events.json")


class UTMStats:
    """Статистика по UTM-кампании"""
    def __init__(self, utm_campaign: str, utm_source: str, utm_medium: str, clicks: int):
        self.utm_campaign = utm_campaign
        self.utm_source = utm_source
        self.utm_medium = utm_medium
        self.clicks = clicks
    
    def to_dict(self) -> dict:
        return {
            "utm_campaign": self.utm_campaign,
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "clicks": self.clicks
        }


class AnalyticsData:
    """Агрегированные данные аналитики для турнира"""
    def __init__(
        self,
        tournament_id: int,
        impressions_7d: int = 0,
        impressions_30d: int = 0,
        clicks_7d: int = 0,
        clicks_30d: int = 0,
        clicks_by_source: Optional[Dict[str, int]] = None,
        utm_breakdown: Optional[List[UTMStats]] = None
    ):
        self.tournament_id = tournament_id
        self.impressions_7d = impressions_7d
        self.impressions_30d = impressions_30d
        self.clicks_7d = clicks_7d
        self.clicks_30d = clicks_30d
        self.clicks_by_source = clicks_by_source or {"bot_search": 0, "tg_channel": 0, "mailing": 0}
        self.utm_breakdown = utm_breakdown or []
    
    def to_dict(self) -> dict:
        return {
            "tournament_id": self.tournament_id,
            "impressions_7d": self.impressions_7d,
            "impressions_30d": self.impressions_30d,
            "clicks_7d": self.clicks_7d,
            "clicks_30d": self.clicks_30d,
            "clicks_by_source": self.clicks_by_source,
            "utm_breakdown": [utm.to_dict() for utm in self.utm_breakdown]
        }


class AnalyticsService:
    """Сервис для логирования и агрегации аналитики турниров"""
    
    def __init__(self):
        self._ensure_data_dir()
        self._events: List[AnalyticsEvent] = []
        self._load_events()
    
    def _ensure_data_dir(self):
        """Создаёт директорию data если не существует"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
    
    def _load_events(self):
        """Загружает события из файла"""
        if os.path.exists(ANALYTICS_FILE):
            try:
                with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._events = [AnalyticsEvent.from_dict(e) for e in data]
                logger.info(f"Loaded {len(self._events)} analytics events")
            except Exception as e:
                logger.error(f"Error loading analytics events: {e}")
                self._events = []
        else:
            self._events = []
    
    def _save_events(self):
        """Сохраняет события в файл"""
        try:
            with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
                json.dump([e.to_dict() for e in self._events], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving analytics events: {e}")
    
    def _get_next_id(self) -> int:
        """Генерирует следующий ID для события"""
        if not self._events:
            return 1
        return max(e.id or 0 for e in self._events) + 1
    
    async def log_impression(self, tournament_id: int, context: str) -> AnalyticsEvent:
        """
        Логирует показ турнира в выдаче.
        
        Args:
            tournament_id: ID турнира
            context: Контекст показа (search, tournaments_command)
        
        Returns:
            Созданное событие
        """
        event = AnalyticsEvent(
            id=self._get_next_id(),
            event_type="impression",
            tournament_id=tournament_id,
            context=context,
            timestamp=datetime.utcnow()
        )
        self._events.append(event)
        self._save_events()
        logger.debug(f"Logged impression for tournament {tournament_id}, context={context}")
        return event
    
    async def log_click(
        self, 
        tournament_id: int, 
        source: str, 
        utm_params: Optional[Dict[str, str]] = None
    ) -> AnalyticsEvent:
        """
        Логирует клик по ссылке на турнир.
        
        Args:
            tournament_id: ID турнира
            source: Источник клика (bot, channel, mailing)
            utm_params: UTM-параметры (utm_source, utm_medium, utm_campaign)
        
        Returns:
            Созданное событие
        """
        utm_params = utm_params or {}
        event = AnalyticsEvent(
            id=self._get_next_id(),
            event_type="click",
            tournament_id=tournament_id,
            source=source,
            utm_source=utm_params.get("utm_source"),
            utm_medium=utm_params.get("utm_medium"),
            utm_campaign=utm_params.get("utm_campaign"),
            timestamp=datetime.utcnow()
        )
        self._events.append(event)
        self._save_events()
        logger.debug(f"Logged click for tournament {tournament_id}, source={source}")
        return event
    
    async def get_impressions(self, tournament_id: int, days: int) -> int:
        """
        Получает количество показов турнира за период.
        
        Args:
            tournament_id: ID турнира
            days: Количество дней (7 или 30)
        
        Returns:
            Количество показов
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = sum(
            1 for e in self._events
            if e.event_type == "impression"
            and e.tournament_id == tournament_id
            and e.timestamp >= cutoff
        )
        return count
    
    async def get_clicks(self, tournament_id: int, days: int) -> int:
        """
        Получает количество кликов по турниру за период.
        
        Args:
            tournament_id: ID турнира
            days: Количество дней (7 или 30)
        
        Returns:
            Количество кликов
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        count = sum(
            1 for e in self._events
            if e.event_type == "click"
            and e.tournament_id == tournament_id
            and e.timestamp >= cutoff
        )
        return count
    
    async def get_clicks_by_source(self, tournament_id: int, days: int) -> Dict[str, int]:
        """
        Получает разбивку кликов по источникам.
        
        Args:
            tournament_id: ID турнира
            days: Количество дней
        
        Returns:
            Словарь {source: count}
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = {"bot_search": 0, "tg_channel": 0, "mailing": 0, "telegraph": 0}
        
        for e in self._events:
            if (e.event_type == "click" 
                and e.tournament_id == tournament_id 
                and e.timestamp >= cutoff
                and e.source):
                # Нормализуем source к стандартным значениям
                source_key = e.source
                if source_key == "bot":
                    source_key = "bot_search"
                elif source_key == "channel":
                    source_key = "tg_channel"
                elif source_key in ("teletype", "telegra.ph", "telegraph", "short_link"):
                    source_key = "telegraph"
                
                if source_key in result:
                    result[source_key] += 1
                else:
                    result[source_key] = 1
        
        return result
    
    async def get_utm_breakdown(self, tournament_id: int, days: int) -> List[UTMStats]:
        """
        Получает разбивку кликов по UTM-кампаниям.
        
        Args:
            tournament_id: ID турнира
            days: Количество дней
        
        Returns:
            Список UTMStats
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        utm_counts: Dict[tuple, int] = defaultdict(int)
        
        for e in self._events:
            if (e.event_type == "click" 
                and e.tournament_id == tournament_id 
                and e.timestamp >= cutoff
                and (e.utm_campaign or e.utm_source or e.utm_medium)):
                key = (
                    e.utm_campaign or "",
                    e.utm_source or "",
                    e.utm_medium or ""
                )
                utm_counts[key] += 1
        
        result = [
            UTMStats(
                utm_campaign=key[0],
                utm_source=key[1],
                utm_medium=key[2],
                clicks=count
            )
            for key, count in utm_counts.items()
        ]
        
        # Сортируем по количеству кликов
        result.sort(key=lambda x: x.clicks, reverse=True)
        return result
    
    def reload_events(self):
        """Перезагружает события из файла (для актуализации данных)"""
        self._load_events()
        logger.info(f"📊 Reloaded {len(self._events)} analytics events from file")
    
    async def get_tournament_analytics(self, tournament_id: int) -> AnalyticsData:
        """
        Получает полную аналитику по турниру.
        
        Args:
            tournament_id: ID турнира
        
        Returns:
            AnalyticsData с агрегированными данными
        """
        # Перезагружаем события для актуальных данных
        self.reload_events()
        
        return AnalyticsData(
            tournament_id=tournament_id,
            impressions_7d=await self.get_impressions(tournament_id, 7),
            impressions_30d=await self.get_impressions(tournament_id, 30),
            clicks_7d=await self.get_clicks(tournament_id, 7),
            clicks_30d=await self.get_clicks(tournament_id, 30),
            clicks_by_source=await self.get_clicks_by_source(tournament_id, 30),
            utm_breakdown=await self.get_utm_breakdown(tournament_id, 30)
        )
    
    def get_events_for_tournament(self, tournament_id: int) -> List[AnalyticsEvent]:
        """
        Получает все события для турнира (для тестирования).
        Данные анонимизированы - не содержат user_id или contact_id.
        """
        return [e for e in self._events if e.tournament_id == tournament_id]
    
    def clear_events(self):
        """Очищает все события (для тестирования)"""
        self._events = []
        self._save_events()


# Singleton instance
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Получает singleton экземпляр сервиса аналитики"""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service
