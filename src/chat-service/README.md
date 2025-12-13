# Chat Service

Сервис чата с поддержкой RAG (Retrieval Augmented Generation) для подготовки к собеседованиям.

## Особенности

- REST API на FastAPI
- RAG интеграция через db-service
- Хранение истории диалогов в Redis (LangGraph)
- Поддержка множества пользователей
- OpenAI GPT-4o-mini
- Автоматическое управление контекстом
- Swagger/ReDoc документация

## Быстрый старт

### 1. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env и укажите OPENAI_API_KEY
```

### 2. Запуск через Docker Compose

```bash
docker-compose up -d
```

Сервис будет доступен на `http://localhost:8084`

### 3. Проверка работы

```bash
# Health check
curl http://localhost:8084/health

# Документация
open http://localhost:8084/docs
```

## API Endpoints

### POST /api/v1/chat
Отправка сообщения в чат

**Request:**
```json
{
  "user_id": "user123",
  "message": "Что такое замыкание в JavaScript?"
}
```

**Response:**
```json
{
  "user_id": "user123",
  "message": "Замыкание (closure) в JavaScript - это функция, которая..."
}
```

### POST /api/v1/reset
Сброс контекста диалога пользователя

**Request:**
```json
{
  "user_id": "user123"
}
```

**Response:**
```json
{
  "status": "OK",
  "message": "Context for user user123 has been reset"
}
```

### GET /api/v1/health
Проверка здоровья сервиса

**Response:**
```json
{
  "status": "healthy",
  "service": "chat-service"
}
```

## Структура проекта

```
chat-service/
├── api/
│   ├── core/              # Конфигурация и dependencies
│   ├── routers/           # API endpoints
│   ├── schemas/           # Pydantic модели
│   ├── services/          # Бизнес-логика (LLM, DB client)
│   └── main.py           # FastAPI приложение
├── prompts/              # System prompts для LLM
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

Подробнее см. [ARCHITECTURE.md](ARCHITECTURE.md)

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `OPENAI_API_KEY` | API ключ OpenAI | - (обязательно) |
| `REDIS_URI` | URI Redis | `redis://redis:6379` |
| `DB_SERVICE_URL` | URL db-service | `http://api:8080` |
| `TOP_K_DOCUMENTS` | Кол-во документов RAG | `5` |
| `MAX_TOKENS` | Макс. токенов контекста | `10000` |
| `OPENAI_MODEL` | Модель OpenAI | `gpt-4o-mini-2024-07-18` |

## Примеры использования

### Python

```python
import requests

# Отправка сообщения
response = requests.post(
    "http://localhost:8084/api/v1/chat",
    json={
        "user_id": "user123",
        "message": "Что такое SOLID принципы?"
    }
)
print(response.json()["message"])

# Сброс контекста
requests.post(
    "http://localhost:8084/api/v1/reset",
    json={"user_id": "user123"}
)
```

### cURL

```bash
# Отправка сообщения
curl -X POST http://localhost:8084/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "message": "Объясни принцип работы Promise в JavaScript"
  }'

# Сброс контекста
curl -X POST http://localhost:8084/api/v1/reset \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123"}'
```

### Тестовый скрипт

```bash
python3 test_client.py
```

## Документация

- **Swagger UI**: http://localhost:8084/docs
- **ReDoc**: http://localhost:8084/redoc
- **Архитектура**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Быстрый старт**: [QUICKSTART.md](QUICKSTART.md)

## Разработка

### Локальный запуск

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера
uvicorn api.main:app --reload --port 8080
```

### Логи

```bash
# Все сервисы
docker-compose logs -f

# Только chat-service
docker-compose logs -f chat-service
```

## Архитектура

### RAG Flow

```
User Question
    ↓
db-service /retrieve → Top-K Documents
    ↓
Augmented Prompt (Question + Context)
    ↓
LangGraph + Redis (History)
    ↓
OpenAI GPT-4o-mini
    ↓
Response + Save to Redis
```

### Технологии

- **FastAPI** - веб-фреймворк
- **LangChain** - интеграция с LLM
- **LangGraph** - управление диалогом
- **Redis** - хранение истории
- **Pydantic** - валидация данных
- **httpx** - асинхронный HTTP клиент

## Troubleshooting

### Ошибка подключения к Redis

```bash
docker-compose ps redis
docker-compose logs redis
```

### Ошибка подключения к db-service

```bash
# Проверьте что db-service запущен
curl http://localhost:8083/health

# Обновите DB_SERVICE_URL в .env
```

### Пересборка

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## License

MIT
