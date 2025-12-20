# 📊 Telegram Monitor & CRM

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Aiogram-3.x-blue.svg" alt="Aiogram">
  <img src="https://img.shields.io/badge/Telethon-1.x-purple.svg" alt="Telethon">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

Комплексная система мониторинга Telegram и WhatsApp с CRM функциями, AI-анализом контактов, турнирами и автопостингом.

## 🎯 Основные модули

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

### 4. 🤖 CupGuide Bot (telegram_bot/)
- Telegram бот для поиска турниров
- LLM-консультант для умного поиска
- Личный кабинет организатора через WebApp
- Premium функции

### 5. 🎯 LeadRazor Bot (freelance_bot/)
- Telegram бот для квалификации лидов
- FSM воронка с 3 вопросами скрининга
- AI-скоринг ответов через MegaLLM (категории A/B/C)
- Уведомления владельцу о новых заявках
- Веб-интерфейс для просмотра лидов `/leads`

### 6. 📢 Автопостинг в Telegram
- Постинг объявлений в группы от личного аккаунта (Telethon)
- Веб-интерфейс управления `/autopost`
- Загрузка групп из папок Telegram
- Редактирование текста с live-превью и счётчиком символов
- Превью ссылок в сообщениях (link_preview)
- Задержка между постами (40 сек), лимит 35/час
- Тихие часы (2:00-6:00)
- Fallback на текст если фото запрещено
- Повторная попытка при ошибках (только успешные посты пропускаются)

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Interface                             │
│              (FastAPI + Jinja2 + TailwindCSS)                   │
├─────────────────────────────────────────────────────────────────┤
│  /contacts  │  /tournaments  │  /leads  │  /autopost  │  /admin │
└──────┬──────┴───────┬────────┴────┬─────┴──────┬──────┴────┬────┘
       │              │             │            │           │
       ▼              ▼             ▼            ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                           │
│                    app/api/ + app/services/                      │
└──────┬──────────────┬─────────────┬────────────┬────────────────┘
       │              │             │            │
       ▼              ▼             ▼            ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ Green API│   │ MegaLLM  │   │ Telegram │   │  JSON    │
│(WhatsApp)│   │   API    │   │   API    │   │ Storage  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Telegram Bots                               │
├────────────────────────────┬────────────────────────────────────┤
│   CupGuide Bot (Aiogram)   │   LeadRazor Bot (Aiogram + FSM)    │
│   telegram_bot/bot.py      │   freelance_bot/bot.py             │
├────────────────────────────┴────────────────────────────────────┤
│                  Autopost (Telethon Userbot)                     │
│                freelance_bot/autopost/poster.py                  │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Структура проекта

```
├── app/                          # FastAPI Backend
│   ├── api/                      # API endpoints
│   │   ├── contacts.py           # CRUD контактов + enrichment
│   │   ├── tournaments.py        # CRUD турниров
│   │   ├── autopost.py           # Автопостинг API
│   │   ├── leads.py              # Лиды от бота
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
│   │   └── ...
│   ├── models/                   # Pydantic модели
│   ├── templates/                # Jinja2 HTML шаблоны
│   ├── static/                   # CSS, JS, медиа
│   └── main.py                   # FastAPI app
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
│   │   └── messages.py
│   ├── keyboards/                # Inline клавиатуры
│   └── autopost/                 # Модуль автопостинга
│       ├── poster.py             # Логика постинга (Telethon)
│       ├── groups.py             # Список групп
│       ├── message.py            # Текст объявления
│       └── config.py             # Настройки постинга
│
├── telegram_bot/                 # CupGuide Bot
│   ├── bot.py                    # Главный файл бота
│   ├── llm_consultant.py         # AI консультант
│   ├── cabinet_handlers.py       # Личный кабинет
│   ├── backend_client.py         # Клиент к API
│   └── ...
│
├── data/                         # JSON хранилище
│   ├── contacts.json             # Контакты
│   ├── tournaments.json          # Турниры
│   ├── leads.json                # Лиды
│   ├── whatsapp_messages.json    # Сообщения WhatsApp
│   ├── enrichment_checkpoint.json # Checkpoint обогащения
│   └── ...
│
├── .env                          # Переменные окружения
├── .env.example                  # Пример .env
├── requirements.txt              # Python зависимости
└── run.py                        # Запуск сервера
```


## 🚀 Быстрый старт

### 1. Клонирование и установка

```bash
git clone <repo>
cd telegram-monitor
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
# === Telegram Bot (CupGuide) ===
TELEGRAM_BOT_TOKEN=xxx:yyy

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

Для LeadRazor бота (`freelance_bot/.env`):

```env
FREELANCE_BOT_TOKEN=xxx:yyy
OWNER_TELEGRAM_ID=123456789
MEGALLM_API_KEY=sk-mega-xxx
MEGALLM_BASE_URL=https://ai.megallm.io/v1

# Autopost (Telethon)
TELEGRAM_API_ID=12345
TELEGRAM_API_HASH=abcdef
```

### 3. Запуск

```bash
# Веб-сервер (основной)
python run.py

# CupGuide бот (отдельный терминал)
cd telegram_bot
python bot.py

# LeadRazor бот (отдельный терминал)
cd freelance_bot
python bot.py
```

## 🌐 Веб-интерфейс

| URL | Описание |
|-----|----------|
| `/` | Главная страница / Дашборд |
| `/contacts` | CRM контактов с AI-анализом |
| `/tournaments` | Каталог турниров |
| `/tournament/{id}` | Карточка турнира |
| `/tournament/create` | Создание турнира |
| `/leads` | Лиды от LeadRazor бота |
| `/autopost` | Автопостинг в Telegram группы |
| `/admin` | Админ-панель |

## 📊 API Endpoints

### Контакты
```
GET    /api/contacts              # Список контактов
GET    /api/contacts/{id}         # Детали контакта
POST   /api/contacts/enrich-all   # Обогатить все контакты
POST   /api/contacts/enrich-all?reset=true  # Начать с нуля
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
POST   /api/autopost/groups       # Сохранить список групп
POST   /api/autopost/post         # Запустить постинг
POST   /api/autopost/stop         # Остановить постинг
GET    /api/autopost/logs         # Логи постинга
GET    /api/autopost/folders      # Папки Telegram
```

### Лиды
```
GET    /api/leads                 # Список лидов
GET    /api/leads/{id}            # Детали лида
```

### WhatsApp
```
GET    /api/whatsapp/messages     # Сообщения WhatsApp
POST   /api/green-api/sync        # Синхронизация контактов
```

## 🤖 LeadRazor Bot

Бот для квалификации клиентов на услуги разработки чат-ботов.

### Воронка:
1. **Вход** — `/start` или слово "БОТ" в группе
2. **Q1** — Что нужно автоматизировать?
3. **Q2** — Какой бюджет?
4. **Q3** — Когда нужно?
5. **Скоринг** — AI оценивает ответы
6. **Роутинг**:
   - **A** (горячий) → форма заявки
   - **B** (тёплый) → форма заявки
   - **C** (холодный) → вежливый отказ

### Команды:
- `/start` — начать воронку
- `БОТ` — триггер в группах

## 📢 Автопостинг

Веб-интерфейс `/autopost` для постинга объявлений:

1. **Авторизация** — ввод телефона и кода (один раз)
2. **Выбор групп** — загрузка из папок Telegram
3. **Редактирование** — текст с Markdown, live-превью
4. **Постинг** — автоматический с задержкой 40 сек

Особенности:
- Лимит 1024 символа для caption (если с картинкой)
- Превью ссылок включено
- Пропуск только успешно отправленных постов
- Fallback на текст если фото запрещено

## 🔐 Безопасность

- ✅ Секреты в переменных окружения
- ✅ JWT авторизация для WebApp
- ✅ Валидация Telegram initData
- ✅ Санитизация пользовательского ввода
- ✅ Rate limiting

## 🛠️ Технологии

| Компонент | Технология |
|-----------|------------|
| Backend | FastAPI, Pydantic, Jinja2 |
| Frontend | TailwindCSS, Alpine.js |
| Bots | Aiogram 3.x (FSM) |
| Userbot | Telethon |
| AI | MegaLLM API |
| WhatsApp | Green API |
| Storage | JSON файлы |

## 📝 Лицензия

MIT License

---

<p align="center">
  Made with ❤️
</p>
