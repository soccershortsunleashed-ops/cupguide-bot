"""
Сервис для управления Премиум-размещением турниров
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from app.services.tournament_service import tournament_service
from app.models.tournament import Tournament

logger = logging.getLogger(__name__)

# Константы цен и сроков
PREMIUM_DURATION_DAYS = 7
PREMIUM_PRICE = 3000  # ₽
PREMIUM_EXTEND_PRICE = 2000  # ₽ за 7 дней
PREMIUM_DAY_PRICE = 500  # ₽ за 1 день
COOLDOWN_HOURS = 24  # Часов ожидания после окончания


class PremiumService:
    """Сервис управления Премиум-размещением"""
    
    def __init__(self):
        pass
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Парсит строку даты в datetime"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except:
                return None
    
    def _format_date(self, dt: datetime) -> str:
        """Форматирует datetime в строку YYYY-MM-DD"""
        return dt.strftime('%Y-%m-%d')
    
    def _format_date_display(self, dt: datetime) -> str:
        """Форматирует datetime для отображения DD.MM.YYYY"""
        return dt.strftime('%d.%m.%Y')
    
    def is_premium_active(self, tournament: Tournament) -> bool:
        """Проверяет, активен ли Премиум"""
        if not tournament.is_premium:
            return False
        
        premium_until = self._parse_date(tournament.premium_until)
        if not premium_until:
            return False
        
        return premium_until >= datetime.now()
    
    def can_extend_premium(self, tournament: Tournament) -> bool:
        """Проверяет, можно ли продлить Премиум"""
        return self.is_premium_active(tournament)
    
    def can_buy_premium(self, tournament: Tournament) -> Dict[str, Any]:
        """
        Проверяет, можно ли купить Премиум.
        Возвращает dict с полями:
        - can_buy: bool
        - reason: str (если нельзя)
        - available_at: datetime (когда будет доступно, если нельзя)
        """
        # Если Премиум активен - покупка не нужна
        if self.is_premium_active(tournament):
            return {
                "can_buy": False,
                "reason": "premium_active",
                "message": "Премиум уже активен"
            }
        
        # Проверяем 24-часовое ограничение
        premium_last_ended = self._parse_date(tournament.premium_last_ended)
        if premium_last_ended:
            cooldown_end = premium_last_ended + timedelta(hours=COOLDOWN_HOURS)
            if datetime.now() < cooldown_end:
                return {
                    "can_buy": False,
                    "reason": "cooldown",
                    "message": f"Новая покупка будет доступна через 24 часа после окончания предыдущего периода",
                    "available_at": cooldown_end,
                    "available_at_display": self._format_date_display(cooldown_end)
                }
        
        return {"can_buy": True}
    
    async def activate_premium(self, tournament_id: int) -> Dict[str, Any]:
        """
        Активирует Премиум на 7 дней.
        Цена: 3000 ₽
        """
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            return {"success": False, "error": "Турнир не найден"}
        
        # Проверяем возможность покупки
        can_buy = self.can_buy_premium(tournament)
        if not can_buy["can_buy"]:
            return {"success": False, **can_buy}
        
        # Активируем Премиум
        premium_until = datetime.now() + timedelta(days=PREMIUM_DURATION_DAYS)
        
        await tournament_service.update_tournament(tournament_id, {
            "is_premium": True,
            "premium_until": self._format_date(premium_until)
        })
        
        logger.info(f"✅ Premium activated for tournament {tournament_id} until {premium_until}")
        
        return {
            "success": True,
            "action": "activated",
            "premium_until": self._format_date(premium_until),
            "premium_until_display": self._format_date_display(premium_until),
            "price": PREMIUM_PRICE,
            "message": f"🔝 Премиум активирован до {self._format_date_display(premium_until)}"
        }
    
    async def extend_premium_7days(self, tournament_id: int) -> Dict[str, Any]:
        """
        Продлевает Премиум на 7 дней.
        Цена: 2000 ₽
        Условие: Премиум должен быть активен
        """
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            return {"success": False, "error": "Турнир не найден"}
        
        if not self.can_extend_premium(tournament):
            return {
                "success": False,
                "error": "extend_not_available",
                "message": "Продление доступно только при активном Премиуме"
            }
        
        # Продлеваем от текущей даты окончания
        current_until = self._parse_date(tournament.premium_until)
        new_until = current_until + timedelta(days=PREMIUM_DURATION_DAYS)
        
        await tournament_service.update_tournament(tournament_id, {
            "premium_until": self._format_date(new_until)
        })
        
        logger.info(f"✅ Premium extended for tournament {tournament_id} until {new_until}")
        
        return {
            "success": True,
            "action": "extended_7days",
            "premium_until": self._format_date(new_until),
            "premium_until_display": self._format_date_display(new_until),
            "price": PREMIUM_EXTEND_PRICE,
            "message": f"🔄 Премиум продлён до {self._format_date_display(new_until)}"
        }
    
    async def extend_premium_1day(self, tournament_id: int) -> Dict[str, Any]:
        """
        Докупает 1 день Премиума.
        Цена: 500 ₽
        Условие: Премиум должен быть активен
        """
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            return {"success": False, "error": "Турнир не найден"}
        
        if not self.can_extend_premium(tournament):
            return {
                "success": False,
                "error": "extend_not_available",
                "message": "Докупка дней доступна только при активном Премиуме"
            }
        
        # Добавляем 1 день
        current_until = self._parse_date(tournament.premium_until)
        new_until = current_until + timedelta(days=1)
        
        await tournament_service.update_tournament(tournament_id, {
            "premium_until": self._format_date(new_until)
        })
        
        logger.info(f"✅ Premium extended by 1 day for tournament {tournament_id} until {new_until}")
        
        return {
            "success": True,
            "action": "extended_1day",
            "premium_until": self._format_date(new_until),
            "premium_until_display": self._format_date_display(new_until),
            "price": PREMIUM_DAY_PRICE,
            "message": f"➕ Добавлен 1 день. Премиум до {self._format_date_display(new_until)}"
        }
    
    async def deactivate_premium(self, tournament_id: int, admin: bool = False) -> Dict[str, Any]:
        """
        Отключает Премиум досрочно (только для админа).
        """
        if not admin:
            return {"success": False, "error": "Только администратор может отключить Премиум"}
        
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            return {"success": False, "error": "Турнир не найден"}
        
        # Сохраняем дату окончания для 24ч ограничения
        premium_until = tournament.premium_until
        
        await tournament_service.update_tournament(tournament_id, {
            "is_premium": False,
            "premium_until": None,
            "premium_last_ended": premium_until or self._format_date(datetime.now())
        })
        
        logger.info(f"✅ Premium deactivated for tournament {tournament_id} by admin")
        
        return {
            "success": True,
            "action": "deactivated",
            "message": "Премиум отключён"
        }
    
    async def admin_set_premium(
        self, 
        tournament_id: int, 
        is_premium: bool,
        premium_until: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Админ-управление Премиумом: включить/выключить, задать дату вручную.
        """
        tournament = await tournament_service.get_tournament_by_id(tournament_id)
        if not tournament:
            return {"success": False, "error": "Турнир не найден"}
        
        updates = {"is_premium": is_premium}
        
        if is_premium:
            if premium_until:
                updates["premium_until"] = premium_until
            else:
                # По умолчанию +7 дней
                updates["premium_until"] = self._format_date(
                    datetime.now() + timedelta(days=PREMIUM_DURATION_DAYS)
                )
        else:
            # При отключении сохраняем дату для 24ч ограничения
            if tournament.premium_until:
                updates["premium_last_ended"] = tournament.premium_until
            updates["premium_until"] = None
        
        await tournament_service.update_tournament(tournament_id, updates)
        
        logger.info(f"✅ Admin set premium for tournament {tournament_id}: is_premium={is_premium}, until={updates.get('premium_until')}")
        
        return {
            "success": True,
            "is_premium": is_premium,
            "premium_until": updates.get("premium_until"),
            "message": "Премиум обновлён администратором"
        }
    
    def get_premium_status(self, tournament: Tournament) -> Dict[str, Any]:
        """
        Получает полный статус Премиума для турнира.
        """
        is_active = self.is_premium_active(tournament)
        can_extend = self.can_extend_premium(tournament)
        can_buy_result = self.can_buy_premium(tournament)
        
        premium_until = self._parse_date(tournament.premium_until)
        premium_last_ended = self._parse_date(tournament.premium_last_ended)
        
        # Определяем статус
        if is_active:
            status = "active"
            status_message = f"🔝 Премиум-размещение активно до {self._format_date_display(premium_until)}"
        elif premium_last_ended:
            cooldown_end = premium_last_ended + timedelta(hours=COOLDOWN_HOURS)
            if datetime.now() < cooldown_end:
                status = "cooldown"
                status_message = f"⏳ Премиум недавно завершился. Новая покупка доступна с {self._format_date_display(cooldown_end)}"
            else:
                status = "inactive"
                status_message = "ℹ️ Премиум-размещение не активно"
        else:
            status = "inactive"
            status_message = "ℹ️ Премиум-размещение не активно"
        
        # Доступные действия
        available_actions = []
        if is_active:
            available_actions.append({
                "action": "extend_7days",
                "label": "🔄 Продлить на 7 дней",
                "price": PREMIUM_EXTEND_PRICE
            })
            available_actions.append({
                "action": "extend_1day",
                "label": "➕ Докупить 1 день",
                "price": PREMIUM_DAY_PRICE
            })
        elif can_buy_result["can_buy"]:
            available_actions.append({
                "action": "activate",
                "label": "🔝 Купить Премиум (7 дней)",
                "price": PREMIUM_PRICE
            })
        
        return {
            "is_active": is_active,
            "status": status,
            "status_message": status_message,
            "premium_until": self._format_date(premium_until) if premium_until else None,
            "premium_until_display": self._format_date_display(premium_until) if premium_until else None,
            "can_extend": can_extend,
            "can_buy": can_buy_result["can_buy"],
            "can_buy_reason": can_buy_result.get("reason"),
            "available_actions": available_actions,
            "prices": {
                "activate": PREMIUM_PRICE,
                "extend_7days": PREMIUM_EXTEND_PRICE,
                "extend_1day": PREMIUM_DAY_PRICE
            }
        }
    
    async def check_and_deactivate_expired(self) -> List[int]:
        """
        Фоновая задача: проверяет и отключает истёкшие Премиумы.
        Возвращает список ID турниров, у которых был отключён Премиум.
        """
        tournaments = await tournament_service.get_tournaments()
        deactivated = []
        
        for tournament in tournaments:
            if tournament.is_premium:
                premium_until = self._parse_date(tournament.premium_until)
                if premium_until and premium_until < datetime.now():
                    # Премиум истёк - отключаем
                    await tournament_service.update_tournament(tournament.id, {
                        "is_premium": False,
                        "premium_last_ended": tournament.premium_until,
                        "premium_until": None
                    })
                    deactivated.append(tournament.id)
                    logger.info(f"⏰ Premium expired and deactivated for tournament {tournament.id}")
        
        if deactivated:
            logger.info(f"✅ Deactivated expired premium for {len(deactivated)} tournaments: {deactivated}")
        
        return deactivated


# Singleton instance
premium_service = PremiumService()
