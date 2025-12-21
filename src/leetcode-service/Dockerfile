FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m sandbox_user

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]