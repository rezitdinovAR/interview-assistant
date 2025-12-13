# Chat Service Architecture

## Структура проекта

```
chat-service/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI приложение, точка входа
│   │
│   ├── core/                   # Ядро приложения
│   │   ├── __init__.py
│   │   ├── config.py          # Конфигурация (Settings)
│   │   └── dependencies.py    # FastAPI зависимости
│   │
│   ├── routers/               # API роутеры
│   │   ├── __init__.py
│   │   └── chat.py            # Роутеры для чата
│   │
│   ├── schemas/               # Pydantic схемы
│   │   ├── __init__.py
│   │   └── chat.py            # Схемы для чата
│   │
│   └── services/              # Бизнес-логика
│       ├── __init__.py
│       ├── db_client.py       # Клиент для db-service
│       └── llm_service.py     # LLM с RAG
│
├── prompts/
│   └── system_prompt.txt      # System prompt для LLM
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── ARCHITECTURE.md            # Этот файл
├── QUICKSTART.md
└── test_client.py
```

## Компоненты

### 1. Core Module (`api/core/`)

#### config.py
- Использует `pydantic-settings` для управления конфигурацией
- Загружает настройки из `.env` файла
- Предоставляет глобальный объект `settings`

Основные настройки:
- `redis_uri` - подключение к Redis
- `db_service_url` - URL db-service для RAG
- `openai_api_key` - ключ OpenAI API
- `top_k_documents` - количество документов для RAG
- `max_tokens` - лимит токенов для контекста

#### dependencies.py
- Управление зависимостями FastAPI
- `get_llm()` - dependency для получения LLM сервиса
- `set_llm()` - инициализация LLM при старте
- `cleanup_llm()` - очистка ресурсов при остановке

### 2. Routers Module (`api/routers/`)

#### chat.py
Содержит API endpoints:

- `POST /api/v1/chat` - отправка сообщения в чат
- `POST /api/v1/reset` - сброс контекста пользователя
- `GET /api/v1/health` - проверка здоровья сервиса

Все роутеры используют prefix `/api/v1` для версионирования API.

### 3. Schemas Module (`api/schemas/`)

#### chat.py
Pydantic модели для валидации данных:

- `ChatRequest` - запрос на отправку сообщения
- `ChatResponse` - ответ от чата
- `ResetRequest` - запрос на сброс контекста
- `StatusResponse` - статус операции

Схемы включают примеры (`json_schema_extra`) для автоматической документации.

### 4. Services Module (`api/services/`)

#### db_client.py
Клиент для взаимодействия с db-service:

- Использует `httpx.AsyncClient` для асинхронных HTTP запросов
- `retrieve_documents()` - получение релевантных документов
- Автоматическая обработка ошибок

#### llm_service.py
Основной сервис для работы с LLM и RAG:

**Компоненты:**
- `LangGraph` - управление диалогом и состоянием
- `RedisSaver` - сохранение истории в Redis
- `ChatOpenAI` - интеграция с OpenAI API
- `DBServiceClient` - получение контекста из RAG

**Основные методы:**
- `ask(user_id, message)` - получить ответ от LLM с контекстом RAG
- `reset_context(user_id)` - очистить историю пользователя
- `_augment_with_context()` - дополнение вопроса контекстом

**Процесс обработки запроса:**
```
1. Пользователь отправляет вопрос
2. Поиск релевантных документов в db-service (RAG)
3. Формирование расширенного промпта с контекстом
4. Получение истории диалога из Redis
5. Trim истории до лимита токенов
6. Отправка в LLM
7. Сохранение ответа в Redis
8. Возврат ответа пользователю
```

### 5. Main Application (`api/main.py`)

FastAPI приложение с:
- Lifespan events для инициализации/очистки
- CORS middleware
- Автоматическая документация (Swagger/ReDoc)
- Регистрация роутеров

## Поток данных

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /api/v1/chat
       │ {user_id, message}
       ▼
┌─────────────────────────────────────┐
│      FastAPI (main.py)              │
│  ┌───────────────────────────────┐  │
│  │  Router (chat.py)             │  │
│  │  - валидация через schemas    │  │
│  │  - использует dependency      │  │
│  └──────────┬────────────────────┘  │
└─────────────┼───────────────────────┘
              │ Depends(get_llm)
              ▼
┌─────────────────────────────────────┐
│   LLMGraphMemoryWithRAG             │
│                                     │
│  1. _augment_with_context()        │
│     ├─► DBServiceClient             │
│     │   └─► db-service /retrieve    │
│     └─► Формирует промпт            │
│                                     │
│  2. _invoke_graph()                 │
│     ├─► Redis (история)             │
│     ├─► Trim messages               │
│     └─► OpenAI API                  │
│                                     │
│  3. Сохранение в Redis              │
└─────────────────────────────────────┘
              │
              │ response
              ▼
┌─────────────────┐
│  ChatResponse   │
│  {user_id, msg} │
└─────────────────┘
```

## Управление конфигурацией

### Переменные окружения

Все настройки управляются через `.env` файл:

```env
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini-2024-07-18

# Redis
REDIS_URI=redis://redis:6379

# DB Service
DB_SERVICE_URL=http://api:8080

# RAG
TOP_K_DOCUMENTS=5
MAX_TOKENS=10000
```

### Pydantic Settings

`api/core/config.py` использует `pydantic-settings` для:
- Автоматической загрузки из `.env`
- Валидации типов
- Значений по умолчанию
- Type hints для IDE

## Управление зависимостями

### FastAPI Dependencies

Используется Dependency Injection для:
- Получения LLM сервиса в роутерах
- Управления жизненным циклом
- Изоляции бизнес-логики

```python
@router.post("/chat")
async def chat(
    request: ChatRequest,
    llm: LLMGraphMemoryWithRAG = Depends(get_llm)
):
    response = await llm.ask(request.user_id, request.message)
    return ChatResponse(user_id=request.user_id, message=response)
```

## Обработка ошибок

### Уровни обработки:

1. **Pydantic валидация** (schemas)
   - Автоматическая валидация входных данных
   - HTTP 422 при невалидных данных

2. **Бизнес-логика** (services)
   - Try/catch блоки
   - Логирование ошибок
   - Graceful degradation (RAG опционален)

3. **HTTP обработка** (routers)
   - HTTPException с понятными сообщениями
   - Правильные HTTP статус-коды

## Масштабирование

### Горизонтальное масштабирование

Сервис stateless (состояние в Redis), поэтому можно:
- Запускать несколько экземпляров
- Использовать load balancer
- Автоматическое масштабирование в K8s

### Вертикальное масштабирование

Настройки для оптимизации:
- `MAX_TOKENS` - контроль размера контекста
- `TOP_K_DOCUMENTS` - количество документов RAG
- Workers в uvicorn

## Мониторинг и отладка

### Health checks

- `/health` - основное приложение
- `/api/v1/health` - API роутер
- Redis health check в docker-compose

### Логирование

- Uvicorn access logs
- Application logs (можно добавить structlog)
- Error tracking (можно добавить Sentry)

### Метрики

Можно добавить:
- Prometheus metrics
- Request duration
- Error rates
- LLM token usage
