import logging
import asyncio
import json
import os
from typing import Optional, Dict, Set
from app.services.green_api_service import green_api_service
from app.services.contact_service import contact_service
from app.models.contact import Contact
from app.core.config import settings
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Файл для сохранения прогресса
CHECKPOINT_FILE = os.path.join(settings.DATA_DIR, "enrichment_checkpoint.json")


class ContactEnrichmentService:
    """Service for enriching contacts with WhatsApp profile data"""
    
    def __init__(self):
        self._enrichment_status = {
            "is_running": False,
            "total": 0,
            "processed": 0,
            "updated": 0,
            "failed": 0,
            "current_contact": None,
            "errors": []
        }
        self._processed_ids: Set[int] = set()
        self._load_checkpoint()
    
    def _load_checkpoint(self):
        """Загружает checkpoint с обработанными контактами"""
        try:
            if os.path.exists(CHECKPOINT_FILE):
                with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._processed_ids = set(data.get("processed_ids", []))
                    logger.info(f"📂 Загружен checkpoint: {len(self._processed_ids)} обработанных контактов")
        except Exception as e:
            logger.error(f"Ошибка загрузки checkpoint: {e}")
            self._processed_ids = set()
    
    def _save_checkpoint(self):
        """Сохраняет checkpoint"""
        try:
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "processed_ids": list(self._processed_ids),
                    "last_update": str(asyncio.get_event_loop().time()) if asyncio.get_event_loop().is_running() else None
                }, f)
        except Exception as e:
            logger.error(f"Ошибка сохранения checkpoint: {e}")
    
    def clear_checkpoint(self):
        """Очищает checkpoint для начала с нуля"""
        self._processed_ids = set()
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
            logger.info("🗑️ Checkpoint очищен")
    
    async def enrich_contact(self, contact_id: int) -> Contact:
        """
        Enrich a single contact with WhatsApp profile data (avatar and name).
        
        Args:
            contact_id: The ID of the contact to enrich
            
        Returns:
            Updated Contact object
        """
        contacts = await contact_service.get_contacts()
        contact = next((c for c in contacts if c.id == contact_id), None)
        
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        try:
            # Check if phone is registered on WhatsApp
            whatsapp_check = await green_api_service.check_whatsapp(contact.phone)
            contact.whatsapp_is_registered = whatsapp_check.get("exists", False)
            logger.info(f"Contact {contact.name} WhatsApp registration status: {contact.whatsapp_is_registered}")
            
            # Get WhatsApp info
            info = await green_api_service.get_contact_info(contact.phone)
            
            if info.get("exists"):
                # Update WhatsApp ID if available
                if info.get("whatsapp_id"):
                    contact.whatsapp_id = info["whatsapp_id"]
                    logger.info(f"Updated WhatsApp ID for {contact.name}: {info['whatsapp_id']}")
                
                # Получаем возможное имя из WhatsApp
                whatsapp_name = info.get("name")
                
                # Update WhatsApp name if available
                if whatsapp_name and whatsapp_name != contact.phone:
                    contact.whatsapp_name = whatsapp_name
                    logger.info(f"Updated WhatsApp name for {contact.name}: {whatsapp_name}")
                
                # Заменяем основное имя, если оно пустое или равно номеру телефона
                if whatsapp_name and whatsapp_name != contact.phone:
                    from app.utils.contact_helpers import normalize_phone
                    
                    # Нормализуем телефон для сравнения
                    normalized_phone = normalize_phone(contact.phone)
                    normalized_name = normalize_phone(contact.name) if contact.name else ""
                    
                    # Проверяем, является ли имя пустым или номером телефона
                    is_name_empty = not contact.name or not contact.name.strip()
                    is_name_phone = (normalized_name == normalized_phone) or (contact.name == contact.phone)
                    
                    if is_name_empty or is_name_phone:
                        old_name = contact.name or "(пусто)"
                        contact.name = whatsapp_name
                        logger.info(f"✅ Заменено имя контакта {contact.id}: '{old_name}' -> '{whatsapp_name}' (было пустое или номер телефона)")
                
                # Update additional fields
                if info.get("email"):
                    contact.whatsapp_email = info["email"]
                if info.get("category"):
                    contact.whatsapp_category = info["category"]
                if info.get("description"):
                    contact.whatsapp_description = info["description"]
                if info.get("isBusiness") is not None:
                    contact.whatsapp_is_business = info["isBusiness"]
                if info.get("lastSeen"):
                    contact.whatsapp_last_seen = info["lastSeen"]
                if info.get("products"):
                    contact.whatsapp_products = info["products"]
                
                # Download and save avatar
                avatar_path = await green_api_service.get_avatar(contact.phone)
                if avatar_path:
                    contact.avatar_url = avatar_path
                    logger.info(f"Downloaded avatar for {contact.name}")
            else:
                logger.warning(f"Contact {contact.phone} not found in WhatsApp")
            
            # Update contact in database
            await contact_service.update_contact(contact_id, contact)
            return contact
            
        except Exception as e:
            logger.error(f"Error enriching contact {contact_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to enrich contact: {str(e)}")

    async def enrich_all_contacts(self, reset: bool = False) -> Dict:
        """
        Enrich all contacts with WhatsApp profile data.
        Runs in background and updates status.
        Continues from last checkpoint unless reset=True.
        
        Args:
            reset: If True, start from beginning ignoring checkpoint
        
        Returns:
            Dictionary with job ID and initial status
        """
        if reset:
            self.clear_checkpoint()
        
        # Запускаем в фоне
        asyncio.create_task(self._enrich_all_contacts_background())
        
        skipped = len(self._processed_ids)
        return {
            "status": "started",
            "message": f"Обновление запущено. Пропущено ранее обработанных: {skipped}"
        }
    
    async def _enrich_all_contacts_background(self):
        """Background task to enrich all contacts"""
        try:
            contacts = await contact_service.get_contacts()
            
            # Фильтруем уже обработанные
            pending_contacts = [c for c in contacts if c.id not in self._processed_ids]
            already_processed = len(contacts) - len(pending_contacts)
            
            logger.info(f"📊 Всего контактов: {len(contacts)}, уже обработано: {already_processed}, осталось: {len(pending_contacts)}")
            
            # Инициализируем статус
            self._enrichment_status = {
                "is_running": True,
                "total": len(contacts),
                "processed": already_processed,
                "updated": 0,
                "failed": 0,
                "current_contact": None,
                "errors": [],
                "skipped": already_processed
            }
            
            for idx, contact in enumerate(pending_contacts, start=1):
                self._enrichment_status["current_contact"] = contact.name or contact.phone
                
                try:
                    await self.enrich_contact(contact.id)
                    self._enrichment_status["updated"] += 1
                    
                    # Добавляем в обработанные и сохраняем checkpoint
                    self._processed_ids.add(contact.id)
                    
                    # Сохраняем checkpoint каждые 10 контактов
                    if idx % 10 == 0:
                        self._save_checkpoint()
                        
                except HTTPException as e:
                    self._enrichment_status["failed"] += 1
                    error_msg = f"{contact.name} ({contact.phone}): {e.detail}"
                    self._enrichment_status["errors"].append(error_msg)
                    logger.error(f"Failed to enrich {contact.name}: {e.detail}")
                    # Всё равно помечаем как обработанный чтобы не застрять
                    self._processed_ids.add(contact.id)
                except Exception as e:
                    self._enrichment_status["failed"] += 1
                    error_msg = f"{contact.name} ({contact.phone}): {str(e)}"
                    self._enrichment_status["errors"].append(error_msg)
                    logger.error(f"Failed to enrich {contact.name}: {str(e)}")
                    self._processed_ids.add(contact.id)
                finally:
                    # Обновляем счетчик обработанных
                    self._enrichment_status["processed"] = already_processed + idx
            
            # Финальное сохранение checkpoint
            self._save_checkpoint()
            
            # Финальный статус
            self._enrichment_status["current_contact"] = None
            self._enrichment_status["is_running"] = False
            logger.info(f"✅ Обновление завершено: {self._enrichment_status['updated']} обновлено, {self._enrichment_status['failed']} ошибок")
            
        except Exception as e:
            logger.error(f"Error in background enrichment: {e}", exc_info=True)
            self._enrichment_status["is_running"] = False
            self._enrichment_status["errors"].append(f"Критическая ошибка: {str(e)}")
            # Сохраняем checkpoint даже при ошибке
            self._save_checkpoint()
    
    async def get_enrichment_status(self) -> Dict:
        """Get current enrichment status"""
        remaining = max(0, self._enrichment_status["total"] - self._enrichment_status["processed"])
        
        return {
            "is_running": self._enrichment_status["is_running"],
            "total": self._enrichment_status["total"],
            "processed": self._enrichment_status["processed"],
            "updated": self._enrichment_status["updated"],
            "failed": self._enrichment_status["failed"],
            "remaining": remaining,
            "current_contact": self._enrichment_status["current_contact"],
            "progress_percent": (self._enrichment_status["processed"] / self._enrichment_status["total"] * 100) if self._enrichment_status["total"] > 0 else 0,
            "checkpoint_size": len(self._processed_ids),
            "skipped": self._enrichment_status.get("skipped", 0)
        }

contact_enrichment_service = ContactEnrichmentService()
