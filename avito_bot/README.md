# 🤖 Avito LLM Auto-responder

LLM-автоответчик для Авито с AI-скорингом и интеграцией в CRM.

## Возможности

- **LLM-анализ сообщений** — определение intent, slots, скоринг A/B/C
- **Детерминированный скоринг** — страховка LLM по правилам
- **База знаний** — прайс, кейсы, FAQ из JSON
- **Сценарный контроллер** — обработка диалогов по ТЗ
- **CRM интеграция** — автосоздание лидов
- **Webhook API** — приём сообщений от Авито

## Структура

```
avito_bot/
├── __init__.py
├── config.py              # Конфигурация
├── ROADMAP.md             # План разработки
├── README.md              # Документация
├── models/
│   ├── chat.py            # AvitoChat
│   ├── message.py         # AvitoMessage
│   ├── nlp_event.py       # NLPEvent (intent/slots/score)
│   └── lead.py            # AvitoLead
├── services/
│   ├── llm_adapter.py     # MegaLLM клиент
│   ├── dialog_orchestrator.py  # Сценарный контроллер
│   ├── scoring.py         # Детерминированный скоринг
│   ├── kb_service.py      # База знаний
│   └── crm_connector.py   # Интеграция с CRM
├── api/
│   ├── webhook.py         # Webhook endpoint
│   └── admin.py           # Админ endpoints
├── data/
│   └── kb.json            # База знаний (прайс/кейсы/FAQ)
└── prompts/
    └── system.txt         # System prompt для LLM
```

## Конфигурация

Добавьте в `.env`:

```env
# Avito API
AVITO_CLIENT_ID=your_client_id
AVITO_CLIENT_SECRET=your_client_secret
AVITO_USER_ID=your_user_id
AVITO_WEBHOOK_SECRET=your_webhook_secret

# MegaLLM
MEGALLM_API_KEY=your_api_key
MEGALLM_BASE_URL=https://api.mega-llm.ru/v1
MEGALLM_MODEL=gpt-4o-mini

# Timeouts
LLM_TIMEOUT=30
```

## API Endpoints

### Webhook
- `POST /webhook/avito/` — приём сообщений от Авито
- `GET /webhook/avito/health` — проверка статуса
- `POST /webhook/avito/polling/start` — запуск polling режима
- `POST /webhook/avito/polling/stop` — остановка polling

### Admin
- `POST /admin/avito/test` — тестовый прогон сообщения
- `GET /admin/avito/services` — список услуг из KB
- `GET /admin/avito/kb/summary` — краткое описание KB
- `POST /admin/avito/scoring/test` — тест детерминированного скоринга
- `POST /admin/avito/llm/test` — тест LLM напрямую
- `POST /admin/avito/test/batch` — batch тестирование на наборе диалогов
- `GET /admin/avito/test/dialogs` — список тестовых диалогов
- `POST /admin/avito/masking/test` — тест маскирования контактов

## Тестирование

```bash
# Тест сообщения
curl -X POST http://localhost:8000/admin/avito/test \
  -H "Content-Type: application/json" \
  -d '{"message": "Сколько стоит разработка бота?"}'

# Тест скоринга
curl -X POST "http://localhost:8000/admin/avito/scoring/test?message=Нужен%20бот%20срочно"

# Список услуг
curl http://localhost:8000/admin/avito/services
```

## Скоринг A/B/C

| Грейд | Описание | Действие |
|-------|----------|----------|
| A | Горячий: созвон, договор, срочно | Создать лид сразу |
| B | Тёплый: интерес есть, мало вводных | 1-2 уточнения → лид |
| C | Холодный: просто узнать | Не создавать лид |

## Интенты

- `general_interest` — общий интерес
- `pricing` — вопрос о цене
- `service_question` — вопрос по услуге
- `comparison` — сравнение (бот за 2к vs продающий)
- `objection` — возражение (дорого, справитесь?)
- `request_examples` — запрос примеров/кейсов
- `handoff_request` — запрос созвона/оформления
- `offtopic` — не по теме
- `abuse` — токсичность

## Зависимости

- `openai` — клиент для MegaLLM (OpenAI-совместимый API)
- `httpx` — HTTP клиент для CRM
- `pydantic` — валидация данных
- `fastapi` — API framework
