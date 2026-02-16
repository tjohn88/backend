import sys
import os
import logging
from llama_cpp import Llama

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_model():
    """Загрузка модели через llama-cpp-python"""
    if not os.path.exists(settings.MODEL_PATH):
        logger.error(f"❌ ОШИБКА: Модель не найдена по пути: {settings.MODEL_PATH}")
        logger.error(f"   Положите файл {settings.MODEL_NAME} в папку models/")
        sys.exit(1)
        
    logger.info(f"💾 Загрузка модели из: {settings.MODEL_PATH}")
    # n_gpu_layers=-1 задействует все слои на GPU, если драйвера настроены
    return Llama(
        model_path=settings.MODEL_PATH,
        n_ctx=8192,      # Контекст
        n_gpu_layers=-1, # Максимум на GPU
        verbose=False
    )

def clean_chunk_with_llm(llm, text):
    """Очистка текста через прямой вызов модели"""
    prompt = f"""Исправь ошибки OCR (распознавания текста). Склей разорванные слова. Исправь пунктуацию.
НЕ удаляй информацию. Верни только исправленный текст.

ТЕКСТ:
{text}
"""
    try:
        response = llm.create_chat_completion(
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=None # Лимит по контексту
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f"⚠️ Ошибка LLM: {e}")
        return text # Если упало, возвращаем как есть

def process_book(llm, filename):
    pdf_path = os.path.join(settings.BOOKS_DIR, filename)
    txt_name = filename.replace(".pdf", ".txt")
    
    # 1. Извлечение (pdftotext)
    dirty_path = os.path.join(settings.TEMP_TXT_DIR, txt_name)
    
    print(f"\n📘 Книга: {filename}")
    try:
        if not os.path.exists(dirty_path):
            print("   🔨 Извлекаем текст...")
            subprocess_args = [settings.PDFTOTEXT_PATH, "-enc", "UTF-8", pdf_path, dirty_path]
            # Проверка наличия pdftotext
            if not os.path.exists(settings.PDFTOTEXT_PATH):
                 logger.error(f"❌ pdftotext не найден: {settings.PDFTOTEXT_PATH}")
                 return
                 
            import subprocess
            subprocess.run(subprocess_args, check=True)
    except Exception as e:
        logger.error(f"❌ Ошибка pdftotext: {e}")
        return

    # 2. Очистка (LLM)
    clean_path = os.path.join(settings.CLEAN_TXT_DIR, txt_name)
    if os.path.exists(clean_path):
        print("   ⏩ Уже очищено.")
        return

    with open(dirty_path, "r", encoding="utf-8") as f:
        dirty_text = f.read()

    # Делим на чанки по 2000 символов (чуть меньше, чтобы вошло в промпт)
    chunk_size = 2000
    chunks = [dirty_text[i:i+chunk_size] for i in range(0, len(dirty_text), chunk_size)]
    
    print(f"   🧹 Очистка нейросетью ({len(chunks)} частей)...")
    full_clean = []
    
    for i, chunk in enumerate(chunks):
        print(f"     Часть {i+1}/{len(chunks)}", end="\r")
        cleaned = clean_chunk_with_llm(llm, chunk)
        full_clean.append(cleaned)
    
    with open(clean_path, "w", encoding="utf-8") as f:
        f.write("\n".join(full_clean))
    print(f"\n   ✅ Готово: {clean_path}")

def main():
    llm = load_model()
    
    files = [f for f in os.listdir(settings.BOOKS_DIR) if f.endswith(".pdf")]
    if not files:
        print(f"⚠️ Нет PDF в папке {settings.BOOKS_DIR}")
        
    for f in files:
        process_book(llm, f)

if __name__ == "__main__":
    main()