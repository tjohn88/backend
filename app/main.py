import threading
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.llm_client import get_llm_client, close_llm_client
from app.services.rag_system import RAGSystem
from app.services.sql_service import sql_service
from app.bot.telegram_bot import bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализируем систему поиска один раз
rag_system = RAGSystem()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Запуск приложения...")
    await get_llm_client()
    
    # Бот в фоне
    # Бот в фоне
    def run_bot():
        print("--- [DEBUG] Попытка удалить вебхук перед запуском... ---")
        try:
            bot.remove_webhook()
            print("--- [DEBUG] Вебхук успешно удален. Запуск bot.infinity_polling()... ---")
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logger.error(f"--- [ERROR] Ошибка при запуске бота: {e}")
            
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    yield
    await close_llm_client()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

class SearchRequest(BaseModel):
    query: str
    field: str = None # Для SQL поиска

@app.get("/")
def home():
    return FileResponse("static/index.html")

# 1. API для RAG (Умный ответ)
@app.post("/api/ask")
async def ask(req: SearchRequest):
    # Ищем в базе
    context = rag_system.search(req.query)
    
    llm = await get_llm_client()
    messages = [
        {"role": "system", "content": f"Ответь на вопрос по книгам. Контекст:\n{context}"},
        {"role": "user", "content": req.query}
    ]
    answer = await llm.chat_completion(messages)
    return {"answer": answer, "context": context}

# 2. API для SQL (Точный поиск по каталогу)
@app.post("/api/find_book")
async def find_book(req: SearchRequest):
    table = req.field if req.field else "unit" # Временный хак или передавать отдельно
    # На самом деле нам нужно передавать таблицу в запросе. 
    # Обновим модель SearchRequest ниже.
    
    # Для простоты пока используем поле 'field' как имя поля, а таблицу возьмем из параметров
    # Но лучше сделать SearchRequest более полным.
    pass

class AdvancedSearchRequest(BaseModel):
    query: str
    mode: str = "rag" # rag или sql
    table: str = "unit"
    field: str = "title"

@app.post("/api/search")
async def search_v2(req: AdvancedSearchRequest):
    if req.mode == "sql":
        books = sql_service.search_books(req.field, req.query, req.table)
        return {"results": books, "mode": "sql"}
    else:
        context = rag_system.search(req.query)
        llm = await get_llm_client()
        messages = [
            {"role": "system", "content": f"Ответь на вопрос по книгам. Контекст:\n{context}"},
            {"role": "user", "content": req.query}
        ]
        answer = await llm.chat_completion(messages)
        return {"answer": answer, "context": context, "mode": "rag"}

@app.get("/api/tables")
async def get_tables():
    return {"tables": sql_service.get_available_tables()}

class AnalyzeRequest(BaseModel):
    book_id: int
    table: str

@app.post("/api/analyze")
async def analyze_book(req: AnalyzeRequest):
    from app.bot.telegram_bot import download_pdf_text, clean_llm_response
    
    # 1. Получаем текст/url
    text, url = sql_service.get_book_text(req.book_id, req.table)
    
    if not text and url:
        try:
            text = download_pdf_text(url)
        except Exception as e:
            return {"error": f"Ошибка загрузки PDF: {str(e)}"}
            
    if not text:
        return {"error": "Текст недоступен для анализа"}
        
    # 2. Анализ
    llm = await get_llm_client()
    prompt = f"Проанализируй текст и составь краткое содержание на русском языке:\n\n{text[:8000]}"
    messages = [{"role": "user", "content": prompt}]
    answer = await llm.chat_completion(messages)
    
    clean_answer = clean_llm_response(answer)
    return {"analysis": clean_answer}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)