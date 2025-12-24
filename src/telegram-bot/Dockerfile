FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-cffi \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgobject-2.0-0 \
    libffi-dev \
    shared-mime-info \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CACHE_HOME=/app/.cache

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd -r appuser && \
    useradd -r -g appuser appuser && \
    mkdir -p /app/.cache && \
    chown -R appuser:appuser /app

USER appuser

CMD ["python", "main.py"]