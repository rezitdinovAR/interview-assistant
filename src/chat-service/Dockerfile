FROM python:3.11

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

WORKDIR /workspace

ENTRYPOINT ["uvicorn", "--workers", "1", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
