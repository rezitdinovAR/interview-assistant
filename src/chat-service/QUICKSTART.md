# Быстрый старт Chat Service

## Вариант 1: Запуск только Chat Service + Redis

Этот вариант подходит для разработки и тестирования chat-сервиса отдельно.

### Шаг 1: Создайте .env файл

```bash
cp .env.example .env
```

Отредактируйте `.env` и укажите ваш OpenAI API ключ:
```
OPENAI_API_KEY=sk-your-key-here
```

Если db-service запущен локально на порту 8083, оставьте:
```
DB_SERVICE_URL=http://host.docker.internal:8083
```

### Шаг 2: Запустите сервисы

```bash
docker-compose up -d
```

### Шаг 3: Проверьте работу

```bash
# Проверка здоровья сервиса
curl http://localhost:8084/health

# Отправка тестового сообщения
curl -X POST http://localhost:8084/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "message": "Привет! Что такое замыкание в JavaScript?"
  }'
```

Или используйте тестовый скрипт:
```bash
python3 test_client.py
```

### Остановка

```bash
docker-compose down
```

Для удаления данных Redis:
```bash
docker-compose down -v
rm -rf redis-data/
```

---

## Вариант 2: Запуск всей инфраструктуры

Если нужно запустить весь стек (db-service, embedding, reranking, chat-service):

### Из корневой директории `src/`

```bash
cd ..
docker-compose up -d
```

Chat-service будет доступен на `http://localhost:8084`

---

## Логи и отладка

### Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Только chat-service
docker-compose logs -f chat-service

# Только Redis
docker-compose logs -f redis
```

### Проверка контейнеров

```bash
docker-compose ps
```

### Подключение к Redis CLI

```bash
docker exec -it chat-redis redis-cli

# Примеры команд в Redis:
# KEYS *                    # показать все ключи
# GET key_name              # получить значение
# FLUSHALL                  # очистить все данные (осторожно!)
```

---

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|--------------|
| `OPENAI_API_KEY` | API ключ OpenAI | - (обязательно) |
| `REDIS_URI` | URI подключения к Redis | `redis://redis:6379` |
| `DB_SERVICE_URL` | URL db-service для RAG | `http://api:8080` |
| `TOP_K_DOCUMENTS` | Кол-во документов из RAG | `5` |
| `MAX_TOKENS` | Макс. токенов контекста | `10000` |

---

## Порты

- **8084** - Chat Service API
- **6379** - Redis

---

## Troubleshooting

### Ошибка: "Cannot connect to Redis"

Убедитесь что Redis запущен:
```bash
docker-compose ps redis
```

Проверьте логи Redis:
```bash
docker-compose logs redis
```

### Ошибка: "Error retrieving documents from db-service"

Проверьте что db-service доступен:
```bash
curl http://localhost:8083/health
```

Если db-service на другом хосте, обновите `DB_SERVICE_URL` в `.env`

### Ошибка: "OPENAI_API_KEY not found"

Убедитесь что файл `.env` существует и содержит валидный ключ:
```bash
cat .env | grep OPENAI_API_KEY
```

### Пересоздание контейнеров

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```
