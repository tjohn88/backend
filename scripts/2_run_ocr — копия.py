import os
import requests
from pathlib import Path

INPUT_FOLDER = "input"
OUTPUT_FOLDER = "output"
LLAMA_SERVER_URL = "http://127.0.0.1:8000/completion"

def clean_text_literary_style(text: str) -> str:
    prompt = f"[INST] Ты редактор. Преобразуй следующий текст, полученный через OCR, в грамотный литературный русский язык. Исправляй только ошибки, опечатки и пунктуацию. Не добавляй нового содержания! Не переводи на другой язык, не объясняй, не дополняй, не сокращай. Вот текст:\n{text} [/INST]"
    payload = {
        "prompt": prompt,
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 2048,  # не надо делать огромные чанки
        "stop": ["</s>"]
    }
    response = requests.post(LLAMA_SERVER_URL, json=payload)
    if response.ok:
        return response.json()["content"].strip()
    else:
        print("❌ Ошибка при запросе к Llama Server:", response.text)
        return ""

import difflib

def is_hallucination(orig, edited, threshold=1.5):
    # threshold: во сколько раз длина изменилась
    len_orig = len(orig.split())
    len_edited = len(edited.split())
    if len_edited > len_orig * threshold:
        return True
    # или если процент изменённых слов слишком высок
    diff = list(difflib.unified_diff(orig.split(), edited.split()))
    if len(diff) > len_orig * 0.8:
        return True
    return False


os.makedirs(OUTPUT_FOLDER, exist_ok=True)
for file in os.listdir(INPUT_FOLDER):
    if file.endswith(".txt"):
        print(f"🚀 Обрабатываем файл: {file}")
        input_path = os.path.join(INPUT_FOLDER, file)
        output_path = os.path.join(OUTPUT_FOLDER, f"{Path(file).stem}_cleaned.txt")

        with open(input_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Режем по абзацам
        chunks = [chunk.strip() for chunk in raw_text.split("\n") if chunk.strip()]
        cleaned = []

#-------------
        for i, chunk in enumerate(chunks):
            print(f"  ✏️ [{i+1}/{len(chunks)}] Чистим абзац...")
            cleaned_chunk = clean_text_literary_style(chunk)
            cleaned.append(cleaned_chunk + "\n")
#            if is_hallucination(chunk, cleaned_chunk):
#                print("⚠️ ПОДОЗРИТЕЛЬНО: Модель что-то наколдовала!")
#                print("БЫЛО:", chunk)
#                print("СТАЛО:", cleaned_chunk)
# можно даже записывать это отдельно в suspicious.txt
#            cleaned.append(cleaned_chunk + "\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(cleaned)

        print(f"✅ Готово! Результат: {output_path}\n")
