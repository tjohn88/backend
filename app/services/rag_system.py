import logging
import os
import chromadb
from sentence_transformers import SentenceTransformer
from app.core.config import settings

logger = logging.getLogger(__name__)

class RAGSystem:
    def __init__(self):
        logger.info("Инициализация RAGSystem...")
        
        # 1. Загрузка модели
        model_path = settings.EMBEDDING_MODEL_PATH if hasattr(settings, 'EMBEDDING_MODEL_PATH') else "intfloat/multilingual-e5-large"
        
        # Если путь локальный и существует
        if os.path.exists(model_path) or os.path.exists(os.path.join(settings.BASE_DIR, "intfloat")):
             # Пытаемся найти папку intfloat в корне, если в конфиге пусто
             real_path = model_path if os.path.exists(model_path) else os.path.join(settings.BASE_DIR, "intfloat", "models--intfloat--multilingual-e5-large-instruct")
             logger.info(f"📂 Загружаю локальную модель: {real_path}")
             self.model = SentenceTransformer(real_path)
        else:
             logger.info(f"🌐 Скачиваю модель {model_path}...")
             self.model = SentenceTransformer("intfloat/multilingual-e5-large")

        # 2. Подключение к БД
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(name="library_collection")
        logger.info(f"✅ RAG подключен: {settings.CHROMA_PATH}")

    def add_document(self, text: str, source: str, title: str = "Unknown"):
        """Добавляет документ. Важно: добавляем префикс passage: для E5"""
        # E5 ожидает "passage: " для документов
        content_to_embed = f"passage: {text}" 
        
        # Генерируем вектор с нормализацией!
        embedding = self.model.encode(content_to_embed, normalize_embeddings=True).tolist()
        
        # Генерируем ID
        import hashlib
        doc_id = hashlib.md5((title + source + text[:50]).encode()).hexdigest()
        
        self.collection.upsert(
            ids=[doc_id],
            documents=[text], # Сохраняем оригинальный текст (без passage:) для чтения
            metadatas=[{"source": source, "title": title}],
            embeddings=[embedding]
        )
    
    def add_book(self, book_data: dict):
        """
        Добавляет книгу с полными метаданными в ChromaDB.
        
        Args:
            book_data: Словарь с полями:
                - title: название книги
                - author: автор
                - subject: рубрика/тема
                - grnti: код ГРНТИ
                - bbk: код ББК
                - author_sign: авторский знак
                - systematic_code: систематический шифр
                - owners: держатель (библиотека)
                - pdf_url: ссылка на PDF
                - pdf_ocr: распознанный текст (опционально)
        """
        # Формируем текстовое представление книги для поиска
        text_parts = [
            f"Книга: {book_data.get('title', '')}",
            f"Автор: {book_data.get('author', '')}",
        ]
        
        if book_data.get('subject'):
            text_parts.append(f"Рубрика: {book_data.get('subject', '')}")
        
        if book_data.get('owners'):
            text_parts.append(f"Держатель: {book_data.get('owners', '')}")
        
        if book_data.get('grnti'):
            text_parts.append(f"ГРНТИ: {book_data.get('grnti', '')}")
        
        if book_data.get('bbk'):
            text_parts.append(f"ББК: {book_data.get('bbk', '')}")
        
        if book_data.get('systematic_code'):
            text_parts.append(f"Систематический шифр: {book_data.get('systematic_code', '')}")
        
        if book_data.get('author_sign'):
            text_parts.append(f"Авторский знак: {book_data.get('author_sign', '')}")
        
        # Добавляем распознанный текст, если есть
        if book_data.get('pdf_ocr'):
            text_parts.append(f"\nРаспознанный текст:\n{book_data.get('pdf_ocr', '')}")
        
        text = "\n".join(text_parts)
        
        # Генерируем эмбеддинг
        content_to_embed = f"passage: {text}"
        embedding = self.model.encode(content_to_embed, normalize_embeddings=True).tolist()
        
        # Генерируем ID
        import hashlib
        doc_id = hashlib.md5((book_data.get('title', '') + book_data.get('author', '')).encode()).hexdigest()
        
        # Сохраняем в ChromaDB
        self.collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[{
                "title": book_data.get("title", ""),
                "author": book_data.get("author", ""),
                "subject": book_data.get("subject", ""),
                "grnti": book_data.get("grnti", ""),
                "bbk": book_data.get("bbk", ""),
                "author_sign": book_data.get("author_sign", ""),
                "systematic_code": book_data.get("systematic_code", ""),
                "owners": book_data.get("owners", ""),
                "pdf_url": book_data.get("pdf_url", ""),
            }],
            embeddings=[embedding]
        )
        
        logger.info(f"✅ Добавлена книга: {book_data.get('title', 'Unknown')[:50]}...")

    def search(self, query: str, top_k: int = 5) -> str:
        """Поиск. Важно: добавляем префикс query: для E5"""
        # E5 ожидает "query: " для поисковых запросов
        query_to_embed = f"query: {query}"
        
        # Векторизуем с нормализацией!
        query_vec = self.model.encode(query_to_embed, normalize_embeddings=True).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=top_k
        )
        
        context = ""
        if results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                context += f"\n[Источник: {meta.get('title', 'Книга')}]\n{doc}\n"
                
        if not context:
            return "В базе знаний нет релевантной информации."
            
        return context
        
    def search_flexible(self, query: str, top_k: int = 5) -> str:
        """
        Гибкий поиск с несколькими стратегиями.
        Полезно для коротких запросов типа "Гагарин Ю.А."
        """
        # Стратегия 1: Прямой поиск
        query_variants = [f"query: {query}"]
        
        # Стратегия 2: Если запрос короткий (возможно, имя автора)
        if len(query.split()) <= 3:
            query_variants.append(f"query: автор {query}")
            query_variants.append(f"query: книга автора {query}")
            
            # Убираем инициалы и точки: "Гагарин Ю.А." -> "Гагарин"
            cleaned = query.split()[0] if ' ' in query else query.replace('.', '').strip()
            if cleaned != query:
                query_variants.append(f"query: {cleaned}")
        
        # Ищем по всем вариантам и собираем уникальные результаты
        all_results = {}
        
        for variant in query_variants:
            query_vec = self.model.encode(variant, normalize_embeddings=True).tolist()
            
            results = self.collection.query(
                query_embeddings=[query_vec],
                n_results=top_k
            )
            
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    doc_id = results['ids'][0][i] if 'ids' in results else str(i)
                    if doc_id not in all_results:  # Избегаем дубликатов
                        meta = results['metadatas'][0][i]
                        score = results['distances'][0][i] if 'distances' in results else 0
                        all_results[doc_id] = {
                            'doc': doc,
                            'meta': meta,
                            'score': score
                        }
        
        if not all_results:
            return "В базе знаний нет релевантной информации."
        
        # Сортируем по релевантности и формируем контекст
        sorted_results = sorted(all_results.values(), key=lambda x: x['score'])[:top_k]
        
        context = ""
        for item in sorted_results:
            meta = item['meta']
            doc = item['doc']
            context += f"\n[Источник: {meta.get('title', 'Книга')}]\n{doc}\n"
        
        return context