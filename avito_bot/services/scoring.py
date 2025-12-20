"""
Deterministic Scoring - детерминированный скоринг A/B/C
Правила из ТЗ раздел 8.3
"""
import re
import logging
from typing import Dict, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Сигналы для скоринга (из ТЗ раздел 8.3)
A_SIGNALS = [
    # Просит созвон/договор/оплату/КП
    r"созвон", r"договор", r"оплат", r"счёт", r"счет", r"кп", r"коммерческ",
    # Срочные сроки
    r"срочно", r"сегодня", r"завтра", r"ближайш", r"быстр", r"asap",
    # Конкретика + цена/сроки
    r"когда.*готов", r"сколько.*врем", r"точн.*стоим", r"точн.*цен",
    # Явно хочет интеграцию/CRM
    r"интеграц.*crm", r"crm.*интеграц", r"подключ.*crm", r"связ.*crm",
    r"готов.*обсуд", r"давайте.*начн", r"приступ", r"старт"
]

B_SIGNALS = [
    # Интерес есть, но мало вводных
    r"как.*работа", r"сколько.*стои", r"цен", r"прайс",
    r"расскаж", r"подробн", r"интересн", r"хочу.*узна",
    r"можно.*ли", r"есть.*возможн", r"делает.*ли"
]

C_SIGNALS = [
    # Просто узнать / пока думаю
    r"просто.*узна", r"пока.*дума", r"может.*потом",
    r"посмотр", r"ознаком", r"пока.*не.*реш",
    r"не.*уверен", r"не.*знаю.*нужн"
]

# Токсичные/демпинговые сигналы (понижают скор)
DUMPING_SIGNALS = [
    r"дёшев", r"дешев", r"подешевл", r"недорог", r"бесплатн",
    r"за.*отзыв", r"за.*портфолио", r"за.*опыт",
    r"минимальн.*бюджет", r"как.*можно.*дешевл",
    r"студент", r"начинающ", r"учусь"
]


@dataclass
class ScoringResult:
    """Результат детерминированного скоринга"""
    score_abc: str  # A/B/C
    confidence: float  # 0.0-1.0
    signals_found: Dict[str, list]
    is_dumping: bool


class DeterministicScoring:
    """Детерминированный скоринг лидов"""
    
    def score_message(self, text: str, slots: Dict[str, Any] = None) -> ScoringResult:
        """
        Оценивает сообщение по правилам A/B/C
        
        Args:
            text: Текст сообщения
            slots: Собранные слоты (для дополнительного контекста)
        
        Returns:
            ScoringResult с оценкой
        """
        text_lower = text.lower()
        
        signals_found = {
            "A": [],
            "B": [],
            "C": [],
            "dumping": []
        }
        
        # Проверяем сигналы A
        for pattern in A_SIGNALS:
            if re.search(pattern, text_lower):
                signals_found["A"].append(pattern)
        
        # Проверяем сигналы B
        for pattern in B_SIGNALS:
            if re.search(pattern, text_lower):
                signals_found["B"].append(pattern)
        
        # Проверяем сигналы C
        for pattern in C_SIGNALS:
            if re.search(pattern, text_lower):
                signals_found["C"].append(pattern)
        
        # Проверяем демпинг
        is_dumping = False
        for pattern in DUMPING_SIGNALS:
            if re.search(pattern, text_lower):
                signals_found["dumping"].append(pattern)
                is_dumping = True
        
        # Определяем итоговый скор
        score_abc, confidence = self._calculate_score(signals_found, slots)
        
        # Демпинг понижает скор
        if is_dumping and score_abc == "A":
            score_abc = "B"
            confidence *= 0.7
        elif is_dumping and score_abc == "B":
            score_abc = "C"
            confidence *= 0.7
        
        logger.debug(f"📊 Scoring: {score_abc} (conf={confidence:.2f}), signals={signals_found}")
        
        return ScoringResult(
            score_abc=score_abc,
            confidence=confidence,
            signals_found=signals_found,
            is_dumping=is_dumping
        )
    
    def _calculate_score(
        self, 
        signals: Dict[str, list], 
        slots: Dict[str, Any] = None
    ) -> Tuple[str, float]:
        """Вычисляет итоговый скор"""
        
        a_count = len(signals["A"])
        b_count = len(signals["B"])
        c_count = len(signals["C"])
        
        # Дополнительные баллы за слоты
        slot_bonus = 0
        if slots:
            if slots.get("service_id"):
                slot_bonus += 1
            if slots.get("deadline"):
                slot_bonus += 1
            if slots.get("integrations"):
                slot_bonus += len(slots["integrations"]) * 0.5
        
        # Логика определения скора
        if a_count >= 2 or (a_count >= 1 and slot_bonus >= 2):
            return "A", min(1.0, 0.7 + a_count * 0.1 + slot_bonus * 0.05)
        
        if a_count >= 1 or (b_count >= 2 and slot_bonus >= 1):
            return "B", min(1.0, 0.5 + b_count * 0.1 + slot_bonus * 0.05)
        
        if b_count >= 1:
            return "B", 0.4 + b_count * 0.1
        
        if c_count >= 1:
            return "C", 0.3 + c_count * 0.1
        
        # По умолчанию B с низкой уверенностью
        return "B", 0.3
    
    def compare_with_llm(
        self, 
        deterministic_score: str, 
        llm_score: str
    ) -> Tuple[bool, str]:
        """
        Сравнивает детерминированный и LLM скоры
        
        Returns:
            (match: bool, recommendation: str)
        """
        if deterministic_score == llm_score:
            return True, "Оценки совпадают"
        
        grade_order = {"C": 0, "B": 1, "A": 2}
        det_order = grade_order.get(deterministic_score, 1)
        llm_order = grade_order.get(llm_score, 1)
        
        diff = abs(det_order - llm_order)
        
        if diff == 1:
            # Небольшое расхождение - доверяем LLM
            return False, f"Небольшое расхождение: детерм={deterministic_score}, LLM={llm_score}. Используем LLM."
        else:
            # Большое расхождение - требует внимания
            return False, f"⚠️ Большое расхождение: детерм={deterministic_score}, LLM={llm_score}. Требует проверки!"


# Singleton
deterministic_scoring = DeterministicScoring()
