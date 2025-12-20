# 🚀 Roadmap: LLM-автоответчик для Авито

## Статус: 🟢 Готово

---

## Этап 1: Структура проекта ✅
- [x] Создать папку `avito_bot/`
- [x] Создать ROADMAP.md
- [x] Создать config.py
- [x] Создать __init__.py

## Этап 2: Модели данных ✅
- [x] `AvitoChat` — диалоги
- [x] `AvitoMessage` — сообщения (in/out)
- [x] `NLPEvent` — intent/slots/score
- [x] `AvitoLead` — лиды для CRM

## Этап 3: База знаний (KB) ✅
- [x] Загрузить прайс из ТЗ в JSON
- [x] Кейсы и FAQ
- [x] KBService для работы с данными

## Этап 4: LLM Adapter (MegaLLM) ✅
- [x] `llm_adapter.py` — клиент MegaLLM
- [x] System prompt по ТЗ
- [x] JSON-схема ответа (intent/slots/score/reply/next_action)
- [x] Парсинг и валидация ответа
- [x] Fallback при ошибках

## Этап 5: Dialog Orchestrator ✅
- [x] Сценарный контроллер
- [x] Детерминированный скоринг A/B/C
- [x] Обработка интентов
- [x] Генерация ответов по KB
- [x] Шаблоны ответов из ТЗ

## Этап 6: Интеграция с Авито ✅
- [x] Webhook endpoint `/webhook/avito`
- [x] Дедупликация сообщений
- [x] Антипетля (не отвечать на свои)
- [x] Background tasks для обработки
- [x] Polling режим (резерв)
- [x] Avito API Client

## Этап 7: CRM Connector ✅
- [x] Интеграция с существующей CRM
- [x] Создание лида с payload
- [x] Идемпотентность (проверка дублей)
- [x] Fallback при ошибке CRM

## Этап 8: API Endpoints ✅
- [x] `POST /webhook/avito` — приём сообщений
- [x] `GET /webhook/avito/health` — статус
- [x] `POST /webhook/avito/polling/start` — запуск polling
- [x] `POST /webhook/avito/polling/stop` — остановка polling
- [x] `POST /admin/avito/test` — тестовый прогон
- [x] `GET /admin/avito/services` — список услуг
- [x] `POST /admin/avito/scoring/test` — тест скоринга
- [x] `POST /admin/avito/llm/test` — тест LLM
- [x] `POST /admin/avito/test/batch` — batch тестирование
- [x] `GET /admin/avito/test/dialogs` — список тестовых диалогов
- [x] `POST /admin/avito/masking/test` — тест маскирования

## Этап 9: Тестирование ✅
- [x] Тест-набор диалогов (50+ сценариев)
- [x] Pytest тесты для скоринга
- [x] Pytest тесты для маскирования
- [x] Batch тестирование через API

## Этап 10: Безопасность ✅
- [x] Проверка подписи webhook
- [x] Валидация входных данных (Pydantic)
- [x] Обработка ошибок
- [x] Логирование
- [x] Маскирование контактов в логах

---

## Архитектура

```
avito_bot/
├── __init__.py
├── config.py              # Конфигурация
├── models/
│   ├── __init__.py
│   ├── chat.py            # AvitoChat
│   ├── message.py         # AvitoMessage
│   ├── nlp_event.py       # NLPEvent
│   └── lead.py            # AvitoLead
├── services/
│   ├── __init__.py
│   ├── llm_adapter.py     # MegaLLM клиент
│   ├── dialog_orchestrator.py  # Сценарный контроллер
│   ├── scoring.py         # Детерминированный скоринг
│   ├── kb_service.py      # База знаний
│   └── crm_connector.py   # Интеграция с CRM
├── api/
│   ├── __init__.py
│   ├── webhook.py         # Webhook endpoint
│   └── admin.py           # Админ endpoints
├── data/
│   └── kb.json            # База знаний (прайс/кейсы/FAQ)
└── prompts/
    ├── system.txt         # System prompt
    └── parser.txt         # Parser prompt
```

## Зависимости от существующего кода

- `app/services/lead_service.py` — создание лидов в CRM
- `app/models/lead.py` — модель лида
- `freelance_bot/services/llm_scoring.py` — паттерн LLM скоринга
- `freelance_bot/services/deterministic_scoring.py` — детерминированный скоринг

---

*Последнее обновление: 2025-12-19*
