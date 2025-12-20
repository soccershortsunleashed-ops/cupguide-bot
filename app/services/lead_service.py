"""
Lead Service - сервис для работы с лидами фриланс-воронки
"""
import json
import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

import aiofiles

from app.core.config import settings
from app.models.lead import (
    Lead, LeadEvent, LeadConversation, LeadApplication,
    LeadStatus, LeadGrade, LeadRoute
)
from app.models.contact import Contact

logger = logging.getLogger(__name__)

# Группа для фриланс-контактов
FREELANCE_CONTACT_GROUP = "Фриланс"


class LeadService:
    """Сервис для работы с лидами"""
    
    def __init__(self):
        self.leads_file = os.path.join(settings.DATA_DIR, "leads.json")
        self.events_file = os.path.join(settings.DATA_DIR, "lead_events.json")
        self.conversations_file = os.path.join(settings.DATA_DIR, "lead_conversations.json")
        self.applications_file = os.path.join(settings.DATA_DIR, "lead_applications.json")
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Создаёт файлы если не существуют"""
        os.makedirs(os.path.dirname(self.leads_file), exist_ok=True)
        
        for file_path in [self.leads_file, self.events_file, 
                          self.conversations_file, self.applications_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([], f)
    
    # ============================================================
    # LEADS CRUD
    # ============================================================
    
    async def get_leads(self, 
                        status: Optional[str] = None,
                        grade: Optional[str] = None,
                        route: Optional[str] = None,
                        limit: int = 100) -> List[Lead]:
        """Получает список лидов с фильтрацией"""
        async with aiofiles.open(self.leads_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            
            data = json.loads(content)
            leads = [Lead(**item) for item in data]
        
        # Фильтрация
        if status:
            leads = [l for l in leads if l.status == status]
        if grade:
            leads = [l for l in leads if l.llm_grade == grade]
        if route:
            leads = [l for l in leads if l.final_route == route]
        
        # Сортировка по дате (новые первые)
        leads.sort(key=lambda x: x.created_at, reverse=True)
        
        return leads[:limit]
    
    async def get_lead_by_id(self, lead_id: int) -> Optional[Lead]:
        """Получает лида по ID"""
        leads = await self.get_leads(limit=10000)
        for lead in leads:
            if lead.id == lead_id:
                return lead
        return None
    
    async def get_lead_by_telegram_id(self, telegram_user_id: int) -> Optional[Lead]:
        """Получает лида по Telegram user ID"""
        leads = await self.get_leads(limit=10000)
        for lead in leads:
            if lead.telegram_user_id == telegram_user_id:
                return lead
        return None
    
    async def create_lead(self, lead_data: Dict[str, Any]) -> Lead:
        """Создаёт нового лида"""
        leads = await self.get_leads(limit=10000)
        
        # Генерируем ID
        next_id = max([l.id for l in leads if l.id], default=0) + 1
        
        # Проверяем дубликат по telegram_user_id
        telegram_user_id = lead_data.get("telegram_user_id")
        if telegram_user_id:
            existing = await self.get_lead_by_telegram_id(telegram_user_id)
            if existing:
                logger.info(f"Lead already exists for telegram_user_id={telegram_user_id}, updating...")
                return await self.update_lead(existing.id, lead_data)
        
        # Создаём лида
        lead = Lead(
            id=next_id,
            **lead_data
        )
        
        leads.append(lead)
        await self._save_leads(leads)
        
        logger.info(f"✅ Created lead {lead.id} for telegram_user_id={telegram_user_id}")
        
        # Логируем событие
        await self.log_event(lead.id, "lead_created", lead_data)
        
        # Создаём контакт в группе "Фриланс"
        contact_id = await self._create_freelance_contact(lead, lead_data)
        if contact_id:
            lead.contact_id = contact_id
            await self._save_leads(leads)
            logger.info(f"✅ Linked lead {lead.id} to contact {contact_id}")
        
        return lead
    
    async def _create_freelance_contact(self, lead: Lead, lead_data: Dict[str, Any]) -> Optional[int]:
        """Создаёт контакт в группе Фриланс для лида"""
        try:
            from app.services.contact_service import contact_service
            
            # Формируем имя контакта
            first_name = lead_data.get("first_name", "")
            last_name = lead_data.get("last_name", "")
            name = f"{first_name} {last_name}".strip()
            if not name:
                name = lead_data.get("username") or f"Lead #{lead.id}"
            
            # Получаем телефон
            phone = lead_data.get("contact_preferred", "")
            if not phone:
                # Если телефона нет, используем telegram username
                username = lead_data.get("username")
                if username:
                    phone = f"@{username}"
                else:
                    phone = f"tg:{lead_data.get('telegram_user_id', 'unknown')}"
            
            # Проверяем, нет ли уже такого контакта
            contacts = await contact_service.get_contacts()
            
            # Ищем по telegram_user_id
            telegram_user_id = lead_data.get("telegram_user_id")
            for c in contacts:
                if c.telegram_user_id == telegram_user_id:
                    logger.info(f"📋 Contact already exists for telegram_user_id={telegram_user_id}: {c.id}")
                    # Обновляем группу на Фриланс если нужно
                    if c.group != FREELANCE_CONTACT_GROUP:
                        c.group = FREELANCE_CONTACT_GROUP
                        await contact_service.update_contact(c.id, c)
                        logger.info(f"📋 Moved contact {c.id} to group '{FREELANCE_CONTACT_GROUP}'")
                    return c.id
            
            # Ищем по телефону (если это телефон, а не username)
            if phone and not phone.startswith("@") and not phone.startswith("tg:"):
                from app.utils.contact_helpers import normalize_phone
                normalized = normalize_phone(phone)
                for c in contacts:
                    if c.phone and normalize_phone(c.phone) == normalized:
                        logger.info(f"📋 Contact already exists with phone {phone}: {c.id}")
                        # Обновляем группу на Фриланс если нужно
                        if c.group != FREELANCE_CONTACT_GROUP:
                            c.group = FREELANCE_CONTACT_GROUP
                            await contact_service.update_contact(c.id, c)
                            logger.info(f"📋 Moved contact {c.id} to group '{FREELANCE_CONTACT_GROUP}'")
                        return c.id
            
            # Формируем extracted_info с данными лида
            extracted_parts = []
            if lead_data.get("niche_text"):
                extracted_parts.append(f"📝 Ниша: {lead_data['niche_text']}")
            if lead_data.get("goal"):
                goal_labels = {"sales": "Продажи", "leads": "Лиды/база", "automate": "Автоматизация"}
                extracted_parts.append(f"🎯 Цель: {goal_labels.get(lead_data['goal'], lead_data['goal'])}")
            if lead_data.get("llm_grade"):
                extracted_parts.append(f"📊 Грейд: {lead_data['llm_grade']} ({lead_data.get('llm_score', '?')}/100)")
            if lead_data.get("final_route"):
                route_labels = {"A_FLOW": "A (взрослый лид)", "B_FLOW": "B (прототип)", "TRASH_FLOW": "TRASH"}
                extracted_parts.append(f"🚦 Маршрут: {route_labels.get(lead_data['final_route'], lead_data['final_route'])}")
            if lead_data.get("bot_platform"):
                extracted_parts.append(f"📱 Платформа: {lead_data['bot_platform']}")
            if lead_data.get("start_window"):
                extracted_parts.append(f"📅 Старт: {lead_data['start_window']}")
            
            extracted_info = "\n".join(extracted_parts) if extracted_parts else None
            
            # Создаём новый контакт
            new_contact = Contact(
                name=name,
                phone=phone,
                group=FREELANCE_CONTACT_GROUP,
                telegram_user_id=telegram_user_id,
                telegram_username=lead_data.get("username"),
                extracted_info=extracted_info
            )
            
            await contact_service.save_contacts([new_contact])
            
            # Получаем ID созданного контакта
            contacts = await contact_service.get_contacts()
            for c in contacts:
                if c.telegram_user_id == telegram_user_id:
                    logger.info(f"✅ Created freelance contact {c.id} ({name}) in group '{FREELANCE_CONTACT_GROUP}'")
                    return c.id
            
            logger.warning(f"⚠️ Contact created but could not find it by telegram_user_id={telegram_user_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creating freelance contact: {e}", exc_info=True)
            return None
    
    async def update_lead(self, lead_id: int, update_data: Dict[str, Any]) -> Optional[Lead]:
        """Обновляет лида"""
        leads = await self.get_leads(limit=10000)
        
        for i, lead in enumerate(leads):
            if lead.id == lead_id:
                # Обновляем поля
                for key, value in update_data.items():
                    if hasattr(lead, key) and value is not None:
                        setattr(lead, key, value)
                
                lead.updated_at = datetime.now()
                leads[i] = lead
                
                await self._save_leads(leads)
                logger.info(f"✅ Updated lead {lead_id}")
                
                return lead
        
        return None
    
    async def update_lead_status(self, lead_id: int, status: str, notes: Optional[str] = None) -> Optional[Lead]:
        """Обновляет статус лида"""
        update_data = {"status": status}
        if notes:
            update_data["notes"] = notes
        
        lead = await self.update_lead(lead_id, update_data)
        
        if lead:
            await self.log_event(lead_id, "status_changed", {
                "new_status": status,
                "notes": notes
            })
        
        return lead
    
    async def _save_leads(self, leads: List[Lead]):
        """Сохраняет лидов в файл"""
        data = [l.model_dump() for l in leads]
        async with aiofiles.open(self.leads_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    
    # ============================================================
    # EVENTS
    # ============================================================
    
    async def log_event(self, lead_id: int, event_type: str, payload: Optional[Dict] = None) -> LeadEvent:
        """Логирует событие лида"""
        async with aiofiles.open(self.events_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            events = json.loads(content) if content.strip() else []
        
        next_id = max([e.get("id", 0) for e in events], default=0) + 1
        
        event = LeadEvent(
            id=next_id,
            lead_id=lead_id,
            event_type=event_type,
            payload=payload
        )
        
        events.append(event.model_dump())
        
        async with aiofiles.open(self.events_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(events, ensure_ascii=False, indent=2, default=str))
        
        logger.debug(f"📝 Event logged: {event_type} for lead {lead_id}")
        
        return event
    
    async def get_lead_events(self, lead_id: int) -> List[LeadEvent]:
        """Получает события лида"""
        async with aiofiles.open(self.events_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            
            events = json.loads(content)
            return [LeadEvent(**e) for e in events if e.get("lead_id") == lead_id]
    
    # ============================================================
    # CONVERSATIONS
    # ============================================================
    
    async def log_message(self, lead_id: int, direction: str, text: str, 
                          message_id: Optional[int] = None,
                          button_data: Optional[str] = None) -> LeadConversation:
        """Логирует сообщение в диалоге"""
        async with aiofiles.open(self.conversations_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            conversations = json.loads(content) if content.strip() else []
        
        next_id = max([c.get("id", 0) for c in conversations], default=0) + 1
        
        conv = LeadConversation(
            id=next_id,
            lead_id=lead_id,
            message_id=message_id,
            direction=direction,
            text=text,
            button_data=button_data
        )
        
        conversations.append(conv.model_dump())
        
        async with aiofiles.open(self.conversations_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(conversations, ensure_ascii=False, indent=2, default=str))
        
        return conv
    
    async def get_lead_conversation(self, lead_id: int) -> List[LeadConversation]:
        """Получает историю диалога с лидом"""
        async with aiofiles.open(self.conversations_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            
            conversations = json.loads(content)
            return [LeadConversation(**c) for c in conversations if c.get("lead_id") == lead_id]
    
    # ============================================================
    # APPLICATIONS
    # ============================================================
    
    async def create_application(self, lead_id: int, app_data: Dict[str, Any]) -> LeadApplication:
        """Создаёт заявку от лида"""
        async with aiofiles.open(self.applications_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            applications = json.loads(content) if content.strip() else []
        
        next_id = max([a.get("id", 0) for a in applications], default=0) + 1
        
        application = LeadApplication(
            id=next_id,
            lead_id=lead_id,
            **app_data
        )
        
        applications.append(application.model_dump())
        
        async with aiofiles.open(self.applications_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(applications, ensure_ascii=False, indent=2, default=str))
        
        logger.info(f"✅ Created application {application.id} for lead {lead_id}")
        
        # Логируем событие
        await self.log_event(lead_id, "application_submitted", app_data)
        
        return application
    
    async def get_applications(self, status: Optional[str] = None) -> List[LeadApplication]:
        """Получает список заявок"""
        async with aiofiles.open(self.applications_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            if not content.strip():
                return []
            
            applications = json.loads(content)
            result = [LeadApplication(**a) for a in applications]
        
        if status:
            result = [a for a in result if a.status == status]
        
        return result
    
    # ============================================================
    # ANALYTICS
    # ============================================================
    
    async def get_funnel_stats(self) -> Dict[str, Any]:
        """Получает статистику воронки"""
        leads = await self.get_leads(limit=10000)
        
        total = len(leads)
        if total == 0:
            return {
                "total": 0,
                "by_grade": {},
                "by_route": {},
                "by_status": {},
                "applications_count": 0,
                "conversion_rate": 0
            }
        
        # По грейдам
        by_grade = {}
        for lead in leads:
            grade = lead.llm_grade or "unknown"
            by_grade[grade] = by_grade.get(grade, 0) + 1
        
        # По маршрутам
        by_route = {}
        for lead in leads:
            route = lead.final_route or "unknown"
            by_route[route] = by_route.get(route, 0) + 1
        
        # По статусам
        by_status = {}
        for lead in leads:
            status = lead.status
            by_status[status] = by_status.get(status, 0) + 1
        
        # Конверсия (заявки / всего)
        applications = await self.get_applications()
        conversion_rate = len(applications) / total * 100 if total > 0 else 0
        
        return {
            "total": total,
            "by_grade": by_grade,
            "by_route": by_route,
            "by_status": by_status,
            "applications_count": len(applications),
            "conversion_rate": round(conversion_rate, 2)
        }


# Singleton instance
lead_service = LeadService()
