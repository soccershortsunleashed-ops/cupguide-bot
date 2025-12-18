"""
API для извлечения данных турниров
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.llm_service import llm_service
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tournament-extract"])

@router.get("/test")
async def test_endpoint():
    """Тестовый эндпоинт для проверки работы роутера"""
    return {"status": "ok", "message": "Tournament extract router is working", "provider": "MegaLLM"}

class ExtractDataRequest(BaseModel):
    """Запрос на извлечение данных турнира из текста"""
    text: str = Field(..., min_length=10, description="Текст для анализа")

@router.post("/extract")
async def extract_tournament_data(request: ExtractDataRequest):
    """
    Извлекает структурированные данные турнира из текста с помощью MegaLLM
    """
    try:
        # Убеждаемся, что LLM сервис настроен
        if not llm_service.configured:
            await llm_service.refresh_client()
            if not llm_service.configured:
                raise HTTPException(status_code=500, detail="LLM service not configured")
        
        logger.info(f"🔄 Extracting tournament data using MegaLLM...")
        
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

        # Генерируем ответ с помощью MegaLLM
        response = await llm_service.generate_content_async(
            extraction_prompt,
            system_prompt="Ты эксперт по извлечению структурированных данных из текста. Отвечай только в формате JSON."
        )
        
        if not response:
            raise HTTPException(status_code=500, detail="Empty response from MegaLLM")
        
        logger.info(f"📝 MegaLLM response: {response}")
        
        # Парсим JSON ответ
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
            
            logger.info(f"✅ Successfully extracted tournament data using MegaLLM: {result}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse MegaLLM response as JSON: {response}")
            raise HTTPException(status_code=500, detail=f"Invalid JSON response from MegaLLM: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting tournament data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))