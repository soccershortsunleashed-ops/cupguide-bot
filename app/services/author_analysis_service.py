"""
Фоновый сервис для анализа авторов сообщений и обновления контактов
"""
import asyncio
import logging
from typing import Dict, List
from datetime import datetime, timedelta
from app.services.whatsapp_message_service import whatsapp_message_service
from app.services.message_analysis_service import message_analysis_service
from app.services.contact_service import contact_service
from app.models.contact import Contact

logger = logging.getLogger(__name__)

class AuthorAnalysisService:
    """Сервис для анализа авторов сообщений и обновления контактов"""
    
    def __init__(self):
        self.is_running = False
        self.last_analysis_time: Dict[str, datetime] = {}  # sender_name -> last_analysis_time
        self.immediate_analysis_queue: Dict[str, datetime] = {}  # sender_id -> last_trigger_time
    
    async def analyze_new_authors(self):
        """Анализирует новых авторов сообщений"""
        from app.services.quota_manager import quota_manager
        
        # Сбрасываем счетчик OCR в начале прогона
        quota_manager.reset_ocr_call_count()
        """
        Анализирует сообщения новых авторов и обновляет контакты
        Запускается периодически в фоне
        """
        if self.is_running:
            logger.debug("Author analysis already running, skipping...")
            return
        
        self.is_running = True
        try:
            # Получаем все сообщения за последние 7 дней
            from datetime import timezone
            since = datetime.now(timezone.utc) - timedelta(days=7)
            all_messages = await whatsapp_message_service.get_messages(since=since)
            
            # Группируем сообщения по авторам и группам
            messages_by_author: Dict[str, Dict[str, List[dict]]] = {}
            # Структура: {sender_name: {group_id: [messages]}}
            
            for msg in all_messages:
                # Используем sender_id для идентификации, если доступен, иначе используем sender
                sender_identifier = msg.sender_id if msg.sender_id else (msg.sender if msg.sender and msg.sender != 'Unknown' else None)
                
                if not sender_identifier:
                    continue
                
                sender = msg.sender or sender_identifier  # Для отображения используем имя, если есть
                group_id = msg.chat_name
                
                # Используем sender_id как ключ для группировки, но сохраняем имя для отображения
                if sender_identifier not in messages_by_author:
                    messages_by_author[sender_identifier] = {}
                
                if group_id not in messages_by_author[sender_identifier]:
                    messages_by_author[sender_identifier][group_id] = []
                
                messages_by_author[sender_identifier][group_id].append({
                    'text': msg.text,
                    'date': msg.date,
                    'message_id': msg.message_id if hasattr(msg, 'message_id') else None,  # Добавляем message_id для отслеживания
                    'media_type': msg.media_type,
                    'sender_id': msg.sender_id,  # Сохраняем sender_id для сопоставления
                    'sender_name': sender  # Сохраняем имя для анализа
                })
            
            # Анализируем каждого автора
            for sender_identifier, groups in messages_by_author.items():
                try:
                    # Получаем имя автора из первого сообщения
                    first_message = None
                    for group_messages in groups.values():
                        if group_messages:
                            first_message = group_messages[0]
                            break
                    
                    sender_name = first_message.get('sender_name', sender_identifier) if first_message else sender_identifier
                    sender_id = first_message.get('sender_id') if first_message else (sender_identifier if '@c.us' in str(sender_identifier) else None)
                    
                    # Проверяем, не анализировали ли мы этого автора недавно (раз в день)
                    analysis_key = sender_id or sender_name
                    last_analysis = self.last_analysis_time.get(analysis_key)
                    if last_analysis and (datetime.now() - last_analysis) < timedelta(days=1):
                        logger.debug(f"Skipping analysis for {sender_name} ({analysis_key}) - analyzed recently")
                        continue
                    
                    # Берем группу с наибольшим количеством сообщений
                    main_group_id = max(groups.keys(), key=lambda g: len(groups[g]))
                    messages = groups[main_group_id]
                    
                    # Получаем название группы
                    group_name = main_group_id
                    try:
                        from app.services.whatsapp_service import whatsapp_service
                        monitored_chats = await whatsapp_service.get_monitored_chats_as_channels()
                        for chat in monitored_chats:
                            if chat.get('id') == main_group_id:
                                group_name = chat.get('title', main_group_id)
                                break
                    except Exception as e:
                        logger.debug(f"Could not get group name for {main_group_id}: {e}")
                        pass
                    
                    # Находим контакт для проверки уже проанализированных сообщений
                    contacts = await contact_service.get_contacts()
                    contact = None
                    if sender_id:
                        for c in contacts:
                            if c.whatsapp_id == sender_id:
                                contact = c
                                break
                    if not contact:
                        for c in contacts:
                            if c.name == sender_name or (c.whatsapp_name and c.whatsapp_name == sender_name):
                                contact = c
                                break
                    
                    # Фильтруем только новые сообщения (которые еще не были проанализированы)
                    analyzed_ids = set(contact.analyzed_message_ids or []) if contact else set()
                    new_messages = []
                    new_message_ids = []
                    
                    for msg in messages:
                        msg_id = msg.get('message_id')
                        if msg_id and msg_id not in analyzed_ids:
                            new_messages.append(msg)
                            new_message_ids.append(msg_id)
                        elif not msg_id:
                            # Если message_id отсутствует, все равно анализируем (для старых сообщений)
                            new_messages.append(msg)
                    
                    if not new_messages:
                        logger.info(f"⏭️ All messages from {sender_name} have already been analyzed. Skipping analysis.")
                        continue
                    
                    logger.info(f"📊 Filtered messages: {len(messages)} total, {len(new_messages)} new (not analyzed yet), {len(messages) - len(new_messages)} already analyzed")
                    
                    # Анализируем только новые сообщения
                    logger.info(f"Analyzing {len(new_messages)} new messages from {sender_name} (ID: {sender_id}) in group {group_name}")
                    try:
                        insight = await message_analysis_service.analyze_author_messages(
                            sender_name=sender_name,
                            group_name=group_name,
                            messages=new_messages
                        )
                    except ValueError as e:
                        error_str = str(e)
                        # Проверяем, является ли это ошибкой недостатка квоты
                        if 'превышена квота' in error_str.lower() or 'insufficient_quota' in error_str.lower() or 'exceeded your current quota' in error_str.lower():
                            logger.warning(f"⚠️ Quota exceeded for {sender_name}. Saving {len(new_messages)} messages for later analysis.")
                            # Сохраняем для отложенной обработки
                            from app.services.pending_analysis_service import pending_analysis_service
                            pending_analysis_service.add_pending_analysis(
                                sender_name=sender_name,
                                sender_id=sender_id or sender_identifier,
                                group_id=main_group_id,
                                group_name=group_name,
                                messages=new_messages
                            )
                            logger.info(f"✅ Saved {len(new_messages)} messages from {sender_name} for pending analysis")
                            continue  # Пропускаем этот анализ
                        else:
                            # Другая ошибка - пробрасываем дальше
                            raise
                    
                    if insight:
                        # Форматируем информацию для контакта
                        formatted_info = message_analysis_service.format_insight_for_contact(insight)
                        
                        # Находим или создаем контакт
                        contacts = await contact_service.get_contacts()
                        
                        # Ищем контакт по WhatsApp ID (приоритет), затем по имени
                        contact = None
                        if sender_id:
                            # Сначала ищем по WhatsApp ID
                            for c in contacts:
                                if c.whatsapp_id == sender_id:
                                    contact = c
                                    logger.info(f"✅ Found contact {c.id} ({c.name}) by WhatsApp ID {sender_id}")
                                    break
                        
                        # Если не нашли по ID, ищем по имени
                        if not contact:
                            for c in contacts:
                                if c.name == sender_name or (c.whatsapp_name and c.whatsapp_name == sender_name):
                                    contact = c
                                    logger.info(f"✅ Found contact {c.id} ({c.name}) by name {sender_name}")
                                    # Обновляем WhatsApp ID, если его не было
                                    if sender_id and not c.whatsapp_id:
                                        c.whatsapp_id = sender_id
                                        logger.info(f"Updated WhatsApp ID for contact {c.id}: {sender_id}")
                                    break
                        
                        if contact:
                            # Обновляем существующий контакт
                            # Сохраняем в draft_info (черновик), а не в extracted_info
                            if formatted_info and formatted_info.strip():
                                # Проверяем на дубликаты
                                is_duplicate = False
                                if contact.draft_info:
                                    check_parts = []
                                    if insight.role:
                                        check_parts.append(insight.role[:50])
                                    if insight.organization:
                                        check_parts.append(insight.organization[:50])
                                    if insight.description:
                                        check_parts.append(insight.description[:150])
                                    if check_parts:
                                        check_text = " ".join(check_parts).strip()
                                        if check_text and check_text in contact.draft_info:
                                            is_duplicate = True
                                
                                if not is_duplicate:
                                    if contact.draft_info:
                                        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
                                        contact.draft_info = f"{contact.draft_info}\n\n--- Обновлено {timestamp} ---\n{formatted_info}"
                                    else:
                                        contact.draft_info = formatted_info
                                    
                                    # Сохраняем ID проанализированных сообщений
                                    if not contact.analyzed_message_ids:
                                        contact.analyzed_message_ids = []
                                    for msg_id in new_message_ids:
                                        if msg_id and msg_id not in contact.analyzed_message_ids:
                                            contact.analyzed_message_ids.append(msg_id)
                                    logger.info(f"✅ Marked {len(new_message_ids)} messages as analyzed. Total analyzed: {len(contact.analyzed_message_ids)}")
                            
                            await contact_service.update_contact(contact.id, contact)
                            logger.info(f"Updated contact {contact.id} ({sender_name}) with draft_info")
                        else:
                            # Создаем новый контакт
                            # Пытаемся извлечь телефон из сообщений или используем имя как телефон
                            phone = insight.contact_info or sender_name
                            
                            # Нормализуем телефон перед созданием контакта
                            from app.utils.contact_helpers import normalize_phone
                            normalized_phone = normalize_phone(phone) if phone else ""
                            if not normalized_phone and phone:
                                # Если нормализация не удалась, используем как есть
                                normalized_phone = phone
                            
                            new_contact = Contact(
                                name=sender_name,
                                phone=normalized_phone,
                                group=insight.group_name or "Общая",
                                whatsapp_name=sender_name,
                                whatsapp_id=sender_id,  # Сохраняем WhatsApp ID
                                extracted_info="",  # Пустое для обработанной информации
                                draft_info=formatted_info  # Сохраняем в черновик
                            )
                            
                            await contact_service.save_contacts([new_contact])
                            logger.info(f"Created new contact for {sender_name} with extracted info")
                        
                        # Обновляем время последнего анализа
                        self.last_analysis_time[sender_name] = datetime.now()
                    else:
                        logger.warning(f"Could not extract insight for {sender_name}")
                        
                except Exception as e:
                    logger.error(f"Error analyzing author {sender_name}: {e}", exc_info=True)
                    continue
            
        except Exception as e:
            logger.error(f"Error in analyze_new_authors: {e}", exc_info=True)
        finally:
            self.is_running = False
    
    async def analyze_author_immediately(self, sender_name: str, sender_id: str = None, group_id: str = None, group_name: str = None):
        """
        Немедленный анализ автора после сохранения сообщения
        Запускается в фоне, не блокирует сохранение сообщения
        """
        logger.info(f"🔍 Starting immediate analysis for {sender_name} (ID: {sender_id}, group: {group_name or group_id})")
        try:
            # Проверяем, не анализировали ли мы этого автора недавно (защита от спама)
            analysis_key = sender_id or sender_name
            logger.info(f"🔑 [IMMEDIATE ANALYSIS] Analysis key: {analysis_key}")
            last_immediate = self.immediate_analysis_queue.get(analysis_key)
            if last_immediate:
                logger.info(f"⏰ [IMMEDIATE ANALYSIS] Last analysis time: {last_immediate}")
            else:
                logger.info(f"⏰ [IMMEDIATE ANALYSIS] No previous analysis found for {analysis_key}")
            if last_immediate:
                from datetime import timezone
                # Нормализуем timezone для сравнения
                if isinstance(last_immediate, datetime):
                    if last_immediate.tzinfo is None:
                        last_immediate = last_immediate.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    time_diff = now - last_immediate
                    if time_diff < timedelta(minutes=5):
                        logger.info(f"⏭️ [IMMEDIATE ANALYSIS] Skipping immediate analysis for {sender_name} - analyzed recently (within 5 minutes, {time_diff.total_seconds():.0f}s ago)")
                        return
                else:
                    logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] last_immediate is not a datetime: {type(last_immediate)}")
            
            # Помечаем время триггера
            from datetime import timezone
            self.immediate_analysis_queue[analysis_key] = datetime.now(timezone.utc)
            logger.info(f"✅ [IMMEDIATE ANALYSIS] Added to queue: {analysis_key} at {datetime.now(timezone.utc)}")
            
            # Получаем последние сообщения от этого автора
            # Увеличиваем период до 7 дней, чтобы найти все сообщения (соответствует периоду хранения)
            since = datetime.now(timezone.utc) - timedelta(days=7)  # За последние 7 дней (соответствует периоду хранения)
            logger.info(f"📥 [IMMEDIATE ANALYSIS] Fetching messages since {since} for {sender_name} (ID: {sender_id})...")
            all_messages = await whatsapp_message_service.get_messages(since=since)
            logger.info(f"📥 [IMMEDIATE ANALYSIS] Retrieved {len(all_messages)} total messages, filtering by author (sender_id: {sender_id}, sender_name: {sender_name})...")
            
            # Фильтруем сообщения по автору
            author_messages = []
            logger.debug(f"🔍 [IMMEDIATE ANALYSIS] Filtering messages: looking for sender_id={sender_id}, sender_name={sender_name}")
            for msg in all_messages:
                msg_sender_id = msg.sender_id if hasattr(msg, 'sender_id') else None
                msg_sender = msg.sender if hasattr(msg, 'sender') else None
                
                # Сопоставляем по sender_id (приоритет) или по имени
                # Также проверяем, если sender_name это sender_id (для случаев, когда нет имени)
                matched = False
                if sender_id and msg_sender_id == sender_id:
                    matched = True
                    logger.debug(f"✅ [IMMEDIATE ANALYSIS] Matched by sender_id: {msg_sender_id}")
                elif msg_sender and msg_sender == sender_name:
                    matched = True
                    logger.debug(f"✅ [IMMEDIATE ANALYSIS] Matched by sender_name: {msg_sender}")
                elif sender_name and '@c.us' in sender_name and msg_sender_id == sender_name:
                    # Если sender_name это на самом деле sender_id (для случаев без имени)
                    matched = True
                    logger.debug(f"✅ [IMMEDIATE ANALYSIS] Matched by sender_name (which is sender_id): {sender_name}")
                
                if matched:
                    # Получаем media_files если есть (новый формат)
                    media_files = None
                    if hasattr(msg, 'media_files') and msg.media_files:
                        media_files = msg.media_files
                    
                    # Получаем message_id для отслеживания проанализированных сообщений
                    msg_id = msg.message_id if hasattr(msg, 'message_id') else None
                    
                    author_messages.append({
                        'text': msg.text,
                        'date': msg.date,
                        'message_id': msg_id,  # Добавляем message_id для отслеживания
                        'media_type': msg.media_type if hasattr(msg, 'media_type') else None,
                        'media_path': msg.media_path if hasattr(msg, 'media_path') else None,
                        'media_files': media_files,  # Добавляем media_files для поддержки нового формата
                        'sender_id': msg_sender_id,
                        'sender_name': msg_sender or sender_name
                    })
            
            if len(author_messages) < 1:
                logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] Not enough messages for {sender_name} (ID: {sender_id}, found {len(author_messages)}, need at least 1)")
                logger.info(f"🔍 [IMMEDIATE ANALYSIS] Debug: total messages retrieved: {len(all_messages)}, sender_id={sender_id}, sender_name={sender_name}")
                # Логируем примеры sender_id из сообщений для отладки
                if all_messages:
                    sample_sender_ids = [getattr(m, 'sender_id', None) for m in all_messages[:5]]
                    sample_senders = [getattr(m, 'sender', None) for m in all_messages[:5]]
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Sample sender_ids from messages: {sample_sender_ids}")
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Sample senders from messages: {sample_senders}")
                else:
                    logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] No messages retrieved at all for period since {since}")
                return
            
            logger.info(f"✅ [IMMEDIATE ANALYSIS] Found {len(author_messages)} messages from {sender_name} (ID: {sender_id}) in group {group_name or group_id}")
            
            # Находим контакт для проверки уже проанализированных сообщений
            contacts = await contact_service.get_contacts()
            contact = None
            if sender_id:
                for c in contacts:
                    if c.whatsapp_id == sender_id:
                        contact = c
                        break
            if not contact:
                for c in contacts:
                    if c.name == sender_name or (c.whatsapp_name and c.whatsapp_name == sender_name):
                        contact = c
                        break
            
            # Фильтруем только новые сообщения (которые еще не были проанализированы)
            analyzed_ids = set(contact.analyzed_message_ids or []) if contact else set()
            new_messages = []
            new_message_ids = []
            
            for msg in author_messages:
                msg_id = msg.get('message_id')
                if msg_id and msg_id not in analyzed_ids:
                    new_messages.append(msg)
                    new_message_ids.append(msg_id)
                elif not msg_id:
                    # Если message_id отсутствует, все равно анализируем (для старых сообщений)
                    new_messages.append(msg)
            
            if not new_messages:
                logger.info(f"⏭️ [IMMEDIATE ANALYSIS] All messages from {sender_name} have already been analyzed. Skipping analysis.")
                return
            
            logger.info(f"📊 [IMMEDIATE ANALYSIS] Filtered messages: {len(author_messages)} total, {len(new_messages)} new (not analyzed yet), {len(author_messages) - len(new_messages)} already analyzed")
            
            # Проверяем, есть ли текстовое содержимое или медиа-файлы для анализа
            texts = [msg.get('text', '') for msg in new_messages if msg.get('text', '').strip()]
            has_media = any(
                msg.get('media_type') in ['photo', 'image'] or 
                msg.get('media_path') or 
                (msg.get('media_files') and any(mf.get('type') in ['photo', 'image'] for mf in msg.get('media_files', [])))
                for msg in new_messages
            )
            
            logger.info(f"Found {len(texts)} messages with text content for {sender_name}. Sample texts: {texts[:2] if texts else 'No texts'}")
            logger.info(f"Found {sum(1 for msg in new_messages if has_media)} messages with media files for {sender_name}")
            
            # Пропускаем анализ только если нет ни текста, ни медиа-файлов
            if not texts and not has_media:
                logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] No text or media content in new messages for {sender_name}")
                return
            
            # Анализируем только новые сообщения
            logger.info(f"Calling message_analysis_service.analyze_author_messages for {sender_name}...")
            try:
                insight = await message_analysis_service.analyze_author_messages(
                    sender_name=sender_name,
                    group_name=group_name or group_id or "Неизвестная группа",
                    messages=new_messages
                )
            except ValueError as e:
                error_str = str(e)
                # Проверяем, является ли это ошибкой недостатка квоты
                if 'превышена квота' in error_str.lower() or 'insufficient_quota' in error_str.lower() or 'exceeded your current quota' in error_str.lower():
                    logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] Quota exceeded for {sender_name}. Saving {len(new_messages)} messages for later analysis.")
                    # Сохраняем для отложенной обработки
                    from app.services.pending_analysis_service import pending_analysis_service
                    pending_analysis_service.add_pending_analysis(
                        sender_name=sender_name,
                        sender_id=sender_id or sender_name,
                        group_id=group_id or "unknown",
                        group_name=group_name or group_id or "Неизвестная группа",
                        messages=new_messages
                    )
                    logger.info(f"✅ [IMMEDIATE ANALYSIS] Saved {len(new_messages)} messages from {sender_name} for pending analysis")
                    return  # Пропускаем этот анализ
                else:
                    # Другая ошибка - пробрасываем дальше
                    raise
            
            if insight:
                logger.info(f"✅ Successfully extracted insight for {sender_name}: role={insight.role}, tournament={insight.tournament_name}, city={insight.city}")
            else:
                logger.warning(f"❌ No insight extracted for {sender_name} - message_analysis_service returned None")
            
            if insight:
                # Форматируем информацию для контакта
                formatted_info = message_analysis_service.format_insight_for_contact(insight)
                
                # Проверяем на дубликаты - не добавляем, если эта информация уже есть в черновике
                # Создаем хеш из ключевых полей для проверки дубликатов
                import hashlib
                insight_hash = hashlib.md5(
                    f"{insight.role or ''}{insight.organization or ''}{insight.description or ''}".encode('utf-8')
                ).hexdigest()
                
                # Находим или создаем контакт
                logger.info(f"🔍 [IMMEDIATE ANALYSIS] Searching for contact: name='{sender_name}', whatsapp_id='{sender_id}'")
                contacts = await contact_service.get_contacts()
                logger.info(f"📋 [IMMEDIATE ANALYSIS] Total contacts in database: {len(contacts)}")
                
                # Ищем контакт по WhatsApp ID (приоритет), затем по имени
                contact = None
                if sender_id:
                    # Сначала ищем по WhatsApp ID
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Searching by WhatsApp ID: {sender_id}")
                    for c in contacts:
                        if c.whatsapp_id == sender_id:
                            contact = c
                            logger.info(f"✅ [IMMEDIATE ANALYSIS] Found contact {c.id} ({c.name}) by WhatsApp ID {sender_id}")
                            break
                
                # Если не нашли по ID, ищем по имени
                if not contact:
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Not found by ID, searching by name: '{sender_name}'")
                    for c in contacts:
                        if c.name == sender_name or (c.whatsapp_name and c.whatsapp_name == sender_name):
                            contact = c
                            logger.info(f"✅ [IMMEDIATE ANALYSIS] Found contact {c.id} ({c.name}) by name '{sender_name}'")
                            # Обновляем WhatsApp ID, если его не было
                            if sender_id and not c.whatsapp_id:
                                c.whatsapp_id = sender_id
                                logger.info(f"📝 [IMMEDIATE ANALYSIS] Updated WhatsApp ID for contact {c.id}: {sender_id}")
                            break
                
                if not contact:
                    logger.info(f"ℹ️ [IMMEDIATE ANALYSIS] Contact not found, will create new one for {sender_name}")
                
                if contact:
                    # Обновляем существующий контакт
                    logger.info(f"📝 [IMMEDIATE ANALYSIS] Updating existing contact {contact.id} ({sender_name})")
                    logger.info(f"📝 [IMMEDIATE ANALYSIS] Current draft_info length: {len(contact.draft_info) if contact.draft_info else 0}")
                    logger.info(f"📝 [IMMEDIATE ANALYSIS] New formatted_info length: {len(formatted_info)}")
                    
                    # Обновляем whatsapp_name, если оно пустое или отличается от sender_name
                    # sender_name может содержать ник из Green API (например, "anofcfinist")
                    if sender_name and sender_name.strip() and sender_name != 'Unknown':
                        if not contact.whatsapp_name or contact.whatsapp_name != sender_name:
                            old_whatsapp_name = contact.whatsapp_name
                            contact.whatsapp_name = sender_name
                            logger.info(f"📝 [IMMEDIATE ANALYSIS] Updated whatsapp_name: '{old_whatsapp_name}' -> '{sender_name}'")
                        # Также обновляем основное имя, если оно пустое или равно номеру телефона
                        if not contact.name or contact.name == contact.phone or (contact.phone and contact.name in contact.phone):
                            if sender_name and sender_name.strip() and sender_name != 'Unknown':
                                contact.name = sender_name
                                logger.info(f"📝 [IMMEDIATE ANALYSIS] Updated name: '{contact.name}' -> '{sender_name}'")
                    
                    # Обновляем email, если он обнаружен в анализе
                    if insight.email and insight.email.strip():
                        # Проверяем, что email валидный (простая проверка)
                        import re
                        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
                        if re.match(email_pattern, insight.email.strip()):
                            # Обновляем email только если он пустой или отличается
                            if not contact.whatsapp_email or contact.whatsapp_email != insight.email.strip():
                                old_email = contact.whatsapp_email
                                contact.whatsapp_email = insight.email.strip()
                                logger.info(f"📧 [IMMEDIATE ANALYSIS] Updated email: '{old_email}' -> '{contact.whatsapp_email}'")
                        else:
                            logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] Invalid email format detected: '{insight.email}', skipping")
                    
                    # Сохраняем информацию в draft_info (черновик)
                    # extracted_info остается для обработанной информации, которую пользователь редактирует вручную
                    from datetime import timezone
                    if formatted_info and formatted_info.strip():
                        # Проверяем на дубликаты - не добавляем, если эта информация уже есть в черновике
                        # Используем более умную проверку - сравниваем ключевые части
                        is_duplicate = False
                        if contact.draft_info:
                            # Проверяем, не содержится ли уже эта информация в черновике
                            # Берем ключевые части formatted_info для проверки (роль, организация, описание)
                            check_parts = []
                            if insight.role:
                                check_parts.append(insight.role[:50])
                            if insight.organization:
                                check_parts.append(insight.organization[:50])
                            if insight.description:
                                # Берем первые 150 символов описания
                                desc = insight.description[:150]
                                check_parts.append(desc)
                            
                            if check_parts:
                                # Создаем проверочную строку из ключевых частей
                                check_text = " ".join(check_parts).strip()
                                # Проверяем, есть ли эта информация в черновике
                                if check_text and check_text in contact.draft_info:
                                    logger.info(f"⏭️ [IMMEDIATE ANALYSIS] Skipping duplicate information (already in draft_info): {check_text[:50]}...")
                                    is_duplicate = True
                                else:
                                    # Дополнительная проверка - сравниваем первые 300 символов formatted_info
                                    formatted_start = formatted_info[:300].strip()
                                    if formatted_start in contact.draft_info:
                                        logger.info(f"⏭️ [IMMEDIATE ANALYSIS] Skipping duplicate (formatted_info start matches)")
                                        is_duplicate = True
                        
                        if not is_duplicate:
                            if contact.draft_info:
                                # Добавляем новую информацию к существующему черновику с разделителем
                                timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
                                contact.draft_info = f"{contact.draft_info}\n\n--- Обновлено {timestamp} ---\n{formatted_info}"
                                logger.info(f"📝 [IMMEDIATE ANALYSIS] Added new information to existing draft_info")
                            else:
                                # Если черновика нет, создаем новый
                                contact.draft_info = formatted_info
                                logger.info(f"📝 [IMMEDIATE ANALYSIS] Set draft_info (no previous draft)")
                            
                            # Сохраняем ID проанализированных сообщений
                            if not contact.analyzed_message_ids:
                                contact.analyzed_message_ids = []
                            # Добавляем новые message_id в список проанализированных
                            for msg_id in new_message_ids:
                                if msg_id and msg_id not in contact.analyzed_message_ids:
                                    contact.analyzed_message_ids.append(msg_id)
                            logger.info(f"✅ [IMMEDIATE ANALYSIS] Marked {len(new_message_ids)} messages as analyzed. Total analyzed: {len(contact.analyzed_message_ids)}")
                        else:
                            logger.info(f"⏭️ [IMMEDIATE ANALYSIS] Information already exists in draft, skipping")
                            # Даже если информация дубликат, помечаем сообщения как проанализированные
                            if not contact.analyzed_message_ids:
                                contact.analyzed_message_ids = []
                            for msg_id in new_message_ids:
                                if msg_id and msg_id not in contact.analyzed_message_ids:
                                    contact.analyzed_message_ids.append(msg_id)
                            logger.info(f"✅ [IMMEDIATE ANALYSIS] Marked {len(new_message_ids)} messages as analyzed (duplicate info, but messages processed). Total analyzed: {len(contact.analyzed_message_ids)}")
                    else:
                        logger.warning(f"⚠️ [IMMEDIATE ANALYSIS] New formatted_info is empty, keeping existing info")
                        # Даже если formatted_info пустой, помечаем сообщения как проанализированные
                        if not contact.analyzed_message_ids:
                            contact.analyzed_message_ids = []
                        for msg_id in new_message_ids:
                            if msg_id and msg_id not in contact.analyzed_message_ids:
                                contact.analyzed_message_ids.append(msg_id)
                        logger.info(f"✅ [IMMEDIATE ANALYSIS] Marked {len(new_message_ids)} messages as analyzed (empty info, but messages processed). Total analyzed: {len(contact.analyzed_message_ids)}")
                    
                    # КРИТИЧЕСКИ ВАЖНО: Создаем копию контакта с явно указанными полями для обновления
                    # Это предотвращает случайное перезаписывание полей других контактов
                    import copy
                    contact_to_update = copy.deepcopy(contact)
                    
                    # Явно устанавливаем extracted_info и draft_info, чтобы они точно обновились
                    # Если extracted_info не должен обновляться, оставляем его как есть в оригинальном контакте
                    # НО: мы обновляем только draft_info, extracted_info НЕ трогаем при анализе
                    # extracted_info обновляется только вручную пользователем
                    
                    logger.info(f"💾 [IMMEDIATE ANALYSIS] Saving updated contact {contact.id} ({sender_name}) with draft_info...")
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Contact ID: {contact.id}, WhatsApp ID: {contact.whatsapp_id}")
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Contact.draft_info before save: length={len(contact.draft_info) if contact.draft_info else 0}")
                    logger.info(f"🔍 [IMMEDIATE ANALYSIS] Contact.extracted_info before save: length={len(contact.extracted_info) if contact.extracted_info else 0}")
                    
                    # ВАЖНО: При обновлении НЕ передаем extracted_info, если мы его не меняли
                    # Это предотвращает случайное перезаписывание extracted_info других контактов
                    # Устанавливаем extracted_info в None, чтобы он НЕ обновлялся
                    contact_to_update.extracted_info = None  # НЕ обновляем extracted_info при анализе
                    
                    # Убеждаемся, что ID правильный
                    if contact_to_update.id != contact.id:
                        logger.error(f"❌ CRITICAL: Contact ID mismatch! contact.id={contact.id}, contact_to_update.id={contact_to_update.id}")
                        raise ValueError(f"Contact ID mismatch: {contact.id} != {contact_to_update.id}")
                    
                    await contact_service.update_contact(contact.id, contact_to_update)
                    logger.info(f"✅ [IMMEDIATE ANALYSIS] Successfully updated contact {contact.id} ({sender_name}) with draft_info")
                    
                    # Проверяем, что информация действительно сохранилась
                    verify_contacts = await contact_service.get_contacts()
                    verify_contact = next((c for c in verify_contacts if c.id == contact.id), None)
                    if verify_contact:
                        verify_draft_length = len(verify_contact.draft_info) if verify_contact.draft_info else 0
                        logger.info(f"✅ [IMMEDIATE ANALYSIS] Verified: contact {contact.id} draft_info length after save: {verify_draft_length}")
                        if verify_draft_length == 0 and contact.draft_info:
                            logger.error(f"❌ [IMMEDIATE ANALYSIS] ERROR: draft_info was NOT saved! Expected {len(contact.draft_info)} chars, got 0")
                    
                    # Проверяем, что информация действительно сохранилась
                    verify_contacts = await contact_service.get_contacts()
                    verify_contact = next((c for c in verify_contacts if c.id == contact.id), None)
                    if verify_contact:
                        verify_length = len(verify_contact.extracted_info) if verify_contact.extracted_info else 0
                        logger.info(f"✅ [IMMEDIATE ANALYSIS] Verified: contact {contact.id} extracted_info length after save: {verify_length}")
                        if verify_length == 0 and contact.extracted_info:
                            logger.error(f"❌ [IMMEDIATE ANALYSIS] ERROR: extracted_info was NOT saved! Expected {len(contact.extracted_info)} chars, got 0")
                    else:
                        logger.error(f"❌ [IMMEDIATE ANALYSIS] ERROR: Could not verify contact {contact.id} after save")
                else:
                    # Создаем новый контакт
                    phone = insight.contact_info or sender_name
                    
                    # Нормализуем телефон перед созданием контакта
                    from app.utils.contact_helpers import normalize_phone
                    normalized_phone = normalize_phone(phone) if phone else ""
                    if not normalized_phone and phone:
                        normalized_phone = phone
                    
                    # Извлекаем email из insight, если он есть
                    contact_email = None
                    if insight.email and insight.email.strip():
                        import re
                        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
                        if re.match(email_pattern, insight.email.strip()):
                            contact_email = insight.email.strip()
                            logger.info(f"📧 [IMMEDIATE ANALYSIS] Setting email for new contact: '{contact_email}'")
                    
                    new_contact = Contact(
                        name=sender_name,
                        phone=normalized_phone,
                        group=insight.group_name or "Общая",
                        whatsapp_name=sender_name,
                        whatsapp_id=sender_id,
                        whatsapp_email=contact_email,  # Email, если обнаружен
                        extracted_info="",  # Пустое для обработанной информации
                        draft_info=formatted_info  # Сохраняем в черновик
                    )
                    
                    logger.info(f"💾 [IMMEDIATE ANALYSIS] Creating new contact for {sender_name}...")
                    await contact_service.save_contacts([new_contact])
                    logger.info(f"✅ [IMMEDIATE ANALYSIS] Successfully created new contact for {sender_name} with extracted info")
                
                # Обновляем время последнего анализа
                self.last_analysis_time[analysis_key] = datetime.now()
            else:
                logger.warning(f"Could not extract insight for {sender_name} (immediate analysis)")
                
        except Exception as e:
            logger.error(f"❌ [IMMEDIATE ANALYSIS] Error in immediate author analysis for {sender_name} (ID: {sender_id}): {e}", exc_info=True)
    
    async def process_pending_analyses(self):
        """
        Обрабатывает отложенные анализы (когда квота была исчерпана)
        Вызывается периодически для проверки и обработки накопленных анализов
        """
        from app.services.pending_analysis_service import pending_analysis_service
        from app.services.quota_manager import quota_manager
        from datetime import timezone
        
        # Сбрасываем счетчик OCR в начале прогона
        quota_manager.reset_ocr_call_count()
        
        pending_list = pending_analysis_service.get_pending_analyses()
        if not pending_list:
            return
        
        logger.info(f"🔄 Processing {len(pending_list)} pending analyses...")
        
        processed_count = 0
        failed_count = 0
        
        for pending in pending_list:
            try:
                logger.info(f"📋 Processing pending analysis for {pending.sender_name} ({pending.sender_id}) in group {pending.group_name}")
                
                # Пытаемся проанализировать
                insight = await message_analysis_service.analyze_author_messages(
                    sender_name=pending.sender_name,
                    group_name=pending.group_name,
                    messages=pending.messages
                )
                
                if insight:
                    # Успешно проанализировано - обновляем контакт
                    formatted_info = message_analysis_service.format_insight_for_contact(insight)
                    
                    # Находим или создаем контакт (аналогично analyze_author_immediately)
                    contacts = await contact_service.get_contacts()
                    contact = None
                    
                    if pending.sender_id:
                        for c in contacts:
                            if c.whatsapp_id == pending.sender_id:
                                contact = c
                                break
                    
                    if not contact:
                        for c in contacts:
                            if c.name == pending.sender_name or (c.whatsapp_name and c.whatsapp_name == pending.sender_name):
                                contact = c
                                if pending.sender_id and not c.whatsapp_id:
                                    c.whatsapp_id = pending.sender_id
                                break
                    
                    if contact:
                        # Обновляем существующий контакт
                        if formatted_info and formatted_info.strip():
                            if contact.draft_info:
                                timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
                                contact.draft_info = f"{contact.draft_info}\n\n--- Обновлено {timestamp} ---\n{formatted_info}"
                            else:
                                contact.draft_info = formatted_info
                            
                            # Сохраняем ID проанализированных сообщений
                            if not contact.analyzed_message_ids:
                                contact.analyzed_message_ids = []
                            for msg in pending.messages:
                                msg_id = msg.get('message_id')
                                if msg_id and msg_id not in contact.analyzed_message_ids:
                                    contact.analyzed_message_ids.append(msg_id)
                            
                            await contact_service.update_contact(contact.id, contact)
                            logger.info(f"✅ Updated contact {contact.id} ({pending.sender_name}) from pending analysis")
                    else:
                        # Создаем новый контакт
                        from app.utils.contact_helpers import normalize_phone
                        phone = insight.contact_info or pending.sender_name
                        normalized_phone = normalize_phone(phone) if phone else ""
                        if not normalized_phone and phone:
                            normalized_phone = phone
                        
                        new_contact = Contact(
                            name=pending.sender_name,
                            phone=normalized_phone,
                            group=insight.group_name or "Общая",
                            whatsapp_name=pending.sender_name,
                            whatsapp_id=pending.sender_id,
                            extracted_info="",
                            draft_info=formatted_info
                        )
                        
                        await contact_service.save_contacts([new_contact])
                        logger.info(f"✅ Created new contact for {pending.sender_name} from pending analysis")
                    
                    # Удаляем из отложенных после успешной обработки
                    pending_analysis_service.remove_pending_analysis(pending.sender_id, pending.group_id)
                    pending_analysis_service.mark_attempt(pending.sender_id, pending.group_id, success=True)
                    processed_count += 1
                    logger.info(f"✅ Successfully processed pending analysis for {pending.sender_name}")
                else:
                    # Не удалось извлечь инсайт - оставляем в отложенных
                    pending_analysis_service.mark_attempt(pending.sender_id, pending.group_id, success=False)
                    failed_count += 1
                    logger.warning(f"⚠️ Could not extract insight for {pending.sender_name}, keeping in pending")
                    
            except ValueError as e:
                error_str = str(e)
                # Проверяем, является ли это ошибкой недостатка квоты
                if 'превышена квота' in error_str.lower() or 'insufficient_quota' in error_str.lower() or 'exceeded your current quota' in error_str.lower():
                    # Квота все еще исчерпана - оставляем в отложенных
                    pending_analysis_service.mark_attempt(pending.sender_id, pending.group_id, success=False)
                    logger.warning(f"⚠️ Quota still exceeded for {pending.sender_name}, keeping in pending")
                    failed_count += 1
                else:
                    # Другая ошибка
                    pending_analysis_service.mark_attempt(pending.sender_id, pending.group_id, success=False)
                    logger.error(f"❌ Error processing pending analysis for {pending.sender_name}: {e}", exc_info=True)
                    failed_count += 1
            except Exception as e:
                pending_analysis_service.mark_attempt(pending.sender_id, pending.group_id, success=False)
                logger.error(f"❌ Error processing pending analysis for {pending.sender_name}: {e}", exc_info=True)
                failed_count += 1
        
        logger.info(f"✅ Processed pending analyses: {processed_count} successful, {failed_count} failed/kept pending")

author_analysis_service = AuthorAnalysisService()

