"""
CRM Connector - интеграция с CRM (создание лидов)
Контракт из ТЗ раздел 10
"""
import logging
import httpx
from typing import Dict, Any, Optional
from dataclasses import dataclass

from avito_bot.config import config
from avito_bot.models.lead import AvitoLead, LeadStatus, LeadPayload

logger = logging.getLogger(__name__)


@dataclass
class CRMResult:
    """Результат операции с CRM"""
    success: bool
    crm_lead_id: Optional[int] = None
    error: Optional[str] = None


class CRMConnector:
    """Коннектор к CRM для создания лидов"""
    
    def __init__(self):
        self.api_url = config.CRM_API_URL
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получает HTTP клиент"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def create_lead(self, payload: Dict[str, Any]) -> CRMResult:
        """
        Создаёт лид в CRM
        
        Args:
            payload: Данные лида (LeadPayload)
        
        Returns:
            CRMResult с результатом
        """
        try:
            # Проверяем идемпотентность (не создавать дубли)
            chat_id = payload.get("chat_id")
            if chat_id:
                existing = await self._check_existing_lead(chat_id)
                if existing:
                    logger.info(f"⚠️ Lead already exists for chat {chat_id}: {existing}")
                    return CRMResult(
                        success=True,
                        crm_lead_id=existing,
                        error="duplicate"
                    )
            
            # Формируем запрос к CRM API
            crm_payload = self._build_crm_payload(payload)
            
            client = await self._get_client()
            response = await client.post(
                self.api_url,
                json=crm_payload
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                crm_lead_id = data.get("id") or data.get("lead_id")
                logger.info(f"✅ Lead created in CRM: {crm_lead_id}")
                return CRMResult(success=True, crm_lead_id=crm_lead_id)
            else:
                error = f"CRM API error: {response.status_code} - {response.text}"
                logger.error(f"❌ {error}")
                return CRMResult(success=False, error=error)
                
        except httpx.TimeoutException:
            logger.error("❌ CRM timeout")
            return CRMResult(success=False, error="timeout")
            
        except Exception as e:
            logger.error(f"❌ CRM error: {e}")
            return CRMResult(success=False, error=str(e))
    
    async def _check_existing_lead(self, chat_id: str) -> Optional[int]:
        """Проверяет, есть ли уже лид для этого чата"""
        try:
            client = await self._get_client()
            # Предполагаем, что CRM API поддерживает поиск по source_channel_id
            # или другому идентификатору
            response = await client.get(
                f"{self.api_url}",
                params={"source_channel_id": chat_id}
            )
            
            if response.status_code == 200:
                leads = response.json()
                if leads and len(leads) > 0:
                    return leads[0].get("id")
            
            return None
            
        except Exception as e:
            logger.debug(f"Check existing lead error: {e}")
            return None
    
    def _build_crm_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Формирует payload для CRM API"""
        
        # Маппинг на существующую модель Lead
        return {
            "telegram_user_id": 0,  # Для Авито нет telegram_user_id
            "source_type": "avito",
            "source_channel_id": hash(payload.get("chat_id", "")) % 10**9,  # Конвертируем в int
            
            # Скрининг данные
            "goal": self._map_service_to_goal(payload.get("service_group")),
            "pain": "integration" if payload.get("integrations") else None,
            "niche_text": payload.get("summary", ""),
            
            # LLM скоринг
            "llm_grade": payload.get("score_abc", "B"),
            "llm_score": self._score_to_number(payload.get("score_abc", "B")),
            "llm_reason": payload.get("comment", ""),
            
            # Маршрутизация
            "final_route": f"{payload.get('score_abc', 'B')}_FLOW",
            "status": "NEW",
            
            # Контактные данные
            "contact_link": payload.get("item_id"),
            "start_window": payload.get("deadline"),
            
            # Заметки
            "notes": f"Авито чат: {payload.get('chat_id')}\n{payload.get('summary', '')}"
        }
    
    def _map_service_to_goal(self, service_group: Optional[str]) -> Optional[str]:
        """Маппинг группы услуг на цель"""
        if not service_group:
            return None
        
        mapping = {
            "Программирование": "leads",
            "CRM-системы": "leads",
            "unknown": None
        }
        return mapping.get(service_group)
    
    def _score_to_number(self, score_abc: str) -> int:
        """Конвертирует A/B/C в числовой скор"""
        mapping = {"A": 85, "B": 55, "C": 25}
        return mapping.get(score_abc, 50)
    
    async def close(self):
        """Закрывает HTTP клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
crm_connector = CRMConnector()
