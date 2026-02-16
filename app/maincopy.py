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
    bot_thread = threading.Thread(target=bot.infinity_polling, daemon=True)
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
    return FileResponse("static/index2.html")

# 1. API для RAG (Умный ответ)
@app.post("/api/ask")
async def ask(req: SearchRequest):
    # Ищем в базе (там теперь и описания из Каталогов, и полные тексты из OCR)
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
    if not req.field: return {"error": "Field required"}
    books = sql_service.search_books(req.field, req.query)
    return {"books": books}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)