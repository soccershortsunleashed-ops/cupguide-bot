"""
Masking Utils - маскирование персональных данных в логах
"""
import re
from typing import Optional


def mask_phone(text: str) -> str:
    """
    Маскирует телефонные номера в тексте
    
    Примеры:
    - +79991234567 -> +7999***4567
    - 89991234567 -> 8999***4567
    - +7 (999) 123-45-67 -> +7 (999) ***-**-67
    """
    # Паттерн для российских номеров
    patterns = [
        # +79991234567 или 89991234567
        (r'(\+?[78])(\d{3})(\d{3})(\d{2})(\d{2})', r'\1\2***\5'),
        # +7 (999) 123-45-67
        (r'(\+?[78]\s*\(\d{3}\)\s*)(\d{3})(-?\d{2})(-?\d{2})', r'\1***\4'),
        # Любые 10-11 цифр подряд
        (r'(\d{3,4})(\d{3})(\d{4})', r'\1***\3'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    
    return result


def mask_email(text: str) -> str:
    """
    Маскирует email адреса в тексте
    
    Примеры:
    - user@example.com -> u***@example.com
    - john.doe@mail.ru -> j***@mail.ru
    """
    def replace_email(match):
        email = match.group(0)
        parts = email.split('@')
        if len(parts) != 2:
            return email
        
        local = parts[0]
        domain = parts[1]
        
        if len(local) <= 1:
            masked_local = local
        else:
            masked_local = local[0] + '***'
        
        return f"{masked_local}@{domain}"
    
    # Паттерн для email
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.sub(email_pattern, replace_email, text)


def mask_telegram(text: str) -> str:
    """
    Маскирует Telegram username в тексте
    
    Примеры:
    - @username -> @u***
    - @john_doe -> @j***
    """
    def replace_username(match):
        username = match.group(0)
        if len(username) <= 2:
            return username
        return username[:2] + '***'
    
    # Паттерн для @username
    tg_pattern = r'@[a-zA-Z0-9_]{3,}'
    return re.sub(tg_pattern, replace_username, text)


def mask_contacts(text: str) -> str:
    """
    Маскирует все контактные данные в тексте
    
    Применяет маскирование:
    - Телефонов
    - Email
    - Telegram username
    """
    if not text:
        return text
    
    result = text
    result = mask_phone(result)
    result = mask_email(result)
    result = mask_telegram(result)
    
    return result


def safe_log(text: str, max_length: int = 200) -> str:
    """
    Подготавливает текст для безопасного логирования
    
    - Маскирует контакты
    - Обрезает длинный текст
    """
    if not text:
        return ""
    
    masked = mask_contacts(text)
    
    if len(masked) > max_length:
        return masked[:max_length] + "..."
    
    return masked
