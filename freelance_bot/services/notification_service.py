"""
Notification Service - уведомления владельцу о новых лидах
"""
import logging
from datetime import datetime, time
from typing import Optional, Dict, Any

from aiogram import Bot

from freelance_bot.config import config

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис уведомлений владельцу"""
    
    def __init__(self):
        self.owner_id = config.OWNER_TELEGRAM_ID
        self.notify_on_a = config.NOTIFY_ON_A_LEAD
        self.notify_on_b = config.NOTIFY_ON_B_LEAD
        self.notify_on_trash = config.NOTIFY_ON_TRASH
        self.quiet_start = config.QUIET_HOURS_START
        self.quiet_end = config.QUIET_HOURS_END
    
    def _is_quiet_hours(self) -> bool:
        """Проверяет, сейчас ли тихие часы"""
        now = datetime.now().time()
        quiet_start = time(self.quiet_start, 0)
        quiet_end = time(self.quiet_end, 0)
        
        # Если тихие часы переходят через полночь (23:00 - 08:00)
        if quiet_start > quiet_end:
            return now >= quiet_start or now < quiet_end
        else:
            return quiet_start <= now < quiet_end
    
    async def notify_new_lead(self, bot: Bot, lead_data: Dict[str, Any]) -> bool:
        """
        Отправляет уведомление о новом лиде
        
        Args:
            bot: Экземпляр бота
            lead_data: Данные лида
        
        Returns:
            True если уведомление отправлено
        """
        if not self.owner_id:
            logger.warning("Owner ID not configured, skipping notification")
            return False
        
        grade = lead_data.get("llm_grade", "B")
        route = lead_data.get("final_route", "B_FLOW")
        
        # Проверяем, нужно ли уведомлять
        should_notify = False
        priority = "MEDIUM"
        
        if grade == "A" and self.notify_on_a:
            should_notify = True
            priority = "HIGH"
        elif grade == "B" and self.notify_on_b:
            should_notify = True
            priority = "MEDIUM"
        elif grade == "TRASH" and self.notify_on_trash:
            should_notify = True
            priority = "LOW"
        
        if not should_notify:
            logger.debug(f"Notification skipped for grade={grade}")
            return False
        
        # Проверяем тихие часы (кроме A-лидов)
        if grade != "A" and self._is_quiet_hours():
            logger.info(f"Quiet hours, notification delayed for grade={grade}")
            # TODO: Сохранить для отложенной отправки
            return False
        
        # Формируем сообщение
        message = self._format_notification(lead_data, priority)
        
        try:
            await bot.send_message(
                chat_id=self.owner_id,
                text=message,
                parse_mode="HTML"
            )
            logger.info(f"✅ Notification sent to owner for {grade} lead")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")
            return False
    
    def _format_notification(self, lead_data: Dict[str, Any], priority: str) -> str:
        """Форматирует уведомление"""
        grade = lead_data.get("llm_grade", "?")
        score = lead_data.get("llm_score", "?")
        route = lead_data.get("final_route", "?")
        
        # Эмодзи по приоритету
        priority_emoji = {
            "HIGH": "🔴",
            "MEDIUM": "🟡",
            "LOW": "⚪"
        }.get(priority, "⚪")
        
        # Эмодзи по грейду
        grade_emoji = {
            "A": "⭐",
            "B": "📊",
            "TRASH": "🗑️"
        }.get(grade, "❓")
        
        lines = [
            f"{priority_emoji} <b>Новый лид!</b> {grade_emoji}",
            "",
            f"📊 Грейд: <b>{grade}</b> ({score}/100)",
            f"🚦 Маршрут: {route}",
        ]
        
        # Данные пользователя
        username = lead_data.get("username")
        first_name = lead_data.get("first_name", "")
        telegram_id = lead_data.get("telegram_user_id")
        
        if username:
            lines.append(f"👤 @{username}")
        elif first_name:
            lines.append(f"👤 {first_name}")
        
        if telegram_id:
            lines.append(f"🆔 {telegram_id}")
        
        # Скрининг
        goal = lead_data.get("goal_label") or lead_data.get("goal")
        pain = lead_data.get("pain_label") or lead_data.get("pain")
        context = lead_data.get("context_label") or lead_data.get("context")
        niche = lead_data.get("niche_text", "")[:100]
        
        if goal or pain or context:
            lines.append("")
            lines.append("📋 <b>Скрининг:</b>")
            if goal:
                lines.append(f"  • Цель: {goal}")
            if pain:
                lines.append(f"  • Боль: {pain}")
            if context:
                lines.append(f"  • Контекст: {context}")
            if niche:
                lines.append(f"  • Ниша: {niche}")
        
        # LLM анализ
        reason = lead_data.get("llm_reason", "")
        if reason:
            lines.append("")
            lines.append(f"🧠 <b>Анализ:</b> {reason[:200]}")
        
        # Контакт
        contact = lead_data.get("contact_preferred")
        if contact:
            lines.append("")
            lines.append(f"📞 <b>Контакт:</b> {contact}")
        
        # Источник
        source_type = lead_data.get("source_type")
        if source_type == "autopost":
            channel_id = lead_data.get("source_channel_id")
            lines.append("")
            lines.append(f"📢 Источник: автопост (канал {channel_id})")
        
        return "\n".join(lines)
    
    async def notify_application(self, bot: Bot, lead_data: Dict[str, Any], 
                                  app_data: Dict[str, Any]) -> bool:
        """Уведомление о новой заявке"""
        if not self.owner_id:
            return False
        
        grade = lead_data.get("llm_grade", "B")
        
        lines = [
            "📝 <b>Новая заявка!</b>",
            "",
            f"📊 Грейд: <b>{grade}</b>",
        ]
        
        # Контакт
        contact = app_data.get("contact_preferred")
        if contact:
            lines.append(f"📞 Контакт: {contact}")
        
        # Платформа
        platform = app_data.get("bot_platform")
        if platform:
            lines.append(f"📱 Платформа: {platform}")
        
        # Окно старта
        start_window = app_data.get("start_window")
        if start_window:
            lines.append(f"📅 Старт: {start_window}")
        
        # Ссылка
        link = app_data.get("project_link")
        if link:
            lines.append(f"🔗 Ссылка: {link}")
        
        try:
            await bot.send_message(
                chat_id=self.owner_id,
                text="\n".join(lines),
                parse_mode="HTML"
            )
            logger.info("✅ Application notification sent")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send application notification: {e}")
            return False


# Singleton instance
notification_service = NotificationService()
