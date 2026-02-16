import sys
import os
import psycopg2

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings
from app.services.rag_system import RAGSystem

def main():
    print("🚀 ШАГ 3: Загрузка книг в ChromaDB с полными метаданными")
    
    # Инициализируем RAG систему
    rag = RAGSystem()
    
    # Подключаемся к PostgreSQL
    print(f"🔌 Подключение к PostgreSQL: {settings.DB_HOST}/{settings.DB_NAME}")
    
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASS
        )
    except psycopg2.OperationalError as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        print("\nСначала запустите: python scripts/2_import_sql.py")
        return
    
    cursor = conn.cursor()
    
    # Получаем все книги
    cursor.execute("""
        SELECT title, author, subject, grnti, bbk, author_sign, 
               systematic_code, owners, pdf_url, pdf_ocr
        FROM csl
    """)
    
    books = cursor.fetchall()
    conn.close()
    
    if not books:
        print("⚠️ В базе данных нет книг.")
        print("Сначала запустите: python scripts/2_import_sql.py")
        return
    
    print(f"📚 Найдено книг в базе: {len(books)}")
    print("🔄 Начинаем индексацию...")
    
    for i, row in enumerate(books, 1):
        book_data = {
            "title": row[0] or "",
            "author": row[1] or "",
            "subject": row[2] or "",
            "grnti": row[3] or "",
            "bbk": row[4] or "",
            "author_sign": row[5] or "",
            "systematic_code": row[6] or "",
            "owners": row[7] or "",
            "pdf_url": row[8] or "",
            "pdf_ocr": row[9] or "",
        }
        
        rag.add_book(book_data)
        
        if i % 100 == 0:
            print(f"✅ Обработано: {i}/{len(books)}")
    
    print(f"🎉 Загрузка завершена! Всего книг: {len(books)}")

if __name__ == "__main__":
    main()