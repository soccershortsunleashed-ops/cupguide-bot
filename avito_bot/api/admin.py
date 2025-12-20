"""
Admin API - тестирование и управление ботом
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from avito_bot.services.dialog_orchestrator import dialog_orchestrator
from avito_bot.services.kb_service import kb_service
from avito_bot.services.llm_adapter import llm_adapter
from avito_bot.services.scoring import deterministic_scoring
from avito_bot.models.chat import AvitoChat, ChatState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/avito", tags=["Avito Admin"])


class TestMessageRequest(BaseModel):
    """Запрос на тестовый прогон"""
    message: str
    chat_id: Optional[str] = "test_chat"
    context: Optional[List[str]] = None


class TestMessageResponse(BaseModel):
    """Ответ тестового прогона"""
    reply: str
    intent: str
    score_abc: str
    next_action: str
    slots: dict
    should_create_lead: bool
    deterministic_score: str
    deterministic_confidence: float


class ServiceInfo(BaseModel):
    """Информация об услуге"""
    id: str
    title: str
    price_from: int
    price_is_fixed: bool
    group_name: str


@router.post("/test", response_model=TestMessageResponse)
async def test_message(request: TestMessageRequest):
    """
    Тестовый прогон сообщения
    
    Позволяет проверить работу LLM и скоринга без реального чата
    """
    try:
        # Создаём тестовый чат
        chat = AvitoChat(
            chat_id=request.chat_id,
            user_id="test_user",
            state=ChatState.NEW
        )
        
        # Формируем контекст
        context = None
        if request.context:
            context = [{"direction": "in", "text": msg} for msg in request.context]
        
        # Детерминированный скоринг
        det_result = deterministic_scoring.score_message(request.message)
        
        # Обрабатываем через оркестратор
        result = await dialog_orchestrator.process_message(
            chat=chat,
            user_message=request.message,
            context_messages=context
        )
        
        return TestMessageResponse(
            reply=result.reply,
            intent=result.intent,
            score_abc=result.score_abc,
            next_action=result.next_action,
            slots=result.slots,
            should_create_lead=result.should_create_lead,
            deterministic_score=det_result.score_abc,
            deterministic_confidence=det_result.confidence
        )
        
    except Exception as e:
        logger.error(f"❌ Test error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=List[ServiceInfo])
async def get_services():
    """Получить список услуг из KB"""
    services = kb_service.get_all_services()
    return [
        ServiceInfo(
            id=s["id"],
            title=s["title"],
            price_from=s["price_from"],
            price_is_fixed=s.get("price_is_fixed", False),
            group_name=s.get("group_name", "")
        )
        for s in services
    ]


@router.get("/kb/summary")
async def get_kb_summary():
    """Получить краткое описание KB для LLM"""
    return {
        "summary": kb_service.get_kb_summary_for_llm(),
        "groups": kb_service.get_service_groups(),
        "faq_count": len(kb_service.get_faq()),
        "cases_count": len(kb_service.get_cases())
    }


@router.post("/scoring/test")
async def test_scoring(message: str):
    """Тестирование детерминированного скоринга"""
    result = deterministic_scoring.score_message(message)
    return {
        "score_abc": result.score_abc,
        "confidence": result.confidence,
        "signals_found": result.signals_found,
        "is_dumping": result.is_dumping
    }


@router.post("/llm/test")
async def test_llm(message: str):
    """Тестирование LLM напрямую"""
    try:
        result = await llm_adapter.analyze_message(message)
        return {
            "success": result.success,
            "intent": result.intent,
            "score_abc": result.score_abc,
            "slots": result.slots,
            "reply": result.reply,
            "next_action": result.next_action,
            "latency_ms": result.latency_ms,
            "error": result.error
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/test/batch")
async def test_batch_dialogs():
    """
    Запускает тестирование на наборе диалогов
    Возвращает статистику по intent и score
    """
    from avito_bot.tests.test_dialogs import get_test_dialogs
    
    dialogs = get_test_dialogs()
    results = []
    
    intent_match = 0
    score_match = 0
    total = len(dialogs)
    
    for dialog in dialogs[:20]:  # Ограничиваем для скорости
        try:
            # Детерминированный скоринг
            det_result = deterministic_scoring.score_message(dialog["message"])
            
            # LLM анализ
            llm_result = await llm_adapter.analyze_message(dialog["message"])
            
            # Проверяем совпадение
            intent_ok = llm_result.intent == dialog["expected_intent"]
            score_ok = llm_result.score_abc == dialog["expected_score"]
            
            if intent_ok:
                intent_match += 1
            if score_ok:
                score_match += 1
            
            results.append({
                "id": dialog["id"],
                "message": dialog["message"][:50] + "...",
                "expected_intent": dialog["expected_intent"],
                "actual_intent": llm_result.intent,
                "intent_match": intent_ok,
                "expected_score": dialog["expected_score"],
                "actual_score": llm_result.score_abc,
                "det_score": det_result.score_abc,
                "score_match": score_ok
            })
            
        except Exception as e:
            results.append({
                "id": dialog["id"],
                "error": str(e)
            })
    
    return {
        "total": total,
        "tested": len(results),
        "intent_accuracy": intent_match / len(results) if results else 0,
        "score_accuracy": score_match / len(results) if results else 0,
        "results": results
    }


@router.get("/test/dialogs")
async def get_test_dialogs_list():
    """Возвращает список тестовых диалогов"""
    from avito_bot.tests.test_dialogs import get_test_dialogs
    
    dialogs = get_test_dialogs()
    return {
        "total": len(dialogs),
        "by_intent": {
            "general_interest": len([d for d in dialogs if d["expected_intent"] == "general_interest"]),
            "pricing": len([d for d in dialogs if d["expected_intent"] == "pricing"]),
            "service_question": len([d for d in dialogs if d["expected_intent"] == "service_question"]),
            "comparison": len([d for d in dialogs if d["expected_intent"] == "comparison"]),
            "objection": len([d for d in dialogs if d["expected_intent"] == "objection"]),
            "request_examples": len([d for d in dialogs if d["expected_intent"] == "request_examples"]),
            "handoff_request": len([d for d in dialogs if d["expected_intent"] == "handoff_request"]),
            "offtopic": len([d for d in dialogs if d["expected_intent"] == "offtopic"]),
            "abuse": len([d for d in dialogs if d["expected_intent"] == "abuse"]),
        },
        "by_score": {
            "A": len([d for d in dialogs if d["expected_score"] == "A"]),
            "B": len([d for d in dialogs if d["expected_score"] == "B"]),
            "C": len([d for d in dialogs if d["expected_score"] == "C"]),
        },
        "dialogs": dialogs
    }


@router.post("/masking/test")
async def test_masking(text: str):
    """Тестирование маскирования контактов"""
    from avito_bot.utils.masking import mask_contacts, mask_phone, mask_email, mask_telegram
    
    return {
        "original": text,
        "masked": mask_contacts(text),
        "phone_masked": mask_phone(text),
        "email_masked": mask_email(text),
        "telegram_masked": mask_telegram(text)
    }
