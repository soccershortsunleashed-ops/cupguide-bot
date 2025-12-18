"""
Сервис для анализа турниров из сообщений
"""
import logging
import os
import re
from typing import Optional, Dict, List
from app.services.llm_service import llm_service
from app.services.ocr_service import ocr_service
from app.core.config import settings
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PyPDF2 = None
    PYPDF2_AVAILABLE = False
import io

logger = logging.getLogger(__name__)

class TournamentAnalysisService:
    """Сервис для анализа информации о турнирах из сообщений"""
    
    def __init__(self):
        self.llm_service = llm_service
    
    async def analyze_message_for_tournament(
        self, 
        message_id: str,
        message_text: Optional[str] = None,
        media_files: Optional[List[Dict]] = None,
        media_path: Optional[str] = None
    ) -> Dict:
        """
        Анализирует сообщение и извлекает информацию о турнире
        
        Args:
            message_id: ID сообщения
            message_text: Текст сообщения
            media_files: Список медиа файлов (новый формат)
            media_path: Путь к медиа файлу (старый формат)
        
        Returns:
            Словарь с извлеченной информацией
        """
        if not self.llm_service.configured:
            logger.warning("LLM service not configured, skipping tournament analysis")
            return {"error": "LLM service not configured"}
        
        logger.info(f"Starting tournament analysis for message {message_id}")
        
        try:
            all_texts = []
            
            # Добавляем текст сообщения, если есть
            if message_text and message_text.strip():
                all_texts.append(f"[Текст сообщения]: {message_text.strip()}")
            
            # Обрабатываем медиа файлы
            if media_files:
                for media_file in media_files:
                    media_type = media_file.get('type')
                    media_path_file = media_file.get('path')
                    
                    if media_type in ['photo', 'image'] and media_path_file:
                        # OCR для изображений
                        full_path = self._get_full_path(media_path_file)
                        if os.path.exists(full_path):
                            logger.info(f"📷 Found image, extracting text via OCR: {full_path}")
                            ocr_text = await ocr_service.extract_text_from_image(full_path)
                            if ocr_text and ocr_text.strip():
                                all_texts.append(f"[Текст с изображения]: {ocr_text.strip()}")
                                logger.info(f"✅ Extracted {len(ocr_text)} chars from image")
                    
                    elif media_type == 'document' and media_path_file and media_path_file.lower().endswith('.pdf'):
                        # Чтение PDF
                        full_path = self._get_full_path(media_path_file)
                        if os.path.exists(full_path):
                            logger.info(f"📄 Found PDF, extracting text: {full_path}")
                            pdf_text = await self._extract_text_from_pdf(full_path)
                            if pdf_text and pdf_text.strip():
                                all_texts.append(f"[Текст из PDF]: {pdf_text.strip()}")
                                logger.info(f"✅ Extracted {len(pdf_text)} chars from PDF")
            
            # Также проверяем старый формат media_path
            if media_path:
                if media_path.lower().endswith('.pdf'):
                    full_path = self._get_full_path(media_path)
                    if os.path.exists(full_path):
                        logger.info(f"📄 Found PDF (old format), extracting text: {full_path}")
                        pdf_text = await self._extract_text_from_pdf(full_path)
                        if pdf_text and pdf_text.strip():
                            all_texts.append(f"[Текст из PDF]: {pdf_text.strip()}")
                            logger.info(f"✅ Extracted {len(pdf_text)} chars from PDF")
                elif any(media_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                    full_path = self._get_full_path(media_path)
                    if os.path.exists(full_path):
                        logger.info(f"📷 Found image (old format), extracting text via OCR: {full_path}")
                        ocr_text = await ocr_service.extract_text_from_image(full_path)
                        if ocr_text and ocr_text.strip():
                            all_texts.append(f"[Текст с изображения]: {ocr_text.strip()}")
                            logger.info(f"✅ Extracted {len(ocr_text)} chars from image")
            
            if not all_texts:
                logger.warning("No text content found for tournament analysis")
                return {"error": "No text content found"}
            
            # Объединяем все тексты
            combined_text = "\n\n".join(all_texts)
            logger.info(f"Combining {len(all_texts)} text sources for analysis (total chars: {len(combined_text)})")
            
            # Создаем промпт для извлечения информации о турнире(ах)
            prompt = f"""ВНИМАТЕЛЬНО проанализируй следующую информацию и определи: это ОДИН турнир или НЕСКОЛЬКО ОТДЕЛЬНЫХ турниров?

Информация из сообщения и медиа:
{combined_text}

🔍 КРИТЕРИИ ДЛЯ РАЗДЕЛЕНИЯ НА ОТДЕЛЬНЫЕ ТУРНИРЫ:
- Разные даты проведения (например: 20-25 февраля И 6-11 марта = 2 турнира)
- Разные возрастные группы с отдельными датами (например: 2012 г.р. 20-25 февраля, 2013 г.р. 6-11 марта = 2 турнира)
- Разные города проведения
- Разные названия турниров

⚠️ ВАЖНО: Если указаны разные даты для разных возрастов - это ОТДЕЛЬНЫЕ турниры!

Верни JSON в одном из двух форматов:

ФОРМАТ 1 - Если это ОДИН турнир:
{{
    "is_multiple": false,
    "tournament": {{
        "title": "название турнира",
        "city": "город проведения",
        "region": "регион проведения (если указан)",
        "sport": "вид спорта",
        "start_date": "дата начала в формате DD.MM.YYYY",
        "end_date": "дата окончания в формате DD.MM.YYYY",
        "format": "формат турнира",
        "teams_min": минимальное количество команд (число),
        "teams_max": максимальное количество команд (число),
        "entry_fee": "взнос за участие",
        "organizer_name": "название организатора",
        "contact": "контактная информация",
        "addons": "дополнительная информация",
        "description_short": "краткое описание турнира",
        "description_full": "полное описание турнира",
        "birth_years": ["годы рождения участников"]
    }}
}}

ФОРМАТ 2 - Если это НЕСКОЛЬКО турниров:
{{
    "is_multiple": true,
    "tournaments": [
        {{
            "title": "название первого турнира (с указанием возраста если нужно)",
            "city": "город проведения",
            "region": "регион проведения",
            "sport": "вид спорта",
            "start_date": "дата начала первого турнира DD.MM.YYYY",
            "end_date": "дата окончания первого турнира DD.MM.YYYY",
            "format": "формат турнира",
            "teams_min": минимальное количество команд,
            "teams_max": максимальное количество команд,
            "entry_fee": "взнос за участие",
            "organizer_name": "название организатора",
            "contact": "контактная информация",
            "addons": "дополнительная информация",
            "description_short": "краткое описание",
            "description_full": "полное описание",
            "birth_years": ["годы рождения для этого турнира"]
        }},
        {{
            "title": "название второго турнира (с указанием возраста если нужно)",
            "city": "город проведения",
            "region": "регион проведения",
            "sport": "вид спорта",
            "start_date": "дата начала второго турнира DD.MM.YYYY",
            "end_date": "дата окончания второго турнира DD.MM.YYYY",
            "format": "формат турнира",
            "teams_min": минимальное количество команд,
            "teams_max": максимальное количество команд,
            "entry_fee": "взнос за участие",
            "organizer_name": "название организатора",
            "contact": "контактная информация",
            "addons": "дополнительная информация",
            "description_short": "краткое описание",
            "description_full": "полное описание",
            "birth_years": ["годы рождения для этого турнира"]
        }}
    ]
}}

ПРАВИЛА:
- Если информация не найдена, используй null
- Для дат используй ТОЛЬКО формат DD.MM.YYYY
- Для birth_years используй массив строк с годами
- Будь максимально внимательным к датам и возрастам
- Если есть сомнения - лучше разделить на отдельные турниры

Верни ТОЛЬКО валидный JSON, без комментариев."""
            
            # Вызываем LLM для анализа
            logger.info(f"Calling LLM API for tournament analysis...")
            try:
                response_text = await self.llm_service.generate_content_async(prompt)
                
                # Проверяем, что ответ не None (может быть при исчерпании квоты)
                if response_text is None:
                    logger.warning("⚠️ LLM API returned None for tournament analysis (quota exhausted or unavailable). Skipping analysis.")
                    return {"error": "LLM quota exhausted or unavailable"}
                
                response_text = response_text.strip()
                logger.info(f"✅ LLM API returned response (length: {len(response_text)} chars)")
            except Exception as e:
                logger.error(f"❌ LLM API error: {e}", exc_info=True)
                return {"error": f"LLM API error: {str(e)}"}
            
            # Очищаем ответ от markdown форматирования, если есть
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Парсим JSON
            try:
                import json
                data = json.loads(response_text)
                
                # Проверяем, один турнир или несколько
                is_multiple = data.get('is_multiple', False)
                
                if is_multiple:
                    # Обрабатываем множественные турниры
                    tournaments = data.get('tournaments', [])
                    logger.info(f"🎯 Detected {len(tournaments)} separate tournaments")
                    
                    # Форматируем информацию для всех турниров
                    draft_parts = []
                    draft_parts.append(f"# 🏆 Обнаружено {len(tournaments)} отдельных турниров")
                    draft_parts.append("")
                    
                    all_tournaments_data = []
                    
                    for i, tournament in enumerate(tournaments, 1):
                        # Форматируем каждый турнир
                        tournament_draft = self._format_single_tournament(tournament, i)
                        draft_parts.append(tournament_draft)
                        draft_parts.append("---")  # Разделитель между турнирами
                        draft_parts.append("")
                        
                        # Сохраняем данные турнира
                        all_tournaments_data.append(tournament)
                    
                    draft_info = "\n".join(draft_parts)
                    
                    return {
                        "success": True,
                        "is_multiple": True,
                        "tournaments_count": len(tournaments),
                        "draft_info": draft_info,
                        "extracted_data": tournaments,  # Массив турниров
                        "tournaments": all_tournaments_data  # Для совместимости
                    }
                
                else:
                    # Обрабатываем один турнир (старая логика)
                    tournament_data = data.get('tournament', data)  # Поддержка обоих форматов
                    logger.info("🎯 Detected single tournament")
                    
                    # Форматируем информацию для одного турнира
                    draft_info = self._format_single_tournament(tournament_data)
                    
                    return {
                        "success": True,
                        "is_multiple": False,
                        "tournaments_count": 1,
                        "draft_info": draft_info,
                        "extracted_data": tournament_data
                    }
                

                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response from LLM: {e}")
                logger.debug(f"Response text: {response_text}")
                return {"error": f"Failed to parse JSON: {str(e)}", "raw_response": response_text}
                
        except Exception as e:
            logger.error(f"Error analyzing tournament: {e}", exc_info=True)
            return {"error": str(e)}
    
    def _get_full_path(self, media_path: str) -> str:
        """Преобразует относительный путь в абсолютный"""
        if media_path.startswith('/static/'):
            filename = os.path.basename(media_path)
            full_path = os.path.join(settings.BASE_DIR, 'app', 'static', 'media', filename)
        elif media_path.startswith('/'):
            full_path = os.path.join(settings.BASE_DIR, media_path.lstrip('/'))
        else:
            full_path = os.path.join(settings.BASE_DIR, media_path)
        return full_path
    
    def _format_single_tournament(self, data: dict, tournament_number: int = None) -> str:
        """Форматирует данные одного турнира в Markdown"""
        draft_parts = []
        
        # Заголовок турнира
        if tournament_number:
            if data.get('title'):
                draft_parts.append(f"## {tournament_number}. {data['title']}")
            else:
                draft_parts.append(f"## {tournament_number}. Турнир")
        else:
            if data.get('title'):
                draft_parts.append(f"# {data['title']}")
        
        draft_parts.append("")  # Пустая строка для разделения
        
        # Основная информация в виде списка
        info_items = []
        if data.get('city'):
            info_items.append(f"**📍 Город:** {data['city']}")
        if data.get('region'):
            info_items.append(f"**🗺️ Регион:** {data['region']}")
        if data.get('sport'):
            info_items.append(f"**⚽ Вид спорта:** {data['sport']}")
        if data.get('start_date'):
            info_items.append(f"**📅 Дата начала:** {data['start_date']}")
        if data.get('end_date'):
            info_items.append(f"**📅 Дата окончания:** {data['end_date']}")
        if data.get('format'):
            info_items.append(f"**🏆 Формат:** {data['format']}")
        if data.get('teams_min') or data.get('teams_max'):
            teams_info = []
            if data.get('teams_min'):
                teams_info.append(f"от {data['teams_min']}")
            if data.get('teams_max'):
                teams_info.append(f"до {data['teams_max']}")
            info_items.append(f"**👥 Количество команд:** {' '.join(teams_info)}")
        if data.get('entry_fee'):
            info_items.append(f"**💰 Взнос:** {data['entry_fee']}")
        if data.get('organizer_name'):
            info_items.append(f"**🏢 Организатор:** {data['organizer_name']}")
        if data.get('contact'):
            info_items.append(f"**📞 Контакты:** {data['contact']}")
        if data.get('birth_years'):
            years = data['birth_years']
            if isinstance(years, list):
                years_str = ', '.join(years)
            else:
                years_str = str(years)
            info_items.append(f"**🎂 Годы рождения:** {years_str}")
        
        if info_items:
            draft_parts.extend(info_items)
            draft_parts.append("")  # Пустая строка для разделения
        
        # Дополнительная информация
        if data.get('addons'):
            if tournament_number:
                draft_parts.append("### ✨ Дополнительные услуги")
            else:
                draft_parts.append("## ✨ Дополнительные услуги")
            draft_parts.append(f"{data['addons']}")
            draft_parts.append("")
        
        # Описания
        if data.get('description_short'):
            if tournament_number:
                draft_parts.append("### 📝 Краткое описание")
            else:
                draft_parts.append("## 📝 Краткое описание")
            draft_parts.append(f"{data['description_short']}")
            draft_parts.append("")
        
        if data.get('description_full'):
            if tournament_number:
                draft_parts.append("### 📖 Подробное описание")
            else:
                draft_parts.append("## 📖 Подробное описание")
            draft_parts.append(f"{data['description_full']}")
        
        return "\n".join(draft_parts)

    async def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Извлекает текст из PDF файла"""
        if not PYPDF2_AVAILABLE:
            logger.warning("PyPDF2 not available, cannot extract text from PDF")
            return ""
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text_parts = []
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_path}: {e}", exc_info=True)
            return ""

tournament_analysis_service = TournamentAnalysisService()

