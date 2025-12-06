"""
Скрипт для рекурсивной обработки txt файлов из raw_data/huggingface.co.learn
и создания JSON файлов для векторизации.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any


def parse_metadata(content: str) -> tuple[Dict[str, str], str]:
    """Парсит YAML-метаданные из начала файла и возвращает (метаданные, основной текст)."""
    if not content.startswith('---'):
        return {}, content

    lines = content.split('\n')
    metadata = {}
    text_start_idx = 0

    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            text_start_idx = i + 1
            break

        if ':' in lines[i]:
            key, value = lines[i].split(':', 1)
            metadata[key.strip()] = value.strip()

    text = '\n'.join(lines[text_start_idx:]).strip()
    return metadata, text


def split_text_into_chunks(text: str, max_words: int = 500, overlap_words: int = 100) -> List[str]:
    """Разбивает текст на перекрывающиеся части."""
    words = text.split()
    total_words = len(words)

    if total_words <= max_words:
        return [text]

    chunks = []
    start = 0

    while start < total_words:
        end = min(start + max_words, total_words)
        chunk_words = words[start:end]
        chunks.append(' '.join(chunk_words))

        if end >= total_words:
            break

        start += max_words - overlap_words

    return chunks


def process_file(file_path: Path, description: str = None, course: str | None = None) -> List[Dict[str, Any]]:
    """Обрабатывает один txt файл."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    metadata, text = parse_metadata(content)
    chunks = split_text_into_chunks(text)

    results = []
    for i, chunk in enumerate(chunks, start=1):
        record_metadata = {
            **metadata,
            "part": i,
            "total_parts": len(chunks),
            "source_file": str(file_path),
        }

        if course:
            record_metadata["course"] = course

        if description:
            record_metadata["description"] = description

        results.append({
            "text": chunk,
            "metadata": record_metadata,
        })

    return results


def process_all_files_recursive(input_dir: str, output_file: str, description: str = None):
    """
    Рекурсивно обрабатывает все txt файлы внутри input_dir, включая вложенные папки.
    Имя верхнеуровневой папки считается названием курса.
    """
    input_path = Path(input_dir)

    # Все txt во всех вложенных папках
    txt_files = sorted(input_path.rglob('*.txt'))

    print(f"Найдено {len(txt_files)} txt файлов\n")

    all_records = []

    for file_path in txt_files:
        # course = имя папки верхнего уровня: agents-course / llm-course
        # raw_data/huggingface.co.learn/agents-course/.../file.txt
        course = file_path.parts[len(input_path.parts)]  # элемент после input_dir

        print(f"[{course}] Обработка: {file_path}")

        records = process_file(
            file_path=file_path,
            description=description,
            course=course,
        )
        all_records.extend(records)

        print(f"  Создано частей: {len(records)}")

    # Сохранение
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nВсего записей: {len(all_records)}")
    print(f"Сохранено в: {output_file}")