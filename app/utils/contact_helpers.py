"""Helper functions for contact data cleaning"""
import re


def normalize_phone(phone: str) -> str:
    """
    Принудительная нормализация номера телефона к формату +7XXXXXXXXXX.
    Обрабатывает все возможные форматы: 8-921-900-123-45, 792190012345, 8(921)90012345 и т.д.
    
    Examples:
        "+7 903 186-09-09" -> "+79031860909"
        "8-903-186-09-09" -> "+79031860909"
        "8(903)186-09-09" -> "+79031860909"
        "792190012345" -> "+792190012345"
        "8-921-900-123-45" -> "+792190012345"
        "43. +7 903 186-09-09" -> "+79031860909"
        "(921) 900-12-34" -> "+79219001234"
    """
    if not phone:
        return ""
    
    # Преобразуем в строку и убираем пробелы по краям
    phone = str(phone).strip()
    
    # Удаляем все символы, кроме цифр, +, 8, скобок, дефисов и пробелов
    # Это поможет найти начало номера
    cleaned = re.sub(r'[^\d\+\-\(\)\s]', '', phone)
    
    # Ищем начало номера: +7, 7, или 8
    result = ""
    
    # Вариант 1: номер начинается с +7
    if "+7" in cleaned:
        idx = cleaned.index("+7")
        result = cleaned[idx:]
    # Вариант 2: номер начинается с 8 (российский формат)
    elif re.search(r'\b8\b', cleaned) or cleaned.startswith("8"):
        # Находим первое вхождение 8, за которым идут цифры
        match = re.search(r'8[\d\s\-\(\)]+', cleaned)
        if match:
            result = match.group(0)
            # Заменяем 8 на +7
            result = "+7" + result[1:]
    # Вариант 3: номер начинается с 7 (международный формат без +)
    elif re.search(r'\b7\d{10}', cleaned):
        match = re.search(r'7\d{10}', cleaned)
        if match:
            result = "+" + match.group(0)
    # Вариант 4: только цифры (10 цифр после 8 или 7)
    elif re.search(r'\d{10,11}', cleaned):
        match = re.search(r'\d{10,11}', cleaned)
        digits = match.group(0)
        if len(digits) == 11 and digits.startswith("8"):
            result = "+7" + digits[1:]
        elif len(digits) == 11 and digits.startswith("7"):
            result = "+" + digits
        elif len(digits) == 10:
            result = "+7" + digits
    
    # Если ничего не нашли, возвращаем пустую строку
    if not result:
        return ""
    
    # Удаляем все нецифровые символы, кроме ведущего +
    normalized = ""
    for i, char in enumerate(result):
        if char.isdigit():
            normalized += char
        elif i == 0 and char == "+":
            normalized += char
    
    # Проверяем, что номер начинается с +7
    if not normalized.startswith("+"):
        if normalized.startswith("7") and len(normalized) == 11:
            normalized = "+" + normalized
        elif len(normalized) == 10:
            normalized = "+7" + normalized
        elif len(normalized) == 11 and normalized.startswith("8"):
            normalized = "+7" + normalized[1:]
        else:
            # Если формат не распознан, пытаемся исправить
            if len(normalized) >= 10:
                # Берем последние 10 цифр и добавляем +7
                digits_only = re.sub(r'\D', '', normalized)
                if len(digits_only) >= 10:
                    normalized = "+7" + digits_only[-10:]
                else:
                    return ""
            else:
                return ""
    
    # Проверяем длину: должно быть +7 и 10 цифр = 12 символов
    if len(normalized) != 12 or not normalized.startswith("+7"):
        return ""
    
    return normalized


def clean_name(name: str) -> str:
    """
    Clean name field by removing row numbers and extra formatting.
    
    Examples:
        "33. +7 988 387-76-05" -> ""
        "34. Иван" -> "Иван"
        "35." -> ""
    """
    if not name:
        return ""
    
    # Remove leading numbers and dots (e.g., "33. ")
    cleaned = re.sub(r'^\d+\.\s*', '', name)
    
    # If after cleaning it looks like a phone number, return empty
    if '+7' in cleaned or cleaned.replace(' ', '').replace('-', '').isdigit():
        return ""
    
    return cleaned.strip()
