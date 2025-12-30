# 📊 Telegram Monitor & CRM Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Aiogram-3.x-blue.svg" alt="Aiogram">
  <img src="https://img.shields.io/badge/Telethon-1.x-purple.svg" alt="Telethon">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

Комплексная платформа для мониторинга мессенджеров, CRM, AI-ботов и автоматизации маркетинга.

---

## 🎯 Модули системы

### 1. 📱 WhatsApp Мониторинг (Green API)
- Синхронизация контактов из WhatsApp групп
- Обогащение контактов данными профиля (имя, аватар, статус)
- AI-анализ переписки через MegaLLM
- Извлечение структурированных данных (интересы, бюджет, потребности)
- Checkpoint система для продолжения обновления с места остановки
- История сообщений с контактами

### 2. 👥 CRM Контактов
- База контактов с детальной информацией
- AI-анализ контактов через MegaLLM
- Поиск и фильтрация контактов
- Карточки контактов с историей взаимодействий
- Экспорт данных

### 3. 🏆 Турниры (CupGuide)
- Каталог футбольных турниров
- Умный поиск на естественном языке через AI
- Личный кабинет организатора (Telegram Mini App)
- OCR извлечение данных из изображений турниров
- Аналитика показов и кликов
- Создание и редактирование турниров

### 4. 🤖 CupGuide Bot (`telegram_bot/`)
- Telegram бот для поиска турниров
- LLM-консультант для умного поиска
- Личный кабинет организатора через WebApp
- Premium функции

### 5. 🎯 LeadRazor Bot (`freelance_bot/`)
- Telegram бот для квалификации лидов
- FSM воронка с 3 вопросами скрининга
- AI-скоринг ответов через MegaLLM (категории A/B/C)
- Уведомления владельцу о новых заявках
- Веб-интерфейс для просмотра лидов `/leads`

### 6. 🛒 Avito Auto-responder (`avito_bot/`)
- LLM-автоответчик для Авито
- AI-скоринг сообщений (A/B/C грейды)
- База знаний (прайс, кейсы, FAQ)
- Сценарный контроллер диалогов
- Маскирование контактов в сообщениях
- Webhook API для приёма сообщений
- Интеграция с CRM (автосоздание лидов)

### 7. 📢 Автопостинг в Telegram
- Постинг объявлений в группы от личного аккаунта (Telethon)
- Веб-интерфейс управления `/autopost`
- Загрузка групп из папок Telegram
- Редактирование текста с live-превью и счётчиком символов
- Превью ссылок в сообщениях (link_preview)
- Задержка между постами (40 сек), лимит 35/час
- Тихие часы (2:00-6:00)
- Fallback на текст если фото запрещено

---

## 🏗️ Архитектура системы

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WEB INTERFACE                                      │
│                  (FastAPI + Jinja2 + TailwindCSS)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ /contacts │ /tournaments │ /leads │ /autopost │ /admin │ /messages │ /channels│
└─────┬─────┴──────┬───────┴───┬────┴─────┬─────┴───┬────┴─────┬─────┴────┬────┘
      │            │           │          │         │          │          │
      ▼            ▼           ▼          ▼         ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI BACKEND                                     │
│                       app/api/ + app/services/                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  contacts.py │ tournaments.py │ leads.py │ autopost.py │ green_api.py │ ... │
└──────┬───────┴───────┬────────┴────┬─────┴──────┬──────┴───────┬──────┴─────┘
       │               │             │            │              │
       ▼               ▼             ▼            ▼              ▼
┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐
│ Green API │   │  MegaLLM  │   │ Telegram  │   │   JSON    │   │  SQLite   │
│ (WhatsApp)│   │    API    │   │    API    │   │  Storage  │   │    DB     │
└───────────┘   └───────────┘   └───────────┘   └───────────┘   └───────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          TELEGRAM BOTS                                       │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│   CupGuide Bot       │   LeadRazor Bot      │   Autopost Userbot            │
│   (Aiogram 3.x)      │   (Aiogram + FSM)    │   (Telethon)                  │
│   telegram_bot/      │   freelance_bot/     │   freelance_bot/autopost/     │
├──────────────────────┴──────────────────────┴───────────────────────────────┤
│                          AVITO BOT                                           │
│                    (LLM Auto-responder)                                      │
│                        avito_bot/                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Webhook API  │  Dialog Orchestrator  │  KB Service  │  CRM Connector       │
└───────────────┴───────────────────────┴──────────────┴──────────────────────┘
```

---

## 📁 Структура проекта

```
├── app/                          # FastAPI Backend
│   ├── api/                      # API endpoints
│   │   ├── contacts.py           # CRUD контактов + enrichment
│   │   ├── tournaments.py        # CRUD турниров
│   │   ├── autopost.py           # Автопостинг API
│   │   ├── leads.py              # Лиды от ботов
│   │   ├── cabinet.py            # Личный кабинет WebApp
│   │   ├── green_api.py          # WhatsApp интеграция
│   │   ├── whatsapp.py           # WhatsApp сообщения
│   │   └── ...
│   ├── services/                 # Бизнес-логика
│   │   ├── contact_service.py
│   │   ├── contact_enrichment_service.py
│   │   ├── green_api_service.py
│   │   ├── llm_service.py
│   │   ├── ocr_service.py
│   │   ├── tournament_service.py
│   │   ├── lead_service.py
│   │   ├── autopost_service.py
│   │   └── ...
│   ├── models/                   # Pydantic модели
│   ├── templates/                # Jinja2 HTML шаблоны
│   ├── static/                   # CSS, JS, медиа
│   └── main.py                   # FastAPI app
│
├── telegram_bot/                 # CupGuide Bot
│   ├── bot.py                    # Главный файл бота
│   ├── llm_consultant.py         # AI консультант поиска
│   ├── cabinet_handlers.py       # Личный кабинет организатора
│   ├── cabinet_service.py        # Сервис кабинета
│   ├── backend_client.py         # Клиент к API
│   ├── premium_handlers.py       # Premium функции
│   ├── config.py                 # Конфигурация
│   └── ...
│
├── freelance_bot/                # LeadRazor Bot
│   ├── bot.py                    # Главный файл бота
│   ├── states.py                 # FSM состояния воронки
│   ├── config.py                 # Конфигурация
│   ├── handlers/                 # Обработчики сообщений
│   │   ├── entry.py              # /start, триггер "БОТ"
│   │   ├── screening.py          # Вопросы Q1/Q2/Q3
│   │   ├── application.py        # Заявка
│   │   └── routing.py            # Роутинг по скорингу
│   ├── services/                 # Сервисы
│   │   ├── llm_scoring.py        # AI скоринг через MegaLLM
│   │   ├── deterministic_scoring.py  # Fallback скоринг
│   │   └── notification_service.py   # Уведомления владельцу
│   ├── texts/                    # Тексты сообщений
│   ├── keyboards/                # Inline клавиатуры
│   └── autopost/                 # Модуль автопостинга
│       ├── poster.py             # Логика постинга (Telethon)
│       ├── groups.py             # Список групп
│       ├── message.py            # Текст объявления
│       └── config.py             # Настройки постинга
│
├── avito_bot/                    # Avito LLM Auto-responder
│   ├── config.py                 # Конфигурация
│   ├── models/                   # Модели данных
│   │   ├── chat.py               # AvitoChat
│   │   ├── message.py            # AvitoMessage
│   │   ├── nlp_event.py          # NLPEvent (intent/slots/score)
│   │   └── lead.py               # AvitoLead
│   ├── services/                 # Сервисы
│   │   ├── llm_adapter.py        # MegaLLM клиент
│   │   ├── dialog_orchestrator.py # Сценарный контроллер
│   │   ├── scoring.py            # Детерминированный скоринг
│   │   ├── kb_service.py         # База знаний
│   │   ├── avito_client.py       # Avito API клиент
│   │   ├── polling.py            # Polling режим
│   │   └── crm_connector.py      # Интеграция с CRM
│   ├── api/                      # API endpoints
│   │   ├── webhook.py            # Webhook от Авито
│   │   └── admin.py              # Админ endpoints
│   ├── utils/
│   │   └── masking.py            # Маскирование контактов
│   ├── data/
│   │   └── kb.json               # База знаний
│   └── prompts/
│       └── system.txt            # System prompt для LLM
│
├── data/                         # JSON хранилище
│   ├── contacts.json             # Контакты
│   ├── tournaments.json          # Турниры
│   ├── leads.json                # Лиды
│   ├── channels.json             # Telegram каналы
│   ├── messages.json             # Сообщения
│   ├── whatsapp_messages.json    # Сообщения WhatsApp
│   ├── enrichment_checkpoint.json # Checkpoint обогащения
│   └── ...
│
├── tests/                        # Тесты
│   ├── test_analytics_*.py
│   ├── test_cabinet_*.py
│   └── ...
│
├── .env                          # Переменные окружения
├── .env.example                  # Пример .env
├── requirements.txt              # Python зависимости
└── run.py                        # Запуск сервера
```

---

## 🚀 Быстрый старт

### 1. Клонирование и установка

```bash
git clone https://github.com/soccershortsunleashed-ops/cupguide-bot.git
cd cupguide-bot
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Настройка переменных окружения

```bash
copy .env.example .env
```

Основные переменные:

```env
# === Backend ===
BACKEND_URL=http://127.0.0.1:8000

# === MegaLLM (AI) ===
MEGALLM_API_KEY=sk-mega-xxx
MEGALLM_BASE_URL=https://ai.megallm.io/v1

# === JWT (WebApp авторизация) ===
JWT_SECRET_KEY=your_secret_key

# === Green API (WhatsApp) ===
GREEN_API_INSTANCE_ID=your_instance
GREEN_API_TOKEN=your_token
```

Для CupGuide бота (`telegram_bot/.env`):
```env
TELEGRAM_BOT_TOKEN=xxx:yyy
BACKEND_URL=http://127.0.0.1:8000
```

Для LeadRazor бота (`freelance_bot/.env`):
```env
FREELANCE_BOT_TOKEN=xxx:yyy
OWNER_TELEGRAM_ID=123456789
MEGALLM_API_KEY=sk-mega-xxx

# Autopost (Telethon)
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=abcdef
```

Для Avito бота (в основном `.env`):
```env
AVITO_CLIENT_ID=your_client_id
AVITO_CLIENT_SECRET=your_client_secret
AVITO_USER_ID=your_user_id
```

### 3. Запуск

```bash
# Веб-сервер (основной)
python run.py

# CupGuide бот (отдельный терминал)
cd telegram_bot && python bot.py

# LeadRazor бот (отдельный терминал)
cd freelance_bot && python bot.py
```

---

## 🌐 Веб-интерфейс

| URL | Описание |
|-----|----------|
| `/messages` | Мониторинг сообщений Telegram |
| `/channels` | Управление каналами |
| `/contacts` | CRM контактов с AI-анализом |
| `/tournaments` | Каталог турниров |
| `/tournament/{id}` | Карточка турнира |
| `/leads` | Лиды от ботов |
| `/autopost` | Автопостинг в Telegram группы |
| `/admin` | Админ-панель |

---

## 📊 API Endpoints

### Контакты
```
GET    /api/contacts              # Список контактов
GET    /api/contacts/{id}         # Детали контакта
POST   /api/contacts/enrich-all   # Обогатить все контакты
DELETE /api/contacts/enrich-all/checkpoint  # Очистить checkpoint
```

### Турниры
```
GET    /api/tournaments           # Список турниров
GET    /api/tournaments/{id}      # Детали турнира
POST   /api/tournaments           # Создать турнир
PUT    /api/tournaments/{id}      # Обновить турнир
DELETE /api/tournaments/{id}      # Удалить турнир
POST   /api/tournaments/{id}/extract  # OCR извлечение данных
```

### Автопостинг
```
GET    /api/autopost/status       # Статус подключения Telethon
POST   /api/autopost/connect      # Подключиться (телефон + код)
GET    /api/autopost/groups       # Список групп для постинга
POST   /api/autopost/post         # Запустить постинг
POST   /api/autopost/stop         # Остановить постинг
```

### Лиды
```
GET    /api/leads                 # Список лидов
GET    /api/leads/{id}            # Детали лида
```

### Avito Bot
```
POST   /webhook/avito/            # Webhook от Авито
GET    /webhook/avito/health      # Проверка статуса
POST   /admin/avito/test          # Тест сообщения
GET    /admin/avito/services      # Список услуг из KB
POST   /admin/avito/scoring/test  # Тест скоринга
```

---

## 🤖 Боты

### CupGuide Bot
Telegram бот для поиска детских футбольных турниров.
- Умный поиск через LLM
- Личный кабинет организатора (WebApp)
- Premium функции

### LeadRazor Bot
Бот для квалификации клиентов на услуги разработки.

**Воронка:**
1. `/start` или слово "БОТ" в группе
2. Q1 — Что нужно автоматизировать?
3. Q2 — Какой бюджет?
4. Q3 — Когда нужно?
5. AI-скоринг → роутинг (A/B/C)

### Avito Auto-responder
LLM-автоответчик для Авито.

**Скоринг:**
| Грейд | Описание | Действие |
|-------|----------|----------|
| A | Горячий: созвон, договор, срочно | Создать лид |
| B | Тёплый: интерес есть | 1-2 уточнения → лид |
| C | Холодный: просто узнать | Не создавать лид |

---

## 🔐 Безопасность

- ✅ Секреты в переменных окружения
- ✅ JWT авторизация для WebApp
- ✅ Валидация Telegram initData
- ✅ Маскирование контактов в Avito
- ✅ Санитизация пользовательского ввода

---

## 🛠️ Технологии

| Компонент | Технология |
|-----------|------------|
| Backend | FastAPI, Pydantic, Jinja2 |
| Frontend | TailwindCSS, Alpine.js |
| Telegram Bots | Aiogram 3.x (FSM) |
| Userbot | Telethon |
| AI | MegaLLM API (OpenAI-compatible) |
| WhatsApp | Green API |
| Storage | JSON + SQLite |

---

## 📝 Лицензия

MIT License
8девятьсот2один90четыри/ноль2/пятьдесят2 - Teleграмм
---

<p align="center">
  Made with ❤️
</p>
