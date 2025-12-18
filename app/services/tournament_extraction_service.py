"""
Сервис для извлечения данных турнира из Markdown текста
"""
import re
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

class TournamentExtractionService:
    """Сервис для извлечения структурированных данных турнира из Markdown"""
    
    async def extract_tournament_data(self, markdown_text: str) -> Dict[str, Any]:
        """
        Извлекает данные турнира из Markdown текста
        
        Args:
            markdown_text: Исходный текст турнира в формате Markdown
            
        Returns:
            Словарь с извлеченными данными согласно ExtractedTournament типу
        """
        try:
            # Убеждаемся, что LLM сервис настроен
            if not llm_service.configured:
                await llm_service.refresh_client()
                if not llm_service.configured:
                    raise Exception("LLM service not configured")
            
            # Создаем промпт для извлечения данных
            extraction_prompt = self._create_extraction_prompt(markdown_text)
            
            # Получаем ответ от LLM
            response = await llm_service.generate_content_async(
                extraction_prompt,
                system_prompt="Ты эксперт по извлечению структурированных данных из текста о спортивных турнирах. Отвечай только в формате JSON."
            )
            
            if not response:
                return self._get_empty_result()
            
            # Парсим и валидируем ответ
            extracted_data = self._parse_llm_response(response)
            
            # Постобработка данных
            processed_data = await self._post_process_data(extracted_data)
            
            logger.info(f"✅ Successfully extracted tournament data")
            return processed_data
            
        except Exception as e:
            logger.error(f"Error extracting tournament data: {e}", exc_info=True)
            return self._get_empty_result()
    
    def _create_extraction_prompt(self, markdown_text: str) -> str:
        """Создает промпт для извлечения данных"""
        return f"""Проанализируй следующий текст о турнире и извлеки структурированную информацию.

Текст для анализа:
{markdown_text}

Извлеки следующие данные (если информация отсутствует, используй null):

ОБЯЗАТЕЛЬНЫЕ ПОЛЯ:
- Город проведения (только название города)
- Регион проведения (область, край, республика)
- Дата начала (формат: dd.mm.yyyy)
- Дата окончания (формат: dd.mm.yyyy)
- Года рождения участников (массив чисел)

ФОРМАТЫ МАТЧЕЙ (из таблицы):
- Извлеки таблицу с форматами по возрастам
- Для каждого года: формат игры, размеры поля, ворота, замены, время

ДОПОЛНИТЕЛЬНЫЕ ПОЛЯ:
- Состав команды (игроки + тренер + представитель)
- Документы для регистрации
- Структура турнира
- Система очков (победа/ничья/поражение)
- Награды (командные и индивидуальные)
- Взнос за участие (сумма, валюта, отображение)
- Размещение (объекты + варианты + тарифы)
- Дополнительные услуги
- Контакты (имя, телефон, email)

Верни ответ СТРОГО в формате JSON:
{{
    "location": {{
        "placeRaw": "полное место проведения",
        "city": "город",
        "region": "регион",
        "regionNeedsConfirm": false
    }},
    "startDate": "dd.mm.yyyy",
    "endDate": "dd.mm.yyyy",
    "birthYears": [2014, 2015, 2016],
    "matchFormats": [
        {{
            "year": 2014,
            "format": "8+1",
            "field": "60×40",
            "goal": "5×2",
            "substitutions": "свободные",
            "time": "2×25 мин"
        }}
    ],
    "teamRoster": {{
        "playersMax": 18,
        "coach": 1,
        "representative": 1
    }},
    "documents": ["Заявка", "Медицинские справки"],
    "structure": ["Групповой этап", "Плей-офф"],
    "points": {{
        "win": 3,
        "draw": 1,
        "loss": 0
    }},
    "awardsTeam": ["Кубок", "Медали"],
    "awardsIndividual": ["Лучший игрок"],
    "fee": {{
        "amount": 20000,
        "currency": "RUB",
        "display": "20 000 руб."
    }},
    "accommodation": [
        {{
            "name": "Отель Сочи",
            "rooms": [
                {{
                    "type": "2-местный",
                    "tariffs": [3700, 4300],
                    "display": "3700-4300 руб/сутки"
                }}
            ]
        }}
    ],
    "services": [
        {{
            "type": "transfer",
            "title": "Трансфер",
            "details": "Аэропорт-отель",
            "price": 1500,
            "display": "1500 руб."
        }}
    ],
    "contacts": {{
        "person": "Иван Иванов",
        "phoneDisplay": "+7 904 507-24-50",
        "phoneDigits": "79045072450",
        "email": "contact@tournament.ru"
    }}
}}

Важно: верни ТОЛЬКО JSON, без дополнительных комментариев."""
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Парсит ответ от LLM"""
        try:
            # Очищаем ответ от возможных лишних символов
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            return json.loads(clean_response)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {response}")
            return {}
    
    async def _post_process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Постобработка извлеченных данных"""
        # Нормализация дат
        if data.get('startDate'):
            data['startDate'] = self._normalize_date(data['startDate'])
        if data.get('endDate'):
            data['endDate'] = self._normalize_date(data['endDate'])
        
        # Нормализация телефона
        if data.get('contacts', {}).get('phoneDisplay'):
            phone_display = data['contacts']['phoneDisplay']
            data['contacts']['phoneDigits'] = self._normalize_phone(phone_display)
        
        # Определение региона если не указан
        location = data.get('location', {})
        if location.get('city') and not location.get('region'):
            region = await self._infer_region(location['city'])
            if region:
                location['region'] = region
                location['regionNeedsConfirm'] = False
            else:
                location['regionNeedsConfirm'] = True
        
        return data
    
    def _normalize_date(self, date_str: str) -> str:
        """Нормализует дату в формат dd.mm.yyyy"""
        if not date_str:
            return ""
        
        # Различные форматы дат
        patterns = [
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # dd.mm.yyyy
            r'(\d{1,2})/(\d{1,2})/(\d{4})',   # dd/mm/yyyy
            r'(\d{4})-(\d{1,2})-(\d{1,2})',   # yyyy-mm-dd
        ]
        
        for pattern in patterns:
            match = re.search(pattern, str(date_str))
            if match:
                if pattern.endswith(r'(\d{4})'):  # dd.mm.yyyy или dd/mm/yyyy
                    day, month, year = match.groups()
                else:  # yyyy-mm-dd
                    year, month, day = match.groups()
                
                return f"{day.zfill(2)}.{month.zfill(2)}.{year}"
        
        return str(date_str)
    
    def _normalize_phone(self, phone_str: str) -> str:
        """Извлекает только цифры из номера телефона"""
        if not phone_str:
            return ""
        
        # Извлекаем только цифры
        digits = re.sub(r'\D', '', str(phone_str))
        
        # Если начинается с 8, заменяем на 7
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]
        
        return digits
    
    async def _infer_region(self, city: str) -> Optional[str]:
        """Определяет регион по городу с помощью LLM"""
        if not city:
            return None
        
        try:
            prompt = f"""Определи регион России для города: {city}
            
Верни только название региона без дополнительных слов.
Если город не в России, верни страну.
Если не можешь определить, верни null.

ВАЖНО: Если город уже является названием региона, верни null.
Например, для города "Кабардинка" верни "Краснодарский край", а не "Кабардинка"."""
            
            response = await llm_service.generate_content_async(
                prompt,
                system_prompt="Ты географический справочник. Отвечай кратко. Не дублируй название города как регион."
            )
            
            if response and response.strip().lower() != 'null':
                region = response.strip()
                # Проверяем, что регион не совпадает с городом
                if region.lower() != city.lower():
                    return region
            
        except Exception as e:
            logger.warning(f"Failed to infer region for city {city}: {e}")
        
        return None
    
    def _get_empty_result(self) -> Dict[str, Any]:
        """Возвращает пустой результат"""
        return {
            "location": {
                "placeRaw": None,
                "city": None,
                "region": None,
                "regionNeedsConfirm": False
            },
            "startDate": None,
            "endDate": None,
            "birthYears": [],
            "matchFormats": [],
            "teamRoster": None,
            "documents": [],
            "structure": [],
            "points": None,
            "awardsTeam": [],
            "awardsIndividual": [],
            "fee": None,
            "accommodation": [],
            "services": [],
            "contacts": None
        }

# Создаем экземпляр сервиса
tournament_extraction_service = TournamentExtractionService()