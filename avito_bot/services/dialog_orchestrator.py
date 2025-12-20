"""
Dialog Orchestrator - сценарный контроллер диалогов
Логика из ТЗ раздел 13
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from avito_bot.services.llm_adapter import llm_adapter, LLMResponse
from avito_bot.services.scoring import deterministic_scoring
from avito_bot.services.kb_service import kb_service
from avito_bot.models.chat import AvitoChat, ChatState
from avito_bot.models.nlp_event import Intent, ScoreABC, NextAction
from avito_bot.utils.masking import safe_log

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Результат обработки сообщения"""
    reply: str
    next_action: str
    score_abc: str
    intent: str
    slots: Dict[str, Any]
    should_create_lead: bool = False
    lead_payload: Optional[Dict[str, Any]] = None
    fallback_contact_request: bool = False


class DialogOrchestrator:
    """Сценарный контроллер диалогов"""
    
    # Шаблоны ответов (из ТЗ раздел 13)
    TEMPLATES = {
        "general_interest": (
            "Добрый день. Помогаю с разработкой (боты, автоматизация, интеграции) "
            "и с CRM-сценариями (воронки, роботы, миграции).\n\n"
            "Подскажите, что актуальнее и к какому сроку нужен результат?"
        ),
        "pricing": (
            "Стоимость зависит от объёма и интеграций. {service_info}\n\n"
            "Уточните, пожалуйста: что нужно на выходе и нужна ли интеграция/CRM?"
        ),
        "comparison": (
            "\"Бот за 2к\" чаще всего отвечает шаблонами и не умеет квалифицировать.\n\n"
            "Продающий бот — это сценарии, вопросы по делу, привязка к прайсу "
            "и автосоздание лида в CRM.\n\n"
            "Вам важнее быстро запуститься или повысить конверсию?"
        ),
        "objection_expensive": (
            "Понимаю. Цена отражает результат: сценарии продаж, интеграции, аналитика.\n\n"
            "Можем начать с MVP — базовый функционал, потом расширить.\n\n"
            "Что для вас приоритетнее: скорость запуска или полный функционал?"
        ),
        "request_examples": (
            "Есть реализованные проекты: лид-воронки с AI-скорингом, "
            "интеграции с CRM, автоответчики.\n\n"
            "Какой тип примера интересует: бот, CRM-автоматизация или интеграции?"
        ),
        "handoff_request": (
            "Понял. Зафиксирую запрос как лид в CRM, чтобы согласовать сроки "
            "и точную вилку по стоимости.\n\n"
            "Уточните, пожалуйста, к какому сроку нужен результат "
            "и нужна ли интеграция с внешними сервисами/API?"
        ),
        "crm_fallback": (
            "Похоже, сейчас CRM временно недоступна.\n\n"
            "Можете оставить номер телефона или Telegram-ник? "
            "Зафиксирую заявку вручную и вернусь с предложением."
        ),
        "offtopic": (
            "Давайте вернёмся к теме. Помогаю с разработкой ботов, "
            "автоматизацией и CRM.\n\n"
            "Что из этого вас интересует?"
        ),
        "abuse": (
            "Предлагаю продолжить в конструктивном тоне. "
            "Если есть вопросы по услугам — готов помочь."
        )
    }
    
    async def process_message(
        self,
        chat: AvitoChat,
        user_message: str,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> OrchestratorResult:
        """
        Обрабатывает входящее сообщение и генерирует ответ
        
        Args:
            chat: Текущий чат
            user_message: Сообщение клиента
            context_messages: История диалога
        
        Returns:
            OrchestratorResult с ответом и действиями
        """
        # 1. Детерминированный скоринг
        det_result = deterministic_scoring.score_message(user_message, chat.slots)
        
        # 2. LLM анализ
        llm_result = await llm_adapter.analyze_message(
            user_message=user_message,
            context_messages=context_messages,
            current_slots=chat.slots
        )
        
        # 3. Сравниваем скоры
        match, comparison_note = deterministic_scoring.compare_with_llm(
            det_result.score_abc, 
            llm_result.score_abc
        )
        if not match:
            logger.info(f"📊 {comparison_note}")
        
        # 4. Используем LLM скор (он точнее)
        final_score = llm_result.score_abc
        
        # 5. Обрабатываем по сценарию
        result = await self._handle_scenario(
            chat=chat,
            llm_result=llm_result,
            det_result=det_result,
            final_score=final_score
        )
        
        # Логируем с маскированием
        logger.info(f"📝 Processed: intent={result.intent}, score={result.score_abc}, msg={safe_log(user_message, 50)}")
        
        return result
    
    async def _handle_scenario(
        self,
        chat: AvitoChat,
        llm_result: LLMResponse,
        det_result,
        final_score: str
    ) -> OrchestratorResult:
        """Обрабатывает сценарий по интенту и скору"""
        
        intent = llm_result.intent
        next_action = llm_result.next_action
        
        # Определяем, нужно ли создавать лид
        should_create_lead = False
        lead_payload = None
        
        if next_action == "create_crm_lead":
            should_create_lead = True
            lead_payload = llm_result.lead_payload or self._build_lead_payload(
                chat, llm_result, final_score
            )
        elif final_score == "A" and intent == "handoff_request":
            should_create_lead = True
            lead_payload = self._build_lead_payload(chat, llm_result, final_score)
        
        # Выбираем ответ
        reply = llm_result.reply
        
        # Если LLM не дал ответ, используем шаблон
        if not reply or llm_result.error:
            reply = self._get_template_reply(intent, llm_result.slots)
        
        # Обработка abuse/offtopic
        if intent == "abuse":
            reply = self.TEMPLATES["abuse"]
            should_create_lead = False
        elif intent == "offtopic":
            reply = self.TEMPLATES["offtopic"]
        
        return OrchestratorResult(
            reply=reply,
            next_action=next_action,
            score_abc=final_score,
            intent=intent,
            slots=llm_result.slots,
            should_create_lead=should_create_lead,
            lead_payload=lead_payload
        )
    
    def _get_template_reply(self, intent: str, slots: Dict[str, Any]) -> str:
        """Получает шаблонный ответ по интенту"""
        
        if intent == "pricing":
            # Подставляем информацию об услуге
            service_id = slots.get("service_id")
            service_info = ""
            if service_id:
                service = kb_service.get_service_by_id(service_id)
                if service:
                    service_info = kb_service.format_service_response(service)
            
            if not service_info:
                service_info = "Базово: разработка чат-ботов — от 5 000 ₽."
            
            return self.TEMPLATES["pricing"].format(service_info=service_info)
        
        return self.TEMPLATES.get(intent, self.TEMPLATES["general_interest"])
    
    def _build_lead_payload(
        self, 
        chat: AvitoChat, 
        llm_result: LLMResponse,
        score_abc: str
    ) -> Dict[str, Any]:
        """Формирует payload для создания лида"""
        
        slots = llm_result.slots or {}
        
        # Формируем summary
        service_group = slots.get("service_group", "unknown")
        service_id = slots.get("service_id")
        deadline = slots.get("deadline")
        integrations = slots.get("integrations", [])
        
        summary_parts = []
        if service_group != "unknown":
            summary_parts.append(f"Интерес к {service_group}")
        if service_id:
            service = kb_service.get_service_by_id(service_id)
            if service:
                summary_parts.append(f"услуга: {service['title']}")
        if deadline:
            summary_parts.append(f"срок: {deadline}")
        if integrations:
            summary_parts.append(f"интеграции: {', '.join(integrations)}")
        
        summary = ". ".join(summary_parts) if summary_parts else "Общий интерес к услугам"
        
        # Формируем комментарий для владельца
        comment = self._generate_owner_comment(score_abc, slots)
        
        return {
            "service_group": service_group,
            "service_id": service_id,
            "deadline": deadline,
            "integrations": integrations,
            "summary": summary,
            "score_abc": score_abc,
            "comment": comment,
            "source": "avito",
            "chat_id": chat.chat_id,
            "item_id": chat.item_id
        }
    
    def _generate_owner_comment(self, score_abc: str, slots: Dict[str, Any]) -> str:
        """Генерирует подсказку для владельца"""
        
        if score_abc == "A":
            return "Горячий лид. Готов к обсуждению деталей и оплате."
        elif score_abc == "B":
            if not slots.get("deadline"):
                return "Тёплый лид. Уточнить сроки и бюджет."
            if not slots.get("integrations"):
                return "Тёплый лид. Уточнить нужные интеграции."
            return "Тёплый лид. Нужно 1-2 уточнения."
        else:
            return "Холодный лид. Возможно, вернётся позже."
    
    def handle_crm_error(self, chat: AvitoChat) -> OrchestratorResult:
        """Обработка ошибки CRM — запрос резервного контакта"""
        return OrchestratorResult(
            reply=self.TEMPLATES["crm_fallback"],
            next_action="request_backup_contact",
            score_abc=chat.current_score or "B",
            intent="handoff_request",
            slots=chat.slots or {},
            should_create_lead=False,
            fallback_contact_request=True
        )


# Singleton
dialog_orchestrator = DialogOrchestrator()
