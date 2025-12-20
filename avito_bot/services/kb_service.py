"""
KB Service - сервис базы знаний (прайс, кейсы, FAQ)
"""
import json
import os
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class KBService:
    """Сервис работы с базой знаний"""
    
    def __init__(self):
        self._kb: Optional[Dict[str, Any]] = None
        self._kb_path = Path(__file__).parent.parent / "data" / "kb.json"
    
    def _load_kb(self) -> Dict[str, Any]:
        """Загрузка KB из файла"""
        if self._kb is None:
            try:
                with open(self._kb_path, "r", encoding="utf-8") as f:
                    self._kb = json.load(f)
                logger.info(f"✅ KB loaded: {self._kb.get('version')}")
            except Exception as e:
                logger.error(f"❌ Error loading KB: {e}")
                self._kb = {"service_groups": [], "faq": [], "cases": []}
        return self._kb
    
    def get_all_services(self) -> List[Dict[str, Any]]:
        """Получить все услуги"""
        kb = self._load_kb()
        services = []
        for group in kb.get("service_groups", []):
            for service in group.get("services", []):
                service["group_name"] = group["name"]
                services.append(service)
        return services
    
    def get_service_by_id(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Получить услугу по ID"""
        for service in self.get_all_services():
            if service.get("id") == service_id:
                return service
        return None
    
    def find_services_by_keywords(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """Найти услуги по ключевым словам"""
        keywords_lower = [k.lower() for k in keywords]
        matched = []
        
        for service in self.get_all_services():
            title_lower = service.get("title", "").lower()
            desc_lower = service.get("short_desc", "").lower()
            
            for kw in keywords_lower:
                if kw in title_lower or kw in desc_lower:
                    matched.append(service)
                    break
        
        return matched
    
    def get_service_groups(self) -> List[str]:
        """Получить список групп услуг"""
        kb = self._load_kb()
        return [g["name"] for g in kb.get("service_groups", [])]
    
    def get_services_by_group(self, group_name: str) -> List[Dict[str, Any]]:
        """Получить услуги по группе"""
        kb = self._load_kb()
        for group in kb.get("service_groups", []):
            if group["name"] == group_name:
                return group.get("services", [])
        return []
    
    def get_faq(self) -> List[Dict[str, str]]:
        """Получить FAQ"""
        kb = self._load_kb()
        return kb.get("faq", [])
    
    def get_cases(self) -> List[Dict[str, Any]]:
        """Получить кейсы"""
        kb = self._load_kb()
        return kb.get("cases", [])
    
    def get_style_rules(self) -> Dict[str, Any]:
        """Получить правила стиля"""
        kb = self._load_kb()
        return kb.get("style_rules", {})
    
    def format_service_response(self, service: Dict[str, Any]) -> str:
        """Форматировать ответ по услуге (1-3 абзаца)"""
        title = service.get("title", "")
        desc = service.get("short_desc", "")
        price_from = service.get("price_from", 0)
        is_fixed = service.get("price_is_fixed", False)
        affects = service.get("what_affects_price", [])
        
        # Формат: описание → цена → что влияет
        price_str = f"{price_from:,} ₽".replace(",", " ")
        if is_fixed:
            price_text = f"Стоимость: {price_str} (фикс)."
        else:
            price_text = f"Стоимость: от {price_str}."
        
        affects_text = ""
        if affects:
            affects_text = f" Итог зависит от: {', '.join(affects[:3])}."
        
        return f"{desc}\n\n{price_text}{affects_text}"
    
    def get_kb_summary_for_llm(self) -> str:
        """Получить краткое описание KB для LLM"""
        services = self.get_all_services()
        
        lines = ["Доступные услуги:"]
        for service in services:
            price = service.get("price_from", 0)
            fixed = " (фикс)" if service.get("price_is_fixed") else ""
            lines.append(f"- {service['title']}: от {price:,} ₽{fixed}".replace(",", " "))
        
        return "\n".join(lines)


# Singleton
kb_service = KBService()
