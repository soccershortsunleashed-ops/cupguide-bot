"""
Backend API Client for Telegram Bot
"""
import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from config import config

logger = logging.getLogger(__name__)

class BackendClient:
    """Client for interacting with backend API"""
    
    def __init__(self):
        self.base_url = config.BACKEND_URL
        self.timeout = 10.0  # Reduced timeout for faster responses
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to backend"""
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                if method.upper() == "GET":
                    response = await client.get(url, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, json=data, params=params)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=data, params=params)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code} for {method} {url}: {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error for {method} {url}: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error for {method} {url}: {e}")
                raise
    
    # Tournament API methods
    async def search_tournaments(
        self,
        q: Optional[str] = None,
        city: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        age: Optional[str] = None,
        format: Optional[str] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Search tournaments"""
        params = {"limit": limit}
        
        if q:
            params["q"] = q
        if city:
            params["city"] = city
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if age:
            params["age"] = age
        if format:
            params["format"] = format
        
        try:
            result = await self._make_request("GET", "/api/tournaments/search", params=params)
            return result.get("tournaments", [])
        except Exception as e:
            logger.error(f"Error searching tournaments: {e}")
            return []
    
    async def get_tournament(self, tournament_id: int) -> Optional[Dict[str, Any]]:
        """Get tournament by ID"""
        try:
            return await self._make_request("GET", f"/api/tournaments/{tournament_id}")
        except Exception as e:
            logger.error(f"Error getting tournament {tournament_id}: {e}")
            return None
    
    async def get_tournaments(self) -> List[Dict[str, Any]]:
        """Get all tournaments"""
        try:
            result = await self._make_request("GET", "/api/tournaments")
            if isinstance(result, list):
                return result
            return result.get("tournaments", result.get("items", []))
        except Exception as e:
            logger.error(f"Error getting tournaments: {e}")
            return []
    
    async def get_organizer_tournaments(self, contact_id: int) -> List[Dict[str, Any]]:
        """Get tournaments by organizer contact_id"""
        try:
            result = await self._make_request("GET", f"/api/tournaments/organizer/{contact_id}")
            if isinstance(result, list):
                return result
            return result.get("tournaments", result.get("items", []))
        except Exception as e:
            logger.error(f"Error getting organizer tournaments: {e}")
            return []
    
    async def get_tournament_card(self, tournament_id: int) -> Dict[str, Any]:
        """Get tournament card"""
        try:
            result = await self._make_request("GET", f"/api/tournaments/{tournament_id}/card")
            return result
        except Exception as e:
            logger.error(f"Error getting tournament card {tournament_id}: {e}")
            # Fallback to URL
            return {
                "type": "url",
                "url": f"{self.base_url}/tournaments/{tournament_id}"
            }
    
    async def create_tournament_lead(
        self,
        tournament_id: int,
        contact_id: int,
        comment: str,
        source: str = "telegram"
    ) -> Dict[str, Any]:
        """Create tournament lead"""
        data = {
            "contact_id": contact_id,
            "comment": comment,
            "source": source
        }
        
        try:
            return await self._make_request("POST", f"/api/tournaments/{tournament_id}/lead", data=data)
        except Exception as e:
            logger.error(f"Error creating lead for tournament {tournament_id}: {e}")
            raise
    
    # Contacts API methods
    async def upsert_contact(
        self,
        telegram_user_id: int,
        phone: str,
        first_name: str,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
        consent_version: str = "1.0",
        consent_given_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Create or update contact"""
        data = {
            "telegram_user_id": telegram_user_id,
            "phone": phone,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "consent_version": consent_version,
            "consent_given_at": consent_given_at.isoformat() if consent_given_at else None
        }
        
        try:
            return await self._make_request("POST", "/contacts/upsert", data=data)
        except Exception as e:
            logger.error(f"Error upserting contact for user {telegram_user_id}: {e}")
            raise
    
    async def merge_contact_tags(
        self,
        contact_id: int,
        add_tags: List[Dict[str, Any]],
        remove_tags: Optional[List[Dict[str, Any]]] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Merge contact tags"""
        data = {
            "add": add_tags,
            "remove": remove_tags or [],
            "meta": meta or {}
        }
        
        try:
            return await self._make_request("POST", f"/contacts/{contact_id}/tags/merge", data=data)
        except Exception as e:
            logger.error(f"Error merging tags for contact {contact_id}: {e}")
            raise
    
    async def delete_contact(self, contact_id: int) -> Dict[str, Any]:
        """Delete contact"""
        try:
            return await self._make_request("DELETE", f"/contacts/{contact_id}")
        except Exception as e:
            logger.error(f"Error deleting contact {contact_id}: {e}")
            raise
    
    async def get_contact_by_telegram_id(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Get contact by Telegram user ID"""
        try:
            # Увеличенный таймаут для этого запроса
            url = f"{self.base_url}/contacts/by-telegram/{telegram_user_id}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                result = response.json()
            if result.get("found"):
                logger.info(f"✅ Found existing contact for telegram_user_id {telegram_user_id}: contact_id={result.get('contact_id')}")
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting contact by telegram_user_id {telegram_user_id}: {e}")
            return None
    
    # Logging API methods
    async def log_message(
        self,
        contact_id: Optional[int],
        telegram_user_id: int,
        direction: str,
        message_type: str,
        text: str,
        payload: Dict[str, Any],
        timestamp: datetime
    ) -> Dict[str, Any]:
        """Log message"""
        data = {
            "contact_id": contact_id,
            "telegram_user_id": telegram_user_id,
            "direction": direction,
            "message_type": message_type,
            "text": text,
            "payload": payload,
            "timestamp": timestamp.isoformat()
        }
        
        try:
            return await self._make_request("POST", "/api/logs/message", data=data)
        except Exception as e:
            logger.error(f"Error logging message: {e}")
            # Don't raise - logging failures shouldn't break the bot
            return {}
    
    async def log_llm_call(
        self,
        contact_id: Optional[int],
        model: str,
        prompt_version: str,
        tool_calls: List[Dict[str, Any]],
        answer: str,
        latency_ms: int,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """Log LLM call"""
        data = {
            "contact_id": contact_id,
            "model": model,
            "prompt_version": prompt_version,
            "tool_calls": tool_calls,
            "answer": answer,
            "latency_ms": latency_ms,
            "error": error
        }
        
        try:
            return await self._make_request("POST", "/api/logs/llm", data=data)
        except Exception as e:
            logger.error(f"Error logging LLM call: {e}")
            # Don't raise - logging failures shouldn't break the bot
            return {}

    
    async def get_contact(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Get contact by ID"""
        try:
            # Получаем все контакты и ищем нужный
            url = f"{self.base_url}/contacts/"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                contacts = response.json()
            
            for contact in contacts:
                if contact.get('id') == contact_id:
                    return contact
            
            return None
        except Exception as e:
            logger.error(f"Error getting contact {contact_id}: {e}")
            return None
    
    async def update_contact_draft(self, contact_id: int, draft_info: str) -> Dict[str, Any]:
        """Update contact's draft_info field"""
        try:
            # Сначала получаем текущий контакт
            contact = await self.get_contact(contact_id)
            if not contact:
                logger.error(f"Contact {contact_id} not found for draft update")
                return {}
            
            # Обновляем только draft_info, сохраняя остальные поля
            data = {
                "name": contact.get("name", ""),
                "phone": contact.get("phone", ""),
                "group": contact.get("group", "Общая"),
                "draft_info": draft_info
            }
            
            return await self._make_request("PUT", f"/contacts/{contact_id}", data=data)
        except Exception as e:
            logger.error(f"Error updating contact draft for {contact_id}: {e}")
            raise

    # ========== Premium API methods ==========
    
    async def get_premium_status(self, tournament_id: int) -> Dict[str, Any]:
        """Get premium status for tournament"""
        try:
            return await self._make_request("GET", f"/api/tournaments/premium/{tournament_id}/status")
        except Exception as e:
            logger.error(f"Error getting premium status for tournament {tournament_id}: {e}")
            return {"error": str(e)}
    
    async def premium_action(self, tournament_id: int, action: str) -> Dict[str, Any]:
        """
        Perform premium action on tournament.
        
        Actions:
        - activate: Buy premium (7 days) - 3000 ₽
        - extend_7days: Extend by 7 days - 2000 ₽
        - extend_1day: Add 1 day - 500 ₽
        """
        try:
            return await self._make_request(
                "POST", 
                f"/api/tournaments/premium/{tournament_id}/action",
                data={"action": action}
            )
        except Exception as e:
            logger.error(f"Error performing premium action {action} for tournament {tournament_id}: {e}")
            return {"success": False, "error": str(e)}

    # ========== Analytics API methods ==========
    
    async def log_analytics_event(
        self,
        tournament_id: int,
        event_type: str,
        context: str = None,
        source: str = None,
        utm_source: str = None,
        utm_medium: str = None,
        utm_campaign: str = None
    ) -> Dict[str, Any]:
        """
        Log analytics event for tournament.
        
        Args:
            tournament_id: ID турнира
            event_type: Тип события (impression, click)
            context: Контекст показа (bot_search, tournaments_command)
            source: Источник клика (bot, channel, mailing)
            utm_*: UTM-параметры
        """
        data = {
            "tournament_id": tournament_id,
            "event_type": event_type,
            "context": context,
            "source": source,
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign
        }
        
        try:
            return await self._make_request("POST", "/api/analytics/event", data=data)
        except Exception as e:
            logger.debug(f"Error logging analytics event: {e}")
            # Don't raise - analytics failures shouldn't break the bot
            return {}
