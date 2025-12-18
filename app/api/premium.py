"""
API endpoints для управления Премиум-размещением турниров
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from app.services.premium_service import premium_service
from app.services.tournament_service import tournament_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/premium", tags=["premium"])


class PremiumActionRequest(BaseModel):
    """Запрос на действие с Премиумом"""
    action: str = Field(..., description="Действие: activate, extend_7days, extend_1day")


class AdminPremiumRequest(BaseModel):
    """Запрос админа на управление Премиумом"""
    is_premium: bool = Field(..., description="Включить/выключить Премиум")
    premium_until: Optional[str] = Field(None, description="Дата окончания (YYYY-MM-DD)")


@router.get("/{tournament_id}/status")
async def get_premium_status(tournament_id: int):
    """
    Получить статус Премиума для турнира.
    
    Возвращает:
    - is_active: активен ли Премиум
    - status: active / cooldown / inactive
    - status_message: сообщение для пользователя
    - premium_until: дата окончания
    - can_extend: можно ли продлить
    - can_buy: можно ли купить
    - available_actions: доступные действия с ценами
    """
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail="Турнир не найден")
    
    status = premium_service.get_premium_status(tournament)
    return {
        "tournament_id": tournament_id,
        "tournament_title": tournament.title,
        **status
    }


@router.post("/{tournament_id}/action")
async def premium_action(tournament_id: int, request: PremiumActionRequest):
    """
    Выполнить действие с Премиумом.
    
    Действия:
    - activate: Купить Премиум (7 дней) - 3000 ₽
    - extend_7days: Продлить на 7 дней - 2000 ₽
    - extend_1day: Докупить 1 день - 500 ₽
    """
    action = request.action.lower()
    
    if action == "activate":
        result = await premium_service.activate_premium(tournament_id)
    elif action == "extend_7days":
        result = await premium_service.extend_premium_7days(tournament_id)
    elif action == "extend_1day":
        result = await premium_service.extend_premium_1day(tournament_id)
    else:
        raise HTTPException(status_code=400, detail=f"Неизвестное действие: {action}")
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message") or result.get("error"))
    
    return result


@router.post("/{tournament_id}/activate")
async def activate_premium(tournament_id: int):
    """
    Активировать Премиум на 7 дней.
    Цена: 3000 ₽
    """
    result = await premium_service.activate_premium(tournament_id)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message") or result.get("error"))
    
    return result


@router.post("/{tournament_id}/extend")
async def extend_premium(tournament_id: int, days: int = 7):
    """
    Продлить Премиум.
    
    days=7: Продление на 7 дней - 2000 ₽
    days=1: Докупка 1 дня - 500 ₽
    """
    if days == 7:
        result = await premium_service.extend_premium_7days(tournament_id)
    elif days == 1:
        result = await premium_service.extend_premium_1day(tournament_id)
    else:
        raise HTTPException(status_code=400, detail="Допустимые значения: days=7 или days=1")
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message") or result.get("error"))
    
    return result


# ========== Админ-эндпоинты ==========

@router.post("/{tournament_id}/admin/set")
async def admin_set_premium(tournament_id: int, request: AdminPremiumRequest):
    """
    [ADMIN] Установить статус Премиума вручную.
    
    Позволяет:
    - Включить/выключить Премиум
    - Задать дату окончания вручную
    """
    result = await premium_service.admin_set_premium(
        tournament_id=tournament_id,
        is_premium=request.is_premium,
        premium_until=request.premium_until
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.post("/{tournament_id}/admin/deactivate")
async def admin_deactivate_premium(tournament_id: int):
    """
    [ADMIN] Отключить Премиум досрочно.
    """
    result = await premium_service.deactivate_premium(tournament_id, admin=True)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


@router.post("/admin/check-expired")
async def admin_check_expired():
    """
    [ADMIN] Проверить и отключить истёкшие Премиумы.
    
    Эту функцию можно вызывать по cron или вручную.
    """
    deactivated = await premium_service.check_and_deactivate_expired()
    
    return {
        "success": True,
        "deactivated_count": len(deactivated),
        "deactivated_tournament_ids": deactivated
    }


@router.get("/admin/list")
async def admin_list_premium_tournaments():
    """
    [ADMIN] Получить список всех турниров с Премиумом.
    """
    tournaments = await tournament_service.get_tournaments()
    
    premium_tournaments = []
    for t in tournaments:
        if t.is_premium or t.premium_until:
            status = premium_service.get_premium_status(t)
            premium_tournaments.append({
                "tournament_id": t.id,
                "title": t.title,
                "is_premium": t.is_premium,
                "premium_until": t.premium_until,
                "premium_last_ended": t.premium_last_ended,
                "status": status["status"],
                "is_active": status["is_active"]
            })
    
    return {
        "count": len(premium_tournaments),
        "tournaments": premium_tournaments
    }
