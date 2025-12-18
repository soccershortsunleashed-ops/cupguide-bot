"""
Telegraph/Teletype Publishing Service
Публикация турниров в Telegraph (Teletype.in)
"""
import os
import json
import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

class TelegraphService:
    """Сервис для публикации статей в Telegraph/Teletype"""
    
    BASE_URL = "https://api.telegra.ph"
    
    def __init__(self):
        self.access_token = os.getenv("TELEGRAPH_ACCESS_TOKEN", "")
        self.author_name = os.getenv("TELEGRAPH_AUTHOR_NAME", "CupGuide")
        self.author_url = os.getenv("TELEGRAPH_AUTHOR_URL", "")
        
    def _format_date(self, date_str: str) -> str:
        """Форматирует дату в читаемый вид"""
        try:
            if not date_str:
                return "Дата уточняется"
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]
            return f"{dt.day} {months[dt.month-1]} {dt.year}"
        except:
            return date_str or "Дата уточняется"
    
    def _parse_birth_years(self, birth_years) -> str:
        """Парсит годы рождения в читаемый формат"""
        if not birth_years:
            return ""
        
        if isinstance(birth_years, str):
            # Уже строка - возвращаем как есть
            return birth_years
        
        if isinstance(birth_years, list):
            # Очищаем от артефактов типа "['2014'", "'2015'", "'2016']"
            cleaned = []
            for item in birth_years:
                text = str(item).strip()
                text = text.replace("[", "").replace("]", "").replace("'", "").replace('"', "").strip()
                if text and text.isdigit():
                    cleaned.append(text)
            
            if cleaned:
                years = sorted(set(int(y) for y in cleaned))
                if len(years) == 1:
                    return f"{years[0]} г.р."
                return f"{years[0]} - {years[-1]} г.р."
        
        return str(birth_years)
    
    def _process_inline_formatting(self, text: str) -> List:
        """Обрабатывает inline форматирование (жирный, телефоны, email) и возвращает список children"""
        import re
        
        # Сначала убираем ** форматирование
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        
        result = []
        last_end = 0
        
        # Комбинированный паттерн для телефонов и email
        # Телефон: +7 904 507-24-50 или 8(904)507-24-50 и т.д.
        # Email: example@mail.ru
        combined_pattern = r'(\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        
        for match in re.finditer(combined_pattern, text):
            # Добавляем текст до match
            if match.start() > last_end:
                result.append(text[last_end:match.start()])
            
            if match.group(1):  # Телефон - делаем ссылку на Telegram
                phone = match.group(1)
                phone_digits = re.sub(r'\D', '', phone)
                if phone_digits.startswith('8'):
                    phone_digits = '7' + phone_digits[1:]
                # Telegraph не поддерживает tel: ссылки, используем Telegram
                result.append({
                    "tag": "a",
                    "attrs": {"href": f"https://t.me/+{phone_digits}"},
                    "children": [phone]
                })
            elif match.group(2):  # Email
                email = match.group(2)
                result.append({
                    "tag": "a",
                    "attrs": {"href": f"mailto:{email}"},
                    "children": [email]
                })
            
            last_end = match.end()
        
        # Добавляем оставшийся текст
        if last_end < len(text):
            result.append(text[last_end:])
        
        # Если не было форматирования, возвращаем просто текст
        if not result:
            return [text]
        
        return result
    
    def _markdown_to_telegraph(self, text: str) -> List[Dict]:
        """Конвертирует Markdown текст в Telegraph Node формат"""
        import re
        nodes = []
        
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Заголовки - убираем ** из заголовков
            if line.startswith('### '):
                header_text = re.sub(r'\*\*(.+?)\*\*', r'\1', line[4:])
                nodes.append({"tag": "h4", "children": [header_text]})
            elif line.startswith('## '):
                header_text = re.sub(r'\*\*(.+?)\*\*', r'\1', line[3:])
                nodes.append({"tag": "h3", "children": [header_text]})
            elif line.startswith('# '):
                header_text = re.sub(r'\*\*(.+?)\*\*', r'\1', line[2:])
                nodes.append({"tag": "h3", "children": [header_text]})
            # Горизонтальная линия
            elif line == '---' or line == '***':
                nodes.append({"tag": "hr"})
            # Списки
            elif line.startswith('- ') or line.startswith('* '):
                list_items = []
                while i < len(lines) and (lines[i].strip().startswith('- ') or lines[i].strip().startswith('* ')):
                    item_text = lines[i].strip()[2:]
                    children = self._process_inline_formatting(item_text)
                    list_items.append({"tag": "li", "children": children})
                    i += 1
                nodes.append({"tag": "ul", "children": list_items})
                continue
            # Таблицы - конвертируем в читаемый текст (Telegraph не поддерживает <table>)
            elif line.startswith('|'):
                headers = []
                data_rows = []
                is_first_row = True
                
                while i < len(lines) and lines[i].strip().startswith('|'):
                    row = lines[i].strip()
                    # Пропускаем разделитель |---|---|
                    if re.match(r'^\|[\s\-:]+\|', row):
                        i += 1
                        continue
                    
                    cells = [c.strip() for c in row.split('|')[1:-1]]
                    # Убираем ** из ячеек
                    cells = [re.sub(r'\*\*(.+?)\*\*', r'\1', c) for c in cells]
                    
                    if is_first_row:
                        headers = cells
                        is_first_row = False
                    else:
                        data_rows.append(cells)
                    i += 1
                
                # Форматируем таблицу как pre (моноширинный шрифт)
                if headers and data_rows:
                    # Вычисляем ширину каждой колонки
                    col_widths = []
                    for idx, h in enumerate(headers):
                        max_width = len(h)
                        for row in data_rows:
                            if idx < len(row):
                                max_width = max(max_width, len(row[idx]))
                        col_widths.append(max_width + 1)
                    
                    # Формируем текст таблицы
                    table_lines = []
                    
                    # Заголовок
                    header_row = " │ ".join(h.ljust(col_widths[idx]) for idx, h in enumerate(headers))
                    table_lines.append(header_row)
                    
                    # Разделитель
                    separator = "─┼─".join("─" * w for w in col_widths)
                    table_lines.append(separator)
                    
                    # Данные
                    for row_data in data_rows:
                        data_row = " │ ".join(
                            row_data[idx].ljust(col_widths[idx]) if idx < len(row_data) else " " * col_widths[idx]
                            for idx in range(len(headers))
                        )
                        table_lines.append(data_row)
                    
                    table_text = "\n".join(table_lines)
                    nodes.append({"tag": "pre", "children": [table_text]})
                continue
            # Обычный параграф
            else:
                children = self._process_inline_formatting(line)
                nodes.append({"tag": "p", "children": children})
            
            i += 1
        
        return nodes
    
    def _tournament_to_content(self, tournament: Dict[str, Any], base_url: str = "") -> List[Dict]:
        """Конвертирует данные турнира в формат Telegraph Node"""
        content = []
        
        # Изображение турнира (проверяем разные поля)
        img_url = tournament.get("image_cover_16x9_url") or tournament.get("image_original_url") or tournament.get("image_url")
        if img_url:
            if img_url.startswith("/"):
                img_url = f"{base_url}{img_url}"
            content.append({
                "tag": "figure",
                "children": [
                    {"tag": "img", "attrs": {"src": img_url}},
                ]
            })

        # Основная информация
        info_items = []
        
        # Даты
        start_date = self._format_date(tournament.get("start_date", ""))
        end_date = self._format_date(tournament.get("end_date", ""))
        if start_date == end_date or not tournament.get("end_date"):
            info_items.append(f"📅 Дата: {start_date}")
        else:
            info_items.append(f"📅 Даты: {start_date} — {end_date}")
        
        # Место проведения
        location = tournament.get("location") or tournament.get("city") or ""
        if tournament.get("region") and location:
            location = f"{location}, {tournament['region']}"
        if location:
            info_items.append(f"📍 Место: {location}")
        
        # Стоимость
        price = tournament.get("entry_fee") or tournament.get("price")
        if price:
            info_items.append(f"💰 Стоимость: {price}")
        
        # Возрастные группы - используем специальный парсер
        ages = self._parse_birth_years(tournament.get("birth_years"))
        if not ages and tournament.get("birth_years_display"):
            ages = tournament.get("birth_years_display")
        if ages:
            # Добавляем "г.р." только если его нет
            if "г.р." not in str(ages):
                info_items.append(f"👶 Возраст: {ages} г.р.")
            else:
                info_items.append(f"👶 Возраст: {ages}")
        
        # Формат
        if tournament.get("format"):
            info_items.append(f"⚽ Формат: {tournament['format']}")
        
        # Добавляем информацию как список
        for item in info_items:
            content.append({"tag": "p", "children": [{"tag": "strong", "children": [item]}]})
        
        content.append({"tag": "hr"})
        
        # Описание (проверяем разные поля) - конвертируем Markdown
        description = tournament.get("body") or tournament.get("description_full") or tournament.get("description") or tournament.get("short_description")
        if description:
            content.append({"tag": "h3", "children": ["Описание"]})
            # Конвертируем Markdown в Telegraph формат
            desc_nodes = self._markdown_to_telegraph(description)
            content.extend(desc_nodes)
        
        # Условия участия
        if tournament.get("conditions"):
            content.append({"tag": "h4", "children": ["Условия участия"]})
            content.append({"tag": "p", "children": [tournament["conditions"]]})
        
        # Контакты организатора
        organizer_name = tournament.get("organizer_name")
        contact = tournament.get("contact") or tournament.get("organizer_phone")
        contact_person = tournament.get("contact_person")
        
        if organizer_name or contact or contact_person:
            content.append({"tag": "h4", "children": ["Контакты организатора"]})
            if organizer_name:
                content.append({"tag": "p", "children": [f"🏢 {organizer_name}"]})
            if contact_person:
                content.append({"tag": "p", "children": [f"👤 {contact_person}"]})
            if contact:
                # Извлекаем телефон и делаем кликабельным
                import re
                phone_match = re.search(r'(\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})', contact)
                email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', contact)
                
                if phone_match:
                    phone = phone_match.group(1)
                    phone_digits = re.sub(r'\D', '', phone)
                    if phone_digits.startswith('8'):
                        phone_digits = '7' + phone_digits[1:]
                    content.append({
                        "tag": "p",
                        "children": [
                            "📞 ",
                            {"tag": "a", "attrs": {"href": f"tel:+{phone_digits}"}, "children": [phone]}
                        ]
                    })
                else:
                    content.append({"tag": "p", "children": [f"📞 {contact}"]})
                
                if email_match:
                    email = email_match.group(1)
                    content.append({
                        "tag": "p",
                        "children": [
                            "📧 ",
                            {"tag": "a", "attrs": {"href": f"mailto:{email}"}, "children": [email]}
                        ]
                    })
        
        # Ссылка на карточку турнира
        if tournament.get("id") and base_url:
            content.append({"tag": "hr"})
            content.append({
                "tag": "p",
                "children": [
                    "🔗 ",
                    {
                        "tag": "a",
                        "attrs": {"href": f"{base_url}/tournaments/{tournament['id']}"},
                        "children": ["Подробнее на сайте CupGuide"]
                    }
                ]
            })
        
        return content
    
    async def create_page(self, tournament: Dict[str, Any], base_url: str = "") -> Dict[str, Any]:
        """Создаёт страницу турнира в Telegraph"""
        if not self.access_token:
            raise ValueError("TELEGRAPH_ACCESS_TOKEN не настроен")
        
        title = tournament.get("title") or tournament.get("name") or "Турнир"
        content = self._tournament_to_content(tournament, base_url)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/createPage",
                data={
                    "access_token": self.access_token,
                    "title": title,
                    "author_name": self.author_name,
                    "author_url": self.author_url,
                    "content": json.dumps(content),
                    "return_content": "false"
                }
            )
            
            result = response.json()
            
            if result.get("ok"):
                page = result["result"]
                logger.info(f"✅ Турнир '{title}' опубликован: {page['url']}")
                return {
                    "success": True,
                    "url": page["url"],
                    "path": page["path"],
                    "title": page["title"]
                }
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"❌ Ошибка публикации: {error}")
                return {"success": False, "error": error}
    
    async def edit_page(self, path: str, tournament: Dict[str, Any], base_url: str = "") -> Dict[str, Any]:
        """Обновляет существующую страницу турнира"""
        if not self.access_token:
            raise ValueError("TELEGRAPH_ACCESS_TOKEN не настроен")
        
        title = tournament.get("title") or tournament.get("name") or "Турнир"
        content = self._tournament_to_content(tournament, base_url)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/editPage",
                data={
                    "access_token": self.access_token,
                    "path": path,
                    "title": title,
                    "author_name": self.author_name,
                    "content": json.dumps(content),
                    "return_content": "false"
                }
            )
            
            result = response.json()
            
            if result.get("ok"):
                page = result["result"]
                logger.info(f"✅ Турнир '{title}' обновлён: {page['url']}")
                return {"success": True, "url": page["url"], "path": page["path"]}
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"❌ Ошибка обновления: {error}")
                return {"success": False, "error": error}

telegraph_service = TelegraphService()
