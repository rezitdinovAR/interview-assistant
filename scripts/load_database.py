#!/usr/bin/env python3
"""
Скрипт для загрузки данных из JSON файлов в базу данных через API.
Загружает тексты из всех JSON файлов в папке processed_data и отправляет их батчами по 50 штук.
"""

import json
from pathlib import Path
import requests
from typing import List
import time


API_URL = "http://158.160.168.247:8083/add_chunks"
BATCH_SIZE = 50
PROCESSED_DATA_DIR = Path(__file__).parent.parent / "processed_data"


def load_texts_from_json(file_path: Path) -> List[str]:
    """Загружает тексты из JSON файла."""
    print(f"Читаем файл: {file_path.name}")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    texts = [item['text'] for item in data if 'text' in item]
    print(f"  Загружено {len(texts)} текстов из {file_path.name}")
    return texts


def send_batch(texts: List[str], batch_num: int) -> bool:
    """Отправляет батч текстов на API."""
    payload = {"texts": texts}

    try:
        print(f"Отправка батча #{batch_num} ({len(texts)} текстов)...")
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        print(f"  ✓ Батч #{batch_num} успешно загружен")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Ошибка при отправке батча #{batch_num}: {e}")
        return False


def load_all_data():
    """Основная функция загрузки всех данных."""
    if not PROCESSED_DATA_DIR.exists():
        print(f"Ошибка: Папка {PROCESSED_DATA_DIR} не найдена")
        return

    # Собираем все JSON файлы
    json_files = list(PROCESSED_DATA_DIR.glob("*.json"))

    if not json_files:
        print(f"Ошибка: Не найдено JSON файлов в {PROCESSED_DATA_DIR}")
        return

    print(f"Найдено {len(json_files)} JSON файлов")
    print("=" * 60)

    # Собираем все тексты
    all_texts = []
    for json_file in sorted(json_files):
        texts = load_texts_from_json(json_file)
        all_texts.extend(texts)

    print("=" * 60)
    print(f"Всего текстов для загрузки: {len(all_texts)}")
    print(f"Количество батчей: {(len(all_texts) + BATCH_SIZE - 1) // BATCH_SIZE}")
    print("=" * 60)

    # Отправляем батчами
    successful_batches = 0
    failed_batches = 0

    for i in range(0, len(all_texts), BATCH_SIZE):
        batch = all_texts[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1

        if send_batch(batch, batch_num):
            successful_batches += 1
        else:
            failed_batches += 1

        # Небольшая пауза между запросами
        time.sleep(0.5)

    print("=" * 60)
    print(f"Загрузка завершена!")
    print(f"  Успешно: {successful_batches} батчей")
    print(f"  Ошибок: {failed_batches} батчей")
    print(f"  Всего загружено: {successful_batches * BATCH_SIZE} текстов (приблизительно)")


if __name__ == "__main__":
    load_all_data()
