"""
LLM Tagger for extracting user interests from conversations
"""
import json
import logging
from typing import Dict, List, Any, Optional

import openai

from config import config

logger = logging.getLogger(__name__)

class LLMTagger:
    """LLM-powered tagger for extracting user interests"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=config.MEGALLM_API_KEY,
            base_url=config.MEGALLM_BASE_URL,
            max_retries=1,  # Минимум retry для tagger (не критичный функционал)
            timeout=20.0  # Короткий таймаут - теги не критичны
        )
        self.model = "llama3-8b-instruct"  # MegaLLM free tier model
    
    async def extract_tags(
        self, 
        message: str, 
        contact_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Extract tags from user message"""
        try:
            system_prompt = self._get_system_prompt()
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                
                # Validate structure
                if not isinstance(result, dict):
                    raise ValueError("Result is not a dictionary")
                
                # Ensure required fields
                result.setdefault("add", [])
                result.setdefault("remove", [])
                result.setdefault("notes", "")
                
                # Validate tags structure
                for tag_list in [result["add"], result["remove"]]:
                    if not isinstance(tag_list, list):
                        continue
                    
                    for tag in tag_list:
                        if not isinstance(tag, dict):
                            continue
                        
                        # Ensure required tag fields
                        tag.setdefault("key", "")
                        tag.setdefault("value", "")
                        tag.setdefault("confidence", 0.5)
                        
                        # Add metadata
                        tag["last_seen_at"] = None  # Will be set by backend
                        tag["source"] = "telegram_tagger"
                
                logger.info(f"Extracted tags for user {user_id}: {len(result['add'])} add, {len(result['remove'])} remove")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tagger JSON response: {e}")
                logger.error(f"Response text: {result_text}")
                return {"add": [], "remove": [], "notes": "JSON parse error"}
            
        except Exception as e:
            logger.error(f"Error in LLM tagger: {e}")
            return {"add": [], "remove": [], "notes": f"Error: {str(e)}"}
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for tagger"""
        return """
Ты - система извлечения интересов пользователя из сообщений о спортивных турнирах.

Твоя задача - анализировать сообщение пользователя и извлекать его интересы в виде тегов.

ТАКСОНОМИЯ ТЕГОВ:
- city: город интереса (например: "Санкт-Петербург", "Москва", "Сочи", "Кабардинка", "Лазаревское")
- age_year: год рождения (например: "2016", "2015", "2014")
- time_period: временной период (например: "2026-01", "январь", "март", "зима", "весна")
- format: формат игры (например: "5x5", "8x8", "11x11", "futsal")
- budget: бюджет (например: "до 10000", "бесплатно", "дорого")
- topic: тема разговора (например: "поиск турниров", "заявка", "регламент", "контакты", "информация о турнире")
- tournament_interest: название турнира, которым интересуется пользователь (например: "LazaCup", "SIRIUS CUP", "Рождественский кубок")

ПРАВИЛА:
1. Извлекай только явно упомянутые интересы
2. Не придумывай теги, если информации нет
3. Confidence от 0.0 до 1.0 (высокая уверенность = 0.8+)
4. Если пользователь изменил интерес, добавь новый в add и старый в remove
5. Нормализуй значения (например: "СПб" → "Санкт-Петербург")

ФОРМАТ ОТВЕТА (строгий JSON):
{
  "add": [
    {"key": "city", "value": "Санкт-Петербург", "confidence": 0.92},
    {"key": "age_year", "value": "2016", "confidence": 0.88}
  ],
  "remove": [],
  "notes": "Пользователь ищет турниры 2016 г.р. в СПб"
}

ПРИМЕРЫ:

Сообщение: "Найди турниры 2016 года рождения в январе в СПб"
Ответ:
{
  "add": [
    {"key": "city", "value": "Санкт-Петербург", "confidence": 0.95},
    {"key": "age_year", "value": "2016", "confidence": 0.98},
    {"key": "time_period", "value": "2026-01", "confidence": 0.85},
    {"key": "topic", "value": "поиск турниров", "confidence": 0.90}
  ],
  "remove": [],
  "notes": "Поиск турниров для 2016 г.р. в Санкт-Петербурге на январь"
}

Сообщение: "Сколько стоит участие в турнире?"
Ответ:
{
  "add": [
    {"key": "topic", "value": "стоимость", "confidence": 0.95}
  ],
  "remove": [],
  "notes": "Интерес к стоимости участия"
}

Сообщение: "Теперь ищу турниры в Москве, а не в СПб"
Ответ:
{
  "add": [
    {"key": "city", "value": "Москва", "confidence": 0.98}
  ],
  "remove": [
    {"key": "city", "value": "Санкт-Петербург", "confidence": 0.95}
  ],
  "notes": "Смена города интереса с СПб на Москву"
}

Отвечай ТОЛЬКО JSON, без дополнительного текста.
        """.strip()
    
    def normalize_city(self, city: str) -> str:
        """Normalize city names"""
        city_mapping = {
            "спб": "Санкт-Петербург",
            "питер": "Санкт-Петербург",
            "санкт-петербург": "Санкт-Петербург",
            "москва": "Москва",
            "мск": "Москва",
            "сочи": "Сочи",
            "краснодар": "Краснодар",
            "екатеринбург": "Екатеринбург",
            "казань": "Казань",
            "нижний новгород": "Нижний Новгород",
            "челябинск": "Челябинск",
            "омск": "Омск",
            "самара": "Самара",
            "ростов-на-дону": "Ростов-на-Дону",
            "уфа": "Уфа",
            "красноярск": "Красноярск",
            "воронеж": "Воронеж",
            "пермь": "Пермь",
            "волгоград": "Волгоград"
        }
        
        return city_mapping.get(city.lower(), city)
    
    def normalize_format(self, format_str: str) -> str:
        """Normalize game formats"""
        format_mapping = {
            "5на5": "5x5",
            "5 на 5": "5x5",
            "5+1": "5x5",
            "8на8": "8x8",
            "8 на 8": "8x8",
            "8+1": "8x8",
            "11на11": "11x11",
            "11 на 11": "11x11",
            "11+1": "11x11",
            "мини-футбол": "futsal",
            "футзал": "futsal",
            "зал": "futsal"
        }
        
        return format_mapping.get(format_str.lower(), format_str)
    
    def normalize_time_period(self, period: str) -> str:
        """Normalize time periods"""
        month_mapping = {
            "январь": "2026-01",
            "февраль": "2026-02", 
            "март": "2026-03",
            "апрель": "2026-04",
            "май": "2026-05",
            "июнь": "2026-06",
            "июль": "2026-07",
            "август": "2026-08",
            "сентябрь": "2026-09",
            "октябрь": "2026-10",
            "ноябрь": "2026-11",
            "декабрь": "2026-12",
            "зима": "зима",
            "весна": "весна",
            "лето": "лето",
            "осень": "осень"
        }
        
        return month_mapping.get(period.lower(), period)