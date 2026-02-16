import psycopg2
import logging
from typing import List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class SQLService:
    def _get_connection(self):
        return psycopg2.connect(
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASS,
            host=settings.DB_HOST
        )

    def get_available_tables(self) -> List[str]:
        """Получает список всех таблиц с книгами в БД"""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            # Запрос к системному каталогу Postgres для получения списка таблиц
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            # Фильтруем только наши таблицы (можно добавить логику, если есть лишние)
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка при получении списка таблиц: {e}")
            return ["unit"] # Возвращаем дефолтную, если база недоступна

    def search_books(self, field: str, value: str, table: str = "unit") -> List[Dict[str, Any]]:
        """
        Поиск книг в PostgreSQL.
        field: author, title, subject, bbk, grnti, systematic_code
        """
        # Маппинг полей для защиты от SQL-инъекций
        field_map = {
            "author": "author", "title": "title", "subject": "subject",
            "bbk": "bbk", "grnti": "grnti", "code": "systematic_code",
            "year": "year" # Если есть
        }
        db_field = field_map.get(field)
        
        if not db_field:
            return []

        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Используем безопасную подстановку имени таблицы (через форматирование, т.к. имя валидировано)
            # И безопасную подстановку значения (через параметры)
            query = f"""
                SELECT id, title, author, systematic_code, bbk, grnti, subject, owners, pdf_url, pdf_ocr, author_sign 
                FROM {table} 
                WHERE {db_field} ILIKE %s 
                LIMIT 10
            """
            cur.execute(query, (f"%{value}%",))
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": row[0], "title": row[1], "author": row[2], "systematic_code": row[3],
                    "bbk": row[4], "grnti": row[5], "subject": row[6],
                    "owners": row[7], "pdf_url": row[8], "has_text": bool(row[9]), # Флаг, есть ли текст
                    "author_sign": row[10] if len(row) > 10 else None
                })
            
            cur.close()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"SQL Error ({table}): {e}")
            return []

    def get_book_text(self, book_id: int, table: str = "unit") -> tuple:
        """Получает полный текст книги и ссылку по ID"""
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(f"SELECT pdf_ocr, pdf_url FROM {table} WHERE id = %s", (book_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return (row[0], row[1]) if row else (None, None)
        except Exception as e:
            logger.error(f"Error getting book text: {e}")
            return (None, None)

sql_service = SQLService()