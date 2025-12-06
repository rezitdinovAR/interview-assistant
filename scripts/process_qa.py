import re
import json
from pathlib import Path
from typing import Dict, List, Any


def parse_yaml_front_matter(content: str) -> tuple[Dict[str, str], str]:
    """ Извлекает YAML метаданные и возвращает (metadata, text). """
    if not content.startswith('---'):
        return {}, content
    
    lines = content.split("\n")
    metadata = {}
    text_start_idx = 0

    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            text_start_idx = i + 1
            break

        if ':' in lines[i]:
            key, value = lines[i].split(':', 1)
            metadata[key.strip()] = value.strip()

    text = "\n".join(lines[text_start_idx:]).strip()
    return metadata, text


def parse_qa_blocks(text: str) -> List[Dict[str, str]]:
    """Парсит блоки вида '1. Вопрос\nОтвет...'. """
    pattern = r"\n?(\d+)\.\s+([^\n]+)\n(.+?)(?=\n\d+\.|\Z)"
    matches = re.findall(pattern, text, flags=re.S)

    qa_list = []
    for num, question, answer in matches:
        qa_list.append({
            "question_number": int(num),
            "question": question.strip(),
            "answer": answer.strip()
        })

    return qa_list


def process_qa_file(file_path: Path, description: str | None = None) -> List[Dict[str, Any]]:
    """ Создаёт JSON записи для всех Q&A из файла. """
    content = file_path.read_text(encoding="utf-8")

    metadata, text = parse_yaml_front_matter(content)
    qa_items = parse_qa_blocks(text)

    results = []
    for item in qa_items:
        record_metadata = {
            **metadata,
            "question_number": item["question_number"],
            "question": item["question"],
            "source_file": str(file_path)
        }

        if description:
            record_metadata["description"] = description

        results.append({
            "text": f"Q: {item['question']}\nA: {item['answer']}",
            "metadata": record_metadata
        })

    return results


def process_qa_directory(input_dir: str, output_file: str, description: str = None):
    """ Рекурсивно обрабатывает все txt файлы и создаёт JSON с Q&A. """
    input_path = Path(input_dir)
    txt_files = sorted(input_path.rglob("*.txt"))

    all_records = []

    for f in txt_files:
        print(f"Обработка: {f}")
        records = process_qa_file(f, description=description)
        all_records.extend(records)
        print(f"  Q&A найдено: {len(records)}")

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print("\nГотово!")
    print(f"Всего записей: {len(all_records)}")
    print(f"Сохранено в: {output_file}")

def clean_underscores(text: str) -> str:
    """
    Убирает все линии или последовательности подчёркиваний.
    """
    # 1) линии только из подчёркиваний (с любыми \n)
    text = re.sub(r"\n?_+_\n?", "\n", text)
    # 2) последовательности подчёркиваний внутри текста
    text = re.sub(r"_+", "", text)
    # 3) лишние пробелы/новые строки
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def process_plain_qa_file(file_path: Path, description: str = None) -> List[Dict[str, Any]]:
    """
    Обрабатывает txt-файлы формата:
    1. Название секции
    Вопрос: ...
    Ответ: ...
    ____________________
    """

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Убираем подчёркивания в начале
    text = clean_underscores(text)

    # Разбиваем по 1. 2. 3.
    blocks = re.split(r"\n?\s*\d+\.\s+", text)
    blocks = [b.strip() for b in blocks if b.strip()]

    results = []
    q_global = 0

    for block in blocks:
        lines = block.split("\n")
        section_title = lines[0].strip()
        section_text = "\n".join(lines[1:]).strip()

        # Разбиваем на пары Вопрос/Ответ
        qa_pairs = re.split(r"Вопрос:", section_text)
        qa_pairs = [q.strip() for q in qa_pairs if q.strip()]

        for pair in qa_pairs:
            parts = re.split(r"Ответ:", pair)
            if len(parts) < 2:
                continue

            question = clean_underscores(parts[0].strip())
            answer = clean_underscores(parts[1].strip())

            q_global += 1

            results.append({
                "text": f"Вопрос: {question}\nОтвет: {answer}",
                "metadata": {
                    "section": section_title,
                    "question_number": q_global,
                    "question": question,
                    "answer": answer,
                    "source_file": file_path.name,
                    "description": description or None
                }
            })

    return results