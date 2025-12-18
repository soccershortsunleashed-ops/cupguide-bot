import logging
import asyncio
from typing import Optional, Dict
from app.services.green_api_service import green_api_service
from app.services.contact_service import contact_service
from app.models.contact import Contact
from fastapi import HTTPException

logger = logging.getLogger(__name__)

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

    async def enrich_all_contacts(self) -> Dict:
        """
        Enrich all contacts with WhatsApp profile data.
        Runs in background and updates status.
        
        Returns:
            Dictionary with job ID and initial status
        """
        # Запускаем в фоне
        asyncio.create_task(self._enrich_all_contacts_background())
        
        return {
            "status": "started",
            "message": "Обновление запущено"
        }
    
    async def _enrich_all_contacts_background(self):
        """Background task to enrich all contacts"""
        try:
            contacts = await contact_service.get_contacts()
            
            # Инициализируем статус
            self._enrichment_status = {
                "is_running": True,
                "total": len(contacts),
                "processed": 0,
                "updated": 0,
                "failed": 0,
                "current_contact": None,
                "errors": []
            }
            
            for idx, contact in enumerate(contacts, start=1):
                self._enrichment_status["current_contact"] = contact.name or contact.phone
                
                try:
                    await self.enrich_contact(contact.id)
                    self._enrichment_status["updated"] += 1
                except HTTPException as e:
                    self._enrichment_status["failed"] += 1
                    error_msg = f"{contact.name} ({contact.phone}): {e.detail}"
                    self._enrichment_status["errors"].append(error_msg)
                    logger.error(f"Failed to enrich {contact.name}: {e.detail}")
                except Exception as e:
                    self._enrichment_status["failed"] += 1
                    error_msg = f"{contact.name} ({contact.phone}): {str(e)}"
                    self._enrichment_status["errors"].append(error_msg)
                    logger.error(f"Failed to enrich {contact.name}: {str(e)}")
                finally:
                    # Обновляем счетчик обработанных после каждой итерации
                    self._enrichment_status["processed"] = idx
            
            # Финальный статус
            self._enrichment_status["processed"] = len(contacts)
            self._enrichment_status["current_contact"] = None
            self._enrichment_status["is_running"] = False
            
        except Exception as e:
            logger.error(f"Error in background enrichment: {e}", exc_info=True)
            self._enrichment_status["is_running"] = False
            self._enrichment_status["errors"].append(f"Критическая ошибка: {str(e)}")
    
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
            "progress_percent": (self._enrichment_status["processed"] / self._enrichment_status["total"] * 100) if self._enrichment_status["total"] > 0 else 0
        }

contact_enrichment_service = ContactEnrichmentService()
