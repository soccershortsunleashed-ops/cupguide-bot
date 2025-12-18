# ⚽ CupGuide - Telegram Bot для поиска футбольных турниров

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Aiogram-3.x-blue.svg" alt="Aiogram">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

Интеллектуальный Telegram-бот для подбора детских и юношеских футбольных турниров по всей России. Использует LLM для понимания естественного языка и персонализированных рекомендаций.

## 🎯 Возможности

### Для пользователей (тренеров, родителей)
- 🔍 **Умный поиск** — поиск турниров на естественном языке
- 📍 **Фильтрация** — по городу, возрасту, датам, формату игры
- ⭐ **Рекомендации** — персонализированные предложения на основе запроса
- 📊 **Детальная информация** — даты, место, взносы, контакты организаторов

### Для организаторов турниров
- 📋 **Личный кабинет** — управление турнирами через Telegram WebApp
- 🔝 **Премиум-размещение** — повышенная видимость в поиске
- ⭐ **Рейтинг** — приоритет в выдаче и метка "Рекомендуемый"
- 📈 **Аналитика** — показы, клики, CTR, источники трафика

## 🏗️ Архитектура

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Telegram Bot   │────▶│   FastAPI API   │────▶│   JSON Storage  │
│   (Aiogram 3)   │     │   (Backend)     │     │   (Data Layer)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   MegaLLM API   │     │  Analytics Svc  │
│  (AI Consultant)│     │  (Impressions)  │
└─────────────────┘     └─────────────────┘
```

## 📁 Структура проекта

```
├── app/                      # FastAPI Backend
│   ├── api/                  # API endpoints
│   │   ├── tournaments.py    # CRUD турниров
│   │   ├── cabinet.py        # Личный кабинет WebApp
│   │   └── analytics.py      # Аналитика
│   ├── services/             # Бизнес-логика
│   │   ├── tournament_service.py
│   │   ├── analytics_service.py
│   │   ├── premium_service.py
│   │   └── webapp_auth_service.py
│   ├── templates/            # HTML шаблоны
│   └── static/               # CSS, JS, изображения
│
├── telegram_bot/             # Telegram Bot
│   ├── bot.py                # Главный файл бота
│   ├── llm_consultant.py     # AI консультант
│   ├── cabinet_handlers.py   # Обработчики кабинета
│   ├── backend_client.py     # Клиент API
│   └── config.py             # Конфигурация
│
├── tests/                    # Тесты
│   ├── test_webapp_auth_properties.py
│   ├── test_cabinet_api_properties.py
│   └── test_click_tracking_properties.py
│
├── data/                     # JSON хранилище данных
├── .kiro/                    # Kiro IDE specs
└── requirements.txt          # Python зависимости
```

## 🚀 Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/YOUR_USERNAME/cupguide.git
cd cupguide
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# или
source .venv/bin/activate  # Linux/Mac
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

```bash
# Скопируйте пример конфигурации
copy .env.example .env
copy .env.example telegram_bot/.env

# Отредактируйте .env файлы, добавив свои токены
```

### 5. Запуск

```bash
# Терминал 1: Запуск API сервера
python run.py

# Терминал 2: Запуск Telegram бота
python telegram_bot/bot.py
```

## ⚙️ Конфигурация

### Обязательные переменные

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `MEGALLM_API_KEY` | API ключ MegaLLM для AI функций |

### Опциональные переменные

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `BACKEND_URL` | URL API сервера | `http://127.0.0.1:8000` |
| `WEBAPP_CABINET_URL` | URL WebApp кабинета | - |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

## 🤖 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начало работы, согласие на обработку данных |
| `/help` | Справка по боту |
| `/tournaments` | Список ближайших турниров |
| `/search` | Поиск турниров |
| `/cabinet` | Личный кабинет организатора |

## 📊 API Endpoints

### Публичные

- `GET /api/tournaments` — список турниров
- `GET /api/tournaments/{id}` — детали турнира
- `GET /api/tournaments/search` — поиск турниров
- `GET /t/{id}` — короткая ссылка с аналитикой

### Личный кабинет (требует JWT)

- `POST /api/webapp/auth` — авторизация через Telegram WebApp
- `GET /api/cabinet/overview` — обзор кабинета
- `GET /api/cabinet/tournaments` — турниры организатора
- `GET /api/cabinet/tournaments/{id}/analytics` — аналитика турнира
- `GET /api/cabinet/tournaments/{id}/services` — статус услуг
- `POST /api/cabinet/tournaments/{id}/buy` — покупка услуги

## 🧪 Тестирование

```bash
# Запуск всех тестов
python -m pytest tests/ -v

# Запуск property-based тестов
python -m pytest tests/test_webapp_auth_properties.py -v
python -m pytest tests/test_cabinet_api_properties.py -v
```

## 🔐 Безопасность

- ✅ HMAC-SHA256 валидация Telegram initData
- ✅ JWT токены с expiration для сессий
- ✅ Проверка владения турниром перед операциями
- ✅ XSS защита в WebApp (escapeHtml)
- ✅ Секреты хранятся в переменных окружения

## 📈 Аналитика

Система собирает:
- **Показы** — когда турнир показывается в результатах поиска
- **Клики** — переходы по ссылкам на турнир
- **Источники** — бот, канал, рассылка, прямой переход
- **UTM метки** — для отслеживания рекламных кампаний

## 🛠️ Технологии

- **Backend**: FastAPI, Pydantic, Jinja2
- **Bot**: Aiogram 3.x, FSM
- **AI**: MegaLLM API (GPT-совместимый)
- **Auth**: PyJWT, HMAC-SHA256
- **Testing**: Pytest, Hypothesis (property-based)
- **Storage**: JSON файлы (легко мигрировать на БД)

## 📝 Лицензия

MIT License — свободное использование с указанием авторства.

## 🤝 Участие в разработке

Мы приветствуем вклад в развитие проекта! См. [CONTRIBUTING.md](CONTRIBUTING.md) для деталей.

## 👥 Контакты

- Issues: [GitHub Issues](https://github.com/YOUR_USERNAME/cupguide/issues)

---

<p align="center">
  Made with ❤️ for football community
</p>
