# Evaluation Service

Сервис для оценки ответов RAG системы с использованием библиотеки [ragas](https://ragas.io/).

## Описание

Сервис предоставляет API для оценки качества ответов RAG системы по различным метрикам:
- **faithfulness** - верность ответа контексту (насколько ответ основан на предоставленном контексте)
- **answer_relevancy** - релевантность ответа вопросу (насколько ответ соответствует вопросу)
- **context_precision** - точность контекста (насколько релевантен извлеченный контекст)
- **context_recall** - полнота контекста (насколько полон извлеченный контекст)

Сервис автоматически использует embedding-service для метрик, которые требуют эмбеддинги.

## Структура

```
evaluation-service/
├── api/
│   ├── core/
│   │   └── config.py          # Конфигурация
│   ├── routers/
│   │   └── evaluation.py      # API endpoints
│   ├── schemas/
│   │   └── evaluation.py      # Pydantic схемы
│   ├── services/
│   │   ├── embedding_client.py    # Клиент для embedding-service
│   │   └── evaluation_service.py  # Сервис оценки
│   └── main.py                # FastAPI приложение
├── data/
│   └── questions.csv          # Файл с вопросами для оценки
├── Dockerfile
├── requirements.txt
└── README.md
```

## API Endpoints

### POST `/api/v1/evaluate`

Оценить ответы RAG системы.

**Request Body:**
```json
{
  "questions": ["Что такое машинное обучение?"],
  "ground_truths": ["Машинное обучение - это..."],
  "answers": ["Машинное обучение представляет собой..."],
  "contexts": [["Контекст 1", "Контекст 2"]],
  "metrics": ["faithfulness", "answer_relevancy"]
}
```

**Response:**
```json
{
  "results": [
    {
      "metric_name": "faithfulness",
      "score": 0.85,
      "description": "Метрика верности ответа контексту..."
    }
  ],
  "average_score": 0.885,
  "total_samples": 1
}
```

### POST `/api/v1/evaluate-from-csv`

Оценить ответы из CSV файла.

**Query Parameters:**
- `csv_path` (optional) - путь к CSV файлу. Если не указан, используется файл по умолчанию
- `metrics` (optional) - список метрик для вычисления

**CSV файл должен содержать колонки:**
- `Вопрос` - вопросы
- `Эталонный ответ` - эталонные ответы
- `Ответ модели` - ответы модели для оценки

### GET `/api/v1/metrics`

Получить список доступных метрик с описаниями.

### GET `/api/v1/health`

Проверка здоровья сервиса.

## Переменные окружения

- `EMBEDDING_URL` - URL сервиса эмбеддингов (по умолчанию: `http://158.160.168.247:8081`)
- `EMBEDDING_MODEL` - название модели эмбеддингов (по умолчанию: `Qwen3-Embedding-8B`)
- `QUESTIONS_CSV_PATH` - путь к CSV файлу с вопросами (по умолчанию: `/workspace/data/questions.csv`)

## Использование

### Запуск через Docker Compose

Сервис автоматически запускается при использовании `docker-compose.yml`:

```bash
docker-compose up evaluation-service
```

### Пример использования API

```python
import requests

# Оценка ответов
response = requests.post(
    "http://localhost:8000/api/v1/evaluate",
    json={
        "questions": ["Что такое машинное обучение?"],
        "ground_truths": ["Машинное обучение - это метод..."],
        "answers": ["Машинное обучение представляет собой..."],
        "metrics": ["faithfulness", "answer_relevancy"]
    }
)

print(response.json())
```

### Оценка из CSV файла

```bash
curl -X POST "http://localhost:8000/api/v1/evaluate-from-csv?metrics=faithfulness&metrics=answer_relevancy"
```

## Зависимости

- **ragas** - библиотека для оценки RAG систем
- **fastapi** - веб-фреймворк
- **httpx** - HTTP клиент для работы с embedding-service
- **pandas** - для работы с CSV файлами
- **datasets** - для работы с датасетами

## Примечания

- Сервис автоматически использует embedding-service для метрик, требующих эмбеддинги
- Если контексты не предоставлены, они будут пустыми списками
- Все метрики возвращают значения от 0 до 1, где 1 - лучший результат

