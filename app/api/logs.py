"""
API endpoints for logging bot interactions
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime
import logging
import json
import os

from app.core.config import settings

router = APIRouter(tags=["logs"])
logger = logging.getLogger(__name__)

# Pydantic models for request validation
class MessageLogRequest(BaseModel):
    contact_id: Optional[int] = None
    telegram_user_id: int
    direction: str  # "incoming", "outgoing", "system"
    message_type: str  # "text", "command", "callback", "contact", "action", "error"
    text: str
    payload: Dict[str, Any] = {}
    timestamp: str  # ISO format

class LLMLogRequest(BaseModel):
    contact_id: Optional[int] = None
    model: str
    prompt_version: str
    tool_calls: List[Dict[str, Any]] = []
    answer: str
    latency_ms: int
    error: Optional[str] = None

class LogStorage:
    """Simple file-based log storage"""
    
    def __init__(self):
        self.logs_dir = os.path.join(settings.DATA_DIR, "bot_logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        
        self.message_log_file = os.path.join(self.logs_dir, "messages.jsonl")
        self.llm_log_file = os.path.join(self.logs_dir, "llm_calls.jsonl")
    
    def log_message(self, log_data: Dict[str, Any]) -> None:
        """Log a message interaction"""
        try:
            with open(self.message_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write message log: {e}")
    
    def log_llm_call(self, log_data: Dict[str, Any]) -> None:
        """Log an LLM call"""
        try:
            with open(self.llm_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write LLM log: {e}")
    
    def get_recent_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent message logs"""
        try:
            if not os.path.exists(self.message_log_file):
                return []
            
            with open(self.message_log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Get last N lines
            recent_lines = lines[-limit:] if len(lines) > limit else lines
            
            logs = []
            for line in recent_lines:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
            
            return logs
        except Exception as e:
            logger.error(f"Failed to read message logs: {e}")
            return []
    
    def get_recent_llm_calls(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent LLM call logs"""
        try:
            if not os.path.exists(self.llm_log_file):
                return []
            
            with open(self.llm_log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Get last N lines
            recent_lines = lines[-limit:] if len(lines) > limit else lines
            
            logs = []
            for line in recent_lines:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
            
            return logs
        except Exception as e:
            logger.error(f"Failed to read LLM logs: {e}")
            return []

# Global log storage instance
log_storage = LogStorage()

@router.post("/message")
async def log_message(request: MessageLogRequest):
    """Log a message interaction"""
    try:
        log_data = {
            "contact_id": request.contact_id,
            "telegram_user_id": request.telegram_user_id,
            "direction": request.direction,
            "message_type": request.message_type,
            "text": request.text,
            "payload": request.payload,
            "timestamp": request.timestamp,
            "logged_at": datetime.now().isoformat()
        }
        
        log_storage.log_message(log_data)
        
        return {"status": "success", "message": "Message logged"}
        
    except Exception as e:
        logger.error(f"Error logging message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm")
async def log_llm_call(request: LLMLogRequest):
    """Log an LLM API call"""
    try:
        log_data = {
            "contact_id": request.contact_id,
            "model": request.model,
            "prompt_version": request.prompt_version,
            "tool_calls": request.tool_calls,
            "answer": request.answer,
            "latency_ms": request.latency_ms,
            "error": request.error,
            "logged_at": datetime.now().isoformat()
        }
        
        log_storage.log_llm_call(log_data)
        
        return {"status": "success", "message": "LLM call logged"}
        
    except Exception as e:
        logger.error(f"Error logging LLM call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages")
async def get_recent_messages(limit: int = 100):
    """Get recent message logs"""
    try:
        logs = log_storage.get_recent_messages(limit)
        return {
            "status": "success",
            "count": len(logs),
            "logs": logs
        }
    except Exception as e:
        logger.error(f"Error getting message logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/contact/{contact_id}")
async def get_contact_messages(contact_id: int, limit: int = 100):
    """Get message history for a specific contact"""
    try:
        all_logs = log_storage.get_recent_messages(10000)  # Get all logs
        
        # Filter by contact_id
        contact_logs = [
            log for log in all_logs 
            if log.get("contact_id") == contact_id
        ]
        
        # Sort by timestamp (newest first) and limit
        contact_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        contact_logs = contact_logs[:limit]
        
        return {
            "status": "success",
            "contact_id": contact_id,
            "count": len(contact_logs),
            "logs": contact_logs
        }
    except Exception as e:
        logger.error(f"Error getting contact messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/messages/contact/{contact_id}/count/today")
async def get_contact_messages_count_today(contact_id: int):
    """Get count of messages for a specific contact today"""
    try:
        all_logs = log_storage.get_recent_messages(10000)  # Get all logs
        
        # Get today's date
        today = datetime.now().date()
        
        # Filter by contact_id and today's date
        today_count = 0
        for log in all_logs:
            if log.get("contact_id") != contact_id:
                continue
            
            # Parse timestamp
            timestamp_str = log.get("timestamp", "")
            if not timestamp_str:
                continue
            
            try:
                # Handle different timestamp formats
                if "T" in timestamp_str:
                    log_date = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).date()
                else:
                    log_date = datetime.strptime(timestamp_str[:10], "%Y-%m-%d").date()
                
                if log_date == today:
                    today_count += 1
            except (ValueError, TypeError):
                continue
        
        return {
            "status": "success",
            "contact_id": contact_id,
            "count": today_count,
            "date": today.isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting contact messages count today: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/llm")
async def get_recent_llm_calls(limit: int = 100):
    """Get recent LLM call logs"""
    try:
        logs = log_storage.get_recent_llm_calls(limit)
        return {
            "status": "success",
            "count": len(logs),
            "logs": logs
        }
    except Exception as e:
        logger.error(f"Error getting LLM logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_log_stats():
    """Get logging statistics"""
    try:
        message_logs = log_storage.get_recent_messages(1000)  # Last 1000 messages
        llm_logs = log_storage.get_recent_llm_calls(1000)  # Last 1000 LLM calls
        
        # Calculate stats
        total_messages = len(message_logs)
        total_llm_calls = len(llm_logs)
        
        # Message stats by direction
        incoming_count = len([log for log in message_logs if log.get("direction") == "incoming"])
        outgoing_count = len([log for log in message_logs if log.get("direction") == "outgoing"])
        
        # Message stats by type
        message_types = {}
        for log in message_logs:
            msg_type = log.get("message_type", "unknown")
            message_types[msg_type] = message_types.get(msg_type, 0) + 1
        
        # LLM stats
        avg_latency = 0
        error_count = 0
        if llm_logs:
            total_latency = sum(log.get("latency_ms", 0) for log in llm_logs)
            avg_latency = total_latency / len(llm_logs)
            error_count = len([log for log in llm_logs if log.get("error")])
        
        # Unique users
        unique_users = len(set(log.get("telegram_user_id") for log in message_logs if log.get("telegram_user_id")))
        
        return {
            "status": "success",
            "stats": {
                "total_messages": total_messages,
                "incoming_messages": incoming_count,
                "outgoing_messages": outgoing_count,
                "message_types": message_types,
                "total_llm_calls": total_llm_calls,
                "avg_llm_latency_ms": round(avg_latency, 2),
                "llm_error_count": error_count,
                "unique_users": unique_users
            }
        }
    except Exception as e:
        logger.error(f"Error getting log stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/messages")
async def clear_message_logs():
    """Clear message logs (admin only)"""
    try:
        if os.path.exists(log_storage.message_log_file):
            os.remove(log_storage.message_log_file)
        
        return {"status": "success", "message": "Message logs cleared"}
    except Exception as e:
        logger.error(f"Error clearing message logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/llm")
async def clear_llm_logs():
    """Clear LLM logs (admin only)"""
    try:
        if os.path.exists(log_storage.llm_log_file):
            os.remove(log_storage.llm_log_file)
        
        return {"status": "success", "message": "LLM logs cleared"}
    except Exception as e:
        logger.error(f"Error clearing LLM logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))