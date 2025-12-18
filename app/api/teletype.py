"""
API для работы с Telegraph/Teletype
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging

from app.services.telegraph_service import telegraph_service
from app.services.tournament_service import tournament_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/publish/{tournament_id}")
async def publish_tournament_to_telegraph(tournament_id: int, request: Request):
    """Публикует турнир в Telegraph/Teletype"""
    try:
        # Получаем данные турнира
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Турнир не найден")
        
        # Конвертируем в dict для telegraph_service
        tournament_dict = tournament.model_dump() if hasattr(tournament, 'model_dump') else tournament.__dict__
        
        # Определяем base_url для ссылок
        base_url = str(request.base_url).rstrip("/")
        
        # Публикуем в Telegraph
        result = await telegraph_service.create_page(tournament_dict, base_url)
        
        if result.get("success"):
            # Сохраняем ссылку на публикацию в турнире
            updates = {
                "teletype_url": result["url"],
                "teletype_post_id": result["path"]
            }
            await tournament_service.update_tournament(tournament_id, updates)
            
            return {
                "success": True,
                "message": "Турнир опубликован в Telegraph",
                "url": result["url"],
                "path": result["path"]
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Ошибка публикации"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка публикации турнира {tournament_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update/{tournament_id}")
async def update_tournament_in_telegraph(tournament_id: int, request: Request):
    """Обновляет турнир в Telegraph/Teletype"""
    try:
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Турнир не найден")
        
        tournament_dict = tournament.model_dump() if hasattr(tournament, 'model_dump') else tournament.__dict__
        
        if not tournament_dict.get("teletype_post_id"):
            raise HTTPException(status_code=400, detail="Турнир не опубликован в Telegraph")
        
        base_url = str(request.base_url).rstrip("/")
        result = await telegraph_service.edit_page(tournament_dict["teletype_post_id"], tournament_dict, base_url)
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Турнир обновлён в Telegraph",
                "url": result["url"]
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Ошибка обновления"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления турнира {tournament_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{tournament_id}")
async def get_telegraph_status(tournament_id: int):
    """Получает статус публикации турнира"""
    try:
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Турнир не найден")
        
        tournament_dict = tournament.model_dump() if hasattr(tournament, 'model_dump') else tournament.__dict__
        
        return {
            "tournament_id": tournament_id,
            "published": bool(tournament_dict.get("teletype_url")),
            "teletype_url": tournament_dict.get("teletype_url"),
            "teletype_post_id": tournament_dict.get("teletype_post_id")
        }
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        raise HTTPException(status_code=500, detail=str(e))
