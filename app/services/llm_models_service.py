"""
Сервис для получения списка доступных моделей LLM провайдеров
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Попытка импортировать Gemini
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False


def list_gemini_models(api_key: str) -> List[Dict[str, Any]]:
    """
    Получает список доступных моделей Gemini для указанного API ключа.
    
    Args:
        api_key: API ключ Gemini
        
    Returns:
        Список словарей с информацией о моделях
        
    Raises:
        ValueError: Если ключ неверный или произошла ошибка API
    """
    if not GEMINI_AVAILABLE:
        raise ValueError("Google Generative AI библиотека не установлена. Установите: pip install google-generativeai")
    
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        
        result = []
        for model in models:
            # Получаем поддерживаемые методы генерации
            methods = getattr(model, "supported_generation_methods", [])
            
            # Фильтруем только модели с generateContent
            if "generateContent" not in methods:
                continue
            
            model_name = model.name  # "models/gemini-pro"
            short_id = model_name.split("/")[-1] if "/" in model_name else model_name
            
            result.append({
                "id": model_name,
                "short_id": short_id,
                "display_name": getattr(model, "display_name", short_id),
                "methods": list(methods),
                "is_vision": "vision" in short_id.lower() or "multimodal" in str(methods).lower()
            })
        
        logger.info(f"Found {len(result)} Gemini models with generateContent support")
        return result
        
    except Exception as e:
        error_msg = str(e)
        if "UNAUTHENTICATED" in error_msg or "API_KEY_INVALID" in error_msg or "invalid" in error_msg.lower():
            raise ValueError(f"Неверный API ключ Gemini: {error_msg}")
        elif "403" in error_msg or "PERMISSION_DENIED" in error_msg:
            raise ValueError(f"Нет доступа к API: {error_msg}")
        else:
            logger.error(f"Error listing Gemini models: {e}", exc_info=True)
            raise ValueError(f"Ошибка получения списка моделей: {error_msg}")


def list_openai_models(api_key: str) -> List[Dict[str, Any]]:
    """
    Получает список доступных моделей OpenAI.
    
    Args:
        api_key: API ключ OpenAI
        
    Returns:
        Список словарей с информацией о моделях
    """
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        models = client.models.list()
        
        result = []
        for model in models.data:
            # Фильтруем только GPT модели
            if not model.id.startswith("gpt"):
                continue
            
            is_vision = "vision" in model.id.lower() or "4o" in model.id.lower()
            
            result.append({
                "id": model.id,
                "short_id": model.id,
                "display_name": model.id,
                "is_vision": is_vision
            })
        
        logger.info(f"Found {len(result)} OpenAI models")
        return result
        
    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower() or "401" in error_msg or "unauthorized" in error_msg.lower():
            raise ValueError(f"Неверный API ключ OpenAI: {error_msg}")
        else:
            logger.error(f"Error listing OpenAI models: {e}", exc_info=True)
            raise ValueError(f"Ошибка получения списка моделей: {error_msg}")


def list_megallm_models(api_key: str) -> List[Dict[str, Any]]:
    """
    Получает список моделей MegaLLM (OpenAI-совместимый API).
    Если запрос к /models недоступен, возвращаем базовый список.
    """
    from openai import OpenAI
    base_url = "https://ai.megallm.io/v1"
    fallback_models = [
        {"id": "gpt-5", "short_id": "gpt-5", "display_name": "gpt-5", "is_vision": False},
        {"id": "gpt-5-vision", "short_id": "gpt-5-vision", "display_name": "gpt-5-vision", "is_vision": True},
    ]
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        models = client.models.list()
        result = []
        for model in models.data:
            result.append({
                "id": model.id,
                "short_id": model.id,
                "display_name": getattr(model, "owned_by", None) and f"{model.id} ({model.owned_by})" or model.id,
                "is_vision": "vision" in model.id.lower()
            })
        if not result:
            return fallback_models
        return result
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Fallback to static MegaLLM models due to error: {error_msg}")
        return fallback_models


def list_groq_models(api_key: str) -> List[Dict[str, Any]]:
    """
    Получает список доступных моделей Groq (OpenAI-совместимый API).
    """
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        models = client.models.list()
        
        result = []
        for model in models.data:
            result.append({
                "id": model.id,
                "short_id": model.id,
                "display_name": getattr(model, "owned_by", None) and f"{model.id} ({model.owned_by})" or model.id,
                "is_vision": "vision" in model.id.lower()
            })
        
        logger.info(f"Found {len(result)} Groq models")
        return result
        
    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower() or "401" in error_msg or "unauthorized" in error_msg.lower():
            raise ValueError(f"Неверный API ключ Groq: {error_msg}")
        else:
            logger.error(f"Error listing Groq models: {e}", exc_info=True)
            raise ValueError(f"Ошибка получения списка моделей: {error_msg}")

