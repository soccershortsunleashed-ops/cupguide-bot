"""
Logging Client for Telegram Bot
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from backend_client import BackendClient

logger = logging.getLogger(__name__)

class LoggingClient:
    """Client for logging bot interactions"""
    
    def __init__(self):
        self.backend_client = BackendClient()
    
    async def log_message(
        self,
        contact_id: Optional[int],
        telegram_user_id: int,
        direction: str,  # "incoming" or "outgoing"
        message_type: str,  # "text", "command", "callback", "contact", etc.
        text: str,
        payload: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """Log a message interaction"""
        try:
            await self.backend_client.log_message(
                contact_id=contact_id,
                telegram_user_id=telegram_user_id,
                direction=direction,
                message_type=message_type,
                text=text,
                payload=payload,
                timestamp=timestamp
            )
            
            logger.debug(
                f"Logged {direction} {message_type} message for user {telegram_user_id}: {text[:50]}..."
            )
            
        except Exception as e:
            logger.error(f"Failed to log message: {e}")
            # Don't raise - logging failures shouldn't break the bot
    
    async def log_llm_call(
        self,
        contact_id: Optional[int],
        model: str,
        prompt_version: str,
        tool_calls: list,
        answer: str,
        latency_ms: int,
        error: Optional[str] = None
    ) -> None:
        """Log an LLM API call"""
        try:
            await self.backend_client.log_llm_call(
                contact_id=contact_id,
                model=model,
                prompt_version=prompt_version,
                tool_calls=tool_calls,
                answer=answer,
                latency_ms=latency_ms,
                error=error
            )
            
            logger.debug(
                f"Logged LLM call for contact {contact_id}: {model}, {latency_ms}ms, "
                f"{len(tool_calls)} tools, {'error' if error else 'success'}"
            )
            
        except Exception as e:
            logger.error(f"Failed to log LLM call: {e}")
            # Don't raise - logging failures shouldn't break the bot
    
    async def log_user_action(
        self,
        contact_id: Optional[int],
        telegram_user_id: int,
        action: str,
        payload: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> None:
        """Log a user action (consent, contact sharing, etc.)"""
        if timestamp is None:
            timestamp = datetime.now()
        
        await self.log_message(
            contact_id=contact_id,
            telegram_user_id=telegram_user_id,
            direction="incoming",
            message_type="action",
            text=action,
            payload=payload,
            timestamp=timestamp
        )
    
    async def log_bot_response(
        self,
        contact_id: Optional[int],
        telegram_user_id: int,
        response_type: str,
        text: str,
        payload: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> None:
        """Log a bot response"""
        if timestamp is None:
            timestamp = datetime.now()
        
        await self.log_message(
            contact_id=contact_id,
            telegram_user_id=telegram_user_id,
            direction="outgoing",
            message_type=response_type,
            text=text,
            payload=payload,
            timestamp=timestamp
        )
    
    async def log_error(
        self,
        contact_id: Optional[int],
        telegram_user_id: int,
        error_type: str,
        error_message: str,
        payload: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> None:
        """Log an error"""
        if timestamp is None:
            timestamp = datetime.now()
        
        await self.log_message(
            contact_id=contact_id,
            telegram_user_id=telegram_user_id,
            direction="system",
            message_type="error",
            text=f"{error_type}: {error_message}",
            payload=payload,
            timestamp=timestamp
        )