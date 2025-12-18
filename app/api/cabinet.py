"""
API endpoints для личного кабинета организатора (WebApp).

Обеспечивает:
- Авторизацию через Telegram WebApp initData
- Получение данных кабинета (турниры, аналитика, услуги)
- Покупку/продление услуг
- Отдачу WebApp HTML страницы
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services.webapp_auth_service import (
    WebAppAuthService,
    get_webapp_auth_service,
    InvalidSignatureError,
    ExpiredDataError,
    InvalidInitDataError,
)
from app.services.tournament_service import tournament_service
from app.services.contact_service import contact_service
from app.services.analytics_service import get_analytics_service
from app.services.premium_service import premium_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cabinet"])

# Templates for WebApp HTML
import os
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)


# ============== Pydantic Models ==============

class WebAppAuthRequest(BaseModel):
    """Запрос авторизации через WebApp"""
    init_data: str = Field(..., description="URL-encoded initData от Telegram WebApp")


class OrganizerInfo(BaseModel):
    """Информация об организаторе"""
    id: int
    telegram_user_id: int
    name: str
    tournaments_count: int
    active_services: List[str] = []


class WebAppAuthResponse(BaseModel):
    """Ответ авторизации"""
    token: str
    organizer: OrganizerInfo


class CabinetOverview(BaseModel):
    """Обзор кабинета"""
    organizer: OrganizerInfo
    tournaments_count: int
    active_premium_count: int
    active_rating_count: int


class TournamentCard(BaseModel):
    """Карточка турнира для списка"""
    id: int
    title: str
    city: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    rating_active: bool = False
    rating_until: Optional[str] = None
    premium_active: bool = False
    premium_until: Optional[str] = None
    base_placement_active: bool = True


class ServiceStatus(BaseModel):
    """Статус услуг турнира"""
    premium_active: bool = False
    premium_until: Optional[str] = None
    can_buy_premium: bool = True
    can_extend_premium: bool = False
    can_buy_premium_day: bool = False
    premium_unavailable_reason: Optional[str] = None
    
    rating_active: bool = False
    rating_until: Optional[str] = None
    can_buy_rating: bool = True
    
    native_campaign_active: bool = False
    native_mentions_done: int = 0
    native_mentions_total: int = 3
    can_buy_native: bool = True
    native_unavailable_reason: Optional[str] = None


class UTMCampaignStats(BaseModel):
    """Статистика UTM кампании"""
    utm_campaign: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    clicks: int


class TournamentAnalytics(BaseModel):
    """Аналитика турнира"""
    tournament_id: int
    period_days: int
    impressions: int
    clicks: int
    ctr: float
    sources: dict
    utm_campaigns: List[UTMCampaignStats] = []


class BuyServiceRequest(BaseModel):
    """Запрос на покупку услуги"""
    service_type: str = Field(..., description="Тип услуги: premium, premium_extend, premium_day, rating, native")


class BuyServiceResponse(BaseModel):
    """Ответ на покупку услуги"""
    success: bool
    message: str
    service_type: str
    valid_until: Optional[str] = None


# ============== JWT Dependency ==============

async def verify_jwt_token(
    authorization: str = Header(..., description="Bearer JWT token")
) -> dict:
    """
    Dependency для проверки JWT токена.
    
    Ожидает заголовок: Authorization: Bearer <token>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization[7:]  # Remove "Bearer "
    
    try:
        auth_service = get_webapp_auth_service()
        return auth_service.verify_jwt_token(token)
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ============== Auth Endpoints ==============

@router.post("/webapp/auth", response_model=WebAppAuthResponse)
async def webapp_auth(request: WebAppAuthRequest):
    """
    Авторизация через Telegram WebApp initData.
    
    Принимает initData от Telegram, валидирует подпись,
    находит или создаёт организатора, возвращает JWT токен.
    """
    auth_service = get_webapp_auth_service()
    
    try:
        # Валидируем initData
        validated_data = auth_service.validate_init_data(request.init_data)
        user_data = validated_data.get("user")
        
        if not user_data:
            raise HTTPException(status_code=400, detail="User data not found in initData")
        
        telegram_user_id = user_data.get("id")
        if not telegram_user_id:
            raise HTTPException(status_code=400, detail="User ID not found")
        
    except InvalidSignatureError:
        raise HTTPException(status_code=401, detail="Invalid initData signature")
    except ExpiredDataError:
        raise HTTPException(status_code=401, detail="initData expired")
    except InvalidInitDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Ищем контакт по telegram_user_id
    contact = None
    contact_id = None
    try:
        contacts = await contact_service.get_contacts()
        for c in contacts:
            if c.get("telegram_user_id") == telegram_user_id:
                contact = c
                contact_id = c.get("id")
                break
    except Exception as e:
        logger.warning(f"Error finding contact: {e}")
    
    # Получаем турниры организатора
    tournaments = []
    if contact_id:
        try:
            all_tournaments = await tournament_service.get_tournaments()
            tournaments = [
                t for t in all_tournaments 
                if t.organizer_contact_id == contact_id
            ]
        except Exception as e:
            logger.warning(f"Error getting tournaments: {e}")
    
    # Формируем organizer_id (используем contact_id или telegram_user_id)
    organizer_id = contact_id or telegram_user_id
    
    # Определяем активные услуги
    active_services = []
    for t in tournaments:
        if premium_service.is_premium_active(t):
            if "premium" not in active_services:
                active_services.append("premium")
        if getattr(t, 'rating_active', False) or getattr(t, 'priority_rating', False):
            if "rating" not in active_services:
                active_services.append("rating")
    
    # Создаём JWT токен
    token = auth_service.create_jwt_token(
        user_data=user_data,
        organizer_id=organizer_id,
        contact_id=contact_id
    )
    
    # Формируем имя организатора
    name = user_data.get("first_name", "")
    if user_data.get("last_name"):
        name += f" {user_data['last_name']}"
    
    organizer = OrganizerInfo(
        id=organizer_id,
        telegram_user_id=telegram_user_id,
        name=name or f"User {telegram_user_id}",
        tournaments_count=len(tournaments),
        active_services=active_services
    )
    
    logger.info(f"WebApp auth successful for user {telegram_user_id}, organizer_id={organizer_id}")
    
    return WebAppAuthResponse(token=token, organizer=organizer)


# ============== Cabinet Data Endpoints ==============

@router.get("/cabinet/overview", response_model=CabinetOverview)
async def get_cabinet_overview(claims: dict = Depends(verify_jwt_token)):
    """
    Получить обзор кабинета организатора.
    
    Возвращает общую информацию: количество турниров, активные услуги.
    """
    contact_id = claims.get("contact_id")
    telegram_user_id = claims.get("telegram_user_id")
    organizer_id = claims.get("organizer_id")
    
    # Получаем турниры
    tournaments = []
    try:
        all_tournaments = await tournament_service.get_tournaments()
        if contact_id:
            tournaments = [t for t in all_tournaments if t.organizer_contact_id == contact_id]
    except Exception as e:
        logger.warning(f"Error getting tournaments: {e}")
    
    # Считаем активные услуги
    active_premium_count = 0
    active_rating_count = 0
    active_services = []
    
    for t in tournaments:
        if premium_service.is_premium_active(t):
            active_premium_count += 1
            if "premium" not in active_services:
                active_services.append("premium")
        if getattr(t, 'rating_active', False) or getattr(t, 'priority_rating', False):
            active_rating_count += 1
            if "rating" not in active_services:
                active_services.append("rating")
    
    organizer = OrganizerInfo(
        id=organizer_id,
        telegram_user_id=telegram_user_id,
        name=claims.get("first_name", "") + (" " + claims.get("last_name", "")).strip(),
        tournaments_count=len(tournaments),
        active_services=active_services
    )
    
    return CabinetOverview(
        organizer=organizer,
        tournaments_count=len(tournaments),
        active_premium_count=active_premium_count,
        active_rating_count=active_rating_count
    )


@router.get("/cabinet/tournaments", response_model=List[TournamentCard])
async def get_cabinet_tournaments(claims: dict = Depends(verify_jwt_token)):
    """
    Получить список турниров организатора.
    
    Возвращает карточки турниров со статусами премиума и рейтинга.
    """
    contact_id = claims.get("contact_id")
    
    if not contact_id:
        return []
    
    try:
        all_tournaments = await tournament_service.get_tournaments()
        tournaments = [t for t in all_tournaments if t.organizer_contact_id == contact_id]
    except Exception as e:
        logger.error(f"Error getting tournaments: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tournaments")
    
    result = []
    for t in tournaments:
        is_premium = premium_service.is_premium_active(t)
        is_rating = getattr(t, 'rating_active', False) or getattr(t, 'priority_rating', False)
        
        result.append(TournamentCard(
            id=t.id,
            title=t.title,
            city=t.city,
            start_date=t.start_date,
            end_date=t.end_date,
            rating_active=is_rating,
            rating_until=getattr(t, 'rating_until', None),
            premium_active=is_premium,
            premium_until=t.premium_until if is_premium else None,
            base_placement_active=True
        ))
    
    return result


@router.get("/cabinet/tournaments/{tournament_id}/analytics", response_model=TournamentAnalytics)
async def get_tournament_analytics(
    tournament_id: int,
    period: str = "7",
    claims: dict = Depends(verify_jwt_token)
):
    """
    Получить аналитику турнира.
    
    Параметры:
    - period: "7", "14", "30" или количество дней
    """
    contact_id = claims.get("contact_id")
    
    # Проверяем владение турниром
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.organizer_contact_id != contact_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Получаем аналитику
    try:
        period_days = int(period)
    except ValueError:
        period_days = 7
    
    analytics_service = get_analytics_service()
    analytics = await analytics_service.get_tournament_analytics(tournament_id)
    
    # Получаем данные за период
    impressions = analytics.get_impressions(period_days)
    clicks = analytics.get_clicks(period_days)
    
    # Рассчитываем CTR
    ctr = (clicks / impressions * 100) if impressions > 0 else 0.0
    
    # Группируем по источникам
    sources = {
        "bot": analytics.get_clicks_by_source("bot", period_days),
        "channel": analytics.get_clicks_by_source("channel", period_days),
        "mailing": analytics.get_clicks_by_source("mailing", period_days),
    }
    
    # UTM кампании
    utm_campaigns = []
    utm_stats = analytics.get_utm_campaigns(period_days)
    for campaign, stats in utm_stats.items():
        utm_campaigns.append(UTMCampaignStats(
            utm_campaign=campaign,
            utm_source=stats.get("utm_source"),
            utm_medium=stats.get("utm_medium"),
            clicks=stats.get("clicks", 0)
        ))
    
    return TournamentAnalytics(
        tournament_id=tournament_id,
        period_days=period_days,
        impressions=impressions,
        clicks=clicks,
        ctr=round(ctr, 2),
        sources=sources,
        utm_campaigns=utm_campaigns
    )


@router.get("/cabinet/tournaments/{tournament_id}/services", response_model=ServiceStatus)
async def get_tournament_services(
    tournament_id: int,
    claims: dict = Depends(verify_jwt_token)
):
    """
    Получить статус услуг турнира.
    
    Возвращает информацию о премиуме, рейтинге, нативных упоминаниях
    и доступности покупки каждой услуги.
    """
    contact_id = claims.get("contact_id")
    
    # Проверяем владение турниром
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.organizer_contact_id != contact_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Получаем статус премиума
    premium_status = premium_service.get_premium_status(tournament)
    can_buy_result = premium_service.can_buy_premium(tournament)
    
    # Статус рейтинга
    is_rating = getattr(tournament, 'rating_active', False) or getattr(tournament, 'priority_rating', False)
    rating_until = getattr(tournament, 'rating_until', None)
    
    return ServiceStatus(
        premium_active=premium_status["is_active"],
        premium_until=premium_status.get("premium_until"),
        can_buy_premium=can_buy_result.get("can_buy", True),
        can_extend_premium=premium_status.get("can_extend", False),
        can_buy_premium_day=premium_status.get("can_extend", False),  # Доступно только при активном премиуме
        premium_unavailable_reason=can_buy_result.get("message") if not can_buy_result.get("can_buy") else None,
        rating_active=is_rating,
        rating_until=rating_until,
        can_buy_rating=not is_rating,
        native_campaign_active=False,  # TODO: implement native campaigns
        native_mentions_done=0,
        native_mentions_total=3,
        can_buy_native=True
    )


@router.post("/cabinet/tournaments/{tournament_id}/buy", response_model=BuyServiceResponse)
async def buy_tournament_service(
    tournament_id: int,
    request: BuyServiceRequest,
    claims: dict = Depends(verify_jwt_token)
):
    """
    Купить или продлить услугу для турнира.
    
    Типы услуг:
    - premium: Купить премиум (7 дней) - 3000₽
    - premium_extend: Продлить премиум (7 дней) - 2000₽
    - premium_day: Докупить 1 день - 500₽
    - rating: Купить рейтинг (45 дней) - 9000₽
    - native: Заказать 3 нативных упоминания - 12000₽
    """
    contact_id = claims.get("contact_id")
    
    # Проверяем владение турниром
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    
    if tournament.organizer_contact_id != contact_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    service_type = request.service_type.lower()
    
    # Обрабатываем покупку
    if service_type == "premium":
        result = await premium_service.activate_premium(tournament_id)
    elif service_type == "premium_extend":
        result = await premium_service.extend_premium_7days(tournament_id)
    elif service_type == "premium_day":
        result = await premium_service.extend_premium_1day(tournament_id)
    elif service_type == "rating":
        # TODO: implement rating purchase
        return BuyServiceResponse(
            success=False,
            message="Покупка рейтинга временно недоступна. Обратитесь к администратору.",
            service_type=service_type
        )
    elif service_type == "native":
        # TODO: implement native purchase
        return BuyServiceResponse(
            success=False,
            message="Заказ нативных упоминаний временно недоступен. Обратитесь к администратору.",
            service_type=service_type
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown service type: {service_type}")
    
    if not result.get("success"):
        return BuyServiceResponse(
            success=False,
            message=result.get("message") or result.get("error", "Unknown error"),
            service_type=service_type
        )
    
    return BuyServiceResponse(
        success=True,
        message=result.get("message", "Услуга успешно оформлена"),
        service_type=service_type,
        valid_until=result.get("premium_until")
    )


# ============== WebApp HTML Endpoint ==============

@router.get("/cabinet/app", response_class=HTMLResponse)
async def cabinet_webapp(request: Request):
    """
    Отдаёт HTML страницу WebApp личного кабинета.
    
    Эта страница загружается в Telegram WebView при нажатии
    на кнопку "Личный кабинет" в боте.
    """
    return templates.TemplateResponse(
        "cabinet_webapp.html",
        {"request": request}
    )
