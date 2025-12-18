"""
Сервис для сохранения и обработки отложенных анализов сообщений
(когда квота OpenAI API исчерпана)
"""
import json
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from app.core.config import settings

logger = logging.getLogger(__name__)

class PendingAnalysis:
    """Модель для отложенного анализа"""
    def __init__(self, sender_name: str, sender_id: str, group_id: str, group_name: str, 
                 messages: List[Dict], created_at: Optional[datetime] = None):
        self.sender_name = sender_name
        self.sender_id = sender_id
        self.group_id = group_id
        self.group_name = group_name
        self.messages = messages
        self.created_at = created_at or datetime.now(timezone.utc)
        self.attempts = 0
        self.last_attempt = None
    
    def to_dict(self) -> Dict:
        """Преобразует в словарь для сохранения в JSON"""
        return {
            'sender_name': self.sender_name,
            'sender_id': self.sender_id,
            'group_id': self.group_id,
            'group_name': self.group_name,
            'messages': self.messages,
            'created_at': self.created_at.isoformat(),
            'attempts': self.attempts,
            'last_attempt': self.last_attempt.isoformat() if self.last_attempt else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PendingAnalysis':
        """Создает из словаря"""
        obj = cls(
            sender_name=data['sender_name'],
            sender_id=data['sender_id'],
            group_id=data['group_id'],
            group_name=data['group_name'],
            messages=data['messages'],
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data['created_at'], str) else data['created_at']
        )
        obj.attempts = data.get('attempts', 0)
        if data.get('last_attempt'):
            obj.last_attempt = datetime.fromisoformat(data['last_attempt']) if isinstance(data['last_attempt'], str) else data['last_attempt']
        return obj


class PendingAnalysisService:
    """Сервис для управления отложенными анализами"""
    
    def __init__(self):
        self.file_path = os.path.join(settings.DATA_DIR, "pending_analyses.json")
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Создает файл, если его нет"""
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    
    def _load_pending(self) -> List[PendingAnalysis]:
        """Загружает отложенные анализы из файла"""
        try:
            if not os.path.exists(self.file_path):
                return []
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return [PendingAnalysis.from_dict(item) for item in data]
        except Exception as e:
            logger.error(f"Error loading pending analyses: {e}", exc_info=True)
            return []
    
    def _save_pending(self, pending_list: List[PendingAnalysis]):
        """Сохраняет отложенные анализы в файл"""
        try:
            data = [item.to_dict() for item in pending_list]
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending analyses: {e}", exc_info=True)
    
    def add_pending_analysis(self, sender_name: str, sender_id: str, group_id: str, 
                             group_name: str, messages: List[Dict]) -> bool:
        """Добавляет отложенный анализ"""
        try:
            pending_list = self._load_pending()
            
            # Проверяем, нет ли уже такого анализа (по sender_id и group_id)
            analysis_key = f"{sender_id}_{group_id}"
            for pending in pending_list:
                existing_key = f"{pending.sender_id}_{pending.group_id}"
                if existing_key == analysis_key:
                    # Обновляем существующий - добавляем новые сообщения
                    existing_message_ids = {msg.get('message_id') for msg in pending.messages if msg.get('message_id')}
                    for msg in messages:
                        msg_id = msg.get('message_id')
                        if msg_id and msg_id not in existing_message_ids:
                            pending.messages.append(msg)
                            existing_message_ids.add(msg_id)
                        elif not msg_id:
                            # Если нет message_id, добавляем всегда (может быть дубликат, но это лучше чем потерять)
                            pending.messages.append(msg)
                    
                    logger.info(f"Updated pending analysis for {sender_name} ({sender_id}) in group {group_name}: {len(messages)} new messages")
                    self._save_pending(pending_list)
                    return True
            
            # Создаем новый отложенный анализ
            pending = PendingAnalysis(
                sender_name=sender_name,
                sender_id=sender_id,
                group_id=group_id,
                group_name=group_name,
                messages=messages
            )
            pending_list.append(pending)
            
            logger.info(f"Added pending analysis for {sender_name} ({sender_id}) in group {group_name}: {len(messages)} messages")
            self._save_pending(pending_list)
            return True
        except Exception as e:
            logger.error(f"Error adding pending analysis: {e}", exc_info=True)
            return False
    
    def get_pending_analyses(self) -> List[PendingAnalysis]:
        """Получает все отложенные анализы"""
        return self._load_pending()
    
    def remove_pending_analysis(self, sender_id: str, group_id: str) -> bool:
        """Удаляет отложенный анализ после успешной обработки"""
        try:
            pending_list = self._load_pending()
            analysis_key = f"{sender_id}_{group_id}"
            
            original_count = len(pending_list)
            pending_list = [
                p for p in pending_list 
                if f"{p.sender_id}_{p.group_id}" != analysis_key
            ]
            
            if len(pending_list) < original_count:
                self._save_pending(pending_list)
                logger.info(f"Removed pending analysis for {sender_id} in group {group_id}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error removing pending analysis: {e}", exc_info=True)
            return False
    
    def mark_attempt(self, sender_id: str, group_id: str, success: bool = False):
        """Отмечает попытку обработки"""
        try:
            pending_list = self._load_pending()
            analysis_key = f"{sender_id}_{group_id}"
            
            for pending in pending_list:
                if f"{pending.sender_id}_{pending.group_id}" == analysis_key:
                    pending.attempts += 1
                    pending.last_attempt = datetime.now(timezone.utc)
                    if success:
                        # Удаляем после успешной обработки
                        self.remove_pending_analysis(sender_id, group_id)
                    else:
                        self._save_pending(pending_list)
                    break
        except Exception as e:
            logger.error(f"Error marking attempt: {e}", exc_info=True)
    
    def get_pending_count(self) -> int:
        """Возвращает количество отложенных анализов"""
        return len(self._load_pending())


# Глобальный экземпляр сервиса
pending_analysis_service = PendingAnalysisService()

