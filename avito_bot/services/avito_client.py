"""
Avito API Client - клиент для работы с Avito API
Поддержка webhook и polling режимов
"""
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

import httpx

from avito_bot.config import config

logger = logging.getLogger(__name__)


@dataclass
class AvitoToken:
    """Токен доступа Avito"""
    access_token: str
    expires_at: datetime


class AvitoClient:
    """Клиент Avito API"""
    
    BASE_URL = "https://api.avito.ru"
    AUTH_URL = "https://api.avito.ru/token"
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[AvitoToken] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получает HTTP клиент"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def _ensure_token(self) -> str:
        """Получает или обновляет токен доступа"""
        now = datetime.now()
        
        # Проверяем, нужно ли обновить токен
        if self._token and self._token.expires_at > now:
            return self._token.access_token
        
        # Получаем новый токен
        client = await self._get_client()
        
        try:
            response = await client.post(
                self.AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": config.AVITO_CLIENT_ID,
                    "client_secret": config.AVITO_CLIENT_SECRET
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                expires_in = data.get("expires_in", 3600)
                self._token = AvitoToken(
                    access_token=data["access_token"],
                    expires_at=datetime.fromtimestamp(now.timestamp() + expires_in - 60)
                )
                logger.info("✅ Avito token refreshed")
                return self._token.access_token
            else:
                logger.error(f"❌ Avito auth error: {response.status_code} - {response.text}")
                raise Exception(f"Auth failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Avito auth error: {e}")
            raise
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Выполняет запрос к API"""
        token = await self._ensure_token()
        client = await self._get_client()
        
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        
        url = f"{self.BASE_URL}{endpoint}"
        
        response = await client.request(method, url, headers=headers, **kwargs)
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            logger.error(f"❌ Avito API error: {response.status_code} - {response.text}")
            raise Exception(f"API error: {response.status_code}")
    
    async def get_chats(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Получает список чатов"""
        params = {"unread_only": unread_only}
        data = await self._request(
            "GET", 
            f"/messenger/v2/accounts/{config.AVITO_USER_ID}/chats",
            params=params
        )
        return data.get("chats", [])
    
    async def get_messages(
        self, 
        chat_id: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Получает сообщения из чата"""
        params = {"limit": limit}
        data = await self._request(
            "GET",
            f"/messenger/v3/accounts/{config.AVITO_USER_ID}/chats/{chat_id}/messages/",
            params=params
        )
        return data.get("messages", [])
    
    async def send_message(self, chat_id: str, text: str) -> Dict[str, Any]:
        """Отправляет сообщение в чат"""
        data = await self._request(
            "POST",
            f"/messenger/v1/accounts/{config.AVITO_USER_ID}/chats/{chat_id}/messages",
            json={"message": {"text": text}, "type": "text"}
        )
        return data
    
    async def mark_as_read(self, chat_id: str) -> bool:
        """Помечает чат как прочитанный"""
        try:
            await self._request(
                "POST",
                f"/messenger/v1/accounts/{config.AVITO_USER_ID}/chats/{chat_id}/read"
            )
            return True
        except Exception:
            return False
    
    async def close(self):
        """Закрывает клиент"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
avito_client = AvitoClient()
