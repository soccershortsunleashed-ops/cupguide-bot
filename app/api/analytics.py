"""
API endpoints для аналитики турниров (личный кабинет организатора).
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import logging

from app.services.analytics_service import get_analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


@router.get("/tournament/{tournament_id}")
async def get_tournament_analytics(tournament_id: int, days: int = 30):
    """
    Получить аналитику турнира.
    
    Args:
        tournament_id: ID турнира
        days: Период в днях (по умолчанию 30)
    
    Returns:
        Агрегированные данные аналитики
    """
    try:
        analytics_service = get_analytics_service()
        analytics = await analytics_service.get_tournament_analytics(tournament_id)
        
        return {
            "tournament_id": tournament_id,
            "impressions_7d": analytics.impressions_7d,
            "impressions_30d": analytics.impressions_30d,
            "clicks_7d": analytics.clicks_7d,
            "clicks_30d": analytics.clicks_30d,
            "clicks_by_source": analytics.clicks_by_source,
            "utm_breakdown": [utm.to_dict() for utm in analytics.utm_breakdown]
        }
        
    except Exception as e:
        logger.error(f"Error getting tournament analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/impression")
async def log_impression(tournament_id: int, context: str = "search"):
    """
    Логирует показ турнира.
    
    Args:
        tournament_id: ID турнира
        context: Контекст показа (search, tournaments_command)
    """
    try:
        analytics_service = get_analytics_service()
        event = await analytics_service.log_impression(tournament_id, context)
        return {"success": True, "event_id": event.id}
        
    except Exception as e:
        logger.error(f"Error logging impression: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/click")
async def log_click(
    tournament_id: int, 
    source: str = "bot",
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None
):
    """
    Логирует клик по турниру.
    
    Args:
        tournament_id: ID турнира
        source: Источник клика (bot, channel, mailing)
        utm_*: UTM-параметры
    """
    try:
        analytics_service = get_analytics_service()
        utm_params = {}
        if utm_source:
            utm_params["utm_source"] = utm_source
        if utm_medium:
            utm_params["utm_medium"] = utm_medium
        if utm_campaign:
            utm_params["utm_campaign"] = utm_campaign
        
        event = await analytics_service.log_click(tournament_id, source, utm_params)
        return {"success": True, "event_id": event.id}
        
    except Exception as e:
        logger.error(f"Error logging click: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel

class AnalyticsEventRequest(BaseModel):
    """Запрос на логирование события аналитики"""
    tournament_id: int
    event_type: str  # impression, click
    context: Optional[str] = None
    source: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/event")
async def log_event(request: AnalyticsEventRequest):
    """
    Универсальный endpoint для логирования событий аналитики.
    
    Args:
        request: Данные события
    """
    try:
        analytics_service = get_analytics_service()
        
        if request.event_type == "impression":
            event = await analytics_service.log_impression(
                request.tournament_id, 
                request.context or "unknown"
            )
        elif request.event_type == "click":
            utm_params = {}
            if request.utm_source:
                utm_params["utm_source"] = request.utm_source
            if request.utm_medium:
                utm_params["utm_medium"] = request.utm_medium
            if request.utm_campaign:
                utm_params["utm_campaign"] = request.utm_campaign
            
            event = await analytics_service.log_click(
                request.tournament_id, 
                request.source or "unknown",
                utm_params
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown event_type: {request.event_type}")
        
        logger.info(f"📊 Analytics event logged: {request.event_type} for tournament {request.tournament_id}")
        return {"success": True, "event_id": event.id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error logging analytics event: {e}")
        raise HTTPException(status_code=500, detail=str(e))
