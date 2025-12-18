"""
API endpoints для админ-панели управления LLM ключами
"""
from fastapi import APIRouter, HTTPException, Body, Query
from typing import List, Dict, Optional
from pydantic import BaseModel
from app.services.llm_key_service import llm_key_service
from app.services.llm_service import llm_service
from app.services.llm_config_service import llm_config_service
from app.services.llm_models_service import list_gemini_models, list_openai_models, list_groq_models, list_megallm_models
import logging

# Импорт менеджера квот Gemini
try:
    from app.services.gemini_quota_service import gemini_quota_state
    GEMINI_QUOTA_AVAILABLE = True
except ImportError:
    gemini_quota_state = None
    GEMINI_QUOTA_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

class NewKeyRequest(BaseModel):
    key: str
    provider: str = "openai"  # По умолчанию OpenAI, но может быть gemini, anthropic и т.д.

@router.get("/llm-key/active")
async def get_active_key():
    """Возвращает текущий активный ключ (замаскированный)"""
    try:
        masked_key = await llm_key_service.get_active_key_masked()
        return {
            "key": masked_key,
            "has_key": masked_key is not None
        }
    except Exception as e:
        logger.error(f"Error getting active key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llm-key/all")
async def get_all_keys():
    """Возвращает список всех ключей (с маскировкой)"""
    try:
        keys = await llm_key_service.get_all_keys()
        # Убираем full_key из ответа для безопасности
        result = []
        for key_data in keys:
            result.append({
                "key": key_data["key"],  # уже замаскирован
                "provider": key_data.get("provider", "openai"),
                "is_active": key_data["is_active"],
                "is_working": key_data.get("is_working"),
                "last_checked": key_data.get("last_checked"),
                "check_error": key_data.get("check_error"),
                "created_at": key_data["created_at"]
            })
        return {"keys": result}
    except Exception as e:
        logger.error(f"Error getting all keys: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm-key/")
async def add_new_key(request: NewKeyRequest):
    """
    Сохраняет новый ключ и делает его активным.
    Все остальные ключи становятся неактивными.
    """
    try:
        if not request.key or not request.key.strip():
            raise HTTPException(status_code=400, detail="Ключ не может быть пустым")
        
        # Добавляем новый ключ
        await llm_key_service.add_new_key(request.key.strip(), request.provider)
        
        # Обновляем клиенты во всех сервисах
        await llm_service.refresh_client()
        # dialog_analyzer_service и ocr_service обновят клиент при следующем использовании
        
        logger.info("✅ New LLM key added and all services refreshed")
        
        return {
            "status": "success",
            "message": "Ключ успешно сохранен и активирован",
            "active_key": await llm_key_service.get_active_key_masked()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding new key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_admin_status():
    """Возвращает статус системы для админ-панели"""
    try:
        active_key = await llm_key_service.get_active_key_masked()
        active_provider = await llm_key_service.get_active_provider()
        all_keys = await llm_key_service.get_all_keys()
        
        # Проверяем статус LLM сервиса
        await llm_service._ensure_client()
        llm_configured = llm_service.configured
        
        # Проверяем статус активного ключа
        active_key_status = None
        if active_key:
            active_key_full = await llm_key_service.get_active_key()
            if active_key_full:
                key_status = await llm_key_service.get_key_status(active_key_full)
                active_key_status = key_status
        
        return {
            "llm_configured": llm_configured,
            "active_key": active_key,
            "active_provider": active_provider,
            "active_key_status": active_key_status,
            "total_keys": len(all_keys),
            "has_active_key": active_key is not None
        }
    except Exception as e:
        logger.error(f"Error getting admin status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm-key/check")
async def check_active_key():
    """
    Проверяет работоспособность активного ключа через реальный запрос к API.
    """
    try:
        active_key = await llm_key_service.get_active_key()
        if not active_key:
            raise HTTPException(status_code=400, detail="Активный ключ не установлен")
        
        keys = await llm_key_service.get_all_keys()
        provider = "openai"
        for key_data in keys:
            if key_data.get("full_key") == active_key:
                provider = key_data.get("provider", "openai")
                break
        
        is_working, error_msg = await llm_key_service.check_active_key()
        
        return {
            "status": "success",
            "is_working": is_working,
            "error": error_msg,
            "message": "Ключ работает" if is_working else f"Ключ не работает: {error_msg}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking active key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm-key/check/{key_index}")
async def check_specific_key(key_index: int):
    """
    Проверяет работоспособность конкретного ключа по индексу.
    """
    try:
        keys = await llm_key_service.get_all_keys()
        if key_index < 0 or key_index >= len(keys):
            raise HTTPException(status_code=400, detail="Неверный индекс ключа")
        
        key_data = keys[key_index]
        full_key = key_data.get("full_key")
        provider = key_data.get("provider", "openai")
        
        if not full_key:
            raise HTTPException(status_code=400, detail="Ключ не найден")
        
        is_working, error_msg = await llm_key_service.check_and_update_key_status(full_key, provider)
        
        return {
            "status": "success",
            "is_working": is_working,
            "error": error_msg,
            "message": "Ключ работает" if is_working else f"Ключ не работает: {error_msg}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm-key/activate/{key_index}")
async def activate_key(key_index: int):
    """
    Активирует ключ по его индексу в списке.
    Все остальные ключи становятся неактивными.
    """
    try:
        keys = await llm_key_service.get_all_keys()
        if key_index < 0 or key_index >= len(keys):
            raise HTTPException(status_code=400, detail="Неверный индекс ключа")
        
        key_data = keys[key_index]
        full_key = key_data.get("full_key")
        
        if not full_key:
            raise HTTPException(status_code=400, detail="Ключ не найден")
        
        # Активируем ключ
        success = await llm_key_service.activate_key_by_index(key_index)
        
        if not success:
            raise HTTPException(status_code=400, detail="Не удалось активировать ключ")
        
        # Обновляем клиенты во всех сервисах
        await llm_service.refresh_client()
        
        logger.info(f"✅ Key activated (index: {key_index})")
        
        return {
            "status": "success",
            "message": "Ключ успешно активирован",
            "active_key": await llm_key_service.get_active_key_masked()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ========== LLM Configuration Endpoints ==========

class SetProviderRequest(BaseModel):
    provider: str  # "openai", "gemini", "groq" или "megallm"
    api_key: str

class SetModelsRequest(BaseModel):
    provider: str
    text_model: Optional[str] = None
    vision_model: Optional[str] = None

@router.get("/llm/config")
async def get_llm_config():
    """Возвращает текущую конфигурацию LLM"""
    try:
        config = llm_config_service.get_config()
        return {
            "provider": config.provider,
            "openai": {
                "api_key": config.openai.api_key[:6] + "..." + config.openai.api_key[-4:] if config.openai.api_key and len(config.openai.api_key) > 10 else None,
                "text_model": config.openai.text_model,
                "vision_model": config.openai.vision_model
            },
            "gemini": {
                "api_key": config.gemini.api_key[:6] + "..." + config.gemini.api_key[-4:] if config.gemini.api_key and len(config.gemini.api_key) > 10 else None,
                "text_model": config.gemini.text_model,
                "vision_model": config.gemini.vision_model
            },
            "groq": {
                "api_key": config.groq.api_key[:6] + "..." + config.groq.api_key[-4:] if config.groq.api_key and len(config.groq.api_key) > 10 else None,
                "text_model": config.groq.text_model,
                "vision_model": config.groq.vision_model
            },
            "megallm": {
                "api_key": config.megallm.api_key[:6] + "..." + config.megallm.api_key[-4:] if config.megallm.api_key and len(config.megallm.api_key) > 10 else None,
                "text_model": config.megallm.text_model,
                "vision_model": config.megallm.vision_model
            }
        }
    except Exception as e:
        logger.error(f"Error getting LLM config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm/provider")
async def set_llm_provider(request: SetProviderRequest):
    """
    Устанавливает провайдера и API ключ, возвращает список доступных моделей.
    """
    try:
        if request.provider not in ["openai", "gemini", "groq", "megallm"]:
            raise HTTPException(status_code=400, detail="Provider must be 'openai', 'gemini', 'groq' или 'megallm'")
        
        # Получаем текущий конфиг для проверки смены ключа
        old_config = llm_config_service.get_config()
        old_key = None
        if request.provider == "openai":
            old_key = old_config.openai.api_key
        elif request.provider == "gemini":
            old_key = old_config.gemini.api_key
        elif request.provider == "groq":
            old_key = old_config.groq.api_key
        else:
            old_key = old_config.megallm.api_key
        
        # Устанавливаем провайдера и ключ
        llm_config_service.set_provider(request.provider)
        llm_config_service.set_provider_key(request.provider, request.api_key)
        
        # Если ключ изменился, обнуляем модели (как указано в задаче)
        if old_key != request.api_key:
            logger.info(f"API key changed for {request.provider}, resetting models")
            llm_config_service.set_models(request.provider, text_model=None, vision_model=None)
        
        # Получаем список моделей
        models = []
        try:
            if request.provider == "gemini":
                models = list_gemini_models(request.api_key)
            elif request.provider == "groq":
                models = list_groq_models(request.api_key)
            elif request.provider == "megallm":
                models = list_megallm_models(request.api_key)
            else:
                models = list_openai_models(request.api_key)
        except ValueError as e:
            # Если ошибка с ключом, возвращаем ошибку
            raise HTTPException(status_code=400, detail=str(e))
        
        # Обновляем клиенты в сервисах
        await llm_service.refresh_client()
        
        return {
            "status": "ok",
            "provider": request.provider,
            "models": models
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting LLM provider: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llm/models")
async def get_llm_models(provider: str = Query(..., description="Provider: openai, gemini, groq или megallm")):
    """
    Получает список доступных моделей для указанного провайдера.
    """
    try:
        if provider not in ["openai", "gemini", "groq", "megallm"]:
            raise HTTPException(status_code=400, detail="Provider must be 'openai', 'gemini', 'groq' или 'megallm'")
        
        config = llm_config_service.get_config()
        provider_config = llm_config_service.get_provider_config(provider)
        
        if not provider_config.api_key:
            raise HTTPException(status_code=400, detail=f"API key not set for provider: {provider}")
        
        try:
            if provider == "gemini":
                models = list_gemini_models(provider_config.api_key)
            elif provider == "groq":
                models = list_groq_models(provider_config.api_key)
            elif provider == "megallm":
                models = list_megallm_models(provider_config.api_key)
            else:
                models = list_openai_models(provider_config.api_key)
            
            return {
                "status": "ok",
                "provider": provider,
                "models": models
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting LLM models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm/models")
async def set_llm_models(request: SetModelsRequest):
    """
    Устанавливает выбранные модели для провайдера.
    Валидирует, что модели существуют в списке доступных.
    """
    try:
        if request.provider not in ["openai", "gemini", "groq", "megallm"]:
            raise HTTPException(status_code=400, detail="Provider must be 'openai', 'gemini', 'groq' или 'megallm'")
        
        config = llm_config_service.get_config()
        if request.provider != config.provider:
            raise HTTPException(
                status_code=400, 
                detail=f"Provider mismatch: trying to set models for '{request.provider}' but active provider is '{config.provider}'"
            )
        
        # Валидируем модели - проверяем, что они существуют в списке доступных
        provider_config = llm_config_service.get_provider_config(request.provider)
        if not provider_config.api_key:
            raise HTTPException(status_code=400, detail=f"API key not set for provider: {request.provider}")
        
        try:
            if request.provider == "gemini":
                available_models = list_gemini_models(provider_config.api_key)
            elif request.provider == "groq":
                available_models = list_groq_models(provider_config.api_key)
            elif request.provider == "megallm":
                available_models = list_megallm_models(provider_config.api_key)
            else:
                available_models = list_openai_models(provider_config.api_key)
            
            available_model_ids = [m["id"] for m in available_models]
            
            # Проверяем текстовую модель
            if request.text_model and request.text_model not in available_model_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Text model '{request.text_model}' not found in available models. Available: {', '.join(available_model_ids[:5])}..."
                )
            
            # Проверяем vision модель
            if request.vision_model and request.vision_model not in available_model_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Vision model '{request.vision_model}' not found in available models. Available: {', '.join(available_model_ids[:5])}..."
                )
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Устанавливаем модели
        llm_config_service.set_models(
            request.provider,
            text_model=request.text_model,
            vision_model=request.vision_model
        )
        
        # Обновляем клиенты в сервисах
        await llm_service.refresh_client()
        
        return {
            "status": "ok",
            "message": "Models updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting LLM models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llm/quota")
async def get_llm_quota():
    """
    Возвращает состояние квоты Gemini (если используется).
    """
    try:
        if not GEMINI_QUOTA_AVAILABLE or not gemini_quota_state:
            return {
                "available": False,
                "message": "Gemini quota management not available"
            }
        
        state = gemini_quota_state.get_state()
        return {
            "available": True,
            "is_available": state["is_available"],
            "daily_exhausted_until_utc": state["daily_exhausted_until_utc"],
            "last_reset_date": state["last_reset_date"]
        }
    except Exception as e:
        logger.error(f"Error getting LLM quota state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/llm-key/{index}")
async def delete_key(index: int):
    """
    Удаляет неактивный ключ по индексу из истории.
    Нельзя удалить активный ключ.
    """
    try:
        success = await llm_key_service.delete_key_by_index(index)
        if success:
            return {
                "status": "success",
                "message": "Ключ успешно удален"
            }
        else:
            raise HTTPException(status_code=400, detail="Не удалось удалить ключ")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llm-key/{index}/full")
async def get_full_key(index: int):
    """
    Возвращает полный (незамаскированный) ключ по индексу.
    Используется для просмотра и копирования ключа в админ-панели.
    """
    try:
        keys = await llm_key_service.get_all_keys()
        if index < 0 or index >= len(keys):
            raise HTTPException(status_code=404, detail=f"Ключ с индексом {index} не найден")
        
        # Возвращаем полный ключ из full_key (который есть в get_all_keys)
        full_key = keys[index].get("full_key")
        if not full_key:
            raise HTTPException(status_code=404, detail="Полный ключ не найден")
        
        return {
            "key": full_key,
            "provider": keys[index].get("provider", "openai"),
            "is_active": keys[index].get("is_active", False),
            "index": index
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting full key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ========== Tournament Data Extraction ==========

class ExtractTournamentDataRequest(BaseModel):
    """Запрос на извлечение данных турнира из текста"""
    text: str

@router.post("/extract-tournament-data")
async def extract_tournament_data(request: ExtractTournamentDataRequest):
    """
    Извлекает структурированные данные турнира из текста с помощью MegaLLM
    """
    try:
        # Убеждаемся, что LLM сервис настроен
        if not llm_service.configured:
            await llm_service.refresh_client()
            if not llm_service.configured:
                raise HTTPException(status_code=500, detail="LLM service not configured")
        
        logger.info(f"🔄 Extracting tournament data using {llm_service.provider}...")
        
        # Промпт для извлечения данных
        extraction_prompt = f"""Проанализируй следующий текст о турнире и извлеки структурированную информацию.

Текст для анализа:
{request.text}

Извлеки следующие данные (если информация отсутствует, оставь поле пустым):

1. Город проведения (только название города)
2. Регион проведения (область, край, республика)
3. Дата начала турнира (в формате YYYY-MM-DD)
4. Дата окончания турнира (в формате YYYY-MM-DD)
5. Года рождения участников (список через запятую)
6. Формат турнира (например: 11x11, 8+1, 7+1)
7. Взнос за участие (сумма с валютой)
8. Название организатора или ФИО организатора
9. Контактный номер телефона

Верни ответ СТРОГО в формате JSON:
{{
    "city": "название города или null",
    "region": "название региона или null", 
    "start_date": "YYYY-MM-DD или null",
    "end_date": "YYYY-MM-DD или null",
    "birth_years": ["2010", "2011"] или null,
    "format": "формат турнира или null",
    "entry_fee": "сумма взноса или null",
    "organizer_name": "название/ФИО организатора или null",
    "contact": "номер телефона или null"
}}

Важно: верни ТОЛЬКО JSON, без дополнительных комментариев."""

        # Генерируем ответ с помощью активного LLM провайдера (MegaLLM)
        response = await llm_service.generate_content_async(
            extraction_prompt,
            system_prompt="Ты эксперт по извлечению структурированных данных из текста. Отвечай только в формате JSON."
        )
        
        if not response:
            raise HTTPException(status_code=500, detail=f"Empty response from {llm_service.provider}")
        
        logger.info(f"📝 {llm_service.provider} response: {response}")
        
        # Парсим JSON ответ
        import json
        try:
            # Очищаем ответ от возможных лишних символов
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            extracted_data = json.loads(clean_response)
            
            # Валидируем и очищаем данные
            result = {}
            for key, value in extracted_data.items():
                if value and str(value).strip() and str(value).lower() != 'null':
                    result[key] = str(value).strip()
                else:
                    result[key] = None
            
            logger.info(f"✅ Successfully extracted tournament data using {llm_service.provider}: {result}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {llm_service.provider} response as JSON: {response}")
            raise HTTPException(status_code=500, detail=f"Invalid JSON response from {llm_service.provider}: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting tournament data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

