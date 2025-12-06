"""
Скрипт для обработки txt файлов из raw_data/education.yandex.ru/ml и создания JSON файлов для векторизации.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any


def parse_metadata(content: str) -> tuple[Dict[str, str], str]:
    """
    Парсит метаданные из начала файла и возвращает их вместе с основным текстом.

    Args:
        content: Содержимое файла

    Returns:
        Tuple из словаря метаданных и основного текста
    """
    # Проверяем, есть ли метаданные в формате YAML front matter
    if not content.startswith('---'):
        return {}, content

    # Находим конец блока метаданных
    lines = content.split('\n')
    metadata = {}
    text_start_idx = 0

    for i in range(1, len(lines)):
        if lines[i] == '---':
            text_start_idx = i + 1
            break

        # Парсим строку метаданных
        if ':' in lines[i]:
            key, value = lines[i].split(':', 1)
            metadata[key.strip()] = value.strip()

    # Получаем основной текст
    text = '\n'.join(lines[text_start_idx:]).strip()

    return metadata, text


def count_words(text: str) -> int:
    """
    Подсчитывает количество слов в тексте.

    Args:
        text: Текст для подсчета

    Returns:
        Количество слов
    """
    # Удаляем спецсимволы и считаем слова
    words = re.findall(r'\b\w+\b', text)
    return len(words)


def split_text_into_chunks(text: str, max_words: int = 500, overlap_words: int = 100) -> List[str]:
    """
    Разбивает текст на части с перекрытием.

    Args:
        text: Текст для разбивки
        max_words: Максимальное количество слов в одной части
        overlap_words: Количество слов перекрытия между частями

    Returns:
        Список частей текста
    """
    words = text.split()
    total_words = len(words)

    # Если текст короткий, возвращаем его целиком
    if total_words <= max_words:
        return [text]

    chunks = []
    start = 0

    while start < total_words:
        # Определяем конец текущей части
        end = min(start + max_words, total_words)

        # Извлекаем часть
        chunk_words = words[start:end]
        chunk = ' '.join(chunk_words)
        chunks.append(chunk)

        # Если достигли конца, выходим
        if end >= total_words:
            break
        start += max_words - overlap_words

    return chunks


def process_file(file_path: Path, description: str = None) -> List[Dict[str, Any]]:
    """
    Обрабатывает один txt файл и возвращает список записей для JSON.

    Args:
        file_path: Путь к файлу
        description: Описание источника данных

    Returns:
        Список словарей с данными для векторизации
    """
    # Читаем содержимое файла
    with open(file_path, 'r', encoding='utf-8') as f: 
        content = f.read()

    metadata, text = parse_metadata(content)
    chunks = split_text_into_chunks(text, max_words=500, overlap_words=100)

    # Создаем записи для каждой части
    results = []
    for i, chunk in enumerate(chunks, start=1):
        record_metadata = {
            **metadata,  # Копируем все исходные метаданные
            'part': i,
            'total_parts': len(chunks),
            'source_file': str(file_path.name)
        }

        # Добавляем описание, если оно указано
        if description:
            record_metadata['description'] = description

        record = {
            'text': chunk,
            'metadata': record_metadata
        }
        results.append(record)

    return results


def process_all_files(input_dir: str, output_file: str, description: str = None):
    """
    Обрабатывает все txt файлы из директории и сохраняет результат в JSON.

    Args:
        input_dir: Путь к директории с txt файлами
        output_file: Путь к выходному JSON файлу
        description: Описание источника данных (добавляется в метаданные)
    """
    input_path = Path(input_dir)

    # Получаем список всех txt файлов
    txt_files = sorted(input_path.glob('*.txt'))

    print(f"Найдено {len(txt_files)} txt файлов")

    # Обрабатываем все файлы
    all_records = []
    for file_path in txt_files:
        print(f"Обработка: {file_path.name}")
        records = process_file(file_path, description=description)
        all_records.extend(records)
        print(f"  Создано {len(records)} частей")

    # Сохраняем результат
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nВсего обработано записей: {len(all_records)}")
    print(f"Результат сохранен в: {output_file}")
