"""
LLM Scoring Service - оценка лидов через LLM
Промты из ТЗ раздел 10 (4.1 и 4.2) - НЕ ИЗМЕНЯТЬ!
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass

import openai

from freelance_bot.config import config

logger = logging.getLogger(__name__)


# ============================================================
# SYSTEM PROMPT (раздел 4.1 ТЗ) - НЕ ИЗМЕНЯТЬ!
# ============================================================

SYSTEM_PROMPT = """Ты — дерзкий, умный и прямолинейный технический директор.
Твоя задача: классифицировать лида и сформировать следующий шаг воронки.

Стиль: самоуверенно, коротко, с иронией. Без "возможно" и без сюсюканья.
Ты не уговариваешь, ты фильтруешь.

Запрещено:
- извиняться
- быть "службой поддержки"
- обещать "всё что угодно"

Разрешено:
- резать по делу
- ставить рамки
- просить недостающие данные короткими вопросами"""


# ============================================================
# DEVELOPER PROMPT (раздел 4.2 ТЗ) - НЕ ИЗМЕНЯТЬ!
# ============================================================

DEVELOPER_PROMPT = """Входные данные:
- goal: выбранная цель (продажи/заявки/лиды/поддержка/просто бот)
- pain: где ломается (вход/диалог/оплата/интеграции/хаос)
- context: что уже есть (с нуля/после конструктора/есть бот/есть CRM)
- niche_text: ниша+продукт+чек (строка)
- user_last_message: последнее текстовое сообщение пользователя (если есть)

Сделай:
1. Оцени лида: A / B / TRASH
2. Дай скоринг 0..100 и краткое объяснение (1-2 строки)
3. Вытащи требования: список "must_have" (до 6 пунктов)
4. Сформулируй "next_questions" (до 4 коротких вопросов) — только то, что реально нужно
5. Сгенерируй "bot_reply" — текст следующего сообщения пользователю (до 700 символов), дерзкий, но без мата.
6. Определи "route": A_FLOW / B_FLOW / TRASH_FLOW

Правила классификации:
A (70-100): есть понятная цель, бизнес-смысл, чек/маржа, готовность к интеграциям/оплате/воронке, пишет конкретно.
B (40-69): цель есть, но мутно/малый чек/нет ясного оффера/недостаточно данных, возможен прототип.
TRASH (0-39): "просто бот", "дёшево", "как у всех", нет цели/чека/ниши, торг ради торга, хаос без ответственности.

Верни JSON строго в таком виде:
{
  "grade": "A|B|TRASH",
  "score": number,
  "reason": "string",
  "must_have": ["..."],
  "next_questions": ["..."],
  "route": "A_FLOW|B_FLOW|TRASH_FLOW",
  "bot_reply": "string"
}"""


@dataclass
class ScoringResult:
    """Результат LLM скоринга"""
    grade: str  # A/B/TRASH
    score: int  # 0-100
    reason: str
    must_have: list
    next_questions: list
    route: str  # A_FLOW/B_FLOW/TRASH_FLOW
    bot_reply: str
    raw_json: str  # Полный JSON ответ
    success: bool = True
    error: Optional[str] = None


class LLMScoringService:
    """Сервис LLM скоринга лидов"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=config.MEGALLM_API_KEY,
            base_url=config.MEGALLM_BASE_URL,
            max_retries=2,
            timeout=float(config.LLM_TIMEOUT)
        )
        self.model = config.LLM_MODEL
    
    async def score_lead(
        self,
        goal: str,
        pain: str,
        context: str,
        niche_text: str,
        user_last_message: Optional[str] = None
    ) -> ScoringResult:
        """
        Оценивает лида через LLM
        
        Args:
            goal: Выбранная цель (Q1)
            pain: Где ломается (Q2)
            context: Что уже есть (Q3)
            niche_text: Ниша + продукт + чек
            user_last_message: Последнее сообщение пользователя
        
        Returns:
            ScoringResult с оценкой и рекомендациями
        """
        try:
            # Формируем входные данные для LLM
            user_input = self._format_user_input(
                goal, pain, context, niche_text, user_last_message
            )
            
            # Вызываем LLM
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": DEVELOPER_PROMPT + "\n\n" + user_input}
                    ],
                    temperature=0.3,
                    max_tokens=1000
                ),
                timeout=float(config.LLM_TIMEOUT)
            )
            
            # Парсим ответ
            content = response.choices[0].message.content
            result = self._parse_response(content)
            
            logger.info(f"✅ LLM scoring: grade={result.grade}, score={result.score}")
            return result
            
        except asyncio.TimeoutError:
            logger.error("❌ LLM scoring timeout")
            return ScoringResult(
                grade="B",
                score=50,
                reason="Timeout при оценке",
                must_have=[],
                next_questions=[],
                route="B_FLOW",
                bot_reply="Давай уточним детали. Расскажи подробнее о задаче.",
                raw_json="",
                success=False,
                error="timeout"
            )
            
        except Exception as e:
            logger.error(f"❌ LLM scoring error: {e}")
            return ScoringResult(
                grade="B",
                score=50,
                reason=f"Ошибка оценки: {str(e)}",
                must_have=[],
                next_questions=[],
                route="B_FLOW",
                bot_reply="Давай уточним детали. Расскажи подробнее о задаче.",
                raw_json="",
                success=False,
                error=str(e)
            )
    
    def _format_user_input(
        self,
        goal: str,
        pain: str,
        context: str,
        niche_text: str,
        user_last_message: Optional[str]
    ) -> str:
        """Форматирует входные данные для LLM"""
        return f"""Данные лида:
- goal: {goal}
- pain: {pain}
- context: {context}
- niche_text: {niche_text}
- user_last_message: {user_last_message or 'нет'}"""
    
    def _parse_response(self, content: str) -> ScoringResult:
        """Парсит JSON ответ от LLM"""
        try:
            # Пытаемся найти JSON в ответе
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("JSON not found in response")
            
            json_str = content[json_start:json_end]
            data = json.loads(json_str)
            
            # Валидируем обязательные поля
            grade = data.get("grade", "B").upper()
            if grade not in ["A", "B", "TRASH"]:
                grade = "B"
            
            score = int(data.get("score", 50))
            score = max(0, min(100, score))  # Ограничиваем 0-100
            
            route = data.get("route", "B_FLOW")
            if route not in ["A_FLOW", "B_FLOW", "TRASH_FLOW"]:
                # Определяем route по grade
                route = {
                    "A": "A_FLOW",
                    "B": "B_FLOW",
                    "TRASH": "TRASH_FLOW"
                }.get(grade, "B_FLOW")
            
            return ScoringResult(
                grade=grade,
                score=score,
                reason=data.get("reason", ""),
                must_have=data.get("must_have", [])[:6],  # Максимум 6
                next_questions=data.get("next_questions", [])[:4],  # Максимум 4
                route=route,
                bot_reply=data.get("bot_reply", "")[:700],  # Максимум 700 символов
                raw_json=json_str,
                success=True
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            logger.debug(f"Raw content: {content}")
            
            # Fallback - пытаемся извлечь хоть что-то
            return self._fallback_parse(content)
        
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return ScoringResult(
                grade="B",
                score=50,
                reason="Ошибка парсинга ответа",
                must_have=[],
                next_questions=[],
                route="B_FLOW",
                bot_reply="Давай уточним детали.",
                raw_json=content,
                success=False,
                error=str(e)
            )
    
    def _fallback_parse(self, content: str) -> ScoringResult:
        """Fallback парсинг если JSON невалидный"""
        content_lower = content.lower()
        
        # Пытаемся определить grade по ключевым словам
        if "trash" in content_lower or "мусор" in content_lower:
            grade = "TRASH"
            score = 25
            route = "TRASH_FLOW"
        elif '"a"' in content_lower or "grade: a" in content_lower:
            grade = "A"
            score = 75
            route = "A_FLOW"
        else:
            grade = "B"
            score = 50
            route = "B_FLOW"
        
        return ScoringResult(
            grade=grade,
            score=score,
            reason="Fallback оценка",
            must_have=[],
            next_questions=[],
            route=route,
            bot_reply="Давай уточним детали проекта.",
            raw_json=content,
            success=False,
            error="fallback_parse"
        )


# Singleton instance
llm_scoring_service = LLMScoringService()
