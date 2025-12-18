"""
API endpoints для работы с турнирами
"""
from fastapi import APIRouter, HTTPException, Body, UploadFile, File, Form
from typing import Optional, List, Union
from pydantic import BaseModel, Field
from app.services.tournament_analysis_service import tournament_analysis_service
from app.services.tournament_service import tournament_service
from app.services.message_service import message_service
from app.services.whatsapp_message_service import whatsapp_message_service
from app.models.tournament import Tournament
from app.services.llm_service import llm_service
from app.services.image_generation_service import image_generation_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tournaments"])

async def infer_region_from_city(city: Optional[str]) -> Optional[str]:
    """
    Определяет регион по названию города с помощью LLM.
    """
    if not city:
        return None

    if not getattr(llm_service, "configured", False):
        logger.debug("LLM service is not configured; skipping region inference")
        return None

    prompt = (
        "Тебе дан город. Укажи, в каком регионе или субъекте РФ он находится. "
        "Если город не в России, просто укажи страну или область/регион, который чаще всего используют. "
        "Ответ должен содержать только краткое название региона без дополнительных пояснений.\n\n"
        f"Город: {city}"
    )

    try:
        response = await llm_service.generate_content_async(
            prompt,
            system_prompt="Ты географический справочник. Отвечай кратко, только названием региона/страны."
        )
    except Exception as exc:
        logger.warning(f"⚠️ Failed to infer region for city '{city}': {exc}")
        return None

    if not response:
        return None

    region = response.strip().split("\n")[0].strip().strip('.').strip('"').strip("'")
    for prefix in ("регион", "area", "область", "регион РФ", "регион РФ:"):
        if region.lower().startswith(prefix):
            region = region[len(prefix):].lstrip(":").strip()

    return region or None

class AnalyzeTournamentRequest(BaseModel):
    message_id: str
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None

class TournamentUpdateRequest(BaseModel):
    title: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    sport: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    format: Optional[str] = None
    teams_min: Optional[int] = None
    teams_max: Optional[int] = None
    entry_fee: Optional[str] = None
    organizer_name: Optional[str] = None
    contact: Optional[str] = None
    addons: Optional[str] = None
    description_short: Optional[str] = None
    description_full: Optional[str] = None
    selling_text: Optional[str] = None
    status: Optional[str] = None
    birth_years: Optional[Union[List[str], str]] = None
    
    # Новые поля для задачи 38
    body: Optional[str] = None
    short_description: Optional[str] = None
    image_original_url: Optional[str] = None
    image_cover_16x9_url: Optional[str] = None
    image_cover_square_url: Optional[str] = None
    source: Optional[str] = None
    publish_to_teletype: Optional[bool] = None
    publish_to_telegram: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    
    # Рейтинг турнира ⭐
    priority_rating: Optional[bool] = None
    priority_rating_start_date: Optional[str] = None
    
    # Премиум-размещение 🔝
    is_premium: Optional[bool] = None
    premium_until: Optional[str] = None
    premium_last_ended: Optional[str] = None
    
    # Действия с премиумом (для API)
    premium_action: Optional[str] = None  # "activate", "extend_7days", "extend_1day"
@router.post("/analyze")
async def analyze_tournament(request: AnalyzeTournamentRequest):
    """
    Анализирует сообщение и извлекает информацию о турнире
    """
    try:
        logger.error(f"🚨 TOURNAMENT ANALYZE ENDPOINT CALLED! Request: {request}")
        print(f"🚨 TOURNAMENT ANALYZE ENDPOINT CALLED! Request: {request}")
        logger.info(f"✅ Tournament analyze endpoint called with request: {request}")
        
        # Убеждаемся, что LLM сервис настроен
        if not llm_service.configured:
            logger.info("🔄 LLM service not configured, refreshing client...")
            await llm_service.refresh_client()
            if not llm_service.configured:
                logger.error("❌ Failed to configure LLM service")
                raise HTTPException(status_code=500, detail="LLM service configuration failed")
            logger.info("✅ LLM service configured successfully")
        
        message_id = request.message_id
        channel_id = request.channel_id
        channel_title = request.channel_title or ''
        
        if not message_id:
            logger.warning(f"❌ message_id is missing in request: {request}")
            raise HTTPException(status_code=400, detail="message_id is required")
        
        logger.info(f"Analyzing tournament from message {message_id} in channel {channel_id}")
        
        def matches_identifier(candidate, target_id: str) -> bool:
            """Return True if candidate matches target_id via id or message_id."""
            if not candidate or not target_id:
                return False
            target_str = str(target_id)
            candidate_ids = []
            if hasattr(candidate, 'id'):
                candidate_ids.append(getattr(candidate, 'id'))
            if hasattr(candidate, 'message_id'):
                candidate_ids.append(getattr(candidate, 'message_id'))
            for cid in candidate_ids:
                if cid is not None and str(cid) == target_str:
                    return True
            return False
        
        # Ищем сообщение в базе данных
        message = None
        matched_source = None
        matched_by = None
        
        # Пробуем найти в Telegram сообщениях
        try:
            telegram_messages = await message_service.get_messages()
            logger.info(f"   Searched {len(telegram_messages)} Telegram messages for ID {message_id}")
            message = next((m for m in telegram_messages if matches_identifier(m, message_id)), None)
            if message:
                matched_source = "Telegram"
                matched_by = "id"
                logger.info(f"   ✅ Found message in Telegram messages")
        except Exception as e:
            logger.warning(f"   ⚠️ Error searching Telegram messages: {e}")
        
        # Если не нашли, пробуем в WhatsApp сообщениях
        if not message:
            try:
                whatsapp_messages = await whatsapp_message_service.get_messages()
                logger.info(f"   Searched {len(whatsapp_messages)} WhatsApp messages for ID {message_id}")
                message = next((m for m in whatsapp_messages if matches_identifier(m, message_id)), None)
                if message:
                    matched_source = "WhatsApp"
                    # Определяем по какому полю совпало
                    matched_by = "message_id" if hasattr(message, 'message_id') and str(message.message_id) == str(message_id) else "id"
                    logger.info(f"   ✅ Found message in WhatsApp messages (matched by {matched_by})")
            except Exception as e:
                logger.warning(f"   ⚠️ Error searching WhatsApp messages: {e}")
        
        if not message:
            logger.error(f"   ❌ Message {message_id} not found in either Telegram or WhatsApp messages")
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
        
        # Извлекаем данные из сообщения
        message_text = getattr(message, 'text', None) or getattr(message, 'message', None)
        media_files = getattr(message, 'media_files', None)
        media_path = getattr(message, 'media_path', None)
        
        logger.info(f"📊 Extracted message data:")
        logger.info(f"   message_text: {message_text}")
        logger.info(f"   media_files: {media_files}")
        logger.info(f"   media_path: {media_path}")
        
        # Анализируем сообщение
        logger.info(f"🏆 Starting tournament analysis...")
        result = await tournament_analysis_service.analyze_message_for_tournament(
            message_id=str(message_id),
            message_text=message_text,
            media_files=media_files,
            media_path=media_path
        )
        logger.info(f"🏆 Tournament analysis completed: {result.get('success', False)}")
        
        if 'error' in result:
            raise HTTPException(status_code=500, detail=result['error'])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing tournament: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process-draft")
async def process_tournament_draft(request: dict):
    """
    Обрабатывает черновик турнира, создает продающий текст, генерирует постер и создает страницу турнира
    """
    try:
        draft_info = request.get('draft_info')
        extracted_data = request.get('extracted_data')
        message_id = request.get('message_id')
        channel_id = request.get('channel_id')
        
        if not draft_info or not extracted_data:
            raise HTTPException(status_code=400, detail="draft_info and extracted_data are required")
        
        logger.info(f"Processing tournament draft from message {message_id}")
        
        # Создаем продающий текст с помощью LLM
        selling_text_prompt = f"""На основе следующей информации о турнире создай красивый продающий текст для публикации на сайте.

Информация о турнире:
{draft_info}

Требования к тексту:
- Текст должен быть привлекательным и мотивирующим
- Используй эмоциональные формулировки
- Подчеркни уникальность и ценность турнира
- Включи ключевую информацию (даты, город, возраст участников)
- Текст должен быть структурированным с использованием заголовков и списков
- Используй Markdown разметку для форматирования

Верни ТОЛЬКО текст, без дополнительных комментариев."""
        
        selling_text = await llm_service.generate_content_async(selling_text_prompt)
        selling_text = selling_text.strip()
        
        # Нормализуем данные для создания турнира
        def normalize_to_string(value):
            if value is None:
                return None
            if isinstance(value, list):
                return ', '.join(str(item) for item in value if item)
            return str(value) if value else None
        
        # Создаем объект турнира
        birth_years_list = []
        if extracted_data:
            birth_years_list = extracted_data.get('birth_years', []) or []
            if isinstance(birth_years_list, str):
                birth_years_list = [y.strip() for y in birth_years_list.split(',') if y.strip()]

        city_value = normalize_to_string(extracted_data.get('city'))
        region_value = normalize_to_string(extracted_data.get('region'))

        if not region_value:
            inferred_region = await infer_region_from_city(city_value)
            if inferred_region:
                region_value = inferred_region

        tournament = Tournament(
            title=normalize_to_string(extracted_data.get('title')) or 'Турнир',
            city=city_value,
            region=region_value,
            sport=normalize_to_string(extracted_data.get('sport')) or 'футбол',
            start_date=normalize_to_string(extracted_data.get('start_date')),
            end_date=normalize_to_string(extracted_data.get('end_date')),
            format=normalize_to_string(extracted_data.get('format')),
            teams_min=extracted_data.get('teams_min'),
            teams_max=extracted_data.get('teams_max'),
            entry_fee=normalize_to_string(extracted_data.get('entry_fee')),
            organizer_name=normalize_to_string(extracted_data.get('organizer_name')),
            contact=normalize_to_string(extracted_data.get('contact')),
            addons=normalize_to_string(extracted_data.get('addons')),
            description_short=normalize_to_string(extracted_data.get('description_short')),
            description_full=normalize_to_string(extracted_data.get('description_full')),
            selling_text=selling_text,
            status="active",
            draft_info=draft_info,
            message_id=str(message_id) if message_id else None,
            channel_id=str(channel_id) if channel_id else None,
            birth_years=birth_years_list if birth_years_list else None
        )
        
        # Генерируем постер
        logger.info("Generating tournament poster...")
        poster_result = await image_generation_service.generate_tournament_poster(
            tournament_title=tournament.title,
            city=tournament.city or 'Сочи',
            birth_years=birth_years_list if birth_years_list else None,
            start_date=tournament.start_date,
            end_date=tournament.end_date,
            custom_prompt=None  # Используем стандартный промпт с переменными из данных турнира
        )
        
        if poster_result and 'image_url' in poster_result:
            tournament.poster_url = poster_result['image_url']
            tournament.poster_path = poster_result.get('image_path')
            logger.info(f"✅ Poster generated: {tournament.poster_url}")
        else:
            logger.warning("⚠️ Failed to generate poster")
        
        # Сохраняем турнир
        saved_tournament = await tournament_service.save_tournament(tournament)
        
        logger.info(f"✅ Tournament created with ID: {saved_tournament.id}")
        
        return {
            "success": True,
            "tournament_id": saved_tournament.id,
            "tournament": saved_tournament.model_dump()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing tournament draft: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/")
async def list_tournaments():
    """Получить список всех турниров"""
    try:
        tournaments = await tournament_service.get_tournaments()
        return tournaments
    except Exception as e:
        logger.error(f"Error listing tournaments: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load tournaments: {str(e)}")

# ========== Новые эндпоинты для задачи 38 ==========

class CreateTournamentRequest(BaseModel):
    """Запрос на создание турнира"""
    title: str = Field(..., min_length=10, max_length=120, description="Заголовок турнира (10-120 символов)")
    short_description: Optional[str] = Field(None, min_length=50, max_length=400, description="Краткое описание (50-400 символов)")
    body: Optional[str] = Field(None, max_length=15000, description="Основной текст турнира (Markdown/HTML)")
    status: Optional[str] = Field("draft", description="Статус: draft, ready_for_publish, published, archived")
    source: Optional[str] = Field("manual", description="Источник: manual, whatsapp, telegram, other")
    publish_to_teletype: Optional[bool] = Field(False, description="Публиковать в Teletype")
    publish_to_telegram: Optional[bool] = Field(False, description="Публиковать в Telegram")
    telegram_chat_id: Optional[str] = Field(None, description="ID канала/группы Telegram")
    
    # Опциональные поля для обратной совместимости и автоизвлечения
    city: Optional[str] = None
    region: Optional[str] = None
    sport: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    format: Optional[str] = None
    contact: Optional[str] = None
    birth_years: Optional[str] = None
    entry_fee: Optional[str] = None
    organizer_name: Optional[str] = None
    
    # Поля изображений
    image_original_url: Optional[str] = None
    image_cover_16x9_url: Optional[str] = None
    image_cover_square_url: Optional[str] = None
    
    # Поля организатора (для личного кабинета)
    organizer_contact_id: Optional[int] = Field(None, description="ID контакта организатора")
    organizer_phone: Optional[str] = Field(None, description="Телефон организатора (для матчинга)")

@router.post("/")
async def create_tournament(request: CreateTournamentRequest):
    """
    Создает новый турнир вручную
    """
    try:
        from datetime import datetime
        
        # Логируем полученные данные
        logger.info(f"🏆 Creating tournament with data:")
        logger.info(f"   Title: {request.title}")
        logger.info(f"   Body length: {len(request.body or '')}")
        logger.info(f"   Image original: {request.image_original_url}")
        logger.info(f"   Image 16:9: {request.image_cover_16x9_url}")
        logger.info(f"   Image square: {request.image_cover_square_url}")
        logger.info(f"   City: {request.city}")
        logger.info(f"   Contact: {request.contact}")
        
        # Обрабатываем birth_years
        birth_years_list = None
        if request.birth_years:
            if isinstance(request.birth_years, str):
                birth_years_list = [y.strip() for y in request.birth_years.split(',') if y.strip()]
            else:
                birth_years_list = request.birth_years

        # Определяем organizer_contact_id
        organizer_contact_id = request.organizer_contact_id
        
        # Если organizer_contact_id не указан, но есть organizer_phone - пробуем найти контакт
        if not organizer_contact_id and request.organizer_phone:
            matched_contact_id = await tournament_service.match_organizer_phone_to_contact(request.organizer_phone)
            if matched_contact_id:
                organizer_contact_id = matched_contact_id
                logger.info(f"📞 Matched organizer phone {request.organizer_phone} to contact_id {organizer_contact_id}")
        
        # Создаем объект турнира
        tournament = Tournament(
            title=request.title,
            short_description=request.short_description,
            body=request.body,
            status=request.status or "draft",
            source=request.source or "manual",
            publish_to_teletype=request.publish_to_teletype or False,
            publish_to_telegram=request.publish_to_telegram or False,
            telegram_chat_id=request.telegram_chat_id,
            city=request.city,
            region=request.region,
            sport=request.sport or "футбол",
            start_date=request.start_date,
            end_date=request.end_date,
            format=request.format,
            contact=request.contact,
            birth_years=birth_years_list,
            entry_fee=request.entry_fee,
            organizer_name=request.organizer_name,
            # Добавляем поля изображений
            image_original_url=request.image_original_url,
            image_cover_16x9_url=request.image_cover_16x9_url,
            image_cover_square_url=request.image_cover_square_url,
            # Поля организатора
            organizer_contact_id=organizer_contact_id,
            organizer_phone=request.organizer_phone,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Сохраняем турнир
        saved_tournament = await tournament_service.save_tournament(tournament)
        
        logger.info(f"✅ Tournament created with ID: {saved_tournament.id}")
        
        return {
            "success": True,
            "tournament_id": saved_tournament.id,
            "tournament": saved_tournament.model_dump()
        }
        
    except Exception as e:
        logger.error(f"Error creating tournament: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create-with-extracted-data")
async def create_tournament_with_extracted_data(request: dict):
    """
    Создает турнир с извлеченными данными
    """
    try:
        from datetime import datetime
        
        tournament_data = request.get('tournament', {})
        extracted_data = request.get('extracted_data', {})
        
        # Создаем объект турнира
        tournament = Tournament(
            title=tournament_data.get('title'),
            short_description=tournament_data.get('short_description'),
            body=tournament_data.get('body'),
            status=tournament_data.get('status', 'draft'),
            source=tournament_data.get('source', 'manual'),
            publish_to_teletype=tournament_data.get('publish_to_teletype', False),
            publish_to_telegram=tournament_data.get('publish_to_telegram', False),
            telegram_chat_id=tournament_data.get('telegram_chat_id'),
            city=tournament_data.get('city'),
            region=tournament_data.get('region'),
            sport=tournament_data.get('sport', 'футбол'),
            start_date=tournament_data.get('start_date'),
            end_date=tournament_data.get('end_date'),
            format=tournament_data.get('format'),
            contact=tournament_data.get('contact'),
            birth_years=tournament_data.get('birth_years'),
            entry_fee=tournament_data.get('entry_fee'),
            organizer_name=tournament_data.get('organizer_name'),
            image_original_url=tournament_data.get('image_original_url'),
            image_cover_16x9_url=tournament_data.get('image_cover_16x9_url'),
            image_cover_square_url=tournament_data.get('image_cover_square_url'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Сохраняем турнир с извлеченными данными
        saved_tournament = await tournament_service.save_tournament_with_extracted_data(tournament, extracted_data)
        
        logger.info(f"✅ Tournament created with extracted data, ID: {saved_tournament.id}")
        
        return {
            "success": True,
            "tournament_id": saved_tournament.id,
            "tournament": saved_tournament.model_dump()
        }
        
    except Exception as e:
        logger.error(f"Error creating tournament with extracted data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-image")
async def upload_tournament_image(file: UploadFile = File(..., description="Изображение турнира (до 15МБ)")):
    """
    Загружает изображение для турнира и генерирует варианты (оригинал, 16:9, 1:1)
    """
    try:
        logger.info(f"🚀 Upload endpoint called with file: {file.filename}, size: {getattr(file, 'size', 'unknown')}")
    except Exception as e:
        logger.error(f"Error in upload endpoint start: {e}")
    
    try:
        from app.services.tournament_image_service import tournament_image_service
        
        # Проверяем размер файла до чтения (FastAPI может иметь свои ограничения)
        MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB
        logger.info(f"🔍 FastAPI file size check: file.size={getattr(file, 'size', 'unknown')}, MAX_FILE_SIZE={MAX_FILE_SIZE}")
        if hasattr(file, 'size') and file.size and file.size > MAX_FILE_SIZE:
            error_msg = "Файл слишком большой. Максимальный размер: 15 МБ"
            logger.error(f"❌ FastAPI file too large: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Читаем содержимое файла
        file_content = await file.read()
        
        # Дополнительная проверка размера после чтения
        logger.info(f"🔍 FastAPI content size check: len(file_content)={len(file_content)}, MAX_FILE_SIZE={MAX_FILE_SIZE}")
        if len(file_content) > MAX_FILE_SIZE:
            error_msg = "Файл слишком большой. Максимальный размер: 15 МБ"
            logger.error(f"❌ FastAPI content too large: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Сохраняем оригинал
        original_url = await tournament_image_service.save_original(file_content, file.filename)
        
        # Генерируем варианты
        cover_16x9_url = tournament_image_service.generate_cover_16x9(original_url)
        cover_square_url = tournament_image_service.generate_cover_square(original_url)
        
        return {
            "success": True,
            "image_original_url": original_url,
            "image_cover_16x9_url": cover_16x9_url,
            "image_cover_square_url": cover_square_url
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading tournament image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{tournament_id}/upload-image")
async def upload_tournament_image_by_id(
    tournament_id: int,
    file: UploadFile = File(..., description="Изображение турнира"),
    type: str = Form("original", description="Тип картинки: 'square' или 'original'")
):
    """
    Загружает картинку для конкретного турнира.
    type='square' - квадратная картинка (для Telegram), сохраняется как есть без обрезки
    type='original' - оригинальная картинка
    """
    try:
        from app.services.tournament_image_service import tournament_image_service
        import uuid
        import os
        
        # Проверяем существование турнира
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Турнир не найден")
        
        # Проверяем размер файла
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Файл слишком большой. Максимальный размер: 10 МБ")
        
        # Генерируем уникальное имя файла
        file_ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
        if file_ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            file_ext = '.jpg'
        
        unique_id = str(uuid.uuid4())
        
        # Определяем путь сохранения
        media_dir = os.path.join("app", "static", "media", "tournaments")
        os.makedirs(media_dir, exist_ok=True)
        
        if type == "square":
            # Сохраняем квадратную картинку как есть (без автоматической обрезки)
            filename = f"{unique_id}_square{file_ext}"
            filepath = os.path.join(media_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(file_content)
            
            image_url = f"/static/media/tournaments/{filename}"
            
            # Обновляем турнир
            await tournament_service.update_tournament(tournament_id, {
                "image_cover_square_url": image_url
            })
            
            logger.info(f"✅ Загружена квадратная картинка для турнира {tournament_id}: {image_url}")
            
            return {
                "success": True,
                "type": "square",
                "image_url": image_url
            }
        else:
            # Сохраняем оригинальную картинку
            filename = f"{unique_id}{file_ext}"
            filepath = os.path.join(media_dir, filename)
            
            with open(filepath, 'wb') as f:
                f.write(file_content)
            
            image_url = f"/static/media/tournaments/{filename}"
            
            # Обновляем турнир
            await tournament_service.update_tournament(tournament_id, {
                "image_original_url": image_url
            })
            
            logger.info(f"✅ Загружена оригинальная картинка для турнира {tournament_id}: {image_url}")
            
            return {
                "success": True,
                "type": "original",
                "image_url": image_url
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading image for tournament {tournament_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{tournament_id}/remove-image")
async def remove_tournament_image(tournament_id: int, type: str = "original"):
    """
    Удаляет картинку турнира.
    type='square' - удалить квадратную картинку
    type='original' - удалить оригинальную картинку
    """
    try:
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Турнир не найден")
        
        if type == "square":
            await tournament_service.update_tournament(tournament_id, {
                "image_cover_square_url": None
            })
            logger.info(f"✅ Удалена квадратная картинка турнира {tournament_id}")
        else:
            await tournament_service.update_tournament(tournament_id, {
                "image_original_url": None
            })
            logger.info(f"✅ Удалена оригинальная картинка турнира {tournament_id}")
        
        return {"success": True, "type": type}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing image for tournament {tournament_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ExtractDataRequest(BaseModel):
    """Запрос на извлечение данных турнира из текста"""
    text: str = Field(..., min_length=10, description="Текст для анализа")



@router.post("/api-extract-tournament-data")
async def extract_tournament_data(request: ExtractDataRequest):
    """
    Извлекает структурированные данные турнира из текста с помощью LLM
    """
    try:
        from app.services.tournament_extraction_service import tournament_extraction_service
        
        # Используем новый сервис извлечения данных
        extracted_data = await tournament_extraction_service.extract_tournament_data(request.text)
        
        logger.info(f"✅ Successfully extracted tournament data using new service")
        return extracted_data
        
    except Exception as e:
        logger.error(f"Error in new extraction service, falling back to old implementation: {e}")
        # Fallback to old implementation
        return await extract_tournament_data_impl(request)

@router.post("/simple-extract")
async def simple_extract_tournament_data(request: ExtractDataRequest):
    """
    Простое извлечение данных турнира
    """
    try:
        # Убеждаемся, что LLM сервис настроен
        if not llm_service.configured:
            await llm_service.refresh_client()
            if not llm_service.configured:
                return {
                    "city": None, "region": None, "start_date": None, "end_date": None,
                    "birth_years": None, "format": None, "entry_fee": None, 
                    "organizer_name": None, "contact": None
                }
        
        # Простой промпт
        prompt = f"""Извлеки данные из текста о турнире:

{request.text}

Верни JSON:
{{
    "city": "город или null",
    "region": "регион или null",
    "start_date": "YYYY-MM-DD или null",
    "end_date": "YYYY-MM-DD или null", 
    "birth_years": "года рождения или null",
    "format": "формат турнира или null",
    "entry_fee": "взнос или null",
    "organizer_name": "организатор или null",
    "contact": "телефон или null"
}}"""

        response = await llm_service.generate_content_async(prompt, timeout=30)
        
        if not response:
            return {
                "city": None, "region": None, "start_date": None, "end_date": None,
                "birth_years": None, "format": None, "entry_fee": None, 
                "organizer_name": None, "contact": None
            }
        
        # Парсим JSON
        try:
            import json
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            result = json.loads(clean_response)
            
            # Очищаем данные
            for key, value in result.items():
                if value and str(value).strip() and str(value).lower() != 'null':
                    result[key] = str(value).strip()
                else:
                    result[key] = None
            
            return result
            
        except:
            # Если не удалось распарсить, возвращаем пустые данные
            return {
                "city": None, "region": None, "start_date": None, "end_date": None,
                "birth_years": None, "format": None, "entry_fee": None, 
                "organizer_name": None, "contact": None
            }
            
    except Exception as e:
        logger.error(f"Error in extract: {e}")
        return {
            "city": None, "region": None, "start_date": None, "end_date": None,
            "birth_years": None, "format": None, "entry_fee": None, 
            "organizer_name": None, "contact": None
        }

async def extract_tournament_data_impl(request: ExtractDataRequest):
    """
    Извлекает структурированные данные турнира из текста с помощью LLM
    """
    try:
        # Убеждаемся, что LLM сервис настроен
        if not llm_service.configured:
            await llm_service.refresh_client()
            if not llm_service.configured:
                raise HTTPException(status_code=500, detail="LLM service not configured")
        
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

        # Генерируем ответ
        response = await llm_service.generate_content_async(
            extraction_prompt,
            system_prompt="Ты эксперт по извлечению структурированных данных из текста. Отвечай только в формате JSON."
        )
        
        if not response:
            raise HTTPException(status_code=500, detail="Empty response from LLM")
        
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
            
            logger.info(f"✅ Successfully extracted tournament data: {result}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {response}")
            raise HTTPException(status_code=500, detail=f"Invalid JSON response from LLM: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting tournament data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ========== Test endpoint ==========

@router.get("/test-version")
async def test_version():
    """Test endpoint to verify server is running updated code"""
    return {"version": "15MB_LIMIT_VERSION", "timestamp": "2025-12-12_06:40"}

# ========== Параметризованные роуты (должны быть в конце) ==========

# Telegram Bot API endpoints

@router.get("/search")
async def search_tournaments(
    q: Optional[str] = None,
    city: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    age: Optional[str] = None,
    format: Optional[str] = None,
    limit: int = 15
):
    """Search tournaments for Telegram bot"""
    try:
        tournaments = await tournament_service.get_tournaments()
        
        # Filter tournaments based on criteria
        filtered_tournaments = []
        
        for tournament in tournaments:
            # Text search in title, description and alternative names
            if q:
                q_lower = q.lower()
                q_no_spaces = q_lower.replace(' ', '').replace('-', '')
                
                # Основной текст для поиска
                search_text = f"{tournament.title} {tournament.short_description or ''} {tournament.body or ''} {tournament.city or ''}".lower()
                
                # Проверяем основной текст
                found = q_lower in search_text or q_no_spaces in search_text.replace(' ', '')
                
                # Проверяем альтернативные названия
                if not found and tournament.alternative_names:
                    for alt_name in tournament.alternative_names:
                        alt_lower = alt_name.lower()
                        if q_lower in alt_lower or q_no_spaces in alt_lower.replace(' ', ''):
                            found = True
                            break
                        # Обратное вхождение - если альтернативное название в запросе
                        if alt_lower in q_lower or alt_lower.replace(' ', '') in q_no_spaces:
                            found = True
                            break
                
                if not found:
                    continue
            
            # City filter
            if city and tournament.city:
                if city.lower() not in tournament.city.lower():
                    continue
            
            # Date filters - handle both date objects and strings
            # Try both start_date and date_start fields
            def get_start_date(t):
                from datetime import datetime, date
                # Проверяем оба поля - start_date и date_start
                start = getattr(t, 'start_date', None) or getattr(t, 'date_start', None)
                if not start:
                    # Пробуем через dict если это dict-like объект
                    if hasattr(t, '__dict__'):
                        start = t.__dict__.get('start_date') or t.__dict__.get('date_start')
                if start:
                    if isinstance(start, str):
                        try:
                            return datetime.fromisoformat(start).date()
                        except ValueError:
                            return None
                    elif isinstance(start, date):
                        return start
                return None
            
            if date_from == "now":
                from datetime import datetime, date
                current_date = datetime.now().date()
                start = get_start_date(tournament)
                if start and start < current_date:
                    continue
            elif date_from:
                try:
                    from datetime import datetime, date
                    filter_date = datetime.fromisoformat(date_from).date()
                    start = get_start_date(tournament)
                    if start and start < filter_date:
                        continue
                except ValueError:
                    pass
            
            if date_to:
                try:
                    from datetime import datetime, date
                    filter_date = datetime.fromisoformat(date_to).date()
                    start = get_start_date(tournament)
                    # Турнир должен начинаться ДО конца периода
                    if start and start > filter_date:
                        continue
                except ValueError:
                    pass
            
            # Age filter - check if requested year is in tournament's birth years range
            if age:
                birth_years_list = tournament.birth_years_list
                if birth_years_list:
                    # Extract numeric years from the list
                    numeric_years = []
                    for year in birth_years_list:
                        digits = ''.join(ch for ch in str(year) if ch.isdigit())
                        if len(digits) == 4:
                            try:
                                numeric_years.append(int(digits))
                            except ValueError:
                                continue
                    
                    if numeric_years:
                        try:
                            requested_year = int(age)
                            min_year = min(numeric_years)
                            max_year = max(numeric_years)
                            if not (min_year <= requested_year <= max_year):
                                continue
                        except ValueError:
                            # If age is not a number, do text search
                            if age not in (tournament.birth_years_display or ""):
                                continue
                    else:
                        continue
                else:
                    continue
            
            # Format filter
            if format and tournament.format:
                if format.lower() not in tournament.format.lower():
                    continue
            
            # Convert to dict for response
            tournament_dict = {
                "id": tournament.id,
                "title": tournament.title,
                "short_description": tournament.short_description,
                "city": tournament.city,
                "region": tournament.region,
                "date_start": tournament.start_date.isoformat() if hasattr(tournament.start_date, 'isoformat') else str(tournament.start_date) if tournament.start_date else None,
                "date_end": tournament.end_date.isoformat() if hasattr(tournament.end_date, 'isoformat') else str(tournament.end_date) if tournament.end_date else None,
                "age": tournament.birth_years_display,
                "format": tournament.format,
                "entry_fee": tournament.entry_fee,
                "teletype_url": tournament.teletype_url,  # Ссылка на Telegraph
                "priority_rating": tournament.priority_rating or False,  # Рейтинговый турнир ⭐
                "priority_rating_start_date": tournament.priority_rating_start_date,
                "is_premium": tournament.is_premium or False,  # Премиум-турнир 🔝
                "premium_until": tournament.premium_until
            }
            
            filtered_tournaments.append(tournament_dict)
        
        # Проверяем активность рейтинга и премиума по датам
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        
        for t in filtered_tournaments:
            # Рейтинг активен если есть дата начала и не прошло 45 дней
            if t.get("priority_rating") and t.get("priority_rating_start_date"):
                start = datetime.strptime(t["priority_rating_start_date"], "%Y-%m-%d")
                end = start.replace(day=start.day) 
                from datetime import timedelta
                end = start + timedelta(days=45)
                t["rating_active"] = datetime.now() <= end
            else:
                t["rating_active"] = False
            
            # Премиум активен если дата окончания не прошла
            if t.get("is_premium") and t.get("premium_until"):
                t["premium_active"] = t["premium_until"] >= today
            else:
                t["premium_active"] = False
        
        # Сортировка: 1) Рейтинг ⭐, 2) Премиум 🔝, 3) Обычные — по дате
        def sort_key(x):
            # Приоритет: рейтинг (0) > премиум (1) > обычные (2)
            if x.get("rating_active"):
                priority = 0
            elif x.get("premium_active"):
                priority = 1
            else:
                priority = 2
            return (priority, x["date_start"] or "9999-12-31")
        
        filtered_tournaments.sort(key=sort_key)
        
        # Limit results
        return {"tournaments": filtered_tournaments[:limit]}
        
    except Exception as e:
        logger.error(f"Error searching tournaments: {e}")
        return {"tournaments": []}


@router.get("/organizer/{contact_id}")
async def get_organizer_tournaments(contact_id: int):
    """
    Получить турниры организатора по contact_id.
    Используется в личном кабинете организатора.
    """
    try:
        all_tournaments = await tournament_service.get_tournaments()
        
        # Фильтруем по organizer_contact_id
        organizer_tournaments = []
        for t in all_tournaments:
            # Конвертируем в dict если это Pydantic модель
            if hasattr(t, 'model_dump'):
                t_dict = t.model_dump()
            elif hasattr(t, 'dict'):
                t_dict = t.dict()
            else:
                t_dict = t if isinstance(t, dict) else {}
            
            if t_dict.get("organizer_contact_id") == contact_id:
                organizer_tournaments.append(t_dict)
        
        logger.info(f"Found {len(organizer_tournaments)} tournaments for organizer {contact_id}")
        return {"tournaments": organizer_tournaments}
        
    except Exception as e:
        logger.error(f"Error getting organizer tournaments: {e}")
        return {"tournaments": []}


@router.get("/{tournament_id}/card")
async def get_tournament_card(tournament_id: int):
    """Get tournament card for display - returns full tournament data"""
    try:
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        
        # Return full tournament data for bot to format
        from app.core.config import settings
        base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
        
        # Convert tournament to dict
        tournament_data = tournament.model_dump() if hasattr(tournament, 'model_dump') else dict(tournament)
        
        # Add URL for reference
        tournament_data["url"] = f"{base_url}/tournaments/{tournament_id}"
        
        return {
            "type": "data",
            "card": tournament_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tournament card: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CreateLeadRequest(BaseModel):
    contact_id: int
    comment: str
    source: str = "telegram"

@router.post("/{tournament_id}/lead")
async def create_tournament_lead(tournament_id: int, request: CreateLeadRequest):
    """Create a lead for tournament registration"""
    try:
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        
        # For now, just log the lead (can be extended to save to database)
        logger.info(f"Lead created for tournament {tournament_id}: contact_id={request.contact_id}, comment={request.comment}, source={request.source}")
        
        return {
            "status": "success",
            "message": "Lead created successfully",
            "lead_id": f"lead_{tournament_id}_{request.contact_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{tournament_id}")
async def get_tournament(tournament_id: int):
    """Получить турнир по ID"""
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")
    return tournament

@router.put("/{tournament_id}")
async def update_tournament(tournament_id: int, request: TournamentUpdateRequest):
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")

    update_payload = request.model_dump(exclude_unset=True)
    
    # Обновляем updated_at при любом изменении
    from datetime import datetime
    update_payload["updated_at"] = datetime.utcnow()
    
    # Обработка priority_rating ⭐ - устанавливаем дату начала при включении
    if "priority_rating" in update_payload:
        new_priority = update_payload.get("priority_rating")
        old_priority = tournament.priority_rating
        
        # Если включаем рейтинг и раньше не было или дата не установлена
        if new_priority and (not old_priority or not tournament.priority_rating_start_date):
            update_payload["priority_rating_start_date"] = datetime.utcnow().strftime("%Y-%m-%d")
        # Если выключаем рейтинг - сбрасываем дату
        elif not new_priority:
            update_payload["priority_rating_start_date"] = None
    
    # Обработка is_premium 🔝 - новая логика согласно ТЗ "12 задача"
    # Базовый период: 7 дней, продление: +7 дней (2000₽) или +1 день (500₽)
    # Ограничение: новая покупка возможна только через 24ч после окончания предыдущего
    from datetime import timedelta
    
    premium_action = update_payload.pop("premium_action", None)
    
    if premium_action or "is_premium" in update_payload:
        new_premium = update_payload.get("is_premium", tournament.is_premium)
        old_premium = tournament.is_premium
        current_premium_until = tournament.premium_until
        premium_last_ended = tournament.premium_last_ended
        
        # Проверяем текущий статус премиума
        premium_is_active = False
        if old_premium and current_premium_until:
            try:
                premium_end = datetime.strptime(current_premium_until, "%Y-%m-%d")
                premium_is_active = premium_end >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            except:
                pass
        
        if premium_action == "extend_7days":
            # Продление на 7 дней - только при активном премиуме
            if not premium_is_active:
                raise HTTPException(status_code=400, detail="Продление возможно только при активном премиум-статусе")
            
            premium_end = datetime.strptime(current_premium_until, "%Y-%m-%d")
            new_end = premium_end + timedelta(days=7)
            update_payload["premium_until"] = new_end.strftime("%Y-%m-%d")
            update_payload["is_premium"] = True
            logger.info(f"🔝 Premium extended +7 days for tournament {tournament_id}: until {new_end.strftime('%Y-%m-%d')}")
            
        elif premium_action == "extend_1day":
            # Докупка 1 дня - только при активном премиуме
            if not premium_is_active:
                raise HTTPException(status_code=400, detail="Докупка дня возможна только при активном премиум-статусе")
            
            premium_end = datetime.strptime(current_premium_until, "%Y-%m-%d")
            new_end = premium_end + timedelta(days=1)
            update_payload["premium_until"] = new_end.strftime("%Y-%m-%d")
            update_payload["is_premium"] = True
            logger.info(f"🔝 Premium extended +1 day for tournament {tournament_id}: until {new_end.strftime('%Y-%m-%d')}")
            
        elif premium_action == "activate" or (new_premium and not old_premium):
            # Активация нового премиума
            # Проверяем 24-часовое ограничение
            if premium_last_ended:
                try:
                    last_ended = datetime.strptime(premium_last_ended, "%Y-%m-%d %H:%M:%S")
                    hours_since_ended = (datetime.utcnow() - last_ended).total_seconds() / 3600
                    if hours_since_ended < 24:
                        hours_remaining = int(24 - hours_since_ended)
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Новая покупка Премиум-размещения доступна через {hours_remaining} ч. после окончания предыдущего периода"
                        )
                except ValueError:
                    pass  # Неверный формат даты - игнорируем ограничение
            
            # Активируем премиум на 7 дней
            update_payload["is_premium"] = True
            update_payload["premium_until"] = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
            logger.info(f"🔝 Premium activated for tournament {tournament_id}: 7 days")
            
        elif not new_premium and old_premium:
            # Выключаем премиум - сохраняем дату окончания для 24ч ограничения
            update_payload["is_premium"] = False
            update_payload["premium_last_ended"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            update_payload["premium_until"] = None
            logger.info(f"🔝 Premium deactivated for tournament {tournament_id}")

    # Normalize whitespace-only values to None
    for key in ('city', 'region'):
        if key in update_payload and isinstance(update_payload[key], str):
            update_payload[key] = update_payload[key].strip() or None

    if "birth_years" in update_payload:
        birth_years_value = update_payload.get("birth_years")
        if isinstance(birth_years_value, str):
            birth_years_value = [y.strip() for y in birth_years_value.split(",") if y.strip()]
        update_payload["birth_years"] = birth_years_value

    resulting_region = update_payload.get("region") if "region" in update_payload else tournament.region
    city_candidate = update_payload.get("city") if "city" in update_payload else tournament.city

    if not resulting_region and city_candidate:
        inferred_region = await infer_region_from_city(city_candidate)
        if inferred_region:
            update_payload["region"] = inferred_region

    updated = await tournament_service.update_tournament(tournament_id, update_payload)
    response_data = updated.model_dump()
    response_data["birth_years_display"] = updated.birth_years_display
    response_data["birth_years_list"] = updated.birth_years_list
    return response_data

@router.delete("/{tournament_id}")
async def delete_tournament(tournament_id: int):
    """Удалить турнир"""
    await tournament_service.delete_tournament(tournament_id)
    return {"success": True}


@router.post("/regenerate-alternative-names")
async def regenerate_alternative_names():
    """
    Регенерирует альтернативные названия для всех турниров.
    Используется для обновления существующих турниров после добавления функции.
    """
    from app.utils.tournament_name_generator import generate_alternative_names
    
    try:
        tournaments = await tournament_service.get_tournaments()
        updated_count = 0
        
        for tournament in tournaments:
            if tournament.title:
                old_names = tournament.alternative_names or []
                new_names = generate_alternative_names(tournament.title)
                
                if set(new_names) != set(old_names):
                    tournament.alternative_names = new_names
                    updated_count += 1
                    logger.info(f"🏷️ Updated alternative names for '{tournament.title}': {len(new_names)} names")
        
        if updated_count > 0:
            await tournament_service._save_data(tournaments)
        
        return {
            "success": True,
            "updated_count": updated_count,
            "total_tournaments": len(tournaments),
            "message": f"Обновлено {updated_count} турниров из {len(tournaments)}"
        }
        
    except Exception as e:
        logger.error(f"Error regenerating alternative names: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tournament_id}/alternative-names")
async def get_tournament_alternative_names(tournament_id: int):
    """
    Получить альтернативные названия турнира.
    """
    tournament = await tournament_service.get_tournament_by_id(tournament_id)
    if not tournament:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_id} not found")
    
    return {
        "tournament_id": tournament_id,
        "title": tournament.title,
        "alternative_names": tournament.alternative_names or []
    }
