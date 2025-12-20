"""
Leads API - эндпоинты для работы с лидами фриланс-воронки
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.lead_service import lead_service
from app.models.lead import Lead, LeadStatus, LeadGrade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["leads"])


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class LeadCreateRequest(BaseModel):
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    source_type: str = "direct"
    source_channel_id: Optional[int] = None
    source_post_id: Optional[int] = None
    # Скрининг
    goal: Optional[str] = None
    pain: Optional[str] = None
    context: Optional[str] = None
    niche_text: Optional[str] = None
    # LLM скоринг
    llm_grade: Optional[str] = None
    llm_score: Optional[int] = None
    llm_reason: Optional[str] = None
    final_route: Optional[str] = None
    deterministic_score: Optional[int] = None
    deterministic_grade: Optional[str] = None
    # Контакты
    contact_preferred: Optional[str] = None
    contact_link: Optional[str] = None
    bot_platform: Optional[str] = None
    start_window: Optional[str] = None
    status: str = "NEW"
    # A_FLOW бриф
    a_traffic: Optional[str] = None
    a_payment: Optional[str] = None
    a_steps: Optional[str] = None
    # B_FLOW бриф
    b_product: Optional[str] = None
    b_objection: Optional[str] = None
    b_goal: Optional[str] = None
    b_package: Optional[str] = None


class LeadUpdateRequest(BaseModel):
    goal: Optional[str] = None
    pain: Optional[str] = None
    context: Optional[str] = None
    niche_text: Optional[str] = None
    llm_grade: Optional[str] = None
    llm_score: Optional[int] = None
    llm_reason: Optional[str] = None
    final_route: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None


class LeadStatusUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None


class ApplicationCreateRequest(BaseModel):
    contact_preferred: str
    project_link: Optional[str] = None
    bot_platform: str
    start_window: Optional[str] = None
    traffic_source: Optional[str] = None
    payment_crm: Optional[str] = None
    steps_count: Optional[str] = None
    main_product: Optional[str] = None
    main_objection: Optional[str] = None
    final_goal: Optional[str] = None
    selected_package: Optional[str] = None


class FunnelStatsResponse(BaseModel):
    total: int
    by_grade: dict
    by_route: dict
    by_status: dict
    applications_count: int
    conversion_rate: float


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/", response_model=List[Lead])
async def get_leads(
    status: Optional[str] = Query(None, description="Filter by status"),
    grade: Optional[str] = Query(None, description="Filter by grade (A/B/TRASH)"),
    route: Optional[str] = Query(None, description="Filter by route"),
    limit: int = Query(100, ge=1, le=1000)
):
    """Получить список лидов с фильтрацией"""
    try:
        leads = await lead_service.get_leads(
            status=status,
            grade=grade,
            route=route,
            limit=limit
        )
        return leads
    except Exception as e:
        logger.error(f"Error getting leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=FunnelStatsResponse)
async def get_funnel_stats():
    """Получить статистику воронки"""
    try:
        stats = await lead_service.get_funnel_stats()
        return FunnelStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting funnel stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{lead_id}", response_model=Lead)
async def get_lead(lead_id: int):
    """Получить лида по ID"""
    lead = await lead_service.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("/telegram/{telegram_user_id}", response_model=Lead)
async def get_lead_by_telegram(telegram_user_id: int):
    """Получить лида по Telegram user ID"""
    lead = await lead_service.get_lead_by_telegram_id(telegram_user_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/", response_model=Lead)
async def create_lead(request: LeadCreateRequest):
    """Создать нового лида"""
    try:
        lead = await lead_service.create_lead(request.model_dump())
        return lead
    except Exception as e:
        logger.error(f"Error creating lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{lead_id}", response_model=Lead)
async def update_lead(lead_id: int, request: LeadUpdateRequest):
    """Обновить лида"""
    lead = await lead_service.update_lead(lead_id, request.model_dump(exclude_none=True))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}/status", response_model=Lead)
async def update_lead_status(lead_id: int, request: LeadStatusUpdateRequest):
    """Обновить статус лида"""
    lead = await lead_service.update_lead_status(
        lead_id, 
        request.status, 
        request.notes
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("/{lead_id}/events")
async def get_lead_events(lead_id: int):
    """Получить события лида"""
    events = await lead_service.get_lead_events(lead_id)
    return events


@router.get("/{lead_id}/conversation")
async def get_lead_conversation(lead_id: int):
    """Получить историю диалога с лидом"""
    conversation = await lead_service.get_lead_conversation(lead_id)
    return conversation


@router.post("/{lead_id}/application")
async def create_application(lead_id: int, request: ApplicationCreateRequest):
    """Создать заявку от лида"""
    # Проверяем существование лида
    lead = await lead_service.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    try:
        application = await lead_service.create_application(
            lead_id, 
            request.model_dump()
        )
        return application
    except Exception as e:
        logger.error(f"Error creating application: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/applications/")
async def get_applications(status: Optional[str] = None):
    """Получить список заявок"""
    applications = await lead_service.get_applications(status=status)
    return applications
