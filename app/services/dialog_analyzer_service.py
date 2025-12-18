import os
import json
import logging
from typing import List, Dict, Any
from app.core.config import settings
from app.services.llm_service import llm_service
from app.models.contact_insight import ContactInsight
from app.services.whatsapp_message_service import whatsapp_message_service
from app.services.contact_service import contact_service

logger = logging.getLogger(__name__)


class DialogAnalyzerService:
    """Service for analyzing customer dialogs using LLM (OpenAI or Gemini)"""
    
    def __init__(self):
        self.configured = False
    
    async def _ensure_configured(self):
        """Проверяет, что LLM сервис настроен"""
        await llm_service._ensure_client()
        self.configured = llm_service.configured
        if not self.configured:
            logger.warning("LLM service not configured. Dialog analysis will not work.")
    
    async def analyze_contact_dialogs(self, contact_id: int) -> ContactInsight:
        """
        Analyze all dialogs with a contact and generate insights
        
        Args:
            contact_id: ID of the contact to analyze
            
        Returns:
            ContactInsight with AI-generated summary, tags, and dialog history
        """
        await self._ensure_configured()
        if not self.configured:
             raise ValueError("LLM is not configured")

        # Get contact info
        contact = await contact_service.get_contact_by_id(contact_id)
        if not contact:
            raise ValueError(f"Contact {contact_id} not found")
        
        # Get WhatsApp messages
        messages = await self._get_contact_messages(contact.phone)
        
        if not messages:
            # No messages found, return empty insights
            return ContactInsight(
                contact_id=contact_id,
                summary="Нет истории диалогов для анализа",
                tags=[],
                from_dialogs=""
            )
        
        # Build analysis prompt
        prompt = self._build_analysis_prompt(messages, contact.name or "Клиент")
        
        # Call OpenAI API
        try:
            response = await self._call_openai(prompt)
            analysis_result = self._parse_ai_response(response)
            
            # Create ContactInsight from analysis
            insight = ContactInsight(
                contact_id=contact_id,
                summary=analysis_result.get("summary", ""),
                tags=analysis_result.get("tags", []),
                from_dialogs=analysis_result.get("from_dialogs", ""),
                manually_edited=False
            )
            
            logger.info(f"Successfully analyzed dialogs for contact {contact_id}")
            return insight
            
        except Exception as e:
            logger.error(f"Error analyzing dialogs for contact {contact_id}: {e}")
            raise
    
    async def _get_contact_messages(self, phone: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get WhatsApp messages for a contact"""
        # Get all messages
        all_messages = await whatsapp_message_service.get_messages()
        
        # Filter messages by phone number
        contact_messages = []
        for msg in all_messages:
            # Check if message is from or to this contact
            if phone in msg.chat_name or (msg.sender and phone in msg.sender):
                contact_messages.append({
                    "date": msg.date,
                    "sender": msg.sender or "Менеджер",
                    "text": msg.text
                })
        
        # Sort by date and limit
        contact_messages.sort(key=lambda x: x["date"])
        return contact_messages[-limit:]  # Last N messages
    
    def _build_analysis_prompt(self, messages: List[Dict[str, Any]], contact_name: str) -> str:
        """Build prompt for OpenAI analysis"""
        # Format messages for prompt
        dialog_text = ""
        for msg in messages:
            sender = msg["sender"]
            text = msg["text"]
            dialog_text += f"{sender}: {text}\n"
        
        prompt = f"""Ты - AI ассистент для CRM-системы спортивной организации.

Проанализируй диалог с клиентом по имени "{contact_name}" и извлеки следующую информацию:

1. **Краткая информация о потребностях клиента** (summary) - 1-2 предложения о том, что ищет клиент
2. **Теги для сегментации** (tags) - ключевые слова (город, вид спорта, возраст, тип мероприятия и т.д.)
3. **История запросов** (from_dialogs) - краткое перечисление основных запросов из диалога

**Диалог:**
{dialog_text}

**Верни ответ СТРОГО в формате JSON:**
{{
  "summary": "Краткое описание потребностей клиента",
  "tags": ["тег1", "тег2", "тег3"],
  "from_dialogs": "Основные запросы из диалога"
}}

Если диалог не содержит полезной информации о потребностях клиента, верни:
{{
  "summary": "Общение без конкретных запросов",
  "tags": [],
  "from_dialogs": "Нет конкретных запросов"
}}
"""
        return prompt
    
    
    def _parse_ai_response(self, response: str) -> Dict[str, Any]:
        """Parse OpenAI response and extract structured data"""
        try:
            # Try to parse JSON from response
            # Sometimes GPT wraps JSON in markdown code blocks
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]  # Remove ```json
            if response.startswith("```"):
                response = response[3:]  # Remove ```
            if response.endswith("```"):
                response = response[:-3]  # Remove trailing ```
            
            response = response.strip()
            data = json.loads(response)
            
            return {
                "summary": data.get("summary", ""),
                "tags": data.get("tags", []),
                "from_dialogs": data.get("from_dialogs", "")
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"Response was: {response}")
            # Return default values
            return {
                "summary": "Ошибка обработки ответа AI",
                "tags": [],
                "from_dialogs": ""
            }


# Singleton instance
dialog_analyzer_service = DialogAnalyzerService()
