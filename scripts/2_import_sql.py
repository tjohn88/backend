import json
import psycopg2
import os
import sys

# Добавляем путь к проекту для импорта settings
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings

def load_json(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def create_table(conn):
    """Создает таблицу csl, если её нет"""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS csl (
            id SERIAL PRIMARY KEY,
            title TEXT,
            author TEXT,
            subject TEXT,
            grnti TEXT,
            bbk TEXT,
            author_sign TEXT,
            systematic_code TEXT,
            owners TEXT,
            pdf_url TEXT,
            pdf_ocr TEXT
        )
    """)
    conn.commit()
    cur.close()
    print("✅ Таблица csl готова")

def insert_books(data, conn):
    cur = conn.cursor()
    
    # Очищаем таблицу перед импортом
    cur.execute("TRUNCATE TABLE csl RESTART IDENTITY")
    
    for book in data:
        cur.execute("""
            INSERT INTO csl (title, author, subject, grnti, bbk, author_sign, systematic_code, owners, pdf_url, pdf_ocr)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            book.get("title"),
            book.get("author"),
            book.get("subject"),
            book.get("grnti"),
            book.get("bbk"),
            book.get("author_sign"),
            book.get("systematic_code"),
            book.get("owners"),
            book.get("pdf_url"),
            book.get("pdf_ocr")
        ))
    
    conn.commit()
    cur.close()
    print(f"✅ Импортировано записей: {len(data)}")

if __name__ == "__main__":
    # Определяем пути относительно текущего скрипта
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    json_path = os.path.join(project_root, "uploads", "input_catalogs", "books.json")
    
    print(f"📖 Загрузка данных из: {json_path}")
    
    if not os.path.exists(json_path):
        print(f"❌ Файл не найден: {json_path}")
        print("Сначала запустите: python scripts/1_process_catalogs.py")
        exit(1)
    
    books = load_json(json_path)
    print(f"📚 Найдено книг: {len(books)}")
    
    # Подключаемся к PostgreSQL
    print(f"🔌 Подключение к PostgreSQL: {settings.DB_HOST}/{settings.DB_NAME}")
    
    try:
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASS
        )
        
        create_table(conn)
        insert_books(books, conn)
        
        conn.close()
        print("🎉 Готово!")
        
    except psycopg2.OperationalError as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        print("\nПроверьте:")
        print("1. PostgreSQL установлен и запущен")
        print("2. База данных 'books-db' создана")
        print("3. Настройки в .env правильные (DB_HOST, DB_NAME, DB_USER, DB_PASS)")
        print("\nДля создания базы выполните в psql:")
        print("  CREATE DATABASE \"books-db\";")
        exit(1)
