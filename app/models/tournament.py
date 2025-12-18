from pydantic import BaseModel, Field
from typing import Optional, List, Union, Literal
from datetime import datetime

class Tournament(BaseModel):
    """Модель турнира"""
    id: Optional[int] = None
    title: str = Field(..., description="Название турнира")
    alternative_names: Optional[List[str]] = Field(None, description="Альтернативные названия для поиска")
    city: Optional[str] = Field(None, description="Город проведения")
    region: Optional[str] = Field(None, description="Регион")
    sport: Optional[str] = Field(None, description="Вид спорта")
    start_date: Optional[str] = Field(None, description="Дата начала (формат: DD.MM.YYYY)")
    end_date: Optional[str] = Field(None, description="Дата окончания (формат: DD.MM.YYYY)")
    format: Optional[str] = Field(None, description="Формат турнира")
    teams_min: Optional[int] = Field(None, description="Минимальное количество команд")
    teams_max: Optional[int] = Field(None, description="Максимальное количество команд")
    entry_fee: Optional[str] = Field(None, description="Взнос за участие")
    organizer_name: Optional[str] = Field(None, description="Название организатора")
    contact: Optional[str] = Field(None, description="Контактная информация")
    contact_person: Optional[str] = Field(None, description="Имя контактного лица")
    addons: Optional[str] = Field(None, description="Дополнительная информация")
    description_short: Optional[str] = Field(None, description="Краткое описание")
    description_full: Optional[str] = Field(None, description="Полное описание")
    selling_text: Optional[str] = Field(None, description="Продающий текст о турнире")
    
    # Новые поля для задачи 38
    body: Optional[str] = Field(None, description="Основной текст турнира (Markdown/HTML)")
    short_description: Optional[str] = Field(None, description="Короткое описание для анонса (100-400 символов)")
    
    # Изображения
    image_original_url: Optional[str] = Field(None, description="URL исходной загруженной картинки")
    image_cover_16x9_url: Optional[str] = Field(None, description="URL обложки турнира 16:9")
    image_cover_square_url: Optional[str] = Field(None, description="URL квадратной версии обложки 1:1")
    
    # Статус (расширенный enum)
    status: Optional[Literal["draft", "ready_for_publish", "published", "archived", "active", "completed", "cancelled"]] = Field(
        "draft", description="Статус турнира"
    )
    
    # Источник создания
    source: Optional[Literal["manual", "whatsapp", "telegram", "other"]] = Field(
        "manual", description="Источник создания турнира"
    )
    
    # Привязка к организатору (для личного кабинета)
    organizer_contact_id: Optional[int] = Field(None, description="ID контакта организатора в системе")
    organizer_phone: Optional[str] = Field(None, description="Телефон организатора (для матчинга с contact)")
    
    # Рейтинг турнира ⭐ (эксклюзивная рекомендация сервиса, макс 1 на запрос)
    priority_rating: Optional[bool] = Field(False, description="Флаг рейтингового турнира ⭐ (рекомендация сервиса)")
    priority_rating_start_date: Optional[str] = Field(None, description="Дата начала рейтинга (для отсчёта 45 дней)")
    rating_until: Optional[str] = Field(None, description="Дата окончания рейтинга (YYYY-MM-DD)")
    
    # Премиум-размещение 🔝 (усиленная видимость, может быть несколько)
    is_premium: Optional[bool] = Field(False, description="Флаг премиум-турнира 🔝 (выше обычных в выдаче)")
    premium_until: Optional[str] = Field(None, description="Дата окончания премиум-размещения (YYYY-MM-DD)")
    premium_last_ended: Optional[str] = Field(None, description="Дата окончания предыдущего премиума (для 24ч ограничения)")
    
    # Поля для публикации
    publish_to_teletype: Optional[bool] = Field(False, description="Флаг публикации в Teletype")
    publish_to_telegram: Optional[bool] = Field(False, description="Флаг публикации в Telegram")
    teletype_url: Optional[str] = Field(None, description="Ссылка на статью в Teletype")
    teletype_post_id: Optional[str] = Field(None, description="ID поста в Teletype")
    telegram_chat_id: Optional[str] = Field(None, description="ID канала/группы Telegram")
    telegram_message_id: Optional[str] = Field(None, description="ID сообщения в Telegram")
    published_at: Optional[datetime] = Field(None, description="Дата первой успешной публикации")
    
    # Старые поля (для обратной совместимости)
    poster_url: Optional[str] = Field(None, description="URL сгенерированного постера (deprecated, используйте image_cover_16x9_url)")
    poster_path: Optional[str] = Field(None, description="Путь к файлу постера на сервере (deprecated)")
    draft_info: Optional[str] = Field(None, description="Черновик информации из анализа")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Дата создания")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления")
    message_id: Optional[str] = Field(None, description="ID сообщения, из которого был создан турнир")
    channel_id: Optional[str] = Field(None, description="ID канала, из которого был создан турнир")
    birth_years: Optional[Union[List[str], str]] = Field(
        None, description="Список годов рождения участников"
    )

    def _parsed_birth_years(self) -> List[str]:
        value = self.birth_years
        if not value:
            return []

        if isinstance(value, str):
            raw_items = [part.strip() for part in value.replace('г.р.', '').replace('г. р.', '').split(',')]
        else:
            raw_items = value

        cleaned = []
        for item in raw_items:
            text = str(item).strip()
            if not text:
                continue
            # Clean up malformed data like "['2014'" or "'2015'"
            text = text.replace("[", "").replace("]", "").replace("'", "").replace('"', "").strip()
            if text:
                # Проверяем, является ли это диапазоном (например "2019 - 2011" или "2011-2019")
                import re
                range_match = re.match(r'(\d{4})\s*[-–—]\s*(\d{4})', text)
                if range_match:
                    year1 = int(range_match.group(1))
                    year2 = int(range_match.group(2))
                    min_year = min(year1, year2)
                    max_year = max(year1, year2)
                    # Добавляем все годы из диапазона
                    for year in range(min_year, max_year + 1):
                        cleaned.append(str(year))
                else:
                    cleaned.append(text)
        return cleaned

    @property
    def birth_years_list(self) -> List[str]:
        return self._parsed_birth_years()

    @property
    def birth_years_display(self) -> Optional[str]:
        years = self._parsed_birth_years()
        if not years:
            return None

        numeric_years = []
        for year in years:
            digits = ''.join(ch for ch in str(year) if ch.isdigit())
            if len(digits) == 4:
                try:
                    numeric_years.append(int(digits))
                except ValueError:
                    continue

        if numeric_years:
            numeric_years = sorted(set(numeric_years))
            if len(numeric_years) == 1:
                return f"{numeric_years[0]} г.р."
            return f"{numeric_years[0]} - {numeric_years[-1]} г.р."

        return ", ".join(years)

class ExtractedTournamentData(BaseModel):
    """Модель для извлеченных данных турнира"""
    location: Optional[dict] = Field(None, description="Локация турнира")
    startDate: Optional[str] = Field(None, description="Дата начала (dd.mm.yyyy)")
    endDate: Optional[str] = Field(None, description="Дата окончания (dd.mm.yyyy)")
    birthYears: Optional[List[int]] = Field(None, description="Года рождения участников")
    matchFormats: Optional[List[dict]] = Field(None, description="Форматы матчей по возрастам")
    teamRoster: Optional[dict] = Field(None, description="Состав команды")
    documents: Optional[List[str]] = Field(None, description="Документы для регистрации")
    structure: Optional[List[str]] = Field(None, description="Структура турнира")
    points: Optional[dict] = Field(None, description="Система очков")
    awardsTeam: Optional[List[str]] = Field(None, description="Командные награды")
    awardsIndividual: Optional[List[str]] = Field(None, description="Индивидуальные награды")
    fee: Optional[dict] = Field(None, description="Взнос за участие")
    accommodation: Optional[List[dict]] = Field(None, description="Размещение")
    services: Optional[List[dict]] = Field(None, description="Дополнительные услуги")
    contacts: Optional[dict] = Field(None, description="Контакты")
