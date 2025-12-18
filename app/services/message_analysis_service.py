"""
Сервис для анализа сообщений WhatsApp с помощью ИИ
и извлечения структурированной информации об авторах
"""
import logging
from typing import Optional, List
from app.services.llm_service import llm_service
from app.models.message_insight import MessageInsight
import json

logger = logging.getLogger(__name__)

class MessageAnalysisService:
    """Сервис для анализа сообщений и извлечения информации об авторах"""
    
    def __init__(self):
        self.llm_service = llm_service
    
    async def analyze_author_messages(
        self, 
        sender_name: str,
        group_name: str,
        messages: List[dict]
    ) -> Optional[MessageInsight]:
        """
        Анализирует сообщения автора и извлекает структурированную информацию
        
        Args:
            sender_name: Имя автора сообщений
            group_name: Название группы WhatsApp
            messages: Список сообщений автора (каждое с полями 'text', 'date', 'media_type')
        
        Returns:
            MessageInsight с извлеченной информацией или None при ошибке
        """
        if not self.llm_service.configured:
            logger.warning(f"LLM service not configured, skipping message analysis for {sender_name}. Check OPENAI_API_KEY in .env file")
            return None
        
        logger.info(f"Starting LLM analysis for {sender_name}: {len(messages)} messages, group: {group_name}")
        
        try:
            # Объединяем все тексты сообщений для анализа, включая текст из изображений
            all_texts = []
            from app.services.ocr_service import ocr_service
            from app.core.config import settings
            import os
            
            # Сначала обрабатываем все сообщения, включая OCR для изображений
            for msg in messages:
                text = msg.get('text', '')
                if text and text.strip():
                    all_texts.append(text.strip())
                
                # Если есть изображение, извлекаем текст через OCR
                # ВАЖНО: Проверяем изображения даже если нет текста в сообщении
                media_type = msg.get('media_type')
                media_path = msg.get('media_path')
                
                # Также проверяем media_files (новый формат) - ПРИОРИТЕТ над старым форматом
                media_files_list = msg.get('media_files', [])
                if media_files_list:
                    for media_file in media_files_list:
                        if media_file.get('type') in ['photo', 'image']:
                            media_file_path = media_file.get('path')
                            if media_file_path:
                                # Преобразуем относительный путь в абсолютный
                                if media_file_path.startswith('/static/'):
                                    filename = os.path.basename(media_file_path)
                                    full_path = os.path.join(settings.BASE_DIR, 'app', 'static', 'media', filename)
                                elif media_file_path.startswith('/'):
                                    full_path = os.path.join(settings.BASE_DIR, media_file_path.lstrip('/'))
                                else:
                                    full_path = os.path.join(settings.BASE_DIR, media_file_path)
                                
                                if os.path.exists(full_path):
                                    logger.info(f"📷 Found image in message (media_files), extracting text via OCR: {full_path}")
                                    ocr_text = await ocr_service.extract_text_from_image(full_path)
                                    if ocr_text and ocr_text.strip():
                                        all_texts.append(f"[Текст с изображения]: {ocr_text.strip()}")
                                        logger.info(f"✅ Extracted {len(ocr_text)} chars from image")
                                    else:
                                        logger.debug(f"No text extracted from image (may be already processed or no text found): {full_path}")
                                else:
                                    logger.warning(f"⚠️ Image file not found: {full_path}")
                
                # Также проверяем старый формат media_path (если media_files не было обработано)
                if not media_files_list and media_type in ['photo', 'image'] and media_path:
                    # Преобразуем относительный путь в абсолютный
                    if media_path.startswith('/static/'):
                        # Путь вида /static/media/filename.jpg
                        filename = os.path.basename(media_path)
                        full_path = os.path.join(settings.BASE_DIR, 'app', 'static', 'media', filename)
                    elif media_path.startswith('/'):
                        # Абсолютный путь от корня проекта
                        full_path = os.path.join(settings.BASE_DIR, media_path.lstrip('/'))
                    else:
                        # Относительный путь
                        full_path = os.path.join(settings.BASE_DIR, media_path)
                    
                    if os.path.exists(full_path):
                        logger.info(f"📷 Found image in message, extracting text via OCR: {full_path}")
                        # OCR сервис сам проверяет кэш и пропускает уже обработанные изображения
                        ocr_text = await ocr_service.extract_text_from_image(full_path)
                        if ocr_text and ocr_text.strip():
                            all_texts.append(f"[Текст с изображения]: {ocr_text.strip()}")
                            logger.info(f"✅ Extracted {len(ocr_text)} chars from image")
                        else:
                            logger.debug(f"No text extracted from image (may be already processed or no text found): {full_path}")
                    else:
                        logger.debug(f"Image file not found: {full_path}")
            
            # Проверяем наличие текста ПОСЛЕ обработки всех сообщений и OCR
            if not all_texts:
                logger.warning(f"No text content to analyze for sender {sender_name} - all messages are empty or have no text (including OCR)")
                return None
            
            logger.info(f"Combining {len(all_texts)} text messages (including OCR) for analysis (total chars: {sum(len(t) for t in all_texts)})")
            
            combined_text = "\n\n".join(all_texts[:20])  # Берем первые 20 сообщений
            
            # Создаем промпт для извлечения информации
            prompt = f"""Проанализируй сообщения автора "{sender_name}" из группы WhatsApp "{group_name}" и извлеки МАКСИМАЛЬНО ДЕТАЛЬНУЮ информацию о человеке.

Сообщения автора:
{combined_text}

Извлеки следующую информацию в структурированном JSON формате:
{{
    "group_name": "полное название группы, в которой публикует автор",
    "role": "роль автора (например: 'Администратор группы Детско-юношеские турниры по футболу', 'Организатор турниров', 'Тренер', 'Директор спортивной школы' и т.д.)",
    "tournament_name": "название турнира или УТС, если упоминается (например: 'Кубок Территории Спорта', 'УТС в Сочи')",
    "tournament_type": "тип события (турнир, УТС, сборы, матч, лагерь и т.д.)",
    "city": "город проведения событий (например: 'Сочи', 'Москва', 'Краснодар')",
    "dates": "даты проведения (если упоминаются, например: '12-16 декабря 2024', 'с 1 по 7 января')",
    "age_categories": ["список возрастных категорий, например: ['U10', 'U12', 'U14', '2013/2014/2015/2016/2017 год рождения']"],
    "birth_years": ["список годов рождения спортсменов, для которых организуются турниры/УТС (например: ['2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018'])"],
    "tournaments_organized": ["список названий турниров, которые организует автор (например: ['Зимний Кубок Краснодара', 'Кубок Территории Спорта'])"],
    "organization": "название организации, клуба, школы, федерации (например: 'ФК Сочи', 'ДЮСШ', 'РФС')",
    "contact_info": "контактная информация (телефон, WhatsApp) - извлекай ВСЕ упоминания в виде ОДНОЙ строки, разделяя через запятую (например: '8-952-608-22-40')",
    "email": "email адрес (если обнаружен в сообщениях, например: 'fc.finist@mail.ru') - извлекай ОТДЕЛЬНО от contact_info",
    "website": "веб-сайт или ссылка (если упоминается)",
    "social_media": ["список социальных сетей и ссылок (ВК, Instagram, Telegram, YouTube и т.д.)"],
    "description": "подробное описание деятельности автора, его специализации, что он рекламирует, какие услуги предлагает",
    "specializations": ["список специализаций, например: ['детский футбол', 'юношеские турниры', 'УТС', 'организация соревнований']"],
    "confidence": 0.0-1.0
}}

КРИТИЧЕСКИ ВАЖНО:
- Извлекай ВСЮ доступную информацию, даже если она кажется незначительной
- Если автор администратор группы, ОБЯЗАТЕЛЬНО укажи полное название группы в поле "group_name"
- Если автор рекламирует турнир/УТС, ОБЯЗАТЕЛЬНО укажи: название, город, даты, возрастные категории
- ОСОБОЕ ВНИМАНИЕ: Извлекай информацию о ГОДАХ РОЖДЕНИЯ спортсменов (например: 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018) - это критически важно!
- ОСОБОЕ ВНИМАНИЕ: Если автор организует турниры, извлекай ВСЕ названия турниров, которые он организует
- ОСОБОЕ ВНИМАНИЕ: Для каждого турнира указывай, для каких годов рождения он предназначен (например: "Зимний Кубок Краснодара для 2011-2012, 2014, 2015, 2018 годов рождения")
- Извлекай ВСЕ упоминания: городов, дат, организаций, контактов, сайтов, соцсетей, годов рождения, названий турниров
- Если информация не найдена, используй null (не пустую строку)
- Будь максимально точным и конкретным - каждая деталь важна
- confidence должен отражать уверенность в извлеченной информации (0.0-1.0)
- Если в сообщениях есть изображения с текстом (постеры, объявления), учитывай информацию из них, особенно годы рождения и названия турниров

Верни ТОЛЬКО валидный JSON, без дополнительных комментариев и markdown разметки."""
            
            # Вызываем LLM для анализа
            logger.info(f"Calling LLM API for {sender_name}...")
            try:
                response_text = await self.llm_service.generate_content_async(prompt)
                
                # Проверяем, что ответ не None (может быть при исчерпании квоты)
                if response_text is None:
                    logger.warning(f"⚠️ LLM API returned None for {sender_name} (quota exhausted or unavailable). Skipping analysis.")
                    return None
                
                response_text = response_text.strip()
                logger.info(f"✅ LLM API returned response for {sender_name} (length: {len(response_text)} chars)")
            except ValueError as e:
                error_str = str(e)
                # Проверяем, является ли это ошибкой недостатка квоты
                if 'превышена квота' in error_str.lower() or 'insufficient_quota' in error_str.lower() or 'exceeded your current quota' in error_str.lower():
                    logger.warning(
                        f"⚠️ LLM API: Превышена квота для {sender_name}. "
                        "Анализ пропущен. Проверьте баланс API."
                    )
                    # Не логируем полный traceback для ошибок квоты - это не критично
                else:
                    logger.error(f"❌ LLM API error for {sender_name}: {e}", exc_info=True)
                return None
            except Exception as e:
                error_str = str(e)
                if 'превышена квота' in error_str.lower() or 'insufficient_quota' in error_str.lower() or 'exceeded your current quota' in error_str.lower():
                    logger.error(
                        f"❌ LLM API: Превышена квота для {sender_name}. "
                        "Анализ пропущен. Проверьте баланс OpenAI API на https://platform.openai.com/account/billing"
                    )
                else:
                    logger.error(f"❌ LLM API error for {sender_name}: {e}", exc_info=True)
                return None
            
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
                data = json.loads(response_text)
                
                # Нормализуем данные: преобразуем списки в строки для полей, которые должны быть строками
                def normalize_to_string(value):
                    """Преобразует значение в строку, если это список - объединяет элементы"""
                    if value is None:
                        return None
                    if isinstance(value, list):
                        # Объединяем элементы списка через запятую
                        return ', '.join(str(item) for item in value if item)
                    return str(value) if value else None
                
                # Нормализуем поля, которые должны быть строками
                # Применяем нормализацию ко всем строковым полям, чтобы избежать ошибок валидации
                # когда LLM возвращает списки вместо строк
                contact_info = normalize_to_string(data.get('contact_info'))
                email = normalize_to_string(data.get('email'))
                website = normalize_to_string(data.get('website'))
                group_name_normalized = normalize_to_string(data.get('group_name')) or group_name
                role_normalized = normalize_to_string(data.get('role'))
                tournament_name_normalized = normalize_to_string(data.get('tournament_name'))
                tournament_type_normalized = normalize_to_string(data.get('tournament_type'))
                city_normalized = normalize_to_string(data.get('city'))
                dates_normalized = normalize_to_string(data.get('dates'))
                organization_normalized = normalize_to_string(data.get('organization'))
                description_normalized = normalize_to_string(data.get('description'))
                
                # Нормализуем списки для новых полей
                birth_years = data.get('birth_years')
                if birth_years and isinstance(birth_years, str):
                    # Если это строка, пытаемся преобразовать в список
                    birth_years = [y.strip() for y in birth_years.split(',') if y.strip()]
                elif not birth_years:
                    birth_years = None
                
                tournaments_organized = data.get('tournaments_organized')
                if tournaments_organized and isinstance(tournaments_organized, str):
                    # Если это строка, пытаемся преобразовать в список
                    tournaments_organized = [t.strip() for t in tournaments_organized.split(',') if t.strip()]
                elif not tournaments_organized:
                    tournaments_organized = None
                
                # Извлекаем email из contact_info, если он там есть, но не был извлечен отдельно
                # Используем регулярное выражение для поиска email
                import re
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                
                # Если email не был извлечен отдельно, пытаемся найти его в contact_info
                if not email and contact_info:
                    emails_found = re.findall(email_pattern, contact_info)
                    if emails_found:
                        email = emails_found[0]  # Берем первый найденный email
                        # Удаляем email из contact_info, чтобы не дублировать
                        contact_info = re.sub(email_pattern, '', contact_info).strip().rstrip(',').strip()
                
                # Создаем объект MessageInsight
                insight = MessageInsight(
                    group_name=group_name_normalized,
                    role=role_normalized,
                    tournament_name=tournament_name_normalized,
                    tournament_type=tournament_type_normalized,
                    city=city_normalized,
                    dates=dates_normalized,
                    age_categories=data.get('age_categories'),  # Это список, оставляем как есть
                    birth_years=birth_years,  # Годы рождения спортсменов
                    tournaments_organized=tournaments_organized,  # Список турниров, которые организует автор
                    organization=organization_normalized,
                    contact_info=contact_info,
                    email=email,  # Email адрес
                    website=website,
                    social_media=data.get('social_media'),  # Это список, оставляем как есть
                    description=description_normalized,
                    specializations=data.get('specializations'),  # Это список, оставляем как есть
                    confidence=data.get('confidence', 0.5)
                )
                
                logger.info(f"Successfully extracted insight for {sender_name}: role={insight.role}, tournament={insight.tournament_name}")
                return insight
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response from LLM: {e}")
                logger.debug(f"Response text: {response_text}")
                return None
                
        except Exception as e:
            logger.error(f"Error analyzing messages for {sender_name}: {e}", exc_info=True)
            return None
    
    def format_insight_for_contact(self, insight: MessageInsight) -> str:
        """
        Форматирует извлеченную информацию для сохранения в карточке контакта
        
        Returns:
            Структурированная строка с информацией
        """
        parts = []
        
        if insight.role:
            parts.append(f"Роль: {insight.role}")
        
        if insight.group_name:
            parts.append(f"Группа: {insight.group_name}")
        
        if insight.tournament_name:
            tournament_info = f"Рекламирует: {insight.tournament_name}"
            if insight.tournament_type:
                tournament_info += f" ({insight.tournament_type})"
            if insight.city:
                tournament_info += f" в г. {insight.city}"
            if insight.dates:
                tournament_info += f", даты: {insight.dates}"
            parts.append(tournament_info)
        
        if insight.organization:
            parts.append(f"Организация: {insight.organization}")
        
        if insight.age_categories:
            parts.append(f"Возрастные категории: {', '.join(insight.age_categories)}")
        
        if insight.birth_years:
            parts.append(f"Годы рождения спортсменов: {', '.join(insight.birth_years)}")
        
        if insight.tournaments_organized:
            parts.append(f"Организует турниры: {', '.join(insight.tournaments_organized)}")
        
        if insight.specializations:
            parts.append(f"Специализация: {', '.join(insight.specializations)}")
        
        if insight.contact_info:
            parts.append(f"Контакты: {insight.contact_info}")
        
        if insight.website:
            parts.append(f"Сайт: {insight.website}")
        
        if insight.social_media:
            parts.append(f"Соцсети: {', '.join(insight.social_media)}")
        
        if insight.description:
            parts.append(f"Описание: {insight.description}")
        
        return "\n".join(parts)

message_analysis_service = MessageAnalysisService()

