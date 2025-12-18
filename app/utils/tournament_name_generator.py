"""
Генератор альтернативных названий турниров для улучшения поиска.
Учитывает различные варианты написания: Cup/Кап/Кубок, транслитерацию и т.д.
"""
import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)

# Словарь замен для генерации альтернатив
REPLACEMENTS = {
    # Cup варианты (английский -> русский и наоборот)
    "cup": ["кап", "кубок"],
    "кап": ["cup", "кубок"],
    "кубок": ["cup", "кап"],
    
    # Другие спортивные термины
    "tournament": ["турнир"],
    "турнир": ["tournament"],
    "league": ["лига"],
    "лига": ["league"],
    "championship": ["чемпионат"],
    "чемпионат": ["championship"],
    "open": ["опен", "открытый"],
    "опен": ["open", "открытый"],
    "открытый": ["open", "опен"],
    "fest": ["фест", "фестиваль"],
    "фест": ["fest", "фестиваль"],
    "фестиваль": ["fest", "фест"],
    
    # Города и регионы
    "sirius": ["сириус"],
    "сириус": ["sirius"],
    "sochi": ["сочи"],
    "сочи": ["sochi"],
    "moscow": ["москва", "мск"],
    "москва": ["moscow", "мск"],
    "мск": ["москва", "moscow"],
    "spb": ["спб", "санкт-петербург", "питер"],
    "спб": ["spb", "санкт-петербург", "питер"],
    "санкт-петербург": ["spb", "спб", "питер"],
    "питер": ["spb", "спб", "санкт-петербург"],
    "krasnodar": ["краснодар"],
    "краснодар": ["krasnodar"],
    "lazarevskoe": ["лазаревское", "лазаревка"],
    "лазаревское": ["lazarevskoe", "лазаревка"],
    "лазаревка": ["лазаревское", "lazarevskoe"],
    "kabardinka": ["кабардинка", "кабарда"],
    "кабардинка": ["kabardinka", "кабарда"],
    "кабарда": ["кабардинка", "kabardinka"],
    
    # Спортивные термины
    "football": ["футбол"],
    "футбол": ["football"],
    "soccer": ["футбол"],
    "kids": ["дети", "детский"],
    "дети": ["kids"],
    "детский": ["kids"],
    "junior": ["юниор", "юниорский"],
    "юниор": ["junior"],
    "winter": ["зимний", "зима"],
    "зимний": ["winter"],
    "summer": ["летний", "лето"],
    "летний": ["summer"],
    "spring": ["весенний", "весна"],
    "весенний": ["spring"],
}

# Транслитерация русский -> латиница
RU_TO_LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}

# Транслитерация латиница -> русский (основные варианты)
LAT_TO_RU = {
    'a': 'а', 'b': 'б', 'c': 'к', 'ch': 'ч', 'd': 'д', 'e': 'е', 'f': 'ф',
    'g': 'г', 'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л', 'm': 'м',
    'n': 'н', 'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 'sh': 'ш',
    't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'й', 'z': 'з',
}


def transliterate_ru_to_lat(text: str) -> str:
    """Транслитерация русского текста в латиницу"""
    result = []
    for char in text.lower():
        result.append(RU_TO_LAT.get(char, char))
    return ''.join(result)


def transliterate_lat_to_ru(text: str) -> str:
    """Транслитерация латиницы в русский (упрощенная)"""
    result = text.lower()
    # Сначала заменяем двухбуквенные комбинации
    for lat, ru in sorted(LAT_TO_RU.items(), key=lambda x: -len(x[0])):
        result = result.replace(lat, ru)
    return result


def generate_alternative_names(title: str) -> List[str]:
    """
    Генерирует список альтернативных названий турнира.
    
    Args:
        title: Оригинальное название турнира
        
    Returns:
        Список альтернативных названий (включая оригинал)
    """
    if not title:
        return []
    
    alternatives: Set[str] = set()
    
    # Убираем эмодзи и специальные символы из названия
    import re
    # Паттерн для удаления эмодзи
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    
    title_clean = emoji_pattern.sub('', title).strip()
    title_lower = title_clean.lower().strip()
    
    # Добавляем оригинал
    alternatives.add(title_lower)
    
    # 1. Транслитерация
    # Если название на русском - добавляем латиницу
    if any(c in title_lower for c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'):
        lat_version = transliterate_ru_to_lat(title_lower)
        alternatives.add(lat_version)
        # Без пробелов
        alternatives.add(lat_version.replace(' ', ''))
    
    # Если название на латинице - добавляем русский
    if any(c in title_lower for c in 'abcdefghijklmnopqrstuvwxyz'):
        ru_version = transliterate_lat_to_ru(title_lower)
        alternatives.add(ru_version)
        # Без пробелов
        alternatives.add(ru_version.replace(' ', ''))
    
    # 2. Замены по словарю
    words = re.split(r'[\s\-_]+', title_lower)
    
    for i, word in enumerate(words):
        word_clean = word.lower()
        if word_clean in REPLACEMENTS:
            for replacement in REPLACEMENTS[word_clean]:
                # Создаем новое название с заменой
                new_words = words.copy()
                new_words[i] = replacement
                new_title = ' '.join(new_words)
                alternatives.add(new_title)
                alternatives.add(new_title.replace(' ', ''))
                
                # Также добавляем транслитерацию замены
                if any(c in replacement for c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'):
                    lat_replacement = transliterate_ru_to_lat(new_title)
                    alternatives.add(lat_replacement)
                    alternatives.add(lat_replacement.replace(' ', ''))
    
    # 3. Специальные паттерны для Cup/Кап/Кубок
    # Обрабатываем слитное написание типа "SiriusCup", "СириусКап"
    
    # Паттерн для названий с Cup (раздельно или слитно)
    # Например: "SIRIUS CUP 2026" -> sirius, cup
    cup_variants = ["cup", "кап", "кубок"]
    
    # Ищем слово cup/кап/кубок в названии
    for cup_word in ["cup", "кап", "кубок"]:
        if cup_word in title_lower:
            # Разбиваем по cup_word и берём часть до него
            parts = title_lower.split(cup_word)
            if parts[0]:
                base_name = parts[0].strip().rstrip(' -_')
                # Убираем лишние слова (числа, годы)
                base_words = [w for w in base_name.split() if not w.isdigit() and len(w) > 1]
                if base_words:
                    base_name = ' '.join(base_words)
                    base_name_no_spaces = base_name.replace(' ', '')
                    
                    # Генерируем все варианты
                    for variant in cup_variants:
                        alternatives.add(f"{base_name} {variant}")
                        alternatives.add(f"{base_name}{variant}")
                        alternatives.add(f"{base_name_no_spaces}{variant}")
                        alternatives.add(f"{base_name_no_spaces} {variant}")
                    
                    # Транслитерация - добавляем ОБА варианта (латиница и кириллица)
                    lat_base = transliterate_ru_to_lat(base_name)
                    lat_base_no_spaces = lat_base.replace(' ', '')
                    ru_base = transliterate_lat_to_ru(base_name)
                    ru_base_no_spaces = ru_base.replace(' ', '')
                    
                    for variant in cup_variants:
                        # Латинские варианты
                        alternatives.add(f"{lat_base} {variant}")
                        alternatives.add(f"{lat_base}{variant}")
                        alternatives.add(f"{lat_base_no_spaces}{variant}")
                        alternatives.add(f"{lat_base_no_spaces} {variant}")
                        # Русские варианты
                        alternatives.add(f"{ru_base} {variant}")
                        alternatives.add(f"{ru_base}{variant}")
                        alternatives.add(f"{ru_base_no_spaces}{variant}")
                        alternatives.add(f"{ru_base_no_spaces} {variant}")
            break
    
    # Паттерн для CamelCase с Cup
    camel_cup_pattern = re.compile(r'([A-Za-z]+)(cup|Cup|CUP)', re.IGNORECASE)
    match = camel_cup_pattern.search(title_clean)
    if match:
        base_name = match.group(1).lower()
        ru_base = transliterate_lat_to_ru(base_name)
        # Добавляем варианты - и латиница и кириллица
        for variant in cup_variants:
            alternatives.add(f"{base_name} {variant}")
            alternatives.add(f"{base_name}{variant}")
            alternatives.add(f"{ru_base} {variant}")
            alternatives.add(f"{ru_base}{variant}")
    
    # Паттерн для русского слитного написания с Кап/Кубок
    ru_cup_pattern = re.compile(r'([А-Яа-яЁё]+)(кап|Кап|КАП|кубок|Кубок|КУБОК)', re.IGNORECASE)
    match = ru_cup_pattern.search(title_clean)
    if match:
        base_name = match.group(1).lower()
        lat_base = transliterate_ru_to_lat(base_name)
        # Добавляем варианты - и кириллица и латиница
        for variant in cup_variants:
            alternatives.add(f"{base_name} {variant}")
            alternatives.add(f"{base_name}{variant}")
            alternatives.add(f"{lat_base} {variant}")
            alternatives.add(f"{lat_base}{variant}")
    
    # 4. Версия без пробелов
    alternatives.add(title_lower.replace(' ', ''))
    alternatives.add(title_lower.replace('-', ''))
    alternatives.add(title_lower.replace(' ', '').replace('-', ''))
    
    # 5. Версия с дефисами вместо пробелов
    alternatives.add(title_lower.replace(' ', '-'))
    
    # Убираем пустые строки и дубликаты
    result = sorted([a for a in alternatives if a and len(a) > 1])
    
    logger.info(f"🏷️ Generated {len(result)} alternative names for '{title}': {result[:5]}...")
    
    return result


def match_tournament_name(query: str, title: str, alternative_names: List[str] = None) -> bool:
    """
    Проверяет, соответствует ли поисковый запрос названию турнира.
    
    Args:
        query: Поисковый запрос
        title: Название турнира
        alternative_names: Список альтернативных названий
        
    Returns:
        True если есть совпадение
    """
    query_lower = query.lower().strip()
    query_no_spaces = query_lower.replace(' ', '').replace('-', '')
    
    # Проверяем основное название
    title_lower = title.lower()
    if query_lower in title_lower or query_no_spaces in title_lower.replace(' ', ''):
        return True
    
    # Проверяем альтернативные названия
    if alternative_names:
        for alt_name in alternative_names:
            alt_lower = alt_name.lower()
            if query_lower in alt_lower or query_no_spaces in alt_lower.replace(' ', ''):
                return True
            # Также проверяем обратное вхождение
            if alt_lower in query_lower or alt_lower.replace(' ', '') in query_no_spaces:
                return True
    
    return False
