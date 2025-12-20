"""
Deterministic Scoring - детерминированный скоринг лидов
Формула из раздела 6 ТЗ - для страховки LLM
"""
import re
import logging
from typing import Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Токсичные/демпинговые ключевые слова
DUMPING_KEYWORDS = [
    "дёшево", "дешево", "подешевле", "недорого", "бесплатно",
    "за отзыв", "за портфолио", "за опыт",
    "срочно за 2к", "за 5к", "за 3к", "за 1к",
    "как можно дешевле", "минимальный бюджет",
    "студент", "начинающий", "учусь",
    "просто попробовать", "на пробу",
]


@dataclass
class DeterministicResult:
    """Результат детерминированного скоринга"""
    score: int  # 0-100
    grade: str  # A/B/TRASH
    breakdown: dict  # Разбивка по категориям


class DeterministicScoring:
    """Детерминированный скоринг лидов"""
    
    def calculate(
        self,
        goal: str,
        pain: str,
        context: str,
        niche_text: str
    ) -> DeterministicResult:
        """
        Рассчитывает детерминированный скоринг
        
        Баллы (из ТЗ раздел 6):
        • Цель "продажи/заявки" +20, "лиды" +10, "поддержка" +10, "просто бот" -30
        • Боль "оплата/интеграции/диалог" +20, "хаос" +5, "вход" +10
        • Контекст "после конструктора" +15, "есть CRM надо связать" +20, "с нуля" +10
        • Наличие чека в тексте (число) +15
        • Конкретика (есть ниша+продукт) +15
        • Токсичность/демпинг -40
        
        Порог:
        • A ≥ 70
        • B 40–69
        • TRASH < 40
        """
        breakdown = {
            "goal": 0,
            "pain": 0,
            "context": 0,
            "has_price": 0,
            "has_specifics": 0,
            "toxicity": 0,
        }
        
        # === ЦЕЛЬ ===
        goal_lower = goal.lower() if goal else ""
        if goal_lower in ["sales", "продажи"]:
            breakdown["goal"] = 20
        elif goal_lower in ["leads", "заявки"]:
            breakdown["goal"] = 20
        elif goal_lower in ["base", "лиды", "лиды/база"]:
            breakdown["goal"] = 10
        elif goal_lower in ["support", "поддержка", "поддержка/сервис"]:
            breakdown["goal"] = 10
        elif goal_lower in ["just_bot", "просто бот", "просто \"чтоб был бот\""]:
            breakdown["goal"] = -30
        
        # === БОЛЬ ===
        pain_lower = pain.lower() if pain else ""
        if pain_lower in ["payment", "оплата", "до оплаты не доходят"]:
            breakdown["pain"] = 20
        elif pain_lower in ["integration", "интеграции", "автоматизация/интеграции"]:
            breakdown["pain"] = 20
        elif pain_lower in ["dialog", "диалог", "диалог без результата", "диалог есть — результата нет"]:
            breakdown["pain"] = 20
        elif pain_lower in ["chaos", "хаос", "всё в хаосе"]:
            breakdown["pain"] = 5
        elif pain_lower in ["traffic", "вход", "вход/трафик"]:
            breakdown["pain"] = 10
        
        # === КОНТЕКСТ ===
        context_lower = context.lower() if context else ""
        if context_lower in ["after_constructor", "после конструктора", "был конструктор — надо нормально"]:
            breakdown["context"] = 15
        elif context_lower in ["has_crm", "есть crm", "есть crm/сервисы — надо связать"]:
            breakdown["context"] = 20
        elif context_lower in ["from_scratch", "с нуля"]:
            breakdown["context"] = 10
        elif context_lower in ["has_bot", "есть бот", "есть бот — нужно переписать/усилить"]:
            breakdown["context"] = 10
        
        # === НАЛИЧИЕ ЧЕКА ===
        if niche_text and self._has_price(niche_text):
            breakdown["has_price"] = 15
        
        # === КОНКРЕТИКА (ниша + продукт) ===
        if niche_text and self._has_specifics(niche_text):
            breakdown["has_specifics"] = 15
        
        # === ТОКСИЧНОСТЬ/ДЕМПИНГ ===
        if niche_text and self._has_dumping(niche_text):
            breakdown["toxicity"] = -40
        
        # Считаем итоговый скор
        score = sum(breakdown.values())
        
        # Нормализуем в диапазон 0-100
        # Базовый скор может быть от -70 до +90
        # Сдвигаем и масштабируем
        normalized_score = max(0, min(100, score + 30))  # +30 для сдвига в положительную зону
        
        # Определяем грейд
        if normalized_score >= 70:
            grade = "A"
        elif normalized_score >= 40:
            grade = "B"
        else:
            grade = "TRASH"
        
        logger.info(f"📊 Deterministic scoring: score={normalized_score}, grade={grade}, breakdown={breakdown}")
        
        return DeterministicResult(
            score=normalized_score,
            grade=grade,
            breakdown=breakdown
        )
    
    def _has_price(self, text: str) -> bool:
        """Проверяет наличие чека/цены в тексте"""
        # Ищем числа (возможно с пробелами как разделителями тысяч)
        # Примеры: 20000, 20 000, 50к, 100$
        patterns = [
            r'\d{4,}',  # Числа от 4 цифр (1000+)
            r'\d+\s*\d{3}',  # Числа с пробелом (20 000)
            r'\d+\s*[кkК]',  # С буквой к (50к)
            r'\d+\s*[$€₽руб]',  # С валютой
            r'чек\s*\d+',  # "чек 20000"
            r'средний\s*чек',  # "средний чек"
        ]
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _has_specifics(self, text: str) -> bool:
        """Проверяет наличие конкретики (ниша + продукт)"""
        # Ищем признаки конкретной ниши
        niche_keywords = [
            "онлайн-школа", "онлайн школа", "курс", "обучение",
            "магазин", "интернет-магазин", "e-commerce",
            "услуги", "консалтинг", "агентство",
            "недвижимость", "авто", "ремонт",
            "фитнес", "спорт", "здоровье",
            "красота", "салон", "косметика",
            "ресторан", "кафе", "доставка",
            "юрист", "бухгалтер", "финансы",
            "it", "разработка", "дизайн",
            "маркетинг", "реклама", "smm",
            "инфобизнес", "коучинг", "психолог",
        ]
        
        text_lower = text.lower()
        
        # Проверяем наличие хотя бы одного ключевого слова ниши
        has_niche = any(kw in text_lower for kw in niche_keywords)
        
        # Проверяем наличие продукта (слова типа "продукт", "товар", "услуга")
        product_keywords = ["продукт", "товар", "услуга", "сервис", "курс", "программа"]
        has_product = any(kw in text_lower for kw in product_keywords)
        
        # Достаточно наличия ниши ИЛИ продукта + чека
        return has_niche or (has_product and self._has_price(text))
    
    def _has_dumping(self, text: str) -> bool:
        """Проверяет наличие демпинговых/токсичных ключевых слов"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in DUMPING_KEYWORDS)
    
    def compare_with_llm(
        self,
        deterministic_grade: str,
        llm_grade: str
    ) -> Tuple[bool, str]:
        """
        Сравнивает детерминированный и LLM грейды
        
        Returns:
            (match: bool, recommendation: str)
        """
        if deterministic_grade == llm_grade:
            return True, "Оценки совпадают"
        
        # Определяем расхождение
        grade_order = {"TRASH": 0, "B": 1, "A": 2}
        det_order = grade_order.get(deterministic_grade, 1)
        llm_order = grade_order.get(llm_grade, 1)
        
        diff = abs(det_order - llm_order)
        
        if diff == 1:
            # Небольшое расхождение - доверяем LLM
            return False, f"Небольшое расхождение: детерм={deterministic_grade}, LLM={llm_grade}. Используем LLM."
        else:
            # Большое расхождение - требует внимания
            return False, f"⚠️ Большое расхождение: детерм={deterministic_grade}, LLM={llm_grade}. Требует проверки!"


# Singleton instance
deterministic_scoring = DeterministicScoring()
