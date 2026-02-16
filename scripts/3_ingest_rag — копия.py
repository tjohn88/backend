# ✅ ingest_books_json.py (готовый под ключ)

import json
import time
import torch
from typing import List
from langchain.docstore.document import Document
from sentence_transformers import SentenceTransformer
from rag_optimizer import ingest_documents

# === Настройка эмбеддинга ===
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"📡 Using device: {DEVICE}")

print("📦 Loading embedding model...")
embedding_model = SentenceTransformer(
    'intfloat/multilingual-e5-large-instruct',
    cache_folder='./intfloat',
    use_auth_token=False,
    local_files_only=True
)

# === Форматирование текста книги ===
def format_book(book: dict) -> str:
    return "\n".join([
        f"Название: {book.get('title', '')}",
        f"Автор: {book.get('author', '')}",
        f"ГРНТИ: {book.get('grnti', '')}",
        f"ББК: {book.get('bbk', '')}",
        f"Авторский знак: {book.get('author_sign', '')}",
        f"Систематический шифр: {book.get('systematic_code', '')}",
        f"Рубрика: {book.get('subject', '')}",
        f"Держатель: {book.get('owners', '')}",
        f"Ссылка: {book.get('pdf_url', '')}",
        f"Распознанный текст: {book.get('pdf_ocr', '')}"
    ]).strip()

# === Основной код ===
def main():
    start_time = time.time()

    JSON_PATH = "unit.json"
    COLLECTION_NAME = "unit_rag"
    PERSIST_DIR = "./chroma"

    print(f"📖 Загрузка книг из {JSON_PATH}...")
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        books = json.load(f)

    documents = []
    for book in books:
        text = format_book(book)
        metadata = {
            "title": book.get("title", ""),
            "author": book.get("author", ""),
            "grnti": book.get("grnti", ""),
            "bbk": book.get("bbk", ""),
            "author_sign": book.get("author_sign", ""),
            "systematic_code": book.get("systematic_code", ""),
            "subject": book.get("subject", ""),
            "owners": book.get("owners", ""),
            "pdf_url": book.get("pdf_url", ""),
            "pdf_ocr": book.get("pdf_ocr", "")
        }
        documents.append(Document(page_content=text, metadata=metadata))

    print(f"🧠 Генерация эмбеддингов для {len(documents)} документов...")
    texts = [doc.page_content for doc in documents]
    embeddings = embedding_model.encode(texts, convert_to_tensor=False, show_progress_bar=True)

    ingest_documents(
        documents,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings,
        persist_directory=PERSIST_DIR
    )

    elapsed = time.time() - start_time
    print(f"✅ Загрузка завершена за {elapsed:.2f} сек.")

if __name__ == "__main__":
    main()
