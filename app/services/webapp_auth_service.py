"""
Сервис авторизации через Telegram WebApp initData.

Реализует валидацию подписи initData от Telegram и создание JWT токенов
для сессий пользователей в WebApp личного кабинета.

Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote

import jwt

logger = logging.getLogger(__name__)

# Константы
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
INIT_DATA_EXPIRATION_SECONDS = 86400  # 24 часа


class WebAppAuthError(Exception):
    """Базовое исключение для ошибок авторизации WebApp"""
    pass


class InvalidSignatureError(WebAppAuthError):
    """Невалидная подпись initData"""
    pass


class ExpiredDataError(WebAppAuthError):
    """Данные initData устарели"""
    pass


class InvalidInitDataError(WebAppAuthError):
    """Некорректный формат initData"""
    pass


class WebAppAuthService:
    """
    Сервис авторизации через Telegram WebApp.
    
    Валидирует initData от Telegram, создаёт и проверяет JWT токены.
    """
    
    def __init__(self, bot_token: Optional[str] = None, jwt_secret: Optional[str] = None):
        """
        Инициализация сервиса.
        
        Args:
            bot_token: Токен бота Telegram (для валидации initData)
            jwt_secret: Секрет для подписи JWT (если не указан, генерируется из bot_token)
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.jwt_secret = jwt_secret or self._derive_jwt_secret(self.bot_token)
        
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set - initData validation will fail")
    
    def _derive_jwt_secret(self, bot_token: str) -> str:
        """Генерирует JWT секрет из токена бота"""
        if not bot_token:
            return "default_jwt_secret_change_me"
        return hashlib.sha256(f"jwt_secret_{bot_token}".encode()).hexdigest()
    
    def _generate_secret_key(self, bot_token: str) -> bytes:
        """
        Генерирует секретный ключ для валидации initData.
        
        Согласно документации Telegram:
        secret_key = HMAC_SHA256(bot_token, "WebAppData")
        
        Args:
            bot_token: Токен бота
            
        Returns:
            bytes: Секретный ключ для HMAC
        """
        return hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()

    def validate_init_data(self, init_data: str) -> Dict[str, Any]:
        """
        Валидирует initData от Telegram WebApp.
        
        Алгоритм валидации (из документации Telegram):
        1. Парсим URL-encoded строку в пары ключ=значение
        2. Сортируем пары по ключу (кроме hash)
        3. Формируем data_check_string: key=value\nkey=value\n...
        4. Вычисляем HMAC-SHA256(secret_key, data_check_string)
        5. Сравниваем с hash из initData
        
        Args:
            init_data: URL-encoded строка initData от Telegram
            
        Returns:
            dict с данными пользователя и другими полями
            
        Raises:
            InvalidInitDataError: если формат данных некорректен
            InvalidSignatureError: если подпись невалидна
            ExpiredDataError: если данные устарели
        """
        if not init_data:
            raise InvalidInitDataError("Empty initData")
        
        # Парсим URL-encoded строку
        try:
            parsed = parse_qs(init_data, keep_blank_values=True)
            # parse_qs возвращает списки, берём первый элемент
            data = {k: v[0] if v else "" for k, v in parsed.items()}
        except Exception as e:
            raise InvalidInitDataError(f"Failed to parse initData: {e}")
        
        # Извлекаем hash
        received_hash = data.pop("hash", None)
        if not received_hash:
            raise InvalidInitDataError("Missing hash in initData")
        
        # Проверяем auth_date
        auth_date_str = data.get("auth_date")
        if not auth_date_str:
            raise InvalidInitDataError("Missing auth_date in initData")
        
        try:
            auth_date = int(auth_date_str)
        except ValueError:
            raise InvalidInitDataError("Invalid auth_date format")
        
        # Проверяем срок действия
        current_time = int(time.time())
        if current_time - auth_date > INIT_DATA_EXPIRATION_SECONDS:
            raise ExpiredDataError(
                f"initData expired: auth_date={auth_date}, current={current_time}"
            )
        
        # Формируем data_check_string
        # Сортируем по ключу и соединяем через \n
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items())
        )
        
        # Вычисляем подпись
        secret_key = self._generate_secret_key(self.bot_token)
        computed_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Сравниваем подписи (constant-time comparison)
        if not hmac.compare_digest(computed_hash, received_hash):
            raise InvalidSignatureError("Invalid initData signature")
        
        # Парсим user JSON если есть
        user_data = None
        if "user" in data:
            try:
                user_data = json.loads(unquote(data["user"]))
            except json.JSONDecodeError:
                logger.warning("Failed to parse user JSON from initData")
        
        return {
            "user": user_data,
            "auth_date": auth_date,
            "query_id": data.get("query_id"),
            "chat_type": data.get("chat_type"),
            "chat_instance": data.get("chat_instance"),
            "start_param": data.get("start_param"),
            "raw_data": data
        }
    
    def create_jwt_token(
        self, 
        user_data: Dict[str, Any], 
        organizer_id: int,
        contact_id: Optional[int] = None,
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Создаёт JWT токен для сессии пользователя.
        
        Args:
            user_data: Данные пользователя из initData
            organizer_id: ID организатора в системе
            contact_id: ID контакта (если есть)
            extra_claims: Дополнительные claims для токена
            
        Returns:
            str: JWT токен
        """
        now = datetime.utcnow()
        
        payload = {
            "sub": str(user_data.get("id", "")),  # telegram_user_id
            "organizer_id": organizer_id,
            "telegram_user_id": user_data.get("id"),
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", ""),
            "username": user_data.get("username", ""),
            "iat": now,
            "exp": now + timedelta(hours=JWT_EXPIRATION_HOURS),
            "iss": "cupguide_webapp"
        }
        
        if contact_id:
            payload["contact_id"] = contact_id
        
        if extra_claims:
            payload.update(extra_claims)
        
        return jwt.encode(payload, self.jwt_secret, algorithm=JWT_ALGORITHM)
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """
        Проверяет и декодирует JWT токен.
        
        Args:
            token: JWT токен
            
        Returns:
            dict с claims из токена
            
        Raises:
            jwt.InvalidTokenError: если токен невалиден
            jwt.ExpiredSignatureError: если токен истёк
        """
        return jwt.decode(
            token, 
            self.jwt_secret, 
            algorithms=[JWT_ALGORITHM],
            issuer="cupguide_webapp"
        )
    
    def extract_telegram_user_id(self, init_data: str) -> Optional[int]:
        """
        Извлекает telegram_user_id из initData без полной валидации.
        Используется для быстрого получения ID пользователя.
        
        Args:
            init_data: URL-encoded строка initData
            
        Returns:
            int: telegram_user_id или None
        """
        try:
            parsed = parse_qs(init_data, keep_blank_values=True)
            user_str = parsed.get("user", [""])[0]
            if user_str:
                user_data = json.loads(unquote(user_str))
                return user_data.get("id")
        except Exception as e:
            logger.warning(f"Failed to extract telegram_user_id: {e}")
        return None


# Singleton instance
webapp_auth_service = WebAppAuthService()


def get_webapp_auth_service() -> WebAppAuthService:
    """Возвращает singleton экземпляр сервиса"""
    return webapp_auth_service
