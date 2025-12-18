from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
from datetime import datetime
from app.services.contact_service import contact_service
from app.models.contact import Contact
import logging

router = APIRouter(tags=["contacts"])
logger = logging.getLogger(__name__)

class ParseRequest(BaseModel):
    text: str

@router.get("/", response_model=List[Contact])
async def get_contacts():
    return await contact_service.get_contacts()

@router.post("/", response_model=Dict[str, str])
async def save_contacts(contacts: List[Contact]):
    await contact_service.save_contacts(contacts)
    return {"status": "success", "message": f"Saved {len(contacts)} contacts"}


class UpsertContactRequest(BaseModel):
    """Запрос на создание/обновление контакта из Telegram бота"""
    telegram_user_id: int
    phone: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    consent_version: Optional[str] = None
    consent_given_at: Optional[str] = None


@router.post("/upsert")
async def upsert_contact(request: UpsertContactRequest):
    """
    Создает новый контакт или обновляет существующий по telegram_user_id или phone.
    Используется Telegram ботом для регистрации пользователей.
    """
    from app.utils.contact_helpers import normalize_phone
    
    logger.info(f"📱 Upsert contact: telegram_user_id={request.telegram_user_id}, phone={request.phone}")
    
    # Нормализуем телефон
    normalized_phone = normalize_phone(request.phone)
    if not normalized_phone:
        normalized_phone = request.phone
    
    # Формируем имя
    name_parts = []
    if request.first_name:
        name_parts.append(request.first_name)
    if request.last_name:
        name_parts.append(request.last_name)
    name = " ".join(name_parts) if name_parts else f"Telegram User {request.telegram_user_id}"
    
    # Ищем существующий контакт по телефону
    contacts = await contact_service.get_contacts()
    existing_contact = None
    
    for contact in contacts:
        contact_phone = normalize_phone(contact.phone) if contact.phone else None
        if contact_phone and contact_phone == normalized_phone:
            existing_contact = contact
            break
    
    if existing_contact:
        # Обновляем существующий контакт
        logger.info(f"✅ Found existing contact: {existing_contact.id} ({existing_contact.name})")
        
        # Обновляем имя если было пустым
        if not existing_contact.name or existing_contact.name == existing_contact.phone:
            existing_contact.name = name
        
        # Сохраняем telegram_user_id в поле контакта
        if request.telegram_user_id:
            existing_contact.telegram_user_id = request.telegram_user_id
        if request.username:
            existing_contact.telegram_username = request.username
        if request.consent_version:
            existing_contact.consent_version = request.consent_version
        if request.consent_given_at:
            from datetime import datetime
            try:
                existing_contact.consent_given_at = datetime.fromisoformat(request.consent_given_at)
            except:
                pass
        
        await contact_service.update_contact(existing_contact.id, existing_contact)
        
        return {
            "contact_id": existing_contact.id,
            "is_new": False
        }
    else:
        # Создаем новый контакт
        logger.info(f"🆕 Creating new contact: {name}, {normalized_phone}")
        
        # Определяем следующий ID
        next_id = max([c.id for c in contacts if c.id is not None], default=0) + 1
        
        # Парсим дату согласия
        consent_dt = None
        if request.consent_given_at:
            from datetime import datetime
            try:
                consent_dt = datetime.fromisoformat(request.consent_given_at)
            except:
                pass
        
        new_contact = Contact(
            id=next_id,
            name=name,
            phone=normalized_phone,
            group="Telegram",
            telegram_user_id=request.telegram_user_id,
            telegram_username=request.username,
            consent_version=request.consent_version,
            consent_given_at=consent_dt
        )
        
        await contact_service.save_contacts([new_contact])
        
        logger.info(f"✅ Created new contact: {next_id} ({name})")
        
        return {
            "contact_id": next_id,
            "is_new": True
        }

@router.post("/parse", response_model=List[Dict[str, str]])
async def parse_contacts(request: ParseRequest):
    return await contact_service.parse_text_with_ai(request.text)

@router.post("/upload", response_model=List[Dict[str, str]])
async def upload_xlsx(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xls files are supported")
    
    contents = await file.read()
    return await contact_service.parse_xlsx_file(contents)

@router.put("/{contact_id}", response_model=Contact)
async def update_contact(contact_id: int, contact: Contact):
    """Update a contact"""
    return await contact_service.update_contact(contact_id, contact)

@router.delete("/{contact_id}")
async def delete_contact(contact_id: int):
    """Delete a contact by ID"""
    await contact_service.delete_contact(contact_id)
    return {"status": "success", "message": f"Contact {contact_id} deleted"}

@router.post("/{contact_id}/enrich", response_model=Contact)
async def enrich_contact(contact_id: int):
    """Enrich a single contact with WhatsApp profile data"""
    from app.services.contact_enrichment_service import contact_enrichment_service
    return await contact_enrichment_service.enrich_contact(contact_id)

@router.post("/bulk-update-whatsapp-ids")
async def bulk_update_whatsapp_ids():
    """Массовое обновление WhatsApp ID для всех контактов через Green API"""
    result = await contact_service.bulk_update_whatsapp_ids()
    return result

@router.post("/normalize-all-phones")
async def normalize_all_phones():
    """
    Нормализует все номера телефонов в записной книжке к единому формату +7XXXXXXXXXX.
    Приводит все существующие телефоны к единому виду.
    """
    from app.utils.contact_helpers import normalize_phone
    
    contacts = await contact_service.get_contacts()
    updated_count = 0
    failed_count = 0
    errors = []
    
    for contact in contacts:
        if contact.phone and contact.phone.strip():
            try:
                normalized = normalize_phone(contact.phone)
                if normalized and normalized != contact.phone:
                    # Обновляем только если номер изменился
                    contact.phone = normalized
                    updated_count += 1
                    logger.info(f"Normalized phone for contact {contact.id}: {contact.phone} -> {normalized}")
                elif not normalized:
                    # Если нормализация не удалась, логируем
                    failed_count += 1
                    errors.append(f"Contact {contact.id} ({contact.name}): could not normalize '{contact.phone}'")
                    logger.warning(f"Could not normalize phone for contact {contact.id}: {contact.phone}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Contact {contact.id} ({contact.name}): {str(e)}")
                logger.error(f"Error normalizing phone for contact {contact.id}: {e}")
    
    # Сохраняем обновленные контакты
    if updated_count > 0:
        await contact_service._save_data(contacts)
    
    return {
        "status": "success",
        "updated": updated_count,
        "failed": failed_count,
        "total": len(contacts),
        "errors": errors[:10]  # Возвращаем первые 10 ошибок
    }

@router.post("/enrich-all")
async def enrich_all_contacts():
    """Enrich all contacts with WhatsApp profile data"""
    from app.services.contact_enrichment_service import contact_enrichment_service
    return await contact_enrichment_service.enrich_all_contacts()

@router.get("/enrich-all/status")
async def get_enrichment_status():
    """Get current status of enrichment process"""
    from app.services.contact_enrichment_service import contact_enrichment_service
    return await contact_enrichment_service.get_enrichment_status()

@router.post("/{contact_id}/reset-sync")
async def reset_contact_sync(contact_id: int):
    """Reset last_sync_at for a contact to enable full message re-sync"""
    contact = await contact_service.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    
    # Reset last_sync_at to None
    contact.last_sync_at = None
    await contact_service.update_contact(contact_id, contact)
    
    return {"status": "success", "message": f"Sync timestamp reset for contact {contact_id}"}

# Contact Insights Endpoints

@router.get("/{contact_id}/insights")
async def get_contact_insights(contact_id: int):
    """Get AI-generated insights for a contact"""
    from app.services.contact_insight_service import contact_insight_service
    from app.models.contact_insight import ContactInsight
    
    # Проверяем, существует ли контакт
    contact = await contact_service.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    
    insight = await contact_insight_service.get_insights(contact_id)
    if not insight:
        # Возвращаем пустой insight вместо 404, чтобы фронтенд мог отобразить карточку
        return ContactInsight(
            contact_id=contact_id,
            summary="",
            tags=[],
            from_dialogs="",
            manually_edited=False
        )
    return insight

@router.post("/{contact_id}/analyze-author")
async def analyze_contact_author(contact_id: int):
    """Принудительно запустить анализ автора сообщений для контакта"""
    from app.services.author_analysis_service import author_analysis_service
    
    # Check if contact exists
    contact = await contact_service.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    
    if not contact.whatsapp_id:
        raise HTTPException(status_code=400, detail=f"Contact {contact_id} has no WhatsApp ID")
    
    try:
        # Очищаем очередь для этого пользователя, чтобы обойти защиту от спама
        analysis_key = contact.whatsapp_id
        if analysis_key in author_analysis_service.immediate_analysis_queue:
            del author_analysis_service.immediate_analysis_queue[analysis_key]
            logger.info(f"🧹 Cleared analysis queue for {analysis_key} to force re-analysis")
        
        # Запускаем анализ автора принудительно
        await author_analysis_service.analyze_author_immediately(
            sender_name=contact.name or contact.whatsapp_name or contact.whatsapp_id,
            sender_id=contact.whatsapp_id,
            group_id=None,
            group_name=None
        )
        
        return {
            "status": "success",
            "message": f"Analysis triggered for contact {contact_id} (WhatsApp ID: {contact.whatsapp_id})"
        }
    except Exception as e:
        logger.error(f"Error analyzing author for contact {contact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.post("/{contact_id}/insights/analyze")
async def analyze_contact_dialogs(contact_id: int):
    """Trigger AI analysis of contact's WhatsApp dialogs"""
    from app.services.dialog_analyzer_service import dialog_analyzer_service
    from app.services.contact_insight_service import contact_insight_service
    
    # Check if contact exists
    contact = await contact_service.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    
    try:
        # Analyze dialogs
        insight = await dialog_analyzer_service.analyze_contact_dialogs(contact_id)
        
        # Save insights
        saved_insight = await contact_insight_service.create_or_update_insights(insight)
        
        return {
            "status": "success",
            "message": f"Analysis completed for contact {contact_id}",
            "insight": saved_insight
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.put("/{contact_id}/insights")
async def update_contact_insights(
    contact_id: int, 
    request: dict = Body(...)
):
    """Manually update contact insights"""
    from app.services.contact_insight_service import contact_insight_service
    
    # Build update fields
    fields = {}
    if "summary" in request:
        fields["summary"] = request["summary"]
    if "tags" in request:
        fields["tags"] = request["tags"]
    if "from_dialogs" in request:
        fields["from_dialogs"] = request["from_dialogs"]
    
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Update insights
    insight = await contact_insight_service.update_insights_field(contact_id, **fields)
    if not insight:
        raise HTTPException(status_code=404, detail=f"No insights found for contact {contact_id}")
    
    return insight

@router.post("/{contact_id}/refresh-status")
async def refresh_contact_status(contact_id: int):
    """Принудительно обновить статус WhatsApp контакта (lastSeen)"""
    from app.services.green_api_service import green_api_service
    from app.services.contact_service import contact_service
    
    contact = await contact_service.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    
    if not contact.whatsapp_id:
        raise HTTPException(status_code=400, detail="Contact has no WhatsApp ID")
    
    try:
        # Получаем информацию о контакте из Green API
        contact_info = await green_api_service.get_contact_info(contact.whatsapp_id)
        
        if contact_info.get("exists"):
            # Обновляем lastSeen если он есть
            if contact_info.get("lastSeen"):
                contact.whatsapp_last_seen = contact_info["lastSeen"]
                await contact_service.update_contact(contact_id, contact)
                return {
                    "status": "success",
                    "last_seen": contact_info["lastSeen"].isoformat() if hasattr(contact_info["lastSeen"], "isoformat") else str(contact_info["lastSeen"])
                }
            else:
                return {
                    "status": "success",
                    "message": "Last seen not available for this contact"
                }
        else:
            raise HTTPException(status_code=404, detail="Contact not found in WhatsApp")
            
    except Exception as e:
        logger.error(f"Error refreshing contact status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обновления статуса: {str(e)}")

@router.post("/{contact_id}/refresh")
async def refresh_contact_info(contact_id: int):
    """Принудительно обновить всю информацию о контакте из WhatsApp"""
    from app.services.green_api_service import green_api_service
    from app.services.contact_service import contact_service
    
    contact = await contact_service.get_contact_by_id(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
    
    # Используем WhatsApp ID если есть, иначе телефон
    contact_identifier = contact.whatsapp_id or contact.phone
    if not contact_identifier:
        raise HTTPException(status_code=400, detail="Contact has no WhatsApp ID or phone")
    
    try:
        # Получаем информацию о контакте из Green API
        contact_info = await green_api_service.get_contact_info(contact_identifier)
        
        if contact_info.get("exists"):
            # Обновляем все доступные поля
            if contact_info.get("name"):
                contact.whatsapp_name = contact_info["name"]
            if contact_info.get("whatsapp_id"):
                contact.whatsapp_id = contact_info["whatsapp_id"]
            if contact_info.get("email"):
                contact.whatsapp_email = contact_info["email"]
            if contact_info.get("lastSeen"):
                contact.whatsapp_last_seen = contact_info["lastSeen"]
            if contact_info.get("avatar"):
                contact.avatar_url = contact_info["avatar"]
            
            await contact_service.update_contact(contact_id, contact)
            
            return {
                "status": "success",
                "message": "Contact information updated",
                "contact": contact
            }
        else:
            raise HTTPException(status_code=404, detail="Contact not found in WhatsApp")
            
    except Exception as e:
        logger.error(f"Error refreshing contact info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обновления информации: {str(e)}")

@router.post("/{contact_id}/insights/process")
async def process_contact_info_with_llm(
    contact_id: int,
    request: dict = Body(...)
):
    """Обработать информацию о контакте через LLM с пользовательским промптом"""
    from app.services.llm_service import llm_service
    from app.services.contact_service import contact_service
    from app.services.contact_insight_service import contact_insight_service
    
    # Проверяем наличие промпта и текста
    user_prompt = request.get("prompt", "").strip()
    current_text = request.get("text", "").strip()
    
    if not user_prompt:
        raise HTTPException(status_code=400, detail="Промпт не может быть пустым")
    
    if not current_text:
        raise HTTPException(status_code=400, detail="Текст для обработки не может быть пустым")
    
    try:
        # Обрабатываем текст через LLM
        processed_text = await llm_service.process_text_with_prompt(current_text, user_prompt)
        
        # Обновляем insights с обработанным текстом
        insight = await contact_insight_service.update_insights_field(contact_id, summary=processed_text)
        
        if not insight:
            # Если insights не существует, создаем новый
            from app.models.contact_insight import ContactInsight
            insight = ContactInsight(
                contact_id=contact_id,
                summary=processed_text,
                tags=[],
                from_dialogs=""
            )
            from app.services.contact_insight_service import contact_insight_service
            insight = await contact_insight_service.create_or_update_insights(insight)
        
        return {
            "status": "success",
            "processed_text": processed_text,
            "insight": insight
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing contact info with LLM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")

@router.post("/{contact_id}/draft/process")
async def process_draft_info(contact_id: int):
    """Обработать черновик информации через LLM - структурировать, убрать даты и ссылки"""
    from app.services.llm_service import llm_service
    from app.services.contact_service import contact_service
    
    try:
        # Получаем контакт
        contacts = await contact_service.get_contacts()
        contact = next((c for c in contacts if c.id == contact_id), None)
        
        if not contact:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        
        if not contact.draft_info or not contact.draft_info.strip():
            raise HTTPException(status_code=400, detail="Черновик информации пуст")
        
        # Промпт для обработки черновика
        prompt = """Проанализируй предоставленную информацию о контакте и создай структурированное описание.

ИНСТРУКЦИИ:
1. Игнорируй все даты публикации сообщений и временные метки
2. Игнорируй все ссылки на ресурсы (URL, телеграм-каналы, сайты и т.д.)
3. Извлеки и структурируй только значимую информацию о контакте:
   - Роль и деятельность
   - Организация/клуб/школа
   - Специализация
   - Города/регионы работы
   - Контактная информация (только телефоны, без ссылок)
   - Основные направления деятельности
4. Создай краткое, структурированное описание
5. Используй формат с четкими разделами
6. Убери дублирующуюся информацию

Информация для обработки:
{text}

Верни только структурированное описание, без дополнительных комментариев.""".format(text=contact.draft_info)
        
        # Обрабатываем через LLM
        processed_text = await llm_service.generate_content_async(prompt)
        
        if not processed_text:
            raise HTTPException(status_code=500, detail="LLM не вернул результат")
        
        # Обновляем extracted_info обработанным текстом
        contact.extracted_info = processed_text.strip()
        await contact_service.update_contact(contact_id, contact)
        
        return {
            "status": "success",
            "processed_text": processed_text.strip(),
            "message": "Черновик успешно обработан"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing draft info for contact {contact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка обработки черновика: {str(e)}")

@router.delete("/{contact_id}/insights")
async def delete_contact_insights(contact_id: int):
    """Delete insights for a contact"""
    from app.services.contact_insight_service import contact_insight_service
    
    success = await contact_insight_service.delete_insights(contact_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"No insights found for contact {contact_id}")
    
    return {"status": "success", "message": f"Insights for contact {contact_id} deleted"}

class BulkMoveRequest(BaseModel):
    contact_ids: List[int]
    target_group: str

class BulkDeleteRequest(BaseModel):
    contact_ids: List[int]

@router.post("/bulk/move")
async def bulk_move_contacts(request: BulkMoveRequest):
    """Move multiple contacts to a target group"""
    return await contact_service.bulk_move(request.contact_ids, request.target_group)

@router.post("/bulk/delete")
async def bulk_delete_contacts(request: BulkDeleteRequest):
    """Delete multiple contacts"""
    return await contact_service.bulk_delete(request.contact_ids)

@router.get("/count/by-group")
async def get_contacts_count_by_group():
    """Get count of contacts grouped by group name"""
    contacts = await contact_service.get_contacts()
    
    # Count contacts by group
    group_counts = {}
    for contact in contacts:
        group_name = contact.group or "Без группы"
        group_counts[group_name] = group_counts.get(group_name, 0) + 1
    
    return group_counts

@router.get("/count/total")
async def get_total_contacts_count():
    """Get total count of contacts"""
    contacts = await contact_service.get_contacts()
    return {"total": len(contacts)}


@router.get("/by-telegram/{telegram_user_id}")
async def get_contact_by_telegram_id(telegram_user_id: int):
    """
    Получить контакт по Telegram user ID.
    Используется ботом для проверки, зарегистрирован ли пользователь.
    Оптимизировано: сначала быстрый поиск по индексу, потом полный поиск.
    """
    # Быстрый поиск по telegram_user_id через сервис
    contact = await contact_service.get_contact_by_telegram_id(telegram_user_id)
    if contact:
        return {
            "found": True,
            "contact_id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "consent_version": contact.consent_version,
            "consent_given_at": contact.consent_given_at.isoformat() if contact.consent_given_at else None
        }
    
    return {"found": False}

# Group Data Collection Endpoints

class CollectGroupRequest(BaseModel):
    group_id: str

class CollectedContact(BaseModel):
    whatsapp_id: str
    name: Optional[str] = None
    phone: Optional[str] = None

class LoadCollectedRequest(BaseModel):
    contacts: List[CollectedContact]
    group_name: str = "Общая"

@router.post("/collect-group")
async def collect_group_contacts(request: CollectGroupRequest):
    """Собрать контакты участников из группы WhatsApp"""
    try:
        from app.services.green_api_service import green_api_service
        
        group_id = request.group_id.strip()
        
        # Проверяем формат ID группы
        if not group_id.endswith('@g.us'):
            raise HTTPException(status_code=400, detail="ID группы должен заканчиваться на @g.us")
        
        # Получаем данные группы
        group_data = await green_api_service.get_group_data(group_id)
        
        if not group_data or not isinstance(group_data, dict):
            raise HTTPException(status_code=404, detail="Группа не найдена или нет доступа")
        
        participants = group_data.get("participants", [])
        group_name = group_data.get("name", group_id)
        
        collected_contacts = []
        
        # Получаем список всех контактов из адресной книги для сопоставления имен
        address_book = await green_api_service.get_contacts()
        address_book_dict = {}
        for contact in address_book:
            contact_id = contact.get("id", "")
            if contact_id:
                address_book_dict[contact_id] = contact.get("name", "")
        
        for participant in participants:
            if isinstance(participant, str):
                participant_id = participant
            else:
                participant_id = participant.get("id", "")
            
            if participant_id and "@" in participant_id:
                # Пытаемся получить имя из адресной книги
                name = address_book_dict.get(participant_id, None)
                
                # Пытаемся извлечь телефон из ID (если это номер телефона)
                phone = None
                if participant_id.endswith("@c.us"):
                    # Убираем @c.us и проверяем, является ли это номером телефона
                    phone_part = participant_id.replace("@c.us", "")
                    if phone_part.isdigit() and len(phone_part) >= 10:
                        phone = phone_part
                
                collected_contacts.append({
                    "whatsapp_id": participant_id,
                    "name": name,
                    "phone": phone
                })
        
        return {
            "status": "success",
            "group_id": group_id,
            "group_name": group_name,
            "participants_count": len(collected_contacts),
            "contacts": collected_contacts
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error collecting group contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/load-collected")
async def load_collected_contacts(request: LoadCollectedRequest):
    """Загрузить собранные контакты в записную книжку с проверкой дублей"""
    try:
        from app.utils.contact_helpers import normalize_phone
        from datetime import datetime
        
        # Получаем существующие контакты для проверки дублей
        existing_contacts = await contact_service.get_contacts()
        existing_phones = {normalize_phone(c.phone) for c in existing_contacts if c.phone}
        existing_whatsapp_ids = {c.whatsapp_id for c in existing_contacts if c.whatsapp_id}
        
        loaded_count = 0
        duplicate_count = 0
        failed_count = 0
        errors = []
        
        new_contacts = []
        
        for collected in request.contacts:
            try:
                # Проверяем дубли по WhatsApp ID
                if collected.whatsapp_id in existing_whatsapp_ids:
                    duplicate_count += 1
                    continue
                
                # Проверяем дубли по телефону (если есть)
                if collected.phone and collected.phone.strip():
                    normalized_phone = normalize_phone(collected.phone)
                    if normalized_phone and normalized_phone in existing_phones:
                        duplicate_count += 1
                        continue
                
                # Нормализуем телефон перед созданием контакта
                normalized_phone = ""
                if collected.phone and collected.phone.strip():
                    normalized_phone = normalize_phone(collected.phone)
                    if not normalized_phone:
                        logger.warning(f"Could not normalize phone number: {collected.phone}, using as-is")
                        normalized_phone = collected.phone.strip()
                
                # Убеждаемся, что phone не пустая строка (требование модели Contact)
                if not normalized_phone:
                    normalized_phone = collected.whatsapp_id or "N/A"
                
                # Создаем новый контакт
                contact = Contact(
                    name=collected.name or normalized_phone or collected.whatsapp_id or "Без имени",
                    phone=normalized_phone,
                    group=request.group_name,
                    whatsapp_id=collected.whatsapp_id,
                    whatsapp_name=collected.name,
                    created_at=datetime.now()
                )
                
                new_contacts.append(contact)
                loaded_count += 1
                
                # Обновляем множества для проверки дублей в рамках текущей загрузки
                if contact.phone:
                    existing_phones.add(normalize_phone(contact.phone))
                if contact.whatsapp_id:
                    existing_whatsapp_ids.add(contact.whatsapp_id)
                    
            except Exception as e:
                failed_count += 1
                errors.append(f"{collected.whatsapp_id}: {str(e)}")
                logger.error(f"Error processing contact {collected.whatsapp_id}: {e}")
        
        # Сохраняем новые контакты (передаем только новые, save_contacts сам получит существующие)
        if new_contacts:
            await contact_service.save_contacts(new_contacts)
        
        return {
            "status": "success",
            "loaded": loaded_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
            "errors": errors[:10] if errors else []  # Ограничиваем количество ошибок в ответе
        }
    except Exception as e:
        logger.error(f"Error loading collected contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Telegram Bot API Endpoints

class UpsertContactRequest(BaseModel):
    telegram_user_id: int
    phone: str
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    consent_version: str = "1.0"
    consent_given_at: Optional[str] = None

class ContactTagRequest(BaseModel):
    key: str
    value: str
    confidence: float = 0.5
    last_seen_at: Optional[str] = None
    source: str = "telegram"

class MergeTagsRequest(BaseModel):
    add: List[ContactTagRequest] = []
    remove: List[ContactTagRequest] = []
    meta: Dict[str, Any] = {}


@router.post("/{contact_id}/tags/merge")
async def merge_contact_tags(contact_id: int, request: MergeTagsRequest):
    """Merge tags for a contact"""
    try:
        # Get existing contacts
        existing_contacts = await contact_service.get_contacts()
        
        # Find contact
        contact = None
        for c in existing_contacts:
            if c.id == contact_id:
                contact = c
                break
        
        if not contact:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        
        # Initialize tags if not exists
        if not hasattr(contact, 'tags') or contact.tags is None:
            contact.tags = []
        
        # Process add tags
        for tag_req in request.add:
            # Remove existing tag with same key-value if exists
            contact.tags = [t for t in contact.tags if not (t.get('key') == tag_req.key and t.get('value') == tag_req.value)]
            
            # Add new tag
            tag = {
                "key": tag_req.key,
                "value": tag_req.value,
                "confidence": tag_req.confidence,
                "source": tag_req.source,
                "last_seen_at": tag_req.last_seen_at or datetime.now().isoformat()
            }
            contact.tags.append(tag)
        
        # Process remove tags
        for tag_req in request.remove:
            contact.tags = [t for t in contact.tags if not (t.get('key') == tag_req.key and t.get('value') == tag_req.value)]
        
        # Save contacts using _save_data to update existing contacts
        await contact_service._save_data(existing_contacts)
        
        logger.info(f"🏷️ Merged tags for contact {contact_id}: {len(contact.tags)} total tags")
        
        return {
            "ok": True,
            "tags_current": contact.tags
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error merging tags for contact {contact_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))