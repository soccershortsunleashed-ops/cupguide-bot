# Архитектура проекта - Интерактивная диаграмма

## Быстрый обзор

Проект представляет собой систему мониторинга и анализа сообщений из Telegram и WhatsApp с использованием AI для извлечения информации.

## Компоненты системы

### 1. Presentation Layer (Frontend)
- **Templates**: Jinja2 HTML шаблоны
- **JavaScript**: Модульная архитектура
  - `app.js` - основной функционал
  - `contact_enrichment.js` - обогащение контактов
  - `tournaments.js` - управление турнирами
  - `dashboard.js` - дашборд статистики

### 2. Application Layer (API)
- **FastAPI** роутеры для каждого домена:
  - `/auth` - аутентификация
  - `/channels` - управление каналами
  - `/messages` - работа с сообщениями
  - `/contacts` - управление контактами
  - `/whatsapp` - интеграция WhatsApp
  - `/api/tournaments` - управление турнирами
  - `/groups` - управление группами
  - `/green-api` - прокси для Green API
  - `/webhooks` - обработка webhooks

### 3. Business Logic Layer (Services)
- **Core Services**: работа с данными
- **AI Services**: анализ через LLM
- **Integration Services**: интеграция с внешними API
- **Background Services**: фоновые задачи

### 4. Data Layer
- **JSON файлы** для хранения данных
- **Session файлы** для Telegram
- **Media файлы** для медиа контента

## Визуализация архитектуры

```mermaid
graph TB
    subgraph "Client Browser"
        UI[Web UI<br/>HTML/CSS/JS]
    end

    subgraph "FastAPI Application"
        subgraph "Routers"
            R1[Auth Router]
            R2[Channels Router]
            R3[Messages Router]
            R4[Contacts Router]
            R5[WhatsApp Router]
            R6[Tournaments Router]
        end
        
        subgraph "Services"
            S1[Message Service]
            S2[Channel Service]
            S3[Contact Service]
            S4[WhatsApp Service]
            S5[LLM Service]
            S6[Author Analysis]
            S7[Monitoring Service]
        end
    end

    subgraph "External Services"
        E1[OpenAI API]
        E2[Telegram API]
        E3[Green API]
    end

    subgraph "Storage"
        ST1[JSON Files]
        ST2[Media Files]
        ST3[Session Files]
    end

    UI -->|HTTP| R1
    UI -->|HTTP| R2
    UI -->|HTTP| R3
    UI -->|HTTP| R4
    UI -->|HTTP| R5
    UI -->|HTTP| R6

    R1 --> S1
    R2 --> S2
    R3 --> S1
    R4 --> S3
    R5 --> S4
    R6 --> S5

    S5 --> E1
    S2 --> E2
    S4 --> E3

    S1 --> ST1
    S2 --> ST1
    S3 --> ST1
    S4 --> ST1
    S4 --> ST2
    S2 --> ST3

    S7 -.->|Background| S1
    S7 -.->|Background| S2
    S6 -.->|Background| S5
```

## Детальная структура модулей

### API Routers → Services Mapping

| API Router | Основные Services | Функции |
|------------|------------------|---------|
| `/auth` | `telegram_service` | Аутентификация в Telegram |
| `/channels` | `channel_service`, `whatsapp_service` | Управление каналами |
| `/messages` | `message_service`, `whatsapp_message_service` | Получение и обработка сообщений |
| `/contacts` | `contact_service` | CRUD операции с контактами |
| `/whatsapp` | `whatsapp_service`, `whatsapp_message_service` | WhatsApp интеграция |
| `/api/tournaments` | `tournament_service`, `llm_service` | Управление турнирами |

### Service Dependencies

```mermaid
graph LR
    AUTH[Author Analysis] --> MSG_ANAL[Message Analysis]
    MSG_ANAL --> LLM[LLM Service]
    AUTH --> CONT[Contact Service]
    AUTH --> PENDING[Pending Analysis]
    MON[Monitoring] --> MSG[Message Service]
    MON --> CHAN[Channel Service]
    MON --> TG[Telegram Service]
    WA[WhatsApp Service] --> WA_MSG[WhatsApp Message Service]
    WA_MSG --> AUTH
```

## Потоки обработки данных

### Поток 1: Мониторинг и анализ

```
Telegram/WhatsApp → Monitoring Service → Message Service → 
Author Analysis Service → Message Analysis Service → 
LLM Service (OpenAI) → Contact Service → Storage
```

### Поток 2: Отложенная обработка

```
Author Analysis → Quota Error → Pending Analysis Service → 
Storage (pending_analyses.json) → Background Task → 
Check Quota → Process Pending → Contact Service
```

### Поток 3: Загрузка страницы

```
User → Browser → FastAPI → API Routers → Services → 
JSON Storage → Response → Frontend Rendering
```

## Технические детали

### Асинхронность
- Все операции I/O асинхронные (async/await)
- Фоновые задачи через `asyncio.create_task`
- Параллельная загрузка данных через `Promise.all`

### Обработка ошибок
- Graceful degradation при ошибках API
- Сохранение отложенных анализов при ошибках квоты
- Retry логика для внешних API

### Масштабируемость
- Оптимизированная фильтрация данных
- Пагинация для больших объемов
- Ленивая загрузка контента

