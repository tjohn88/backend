import psycopg2
import logging
from typing import List, Dict
from app.core.config import get_settings

logger = logging.getLogger(__name__)

class SQLService:
    def __init__(self):
        self.settings = get_settings()

    def _get_connection(self):
        return psycopg2.connect(
            dbname=self.settings.DB_NAME,
            user=self.settings.DB_USER,
            password=self.settings.DB_PASS,
            host=self.settings.DB_HOST
        )

    def search_books(self, field: str, value: str, table: str = "unit") -> List[Dict]:
        """
        Поиск книг в PostgreSQL.
        field: поле поиска (title, author, subject, bbk, grnti)
        """
        # Маппинг полей, чтобы избежать SQL-инъекций через имя поля
        allowed_fields = {
            "author": "author", "title": "title", 
            "subject": "subject", "bbk": "bbk", "grnti": "grnti"
        }
        db_field = allowed_fields.get(field)
        if not db_field:
            logger.error(f"Недопустимое поле поиска: {field}")
            return []

        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            query = f"""
                SELECT title, author, systematic_code, bbk, grnti, subject, owners, pdf_url 
                FROM {table} 
                WHERE {db_field} ILIKE %s LIMIT 10
            """
            cur.execute(query, (f"%{value}%",))
            rows = cur.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "title": row[0], "author": row[1], "code": row[2],
                    "bbk": row[3], "grnti": row[4], "subject": row[5],
                    "owners": row[6], "pdf_url": row[7]
                })
            
            cur.close()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Ошибка SQL поиска: {e}")
            return []

sql_service = SQLService()