import os
import httpx
import uuid  # <--- ДОБАВЬТЕ ЭТОТ ИМПОРТ
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# --- Инициализация FastAPI ---
app = FastAPI(title="GigaChat Search API")

# --- Модели данных ---
class Query(BaseModel):
    text: str

# --- Настройка статических файлов ---
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Эндпоинты ---
@app.get("/")
async def read_index():
    """Отдает главную HTML страницу."""
    return FileResponse('static/index.html')

@app.post("/ask_gigachat")
async def ask_gigachat(query: Query):
    """
    Принимает текстовый запрос, отправляет его в GigaChat и возвращает ответ.
    """
    api_key = os.getenv("GIGACHAT_ACCESS_TOKEN")
    if not api_key:
        raise HTTPException(status_code=500, detail="GigaChat API ключ не найден. Проверьте файл .env")

    # --- Получение токена доступа ---
    auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    
    # Генерируем уникальный RqUID для каждого запроса
    rq_uid = str(uuid.uuid4())
    
    # Заголовки для запроса токена
    auth_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': rq_uid,  # <--- ИСПОЛЬЗУЕМ СГЕНЕРИРОВАННЫЙ UID
        'Authorization': f'Basic {api_key}'
    }
    
    auth_data = {'scope': 'GIGACHAT_API_PERS'}

    async with httpx.AsyncClient(verify=False) as client:
        try:
            response = await client.post(auth_url, headers=auth_headers, data=auth_data)
            response.raise_for_status()
            access_token = response.json()['access_token']
        except httpx.HTTPStatusError as e:
            # Добавим больше деталей в ошибку для отладки
            error_detail = e.response.json().get('detail', e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=f"Ошибка аутентификации GigaChat: {error_detail}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Не удалось получить токен GigaChat: {str(e)}")

    # --- Отправка запроса к GigaChat (остальной код без изменений) ---
    chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    chat_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    payload = {
        "model": "GigaChat",
        "messages": [{"role": "user", "content": query.text}],
        "temperature": 0.7,
        "max_tokens": 512
    }

    async with httpx.AsyncClient(verify=False) as client:
        try:
            response = await client.post(chat_url, headers=chat_headers, json=payload)
            response.raise_for_status()
            giga_response = response.json()['choices'][0]['message']['content']
            return {"response": giga_response}
        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get('detail', e.response.text)
            raise HTTPException(status_code=e.response.status_code, detail=f"Ошибка API GigaChat: {error_detail}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")
