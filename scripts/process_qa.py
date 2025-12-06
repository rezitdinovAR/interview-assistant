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