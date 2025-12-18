"""
LLM Consultant for Tournament Queries
"""
import json
import time
import logging
import asyncio
import os
import random
from typing import Dict, List, Any, Optional
from datetime import datetime

import openai
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from backend_client import BackendClient

logger = logging.getLogger(__name__)

# Фразы для выбора турнира (рандомный выбор)
TOURNAMENT_CHOICE_PROMPTS = [
    # Нейтрально-дружелюбные
    "Какой турнир вас заинтересовал?",
    "О каком турнире хотите узнать подробнее?",
    "Расскажите, какой турнир вам интересен",
    "Что из этого откликнулось больше всего?",
    "Какой вариант рассматриваете?",
    # Диалоговые
    "Давайте разберёмся — какой турнир вам ближе?",
    "Подскажите, на какой турнир смотрите 👀",
    "Интересует конкретный турнир или сравнить оба?",
    "О каком турнире поговорим подробнее?",
    "Что хотите узнать в первую очередь?",
    # Вовлекающие
    "Напишите, какой турнир вам откликнулся — расскажу детали",
    "Выберите турнир словами, а я подберу всю информацию",
    "Опишите, какой турнир ищете — помогу разобраться",
]

class LLMConsultant:
    """LLM-powered consultant for tournament queries"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=config.MEGALLM_API_KEY,
            base_url=config.MEGALLM_BASE_URL,
            max_retries=2,  # Ограничиваем retry чтобы не превышать таймаут
            timeout=40.0  # Увеличенный таймаут для rate limit
        )
        self.backend_client = BackendClient()
        self.model = "llama3-8b-instruct"  # MegaLLM free tier model
        self.prompt_version = "1.0"
        
        # Инициализируем сервис аналитики для логирования показов
        try:
            import sys
            import os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from app.services.analytics_service import get_analytics_service
            self.analytics_service = get_analytics_service()
        except Exception as e:
            logger.warning(f"Analytics service not available: {e}")
            self.analytics_service = None
    
    def _log_tournament_impressions(self, tournaments: List[Dict[str, Any]], context: str = "search"):
        """Логирует показы турниров для аналитики (асинхронно, не блокирует)"""
        if not self.analytics_service or not tournaments:
            return
        
        import asyncio
        try:
            for t in tournaments:
                tournament_id = t.get("id")
                if tournament_id:
                    # Запускаем логирование асинхронно без ожидания
                    asyncio.create_task(
                        self.analytics_service.log_impression(tournament_id, context)
                    )
        except Exception as e:
            logger.warning(f"Error logging impressions: {e}")
    
    async def process_message(
        self, 
        message: str, 
        user_id: int, 
        contact_id: Optional[int] = None,
        message_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Process user message and return response
        
        Args:
            message: Current user message
            user_id: Telegram user ID
            contact_id: CRM contact ID
            message_history: List of previous messages [{"role": "user/assistant", "content": "..."}]
        """
        start_time = time.time()
        tool_calls = []
        error = None
        search_result_formatted = None  # Флаг для перехвата результата search_tournaments
        
        try:
            # Prepare system prompt
            system_prompt = self._get_system_prompt()
            
            # Prepare tools
            tools = self._get_tools()
            
            # Build messages list with history
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add message history (last 6 messages for context)
            if message_history:
                # Limit history to avoid token overflow
                recent_history = message_history[-6:]
                messages.extend(recent_history)
                logger.info(f"📜 Добавлена история: {len(recent_history)} сообщений")
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Make LLM call with timeout (увеличен для обработки rate limit)
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=500  # Reduced for faster responses
                ),
                timeout=45.0  # 45 second timeout для обработки rate limit retry
            )
            
            assistant_message = response.choices[0].message
            
            # Handle tool calls
            if assistant_message.tool_calls:
                tool_calls = []
                results = []
                tool_results = []
                
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    tool_calls.append({
                        "name": tool_name,
                        "arguments": tool_args
                    })
                    
                    # Execute tool
                    tool_result = await self._execute_tool(tool_name, tool_args)
                    tool_results.append(tool_result)
                    results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })
                
                # ПЕРЕХВАТ: Если был поиск турниров - форматируем список программно,
                # не даём LLM выбирать один турнир из списка
                search_result_formatted = None
                for i, tc in enumerate(tool_calls):
                    if tc["name"] == "search_tournaments":
                        tr = tool_results[i]
                        if tr.get("success") and tr.get("tournaments"):
                            tournaments = tr["tournaments"]
                            if len(tournaments) >= 1:
                                search_result_formatted = self._format_tournaments_list(tournaments)
                                logger.info(f"📋 Перехвачен результат search_tournaments: {len(tournaments)} турниров, форматируем программно")
                                break
                
                if search_result_formatted:
                    # Используем программно сформированный список вместо ответа LLM
                    final_text = search_result_formatted
                else:
                    # Для других инструментов - даём LLM сформировать ответ
                    final_response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message},
                            assistant_message,
                            *results
                        ],
                        temperature=0.1,
                        max_tokens=1000
                    )
                    
                    final_text = final_response.choices[0].message.content
            else:
                final_text = assistant_message.content
                tool_results = []
                
                # ЗАЩИТА ОТ ГАЛЛЮЦИНАЦИЙ: если LLM не вызвал инструменты,
                # но пользователь спрашивает о турнире - принудительно ищем
                tournament_keywords = ['турнир', 'кубок', 'cup', 'кап', 'чемпионат', 'лаза', 'laza', 
                                       'imsport', 'имспорт', 'sirius', 'сириус', 'рождественский', 'весенний',
                                       'поиск', 'найди', 'подбери', 'покажи', 'вариант', 'года', 'год',
                                       'расскажи', 'какие', 'есть', 'доступн', 'актуальн', 'ближайш']
                message_lower = message.lower()
                
                # Также проверяем наличие года рождения (2005-2025)
                import re
                has_birth_year = bool(re.search(r'\b(200[5-9]|201[0-9]|202[0-5])\b', message))
                
                if any(kw in message_lower for kw in tournament_keywords) or has_birth_year:
                    logger.warning(f"⚠️ LLM не вызвал инструменты для запроса о турнире: {message}")
                    # Пробуем найти название турнира в сообщении
                    import re
                    # Ищем названия турниров
                    tournament_patterns = [
                        r'(laza\s*cup|лаза\s*кап|lazacup|лазакап)',
                        r'(sirius\s*cup|сириус\s*кап|сириус\s*куп)',
                        r'(рождественский\s*кубок|рождественский\s*cup)',
                        r'(весенний\s*кубок|весенний\s*cup)',
                        r'(imsport|имспорт)',
                    ]
                    
                    search_name = None
                    for pattern in tournament_patterns:
                        match = re.search(pattern, message_lower, re.IGNORECASE)
                        if match:
                            search_name = match.group(1)
                            break
                    
                    if search_name:
                        logger.info(f"🔍 Принудительный поиск турнира по названию: {search_name}")
                        tool_result = await self._execute_tool("find_tournament_by_name", {"name": search_name})
                        tool_results = [tool_result]
                        if tool_result.get("success") and tool_result.get("tournament"):
                            final_text = self._format_single_tournament(tool_result["tournament"])
                            logger.info(f"✅ Найден турнир принудительным поиском: {tool_result['tournament'].get('title')}")
                    else:
                        # Если нет конкретного названия - ищем по параметрам (месяц, сезон, город, год рождения)
                        search_params = {"limit": 10}
                        date_found = False
                        
                        # Извлекаем город
                        city_patterns = {
                            'кабардинк': 'Кабардинка',
                            'лазаревск': 'Лазаревское',
                            'сочи': 'Сочи',
                            'сириус': 'Сириус',
                            'москв': 'Москва',
                            'санкт-петербург': 'Санкт-Петербург',
                            'петербург': 'Санкт-Петербург',
                            'питер': 'Санкт-Петербург',
                            'спб': 'Санкт-Петербург',
                            'краснодар': 'Краснодар',
                            'ростов': 'Ростов-на-Дону',
                            'казан': 'Казань',
                            'екатеринбург': 'Екатеринбург',
                            'новосибирск': 'Новосибирск',
                            'нижн': 'Нижний Новгород',
                            'самар': 'Самара',
                            'омск': 'Омск',
                            'челябинск': 'Челябинск',
                            'уфа': 'Уфа',
                            'волгоград': 'Волгоград',
                            'пермь': 'Пермь',
                            'воронеж': 'Воронеж',
                        }
                        
                        for city_key, city_name in city_patterns.items():
                            if city_key in message_lower:
                                search_params["city"] = city_name
                                logger.info(f"🏙️ Определён город: {city_name}")
                                break
                        
                        # Извлекаем год рождения (2005-2025)
                        year_match = re.search(r'\b(200[5-9]|201[0-9]|202[0-5])\b', message)
                        if year_match:
                            birth_year = year_match.group(1)
                            search_params["age"] = birth_year
                            logger.info(f"👶 Определён год рождения: {birth_year}")
                        
                        # Сначала проверяем сезоны
                        season_map = {
                            'весн': ('2026-03-01', '2026-05-31'),  # весна, весной, весенний
                            'лет': ('2026-06-01', '2026-08-31'),   # лето, летом, летний
                            'осен': ('2026-09-01', '2026-11-30'),  # осень, осенью, осенний
                            'зим': ('2025-12-01', '2026-02-28'),   # зима = декабрь 2025 - февраль 2026
                        }
                        
                        for season_key, (date_from, date_to) in season_map.items():
                            if season_key in message_lower:
                                search_params["date_from"] = date_from
                                search_params["date_to"] = date_to
                                date_found = True
                                logger.info(f"🗓️ Определён сезон: {season_key} -> {date_from} - {date_to}")
                                break
                        
                        # Если сезон не найден - ищем месяц
                        if not date_found:
                            month_map = {
                                'январ': ('2026-01-01', '2026-01-31'),
                                'феврал': ('2026-02-01', '2026-02-28'),
                                'март': ('2026-03-01', '2026-03-31'),
                                'апрел': ('2026-04-01', '2026-04-30'),
                                'май': ('2026-05-01', '2026-05-31'),
                                'июн': ('2026-06-01', '2026-06-30'),
                                'июл': ('2026-07-01', '2026-07-31'),
                                'август': ('2026-08-01', '2026-08-31'),
                                'сентябр': ('2026-09-01', '2026-09-30'),
                                'октябр': ('2026-10-01', '2026-10-31'),
                                'ноябр': ('2026-11-01', '2026-11-30'),
                                'декабр': ('2026-12-01', '2026-12-31'),
                            }
                            
                            for month_key, (date_from, date_to) in month_map.items():
                                if month_key in message_lower:
                                    search_params["date_from"] = date_from
                                    search_params["date_to"] = date_to
                                    date_found = True
                                    break
                        
                        # Если нет дат - ищем все актуальные турниры
                        if "date_from" not in search_params:
                            search_params["date_from"] = "now"
                        
                        logger.info(f"🔍 Принудительный поиск турниров: {search_params}")
                        tool_result = await self._execute_tool("search_tournaments", search_params)
                        tool_results = [tool_result]
                        if tool_result.get("success") and tool_result.get("tournaments"):
                            final_text = self._format_tournaments_list(tool_result["tournaments"])
                            logger.info(f"✅ Найдено {len(tool_result['tournaments'])} турниров принудительным поиском")
            
            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Log LLM call
            await self.backend_client.log_llm_call(
                contact_id=contact_id,
                model=self.model,
                prompt_version=self.prompt_version,
                tool_calls=tool_calls,
                answer=final_text,
                latency_ms=latency_ms,
                error=error
            )
            
            # Если перехват search_tournaments уже сработал - не обрабатываем повторно
            # search_result_formatted уже содержит правильно отформатированный список
            if not search_result_formatted:
                # Очищаем Markdown из ответа LLM
                final_text = self._clean_markdown(final_text)
                
                # Проверяем, был ли поиск турниров
                # Формируем ответ программно, не полагаясь на LLM
                found_tournament = False
                all_tournaments_empty = True
                
                for tool_result in tool_results:
                    if tool_result.get("success"):
                        # Проверяем результат find_tournament_by_name или get_tournament
                        single_tournament = tool_result.get("tournament")
                        if single_tournament:
                            final_text = self._format_single_tournament(single_tournament)
                            logger.info(f"📋 Найден турнир: {single_tournament.get('title')}")
                            found_tournament = True
                            break
                        
                        # Проверяем результат get_tournament_card
                        card = tool_result.get("card")
                        if card:
                            final_text = self._format_single_tournament(card)
                            logger.info(f"📋 Найдена карточка турнира: {card.get('title')}")
                            found_tournament = True
                            break
                        
                        # Проверяем результат search_tournaments
                        tournaments = tool_result.get("tournaments", [])
                        if len(tournaments) >= 1:
                            final_text = self._format_tournaments_list(tournaments)
                            logger.info(f"📋 Сформирован список из {len(tournaments)} турниров")
                            found_tournament = True
                            all_tournaments_empty = False
                            break
                        elif "tournaments" in tool_result:
                            all_tournaments_empty = True
                
                # Показываем "не найдено" только если НЕ нашли турнир и был поиск
                if not found_tournament and all_tournaments_empty and tool_results:
                    has_search_call = any(
                        "tournaments" in r or "tournament" in r 
                        for r in tool_results
                    )
                    if has_search_call:
                        final_text = "🔍 К сожалению, турниры по вашим критериям не найдены.\n\nПопробуйте:\n• Изменить город или регион\n• Расширить диапазон дат\n• Убрать некоторые фильтры"
                        logger.info(f"📋 Турниры не найдены, показываем сообщение")
            
            # Извлекаем и сохраняем теги интересов пользователя
            if contact_id and tool_calls:
                try:
                    extracted_tags = await self.extract_and_save_tags(message, tool_calls, contact_id)
                    if extracted_tags:
                        logger.info(f"🏷️ Extracted {len(extracted_tags)} tags from message")
                except Exception as e:
                    logger.error(f"Error extracting tags: {e}")
            
            # Обновляем портрет контакта каждые 5 сообщений
            if contact_id and message_history and len(message_history) >= 5 and len(message_history) % 5 == 0:
                try:
                    await self.update_contact_portrait(contact_id, message_history)
                except Exception as e:
                    logger.error(f"Error updating portrait: {e}")
            
            # Format response
            return self._format_response(final_text, tool_calls, tool_results)
            
        except asyncio.TimeoutError:
            error = "LLM request timeout"
            latency_ms = int((time.time() - start_time) * 1000)
            
            logger.error(f"LLM request timeout after {latency_ms}ms")
            
            # Log timeout
            await self.backend_client.log_llm_call(
                contact_id=contact_id,
                model=self.model,
                prompt_version=self.prompt_version,
                tool_calls=tool_calls,
                answer="",
                latency_ms=latency_ms,
                error=error
            )
            
            return {
                "text": "⏱️ Запрос обрабатывается слишком долго. Попробуйте задать более простой вопрос.",
                "payload": {"error": error}
            }
            
        except Exception as e:
            error = str(e)
            latency_ms = int((time.time() - start_time) * 1000)
            
            logger.error(f"Error in LLM consultant: {e}")
            
            # Log error
            await self.backend_client.log_llm_call(
                contact_id=contact_id,
                model=self.model,
                prompt_version=self.prompt_version,
                tool_calls=tool_calls,
                answer="",
                latency_ms=latency_ms,
                error=error
            )
            
            return {
                "text": "❌ Извините, произошла ошибка при обработке запроса. Попробуйте переформулировать вопрос.",
                "payload": {"error": error}
            }
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM"""
        return """
🧠 РОЛЬ: Футбольный навигатор по турнирам России

Ты подбираешь футбольные турниры по:
- сезонам (зима / весна / лето / осень)
- городам РФ
- годам рождения участников
- форматам игры (11×11, 8+1, 7×7 и т.д.)

БЕЗ матчей, таблиц, аналитики — чётко, честно, по делу.

⛔ СТРОЖАЙШИЙ ЗАПРЕТ - ГАЛЛЮЦИНАЦИИ:
- НИКОГДА не придумывай данные о турнирах!
- НИКОГДА не генерируй даты, города, цены, контакты из головы!
- ОБЯЗАТЕЛЬНО вызови search_tournaments или find_tournament_by_name!
- Если инструмент не вернул данные - скажи "Турнир не найден"
- ЗАПРЕЩЕНО отвечать о турнире без вызова инструмента!

📋 ЛОГИКА РАБОТЫ:
1. Всегда уточняй только НЕДОСТАЮЩИЕ параметры
2. Никогда не спрашивай лишнего
3. Принимай параметры в любом порядке
4. Не обещай того, чего не делаешь

🎯 ПАРАМЕТРЫ ПОИСКА:
- age: год рождения (2015, 2016 и т.д.) - НЕ дата турнира!
- date_from/date_to: даты ПРОВЕДЕНИЯ турнира
- city: город проведения
- format: формат игры (8+1, 11×11 и т.д.)

📅 СЕЗОНЫ (текущий год 2025, турниры в 2026):
- зима: date_from="2025-12-01", date_to="2026-02-28"
- весна: date_from="2026-03-01", date_to="2026-05-31"
- лето: date_from="2026-06-01", date_to="2026-08-31"
- осень: date_from="2026-09-01", date_to="2026-11-30"

💬 СТИЛЬ ОБЩЕНИЯ:

ПРИВЕТСТВИЕ (если "привет", "здравствуй", "хай"):
- "👋 Привет! Подберу футбольные турниры в России. С чего начнём?"
- "⚽ Здравствуй! Ищем турнир по городу, сезону или году рождения?"
- "🏟️ Привет! Могу найти турнир по формату, сезону и возрасту."

ЗАПРОС БЕЗ ПАРАМЕТРОВ (если "найди турнир", "хочу турнир"):
- "Отлично. Давай уточним: город или сезон?"
- "Для какого возраста ищем? (год рождения)"
- "В каком формате играют? 11×11, 8+1, 7×7?"

ЧАСТИЧНЫЕ ПАРАМЕТРЫ:
- Только город: "Принял: город — {город}. Какой сезон?"
- Только сезон: "Окей, {сезон}. В каком городе?"
- Только формат: "Формат {формат} принят. В каком городе ищем?"
- Только год: "Год рождения {год}. В каком городе проходит турнир?"

НИЧЕГО НЕ НАЙДЕНО:
- "К сожалению, по этим параметрам турниров не найдено."
- "Попробуй изменить сезон или формат — город можно оставить."
- "Хочешь посмотреть ближайшие по возрасту варианты?"

ФОРМАТИРОВАНИЕ:
- ЗАПРЕЩЕНО использовать Markdown: НЕ пиши **текст**, *текст*
- Пиши ТОЛЬКО обычный текст
- Используй эмодзи: 🏆 📅 📍 💰 📞 ⚽ 🏟️

ОБЯЗАТЕЛЬНО В ОТВЕТЕ О ТУРНИРЕ:
- 📅 Даты проведения
- 📍 Место проведения
- 💰 Стоимость участия
- 📞 Контакты организаторов
- 🔗 Ссылка на Telegraph (если есть teletype_url) или локальная ссылка

ПРИМЕРЫ ВЫЗОВА ИНСТРУМЕНТОВ:
- "расскажи о турнирах" → search_tournaments(date_from="now", limit=15) ← СПИСОК ВСЕХ!
- "какие турниры есть" → search_tournaments(date_from="now", limit=15) ← СПИСОК ВСЕХ!
- "покажи турниры" → search_tournaments(date_from="now", limit=15) ← СПИСОК ВСЕХ!
- "Лето Москва 2012 8+1" → search_tournaments(age="2012", city="Москва", date_from="2026-06-01", date_to="2026-08-31", format="8+1")
- "турниры на весну для 2015" → search_tournaments(age="2015", date_from="2026-03-01", date_to="2026-05-31")
- "турниры зимой" → search_tournaments(date_from="2025-12-01", date_to="2026-02-28")
- "расскажи о SIRIUS CUP" → find_tournament_by_name(name="SIRIUS CUP") ← КОНКРЕТНЫЙ турнир по названию!
- "информация о LazaCup" → find_tournament_by_name(name="LazaCup") ← КОНКРЕТНЫЙ турнир по названию!

⚠️ КРИТИЧЕСКИ ВАЖНО - ВЫБОР ИНСТРУМЕНТА:
- "расскажи о турнирах" (без названия) → search_tournaments → СПИСОК ВСЕХ турниров!
- "расскажи о SIRIUS CUP" (с названием) → find_tournament_by_name → ОДИН турнир!
- Если нет КОНКРЕТНОГО названия турнира → ВСЕГДА используй search_tournaments!

ВАЖНО - ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:
1. На общие запросы ("расскажи о турнирах", "какие турниры есть", "покажи турниры") - ВСЕГДА вызывай search_tournaments для показа СПИСКА!
2. find_tournament_by_name - ТОЛЬКО для запросов с КОНКРЕТНЫМ названием турнира!
3. НИКОГДА не выбирай один турнир из списка для "рассказа" - показывай ВСЕ!
4. Если пользователь просит "расскажи о турнирах" - это запрос на СПИСОК через search_tournaments!
        """.strip()
    
    def _clean_markdown(self, text: str) -> str:
        """Удаляет Markdown форматирование из текста"""
        import re
        # Удаляем **жирный** и *курсив*
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        # Удаляем `код`
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # Удаляем [текст](ссылка) -> текст ссылка
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 \2', text)
        return text
    
    def _transliterate(self, text: str) -> str:
        """Транслитерация русского текста в латиницу и наоборот"""
        # Русский -> Латиница
        ru_to_lat = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
            'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
            'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
        }
        result = []
        for char in text:
            result.append(ru_to_lat.get(char, char))
        return ''.join(result).lower()
    
    def _fuzzy_match_tournaments(self, query: str, tournaments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Нечёткий поиск турниров по названию"""
        if not tournaments:
            return []
        
        query_lower = query.lower()
        query_translit = self._transliterate(query)
        # Нормализуем для сравнения (убираем различия k/c, i/y и т.д.)
        query_normalized = self._normalize_for_compare(query_translit)
        logger.info(f"🔍 Fuzzy: query='{query_lower}', translit='{query_translit}', norm='{query_normalized}'")
        
        matches = []
        for t in tournaments:
            title = t.get('title', '').lower()
            title_translit = self._transliterate(title)
            title_normalized = self._normalize_for_compare(title.lower())
            
            # Проверяем различные варианты совпадения
            score = 0
            
            # Точное вхождение
            if query_lower in title:
                score = 100
            # Транслитерированное вхождение
            elif query_translit in title_translit:
                score = 90
            # Нормализованное вхождение (k=c, i=y и т.д.)
            elif query_normalized in title_normalized:
                score = 85
            # Проверка на похожесть (расстояние Левенштейна)
            elif self._is_similar(query_normalized, title_normalized):
                score = 80
            # Частичное совпадение слов
            else:
                query_words = query_lower.split()
                for word in query_words:
                    if len(word) > 2:
                        word_norm = self._normalize_for_compare(self._transliterate(word))
                        if word in title or word_norm in title_normalized:
                            score += 30
                        # Проверяем похожесть слова
                        elif self._is_similar(word_norm, title_normalized):
                            score += 25
            
            if score > 0:
                matches.append((score, t))
        
        # Сортируем по score и возвращаем турниры
        matches.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in matches[:5]]
    
    def _normalize_for_compare(self, text: str) -> str:
        """Нормализует текст для нечёткого сравнения (k=c, i=y и т.д.)"""
        # Заменяем похожие буквы
        replacements = {
            'k': 'c', 'ck': 'c',  # k и c звучат похоже
            'y': 'i',  # y и i
            'ph': 'f',  # ph = f
            'w': 'v',  # w и v
            'x': 'ks',  # x = ks
            'qu': 'kv',  # qu = kv
        }
        result = text.lower()
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
    
    def _is_similar(self, query: str, text: str, threshold: float = 0.7) -> bool:
        """Проверяет похожесть строк (query должен быть частью text)"""
        if not query or not text:
            return False
        
        # Проверяем вхождение с допуском 1-2 символов
        query_len = len(query)
        
        # Ищем похожую подстроку в тексте
        for i in range(len(text) - query_len + 3):
            if i + query_len > len(text):
                break
            substring = text[i:i + query_len]
            
            # Считаем совпадающие символы
            matches = sum(1 for a, b in zip(query, substring) if a == b)
            similarity = matches / query_len
            
            if similarity >= threshold:
                return True
        
        # Также проверяем если query содержится в text с небольшими отличиями
        # Например "lazacap" похож на "lazacup" (отличие в 1 букве)
        for i in range(len(text) - query_len + 1):
            substring = text[i:i + query_len]
            diff = sum(1 for a, b in zip(query, substring) if a != b)
            if diff <= 2:  # Допускаем до 2 отличий
                return True
        
        return False
    
    def _format_tournaments_list(self, tournaments: List[Dict[str, Any]]) -> str:
        """Форматирует список турниров с иерархией: Рейтинг ⭐ > Премиум 🔝 > Обычные
        Показывает ВСЕ рейтинговые турниры (не ограничивает до 1)
        """
        # Логируем показы турниров для аналитики
        self._log_tournament_impressions(tournaments, context="search")
        
        lines = []
        
        # Разделяем турниры по категориям
        rating_tournaments = []  # ⭐ Рейтинговые (показываем ВСЕ)
        premium_tournaments = []  # 🔝 Премиум
        regular_tournaments = []  # Обычные
        
        for t in tournaments:
            if t.get('rating_active') or t.get('priority_rating'):
                rating_tournaments.append(t)
            elif t.get('premium_active') or t.get('is_premium'):
                premium_tournaments.append(t)
            else:
                regular_tournaments.append(t)
        
        start_num = 1
        
        # 1. Рейтинговые турниры ⭐ (показываем ВСЕ, не ограничиваем до 1)
        if rating_tournaments:
            if len(rating_tournaments) == 1:
                lines.append("⭐ Рекомендуемый турнир")
                lines.append(self._format_tournament_item(rating_tournaments[0], show_number=False))
            else:
                lines.append("⭐ Рекомендуемые турниры")
                for i, t in enumerate(rating_tournaments, 1):
                    lines.append(self._format_tournament_item(t, number=i))
            start_num = len(rating_tournaments) + 1
            lines.append("━━━━━━━━━━━━━━")
            lines.append("")
        
        # 2. Премиум-турниры 🔝
        if premium_tournaments:
            lines.append("🔝 Премиум-турниры")
            for i, t in enumerate(premium_tournaments, start_num):
                lines.append(self._format_tournament_item(t, number=i))
            lines.append("━━━━━━━━━━━━━━")
            lines.append("")
            start_num += len(premium_tournaments)
        
        # 3. Обычные турниры
        if regular_tournaments:
            if rating_tournaments or premium_tournaments:
                lines.append("Другие подходящие турниры:")
            else:
                lines.append(f"🏆 Найдено турниров: {len(tournaments)}\n")
            for i, t in enumerate(regular_tournaments, start_num):
                lines.append(self._format_tournament_item(t, number=i))
        
        if not tournaments:
            lines.append("🔍 Турниры не найдены")
        
        lines.append("")
        lines.append(random.choice(TOURNAMENT_CHOICE_PROMPTS))
        return "\n".join(lines)
    
    def _format_tournament_item(self, t: Dict[str, Any], number: int = None, show_number: bool = True) -> str:
        """Форматирует один турнир для списка"""
        title = t.get('title', 'Турнир')
        start_date = t.get('start_date') or t.get('date_start', '')
        city = t.get('city', '')
        entry_fee = t.get('entry_fee', '')
        t_id = t.get('id', '')
        teletype_url = t.get('teletype_url')
        
        # Форматируем дату
        if start_date:
            try:
                dt = datetime.strptime(start_date, '%Y-%m-%d')
                start_date = dt.strftime('%d.%m.%Y')
            except:
                pass
        
        item_lines = []
        if show_number and number:
            item_lines.append(f"{number}. {title}")
        else:
            item_lines.append(f"{title}")
        
        if start_date:
            item_lines.append(f"   📅 {start_date}")
        if city:
            item_lines.append(f"   📍 {city}")
        if entry_fee:
            item_lines.append(f"   💰 {entry_fee}")
        # Ссылка - кликабельная надпись с HTML
        if teletype_url and t_id:
            item_lines.append(f'   <a href="http://127.0.0.1:8000/t/{t_id}">📖 Подробная информация</a>')
        elif t_id:
            item_lines.append(f'   <a href="http://127.0.0.1:8000/tournaments/{t_id}?utm_source=telegram&utm_medium=bot&utm_campaign=llm_search">📖 Подробная информация</a>')
        item_lines.append("")
        
        return "\n".join(item_lines)
    
    def _format_single_tournament(self, tournament: Dict[str, Any]) -> str:
        """Форматирует краткий рассказ о турнире на основе данных карточки"""
        title = tournament.get('title', 'Турнир')
        
        # Собираем данные для рассказа
        start_date = tournament.get('start_date') or tournament.get('date_start', '')
        end_date = tournament.get('end_date') or tournament.get('date_end', '')
        city = tournament.get('city', '')
        region = tournament.get('region', '')
        birth_years = tournament.get('birth_years_display') or tournament.get('birth_years', '')
        format_str = tournament.get('format', '')
        entry_fee = tournament.get('entry_fee', '')
        organizer = tournament.get('organizer_name', '')
        contact = tournament.get('contact', '')
        short_desc = tournament.get('short_description', '')
        body = tournament.get('body', '')
        t_id = tournament.get('id', '')
        
        # Извлекаем имя контактного лица из body если есть
        contact_person = tournament.get('contact_person', '')
        if not contact_person and body:
            import re
            # Ищем паттерны типа "Телефон: +7 ... (Имя)" или "Контактное лицо: Имя"
            # Учитываем markdown форматирование (**жирный**)
            patterns = [
                r'\*\*Контактное лицо:\*\*\s*([А-Яа-яЁёA-Za-z]+)',  # **Контактное лицо:** Артём
                r'\*\*Контактное лицо\*\*[:\s]+([А-Яа-яЁёA-Za-z]+)',  # **Контактное лицо**: Артём
                r'Контактное лицо[:\s]+([А-Яа-яЁёA-Za-z]+)',  # Контактное лицо: Андрей
                r'\*\*Телефон:\*\*\s*[+\d\s\-()]+\s*\(([А-Яа-яЁёA-Za-z]+)\)',  # **Телефон:** +7... (Имя)
                r'Телефон[:\s]+[+\d\s\-()]+\s*\(([А-Яа-яЁёA-Za-z]+)\)',  # Телефон: +7... (Имя)
                r'[+\d\s\-()]{10,}\s*\(([А-Яа-яЁёA-Za-z]+)\)',  # +7 904 507-24-50 (Никита)
            ]
            for pattern in patterns:
                match = re.search(pattern, body, re.MULTILINE | re.IGNORECASE)
                if match:
                    contact_person = match.group(1)
                    logger.info(f"📞 Извлечено контактное лицо: {contact_person}")
                    break
        
        # Форматируем даты
        dates_str = ""
        if start_date:
            try:
                dt_start = datetime.strptime(start_date, '%Y-%m-%d')
                start_str = dt_start.strftime('%d.%m.%Y')
                if end_date:
                    dt_end = datetime.strptime(end_date, '%Y-%m-%d')
                    end_str = dt_end.strftime('%d.%m.%Y')
                    dates_str = f"с {start_str} по {end_str}"
                else:
                    dates_str = start_str
            except:
                dates_str = start_date
        
        # Форматируем место
        location = city
        if region:
            location += f" ({region})"
        
        # Форматируем возраст
        ages_str = ""
        if birth_years:
            if isinstance(birth_years, list):
                clean_years = [str(y).strip().strip("'\"[]") for y in birth_years]
                ages_str = ", ".join(clean_years) + " г.р."
            else:
                ages_str = str(birth_years)
        
        # Проверяем приоритетный рейтинг
        is_priority = tournament.get('priority_rating', False)
        star = "⭐ " if is_priority else ""
        
        # Генерируем краткий рассказ
        lines = [f"🏆 {star}{title}\n"]
        
        # Вступительное предложение
        intro = f"Приглашаем на турнир \"{title}\""
        if location:
            intro += f", который пройдёт в {location}"
        if dates_str:
            intro += f" {dates_str}"
        intro += "!"
        lines.append(intro)
        lines.append("")
        
        # Информация о возрастах
        if ages_str:
            lines.append(f"👶 Участники: команды {ages_str}")
        
        # Формат игры
        if format_str:
            lines.append(f"⚽ Формат: {format_str}")
        
        # Стоимость
        if entry_fee:
            lines.append(f"💰 Стоимость участия: {entry_fee}")
        
        # Описание если есть
        if short_desc and len(short_desc) < 300:
            lines.append(f"\n📝 {short_desc}")
        
        # Контактная информация
        lines.append("\n📞 Контакты для записи:")
        if organizer:
            lines.append(f"   Организатор: {organizer}")
        if contact_person:
            lines.append(f"   Контактное лицо: {contact_person}")
        if contact:
            lines.append(f"   Телефон: {contact}")
        
        # Ссылки - кликабельные надписи с HTML
        teletype_url = tournament.get('teletype_url')
        if t_id:
            lines.append(f'\n<a href="http://127.0.0.1:8000/tournaments/{t_id}?utm_source=telegram&utm_medium=bot&utm_campaign=recommendation">🌐 Карточка на сайте</a>')
            if teletype_url:
                lines.append(f'<a href="http://127.0.0.1:8000/t/{t_id}">📰 Статья в Telegraph</a>')
        
        return "\n".join(lines)
    
    def _get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for LLM"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_tournaments",
                    "description": "Поиск и показ СПИСКА турниров. ОБЯЗАТЕЛЬНО используй для: 'расскажи о турнирах', 'какие турниры есть', 'покажи турниры', 'все турниры', общих запросов о турнирах. Возвращает СПИСОК всех подходящих турниров.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "q": {
                                "type": "string",
                                "description": "Текстовый запрос для поиска (используй для поиска по городу, названию, региону)"
                            },
                            "date_from": {
                                "type": "string",
                                "description": "Дата начала поиска (YYYY-MM-DD или 'now'). Для актуальных турниров используй 'now'"
                            },
                            "date_to": {
                                "type": "string",
                                "description": "Дата окончания поиска (YYYY-MM-DD)"
                            },
                            "age": {
                                "type": "string",
                                "description": "Возрастная категория (например, '2016', '2015-2016')"
                            },
                            "format": {
                                "type": "string",
                                "description": "Формат игры (например, '5x5', '8x8', '11x11')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Максимальное количество результатов (по умолчанию 15)",
                                "default": 15
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_tournament",
                    "description": "Получить полную информацию о турнире по ID",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tournament_id": {
                                "type": "integer",
                                "description": "ID турнира"
                            }
                        },
                        "required": ["tournament_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_tournament_card",
                    "description": "Получить карточку турнира для показа пользователю",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tournament_id": {
                                "type": "integer",
                                "description": "ID турнира"
                            }
                        },
                        "required": ["tournament_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_tournament_by_name",
                    "description": "Найти ОДИН КОНКРЕТНЫЙ турнир по ТОЧНОМУ названию. Используй ТОЛЬКО когда пользователь явно указал название турнира (например: 'расскажи о SIRIUS CUP', 'информация о LazaCup'). НЕ используй для общих запросов типа 'расскажи о турнирах' - для этого используй search_tournaments!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "ТОЧНОЕ название турнира (например: 'SIRIUS CUP', 'LazaCup', 'Рождественский кубок')"
                            }
                        },
                        "required": ["name"]
                    }
                }
            }
        ]
    
    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool call"""
        try:
            if tool_name == "search_tournaments":
                tournaments = await self.backend_client.search_tournaments(**tool_args)
                
                # Логируем показы (impressions) для аналитики
                for t in tournaments:
                    t_id = t.get('id')
                    if t_id:
                        try:
                            await self.backend_client.log_analytics_event(
                                tournament_id=t_id,
                                event_type="impression",
                                context="bot_search"
                            )
                        except Exception as e:
                            logger.debug(f"Failed to log impression for tournament {t_id}: {e}")
                
                # Собираем картинки для ВСЕХ турниров
                tournaments_with_images = {}
                for t in tournaments:
                    t_id = t.get('id')
                    full_t = await self.backend_client.get_tournament(t_id)
                    if full_t and full_t.get('image_cover_square_url'):
                        img_url = full_t['image_cover_square_url'].lstrip('/')
                        # ВАЖНО: сначала проверяем app/static (правильная папка), потом остальные
                        alt_paths = [
                            f"../app/{img_url}",  # Приоритет: app/static
                            f"app/{img_url}",
                            f"../{img_url}",
                            img_url,
                        ]
                        for alt_path in alt_paths:
                            if os.path.exists(alt_path):
                                tournaments_with_images[t_id] = {
                                    "image_path": alt_path,
                                    "title": full_t.get('title', ''),
                                    "tournament": full_t
                                }
                                break
                
                # Берём картинку первого турнира как дефолтную
                image_path = None
                if tournaments and len(tournaments) > 0:
                    first_id = tournaments[0].get('id')
                    if first_id in tournaments_with_images:
                        image_path = tournaments_with_images[first_id].get('image_path')
                        logger.info(f"📸 Дефолтная картинка (первый турнир): {image_path}")
                
                return {
                    "success": True,
                    "tournaments": tournaments,
                    "count": len(tournaments),
                    "image_path": image_path,
                    "tournaments_with_images": tournaments_with_images
                }
            
            elif tool_name == "get_tournament":
                tournament = await self.backend_client.get_tournament(tool_args["tournament_id"])
                if tournament:
                    # Добавляем путь к изображению для использования в ответе
                    image_path = None
                    if tournament.get('image_cover_square_url'):
                        img_url = tournament['image_cover_square_url'].lstrip('/')
                        # ВАЖНО: сначала проверяем app/static (правильная папка), потом остальные
                        alt_paths = [
                            f"../app/{img_url}",  # Приоритет: app/static
                            f"app/{img_url}",
                            f"../{img_url}",
                            img_url,
                        ]
                        
                        for alt_path in alt_paths:
                            if os.path.exists(alt_path):
                                image_path = alt_path
                                break
                    
                    return {
                        "success": True,
                        "tournament": tournament,
                        "image_path": image_path
                    }
                else:
                    return {
                        "success": False,
                        "error": "Турнир не найден"
                    }
            
            elif tool_name == "get_tournament_card":
                result = await self.backend_client.get_tournament_card(tool_args["tournament_id"])
                # API теперь возвращает {"type": "data", "card": {...}} с полными данными турнира
                card_data = result.get("card") if result.get("type") == "data" else None
                if card_data:
                    return {
                        "success": True,
                        "card": card_data
                    }
                else:
                    # Fallback: если API вернул старый формат с URL, получаем турнир напрямую
                    tournament_id = tool_args["tournament_id"]
                    tournament = await self.backend_client.get_tournament(tournament_id)
                    if tournament:
                        return {
                            "success": True,
                            "card": tournament
                        }
                    return {
                        "success": False,
                        "error": "Турнир не найден"
                    }
            
            elif tool_name == "find_tournament_by_name":
                # Ищем турнир по названию с поддержкой транслитерации
                name_query = tool_args.get("name", "")
                
                # Пробуем найти напрямую
                tournaments = await self.backend_client.search_tournaments(q=name_query, limit=8)
                
                # Если не нашли - пробуем транслитерацию
                if not tournaments or len(tournaments) == 0:
                    transliterated = self._transliterate(name_query)
                    if transliterated != name_query.lower():
                        logger.info(f"🔄 Транслитерация: '{name_query}' -> '{transliterated}'")
                        tournaments = await self.backend_client.search_tournaments(q=transliterated, limit=8)
                
                # Если всё ещё не нашли - пробуем нечёткий поиск по всем турнирам
                if not tournaments or len(tournaments) == 0:
                    all_tournaments = await self.backend_client.search_tournaments(limit=20)
                    logger.info(f"🔍 Fuzzy search: query='{name_query}', all_tournaments={len(all_tournaments) if all_tournaments else 0}")
                    tournaments = self._fuzzy_match_tournaments(name_query, all_tournaments)
                    logger.info(f"🔍 Fuzzy match result: {len(tournaments) if tournaments else 0} турниров")
                
                if tournaments and len(tournaments) > 0:
                    # Берём первый найденный турнир
                    tournament = tournaments[0]
                    tournament_id = tournament.get('id')
                    
                    # Получаем полные данные турнира
                    full_tournament = await self.backend_client.get_tournament(tournament_id)
                    
                    if full_tournament:
                        # Добавляем путь к изображению
                        image_path = None
                        if full_tournament.get('image_cover_square_url'):
                            img_url = full_tournament['image_cover_square_url'].lstrip('/')
                            # ВАЖНО: сначала проверяем app/static (правильная папка), потом остальные
                            alt_paths = [
                                f"../app/{img_url}",  # Приоритет: app/static
                                f"app/{img_url}",
                                f"../{img_url}",
                                img_url,
                            ]
                            for alt_path in alt_paths:
                                if os.path.exists(alt_path):
                                    image_path = alt_path
                                    logger.info(f"📸 Найдена картинка для турнира: {alt_path}")
                                    break
                        
                        return {
                            "success": True,
                            "tournament": full_tournament,
                            "tournament_id": tournament_id,
                            "image_path": image_path
                        }
                
                return {
                    "success": False,
                    "error": f"Турнир '{name_query}' не найден"
                }
            
            else:
                return {
                    "success": False,
                    "error": f"Неизвестный инструмент: {tool_name}"
                }
                
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _format_response(self, text: str, tool_calls: List[Dict[str, Any]], tool_results: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response with optional keyboard and image"""
        response = {
            "text": text,
            "payload": {
                "tool_calls": tool_calls
            }
        }
        
        # Add keyboard based on tool calls
        keyboard = None
        image_path = None
        
        # Проверяем результаты инструментов на наличие изображений
        # Умный выбор картинки - ищем упоминание турнира в тексте ответа
        if tool_results:
            for result in tool_results:
                # Если есть словарь турниров с картинками - ищем упоминание в тексте
                if result.get("tournaments_with_images"):
                    tournaments_with_images = result["tournaments_with_images"]
                    text_lower = text.lower()
                    
                    # Ищем какой турнир упоминается в ответе
                    for t_id, t_data in tournaments_with_images.items():
                        title = t_data.get("title", "").lower()
                        # Проверяем упоминание названия турнира в тексте
                        if title and any(word in text_lower for word in title.split()[:3] if len(word) > 3):
                            image_path = t_data.get("image_path")
                            logger.info(f"📸 Выбрана картинка по названию '{t_data.get('title')}': {image_path}")
                            break
                    
                    # Если не нашли по названию - берём дефолтную
                    if not image_path and result.get("image_path"):
                        image_path = result["image_path"]
                        logger.info(f"📸 Используем дефолтную картинку: {image_path}")
                
                # Простой случай - одна картинка
                elif result.get("image_path") and not image_path:
                    image_path = result["image_path"]
        
        # If search was performed, add buttons for actions
        # Кнопки убраны - пользователь взаимодействует через текст
        # keyboard остаётся None
        
        if image_path:
            response["image_path"] = image_path
        
        return response


    async def generate_conversation_summary(
        self, 
        message_history: List[Dict[str, str]], 
        contact_id: int
    ) -> Optional[str]:
        """
        Генерирует краткое резюме разговора для сохранения в draft_info контакта.
        
        Args:
            message_history: История сообщений [{"role": "user/assistant", "content": "..."}]
            contact_id: ID контакта в CRM
            
        Returns:
            Строка с резюме или None при ошибке
        """
        if not message_history or len(message_history) < 2:
            return None
        
        try:
            # Формируем промпт для создания резюме
            summary_prompt = """Проанализируй историю переписки с пользователем и создай краткое резюме.

ИСТОРИЯ ПЕРЕПИСКИ:
"""
            for msg in message_history[-10:]:  # Последние 10 сообщений
                role = "Пользователь" if msg.get("role") == "user" else "Бот"
                summary_prompt += f"{role}: {msg.get('content', '')}\n"
            
            summary_prompt += """

ЗАДАЧА:
Создай краткое резюме (2-4 предложения) о том:
1. Какие турниры интересовали пользователя
2. Какие критерии поиска использовал (город, возраст, даты)
3. Какие вопросы задавал

Формат ответа - только текст резюме, без заголовков и маркеров."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты помощник для создания кратких резюме разговоров о турнирах."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            summary = response.choices[0].message.content.strip()
            
            if summary:
                # Добавляем timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                formatted_summary = f"[Telegram {timestamp}] {summary}"
                
                # Сохраняем в draft_info контакта
                try:
                    await self._update_contact_draft(contact_id, formatted_summary)
                    logger.info(f"📝 Summary saved for contact {contact_id}: {len(summary)} chars")
                except Exception as e:
                    logger.error(f"Error saving summary to contact {contact_id}: {e}")
                
                return formatted_summary
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating conversation summary: {e}")
            return None
    
    async def _update_contact_draft(self, contact_id: int, new_summary: str) -> None:
        """Обновляет draft_info контакта, добавляя новое резюме"""
        try:
            # Получаем текущий контакт
            contact = await self.backend_client.get_contact(contact_id)
            
            if not contact:
                logger.warning(f"Contact {contact_id} not found for draft update")
                return
            
            # Получаем текущий draft_info
            current_draft = contact.get('draft_info', '') or ''
            
            # Добавляем новое резюме
            if current_draft:
                updated_draft = f"{current_draft}\n\n{new_summary}"
            else:
                updated_draft = new_summary
            
            # Обновляем контакт
            await self.backend_client.update_contact_draft(contact_id, updated_draft)
            
        except Exception as e:
            logger.error(f"Error updating contact draft: {e}")
            raise

    async def extract_and_save_tags(
        self, 
        message: str, 
        tool_calls: List[Dict[str, Any]], 
        contact_id: int
    ) -> List[Dict[str, Any]]:
        """
        Извлекает теги интересов из сообщения пользователя и сохраняет их в карточку контакта.
        
        Args:
            message: Сообщение пользователя
            tool_calls: Список вызовов инструментов (для извлечения параметров поиска)
            contact_id: ID контакта в CRM
            
        Returns:
            Список извлеченных тегов
        """
        if not contact_id:
            return []
        
        tags_to_add = []
        
        try:
            # Извлекаем теги из параметров поиска турниров
            for tool_call in tool_calls:
                if tool_call.get("name") == "search_tournaments":
                    args = tool_call.get("arguments", {})
                    
                    # Город
                    if args.get("q"):
                        # Проверяем, содержит ли запрос город
                        city_keywords = ["сочи", "москва", "спб", "санкт-петербург", "краснодар", 
                                        "кабардинка", "лазаревское", "сириус", "анапа", "геленджик"]
                        q_lower = args["q"].lower()
                        for city in city_keywords:
                            if city in q_lower:
                                tags_to_add.append({
                                    "key": "interest_city",
                                    "value": city.capitalize(),
                                    "confidence": 0.9,
                                    "source": "telegram_search"
                                })
                                break
                    
                    # Возраст детей
                    if args.get("age"):
                        tags_to_add.append({
                            "key": "child_birth_year",
                            "value": args["age"],
                            "confidence": 0.95,
                            "source": "telegram_search"
                        })
                    
                    # Формат игры
                    if args.get("format"):
                        tags_to_add.append({
                            "key": "interest_format",
                            "value": args["format"],
                            "confidence": 0.9,
                            "source": "telegram_search"
                        })
                    
                    # Период (месяц/сезон)
                    if args.get("date_from") and args["date_from"] != "now":
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(args["date_from"], "%Y-%m-%d")
                            month_names = {
                                1: "январь", 2: "февраль", 3: "март", 4: "апрель",
                                5: "май", 6: "июнь", 7: "июль", 8: "август",
                                9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
                            }
                            tags_to_add.append({
                                "key": "interest_month",
                                "value": month_names.get(dt.month, str(dt.month)),
                                "confidence": 0.8,
                                "source": "telegram_search"
                            })
                        except:
                            pass
                
                elif tool_call.get("name") in ["get_tournament", "find_tournament_by_name", "get_tournament_card"]:
                    # Пользователь интересуется конкретным турниром
                    args = tool_call.get("arguments", {})
                    if args.get("name"):
                        tags_to_add.append({
                            "key": "interest_tournament",
                            "value": args["name"],
                            "confidence": 0.85,
                            "source": "telegram_search"
                        })
            
            # Дополнительный анализ текста сообщения для извлечения интересов
            message_lower = message.lower()
            
            # Роль пользователя
            if any(word in message_lower for word in ["тренер", "тренирую", "моя команда"]):
                tags_to_add.append({
                    "key": "role",
                    "value": "тренер",
                    "confidence": 0.8,
                    "source": "telegram_message"
                })
            elif any(word in message_lower for word in ["сын", "дочь", "ребенок", "мой ребёнок"]):
                tags_to_add.append({
                    "key": "role",
                    "value": "родитель",
                    "confidence": 0.8,
                    "source": "telegram_message"
                })
            
            # Сохраняем теги через API
            if tags_to_add and contact_id:
                try:
                    await self.backend_client.merge_contact_tags(
                        contact_id=contact_id,
                        add_tags=tags_to_add,
                        meta={"source": "telegram_bot", "message": message[:100]}
                    )
                    logger.info(f"🏷️ Saved {len(tags_to_add)} tags for contact {contact_id}: {[t['key'] + '=' + t['value'] for t in tags_to_add]}")
                except Exception as e:
                    logger.error(f"Error saving tags for contact {contact_id}: {e}")
            
            return tags_to_add
            
        except Exception as e:
            logger.error(f"Error extracting tags: {e}")
            return []

    async def update_contact_portrait(
        self, 
        contact_id: int,
        message_history: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Обновляет "портрет" контакта на основе накопленной информации.
        Анализирует draft_info и создает структурированное описание.
        
        Args:
            contact_id: ID контакта
            message_history: История сообщений для анализа
            
        Returns:
            Обновленный портрет или None
        """
        if not contact_id or not message_history or len(message_history) < 4:
            return None
        
        try:
            # Получаем контакт с текущими данными
            contact = await self.backend_client.get_contact(contact_id)
            if not contact:
                return None
            
            # Собираем информацию для анализа
            draft_info = contact.get('draft_info', '') or ''
            tags = contact.get('tags', []) or []
            
            # Формируем промпт для создания портрета
            portrait_prompt = f"""Проанализируй информацию о пользователе и создай краткий "портрет".

ТЕКУЩИЕ ТЕГИ ИНТЕРЕСОВ:
{json.dumps(tags, ensure_ascii=False, indent=2) if tags else "Нет тегов"}

ИСТОРИЯ ВЗАИМОДЕЙСТВИЙ:
{draft_info if draft_info else "Нет истории"}

ПОСЛЕДНИЕ СООБЩЕНИЯ:
"""
            for msg in message_history[-6:]:
                role = "Пользователь" if msg.get("role") == "user" else "Бот"
                portrait_prompt += f"{role}: {msg.get('content', '')[:200]}\n"
            
            portrait_prompt += """

ЗАДАЧА:
Создай краткий портрет пользователя (3-5 предложений):
1. Роль (тренер/родитель/организатор)
2. Интересующие регионы/города
3. Возраст детей (год рождения)
4. Предпочтения по турнирам (формат, сезон)
5. Особые запросы или потребности

Формат: только текст портрета, без заголовков."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты аналитик CRM, создающий портреты клиентов."},
                    {"role": "user", "content": portrait_prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            portrait = response.choices[0].message.content.strip()
            
            if portrait:
                # Добавляем портрет в draft_info с меткой
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                formatted_portrait = f"\n\n--- ПОРТРЕТ КОНТАКТА ({timestamp}) ---\n{portrait}"
                
                # Обновляем draft_info
                current_draft = draft_info
                
                # Удаляем старый портрет если есть
                if "--- ПОРТРЕТ КОНТАКТА" in current_draft:
                    import re
                    current_draft = re.sub(r'\n\n--- ПОРТРЕТ КОНТАКТА.*?(?=\n\n---|$)', '', current_draft, flags=re.DOTALL)
                
                updated_draft = current_draft + formatted_portrait
                
                await self.backend_client.update_contact_draft(contact_id, updated_draft)
                logger.info(f"👤 Updated portrait for contact {contact_id}: {len(portrait)} chars")
                
                return portrait
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating contact portrait: {e}")
            return None


