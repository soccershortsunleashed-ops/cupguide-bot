"""
Менеджер квот для Gemini API
Отслеживает дневной лимит и блокирует вызовы до конца суток при исчерпании квоты
"""
import json
import logging
from pathlib import Path
from datetime import datetime, date, time, timedelta
from threading import Lock
from app.core.config import settings

logger = logging.getLogger(__name__)

STATE_PATH = Path(settings.DATA_DIR) / "gemini_quota_state.json"


class GeminiQuotaState:
    def __init__(self):
        self.lock = Lock()
        self.daily_exhausted_until_utc: datetime | None = None
        self.last_reset_date: date | None = None
        self._load()

    # ---------- публичные методы ----------

    def is_available(self) -> bool:
        """Можно ли сейчас дергать Gemini (без риска 429 по дневному лимиту)."""
        with self.lock:
            self._reset_if_new_day()

            if self.daily_exhausted_until_utc is None:
                return True

            now = datetime.utcnow()
            if now >= self.daily_exhausted_until_utc:
                # День сменился или время истекло — сбрасываем блокировку
                logger.info(
                    "[GEMINI QUOTA] Daily block expired at %s, enabling Gemini again",
                    self.daily_exhausted_until_utc,
                )
                self.daily_exhausted_until_utc = None
                self._save()
                return True

            # Всё ещё в блоке
            return False

    def mark_daily_exhausted(self):
        """Отметить, что суточная квота выбрана, блокируем до конца текущих суток (UTC)."""
        with self.lock:
            now = datetime.utcnow()
            tomorrow = date.today() + timedelta(days=1)
            block_until = datetime.combine(tomorrow, time.min)  # полночь следующего дня (UTC)

            self.daily_exhausted_until_utc = block_until
            self.last_reset_date = date.today()

            logger.warning(
                "[GEMINI QUOTA] Daily quota exhausted. Blocking Gemini until %s (UTC)",
                block_until,
            )
            self._save()

    def get_state(self) -> dict:
        """Возвращает текущее состояние квоты для отображения в админке"""
        with self.lock:
            self._reset_if_new_day()
            return {
                "is_available": self.is_available(),
                "daily_exhausted_until_utc": self.daily_exhausted_until_utc.isoformat() if self.daily_exhausted_until_utc else None,
                "last_reset_date": self.last_reset_date.isoformat() if self.last_reset_date else None,
            }

    # ---------- служебные ----------

    def _reset_if_new_day(self):
        today = date.today()
        if self.last_reset_date is None:
            self.last_reset_date = today
            self._save()
            return

        if today > self.last_reset_date:
            # Новый день — сбрасываем блокировку
            logger.info(
                "[GEMINI QUOTA] New day detected (%s > %s). Resetting daily quota state.",
                today,
                self.last_reset_date,
            )
            self.daily_exhausted_until_utc = None
            self.last_reset_date = today
            self._save()

    def _load(self):
        if not STATE_PATH.exists():
            self.last_reset_date = date.today()
            self.daily_exhausted_until_utc = None
            self._save()
            return

        try:
            data = json.loads(STATE_PATH.read_text("utf-8"))
            last_date_str = data.get("last_reset_date")
            self.last_reset_date = (
                date.fromisoformat(last_date_str) if last_date_str else date.today()
            )

            block_until_str = data.get("daily_exhausted_until_utc")
            self.daily_exhausted_until_utc = (
                datetime.fromisoformat(block_until_str) if block_until_str else None
            )
        except Exception as e:
            logger.error("Failed to load Gemini quota state: %s", e, exc_info=True)
            self.last_reset_date = date.today()
            self.daily_exhausted_until_utc = None

    def _save(self):
        try:
            data = {
                "last_reset_date": self.last_reset_date.isoformat()
                if self.last_reset_date
                else None,
                "daily_exhausted_until_utc": self.daily_exhausted_until_utc.isoformat()
                if self.daily_exhausted_until_utc
                else None,
            }
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except Exception as e:
            logger.error("Failed to save Gemini quota state: %s", e, exc_info=True)


# Глобальный экземпляр для импорта
gemini_quota_state = GeminiQuotaState()

