"""
LLM Adapter - клиент MegaLLM для Avito Bot
JSON-схема ответа из ТЗ раздел 11
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

import openai

from avito_bot.config import config
from avito_bot.services.kb_service import kb_service

logger = logging.getLogger(__name__)

# Загружаем system prompt
SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.txt"
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
except Exception:
    SYSTEM_PROMPT = "Ты — менеджер IT-услуг. Отвечай профессионально, без смайликов."


# JSON-схема ответа (из ТЗ раздел 11)
RESPONSE_SCHEMA = """
Верни JSON строго в таком формате:
{
  "intent": "general_interest|pricing|service_question|comparison|objection|request_examples|handoff_request|offtopic|abuse",
  "score_abc": "A|B|C",
  "slots": {
    "service_group": "Программирование|CRM-системы|unknown",
    "service_id": "string или null",
    "deadline": "string или null",
    "integrations": ["список строк"],
    "budget_hint": "string или null"
  },
  "reply": "текст ответа клиенту (1-3 абзаца)",
  "next_action": "ask_qualifying_questions|give_price_from_and_explain|create_crm_lead|handoff_manager|request_backup_contact|close",
  "lead_payload": {
    "service_group": "string",
    "service_id": "string или null",
    "deadline": "string или null",
    "integrations": ["список"],
    "summary": "1-2 предложения о задаче клиента",
    "score_abc": "A|B|C",
    "comment": "подсказка владельцу"
  }
}
"""


@dataclass
class LLMResponse:
    """Результат LLM-анализа"""
    intent: str
    score_abc: str
    slots: Dict[str, Any]
    reply: str
    next_action: str
    lead_payload: Optional[Dict[str, Any]] = None
    raw_json: str = ""
    success: bool = True
    error: Optional[str] = None
    latency_ms: int = 0


class LLMAdapter:
    """Адаптер для MegaLLM"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=config.MEGALLM_API_KEY,
            base_url=config.MEGALLM_BASE_URL,
            max_retries=2,
            timeout=float(config.LLM_TIMEOUT)
        )
        self.model = config.MEGALLM_MODEL
    
    async def analyze_message(
        self,
        user_message: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
        current_slots: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Анализирует сообщение клиента и генерирует ответ
        
        Args:
            user_message: Текст сообщения клиента
            context_messages: История диалога (последние N сообщений)
            current_slots: Текущие собранные слоты
        
        Returns:
            LLMResponse с intent, slots, reply, next_action
        """
        import time
        start_time = time.time()
        
        try:
            # Формируем контекст
            kb_summary = kb_service.get_kb_summary_for_llm()
            
            user_prompt = self._build_user_prompt(
                user_message, 
                context_messages, 
                current_slots,
                kb_summary
            )
            
            # Вызываем LLM
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1500
                ),
                timeout=float(config.LLM_TIMEOUT)
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Парсим ответ
            content = response.choices[0].message.content
            result = self._parse_response(content)
            result.latency_ms = latency_ms
            
            logger.info(f"✅ LLM: intent={result.intent}, score={result.score_abc}, latency={latency_ms}ms")
            return result
            
        except asyncio.TimeoutError:
            logger.error("❌ LLM timeout")
            return self._fallback_response("timeout")
            
        except Exception as e:
            logger.error(f"❌ LLM error: {e}")
            return self._fallback_response(str(e))
    
    def _build_user_prompt(
        self,
        user_message: str,
        context_messages: Optional[List[Dict[str, str]]],
        current_slots: Optional[Dict[str, Any]],
        kb_summary: str
    ) -> str:
        """Формирует промпт для LLM"""
        
        # Контекст диалога
        context_str = ""
        if context_messages:
            context_lines = []
            for msg in context_messages[-5:]:  # Последние 5 сообщений
                direction = "Клиент" if msg.get("direction") == "in" else "Менеджер"
                context_lines.append(f"{direction}: {msg.get('text', '')}")
            context_str = "\n".join(context_lines)
        
        # Текущие слоты
        slots_str = ""
        if current_slots:
            slots_str = f"Уже известно о клиенте: {json.dumps(current_slots, ensure_ascii=False)}"
        
        prompt = f"""
{kb_summary}

{f"История диалога:{chr(10)}{context_str}" if context_str else ""}

{slots_str}

Новое сообщение клиента:
{user_message}

{RESPONSE_SCHEMA}
"""
        return prompt.strip()
    
    def _parse_response(self, content: str) -> LLMResponse:
        """Парсит JSON ответ от LLM"""
        try:
            # Убираем markdown если есть
            clean_content = content.strip()
            if clean_content.startswith("```json"):
                clean_content = clean_content[7:]
            if clean_content.startswith("```"):
                clean_content = clean_content[3:]
            if clean_content.endswith("```"):
                clean_content = clean_content[:-3]
            clean_content = clean_content.strip()
            
            # Ищем JSON
            json_start = clean_content.find("{")
            json_end = clean_content.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("JSON not found")
            
            json_str = clean_content[json_start:json_end]
            data = json.loads(json_str)
            
            # Валидируем и нормализуем
            intent = self._validate_intent(data.get("intent", "general_interest"))
            score_abc = self._validate_score(data.get("score_abc", "B"))
            next_action = self._validate_action(data.get("next_action", "ask_qualifying_questions"))
            
            return LLMResponse(
                intent=intent,
                score_abc=score_abc,
                slots=data.get("slots", {}),
                reply=data.get("reply", "Уточните, пожалуйста, вашу задачу."),
                next_action=next_action,
                lead_payload=data.get("lead_payload"),
                raw_json=json_str,
                success=True
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            return self._fallback_response(f"json_error: {e}")
        
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return self._fallback_response(str(e))
    
    def _validate_intent(self, intent: str) -> str:
        """Валидация интента"""
        valid_intents = [
            "general_interest", "pricing", "service_question", "comparison",
            "objection", "request_examples", "handoff_request", "offtopic", "abuse"
        ]
        return intent if intent in valid_intents else "general_interest"
    
    def _validate_score(self, score: str) -> str:
        """Валидация скоринга"""
        return score.upper() if score.upper() in ["A", "B", "C"] else "B"
    
    def _validate_action(self, action: str) -> str:
        """Валидация действия"""
        valid_actions = [
            "ask_qualifying_questions", "give_price_from_and_explain",
            "create_crm_lead", "handoff_manager", "request_backup_contact", "close"
        ]
        return action if action in valid_actions else "ask_qualifying_questions"
    
    def _fallback_response(self, error: str) -> LLMResponse:
        """Fallback ответ при ошибке"""
        return LLMResponse(
            intent="general_interest",
            score_abc="B",
            slots={},
            reply="Подскажите, пожалуйста, что именно вас интересует? Помогу разобраться с задачей.",
            next_action="ask_qualifying_questions",
            raw_json="",
            success=False,
            error=error
        )


# Singleton
llm_adapter = LLMAdapter()
