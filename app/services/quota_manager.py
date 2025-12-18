"""
Сервис для управления квотами LLM провайдеров и отслеживания статуса OCR
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Literal
from dataclasses import dataclass, asdict
import json
import os
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OCRStatus:
    """Статус OCR для сообщения"""
    status: Literal["success", "error", "permanent_error"] = "error"
    attempts_count: int = 0
    last_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    last_error_type: Optional[str] = None  # "429", "timeout", "network", etc.


class QuotaManager:
    """Управление квотами и статусами OCR"""
    
    def __init__(self):
        self.status_file = os.path.join(settings.DATA_DIR, "ocr_status.json")
        self._ocr_statuses: Dict[str, OCRStatus] = {}
        self._provider_unavailable: Dict[str, float] = {}  # provider -> unavailable_until timestamp
        self._ocr_call_count = 0  # Счетчик вызовов OCR в текущем прогоне
        self._max_ocr_per_run = 20  # Максимальное количество OCR вызовов за один прогон
        
        self._load_statuses()
    
    def _load_statuses(self):
        """Загружает статусы OCR из файла"""
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, status_data in data.get("ocr_statuses", {}).items():
                        self._ocr_statuses[key] = OCRStatus(**status_data)
                    self._provider_unavailable = data.get("provider_unavailable", {})
                    logger.debug(f"Loaded {len(self._ocr_statuses)} OCR statuses from file")
        except Exception as e:
            logger.error(f"Error loading OCR statuses: {e}", exc_info=True)
            self._ocr_statuses = {}
            self._provider_unavailable = {}
    
    def _save_statuses(self):
        """Сохраняет статусы OCR в файл"""
        try:
            os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
            data = {
                "ocr_statuses": {
                    key: asdict(status) for key, status in self._ocr_statuses.items()
                },
                "provider_unavailable": self._provider_unavailable
            }
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving OCR statuses: {e}", exc_info=True)
    
    def get_ocr_status(self, message_key: str) -> Optional[OCRStatus]:
        """Получить статус OCR для сообщения"""
        return self._ocr_statuses.get(message_key)
    
    def set_ocr_status(self, message_key: str, status: Literal["success", "error", "permanent_error"], 
                      error: Optional[str] = None, error_type: Optional[str] = None):
        """Установить статус OCR для сообщения"""
        if message_key not in self._ocr_statuses:
            self._ocr_statuses[message_key] = OCRStatus()
        
        ocr_status = self._ocr_statuses[message_key]
        ocr_status.status = status
        ocr_status.attempts_count += 1
        ocr_status.last_attempt_at = datetime.now(timezone.utc).isoformat()
        if error:
            ocr_status.last_error = error
        if error_type:
            ocr_status.last_error_type = error_type
        
        self._save_statuses()
        logger.debug(f"Updated OCR status for {message_key}: {status} (attempts: {ocr_status.attempts_count})")
    
    def should_skip_ocr(self, message_key: str, error_type: Optional[str] = None) -> bool:
        """
        Определяет, нужно ли пропустить OCR для сообщения.
        
        Args:
            message_key: Уникальный ключ сообщения (например, путь к файлу или ID сообщения)
            error_type: Тип ошибки, если есть (например, "429", "timeout", "network")
        
        Returns:
            True если нужно пропустить OCR, False если можно попробовать
        """
        status = self.get_ocr_status(message_key)
        if not status:
            return False
        
        # Если успешно обработано - пропускаем
        if status.status == "success":
            return True
        
        # Если permanent_error - всегда пропускаем
        if status.status == "permanent_error":
            return True
        
        # Если была ошибка, проверяем условия для повторной попытки
        if status.status == "error":
            # Если была ошибка 429 (quota) и нет специальной причины пробовать снова - пропускаем
            if status.last_error_type == "429" and status.attempts_count >= 1:
                return True
            
            # Если было много попыток (>= 2) - пропускаем
            if status.attempts_count >= 2:
                return True
            
            # Если та же ошибка повторяется - пропускаем
            if error_type and status.last_error_type == error_type and status.attempts_count >= 1:
                return True
        
        return False
    
    def mark_provider_unavailable(self, provider: str, retry_delay: float = 60.0):
        """
        Помечает провайдера как недоступного до указанного времени.
        
        Args:
            provider: Имя провайдера ("gemini", "openai")
            retry_delay: Задержка в секундах до следующей попытки
        """
        unavailable_until = time.time() + retry_delay
        self._provider_unavailable[provider] = unavailable_until
        self._save_statuses()
        logger.warning(f"⚠️ {provider.upper()} marked as unavailable until {datetime.fromtimestamp(unavailable_until).isoformat()}")
    
    def is_provider_available(self, provider: str) -> bool:
        """Проверяет, доступен ли провайдер"""
        if provider not in self._provider_unavailable:
            return True
        
        unavailable_until = self._provider_unavailable[provider]
        if time.time() >= unavailable_until:
            # Время прошло, провайдер снова доступен
            del self._provider_unavailable[provider]
            self._save_statuses()
            logger.info(f"✅ {provider.upper()} is now available again")
            return True
        
        return False
    
    def reset_ocr_call_count(self):
        """Сбрасывает счетчик вызовов OCR (вызывается в начале нового прогона)"""
        self._ocr_call_count = 0
        logger.debug("Reset OCR call count")
    
    def can_make_ocr_call(self) -> bool:
        """Проверяет, можно ли сделать еще один вызов OCR"""
        if self._ocr_call_count >= self._max_ocr_per_run:
            logger.warning(f"⚠️ OCR call limit reached ({self._max_ocr_per_run} calls per run). Skipping OCR.")
            return False
        return True
    
    def increment_ocr_call_count(self):
        """Увеличивает счетчик вызовов OCR"""
        self._ocr_call_count += 1
        logger.debug(f"OCR call count: {self._ocr_call_count}/{self._max_ocr_per_run}")
    
    def get_ocr_call_count(self) -> int:
        """Возвращает текущее количество вызовов OCR"""
        return self._ocr_call_count


# Глобальный экземпляр
quota_manager = QuotaManager()

