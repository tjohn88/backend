# =============================================================================
# Файл: app/core/config.py
# Назначение: Загрузка конфигурации из .env файла.
# Этот файл использует библиотеку pydantic-settings для удобной загрузки
# настроек из файла .env. Это позволяет хранить "секреты" (ключи, пароли)
# отдельно от кода.
# =============================================================================
import os
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # --- Общие настройки приложения ---
    PROJECT_NAME: str = Field(default="AI-Консультант", env="PROJECT_NAME")
    VERSION: str = Field(default="1.0.0", env="VERSION")
    API_V1_STR: str = Field(default="/api/v1", env="API_V1_STR")
    DEBUG: bool = Field(default=True, env="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # --- Переключатель моделей ---
    LLM_PROVIDER: str = Field(default="local", env="LLM_PROVIDER")

    # --- Настройки для локальной модели ---
    LLM_BASE_URL: str = Field(default="http://localhost:8080", env="LLM_BASE_URL")
    LLM_MODEL_NAME: str = Field(default="chatgpt-oss-20b", env="LLM_MODEL_NAME")
    LLM_MODEL_PATH: str = Field(default="./models/chatgpt-oss-20b-F16.gguf", env="LLM_MODEL_PATH")
    
    # --- Ключи для API ---
    OPENROUTER_API_KEY: str = Field(default="", env="OPENROUTER_API_KEY")
    AGENTROUTER_API_KEY: str = Field(default="", env="AGENTROUTER_API_KEY")

    # --- Настройки для GigaChat ---
    GIGACHAT_ACCESS_TOKEN: str = Field(default="", env="GIGACHAT_ACCESS_TOKEN")
    GIGACHAT_AUTH_DATA: str = Field(default="", env="GIGACHAT_AUTH_DATA")

# === 🆕 ДОБАВЛЯЕМ ЭТО ДЛЯ БИБЛИОТЕКИ ===
    
    # Настройки Telegram
    TELEGRAM_TOKEN: str = Field(default="", env="TELEGRAM_TOKEN")

    # Настройки PostgreSQL (для поиска книг)
    DB_HOST: str = Field(default="localhost", env="DB_HOST")
    DB_NAME: str = Field(default="books-db", env="DB_NAME")
    DB_USER: str = Field(default="postgres", env="DB_USER")
    DB_PASS: str = Field(default="1", env="DB_PASS")
    
# === ПУТИ (ВСЁ ВНУТРИ UPLOADS) ===
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    EMBEDDING_MODEL_PATH: str = os.path.join(BASE_DIR, "intfloat", "models--intfloat--multilingual-e5-large-instruct/snapshots/84344a23ee1820ac951bc365f1e91d094a911763")
    
    # Корневая папка загрузок
    UPLOAD_ROOT: str = os.path.join(BASE_DIR, "uploads")

    # Подпапки
    CATALOG_DIR: str = os.path.join(UPLOAD_ROOT, "input_catalogs")  # Шаг 1: Сюда Rusmark
    BOOKS_DIR: str = os.path.join(UPLOAD_ROOT, "input_books")        # Шаг 2: Сюда PDF
    TEMP_TXT_DIR: str = os.path.join(UPLOAD_ROOT, "temp_dirty")      # Промежуточные
    CLEAN_TXT_DIR: str = os.path.join(UPLOAD_ROOT, "clean_texts")    # Итог OCR
    
    CHROMA_PATH: str = os.path.join(BASE_DIR, "chromadb_store")
    
    # === Настройки OCR движка ===
    OCR_ENGINE_DIR: str = os.path.join(BASE_DIR, "ocr_engine")
    
    # Пути к exe
    PDFTOTEXT_PATH: str = os.path.join(OCR_ENGINE_DIR, "Library", "bin", "pdftotext.exe")
    
    # Модель для очистки текста (в папке models)
    MODELS_DIR: str = os.path.join(BASE_DIR, "models")
    MODEL_NAME: str = "YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf"
    MODEL_PATH: str = os.path.join(MODELS_DIR, MODEL_NAME)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore" # Игнорировать лишние переменные
        
# Глобальный экземпляр настроек для всего приложения
settings = Settings()

# Автоматическое создание структуры папок
folders = [
    settings.UPLOAD_ROOT,
    settings.CATALOG_DIR,
    settings.BOOKS_DIR,
    settings.TEMP_TXT_DIR,
    settings.CLEAN_TXT_DIR,
    settings.CHROMA_PATH
]
# Создаем папки автоматом
for p in folders:
    os.makedirs(p, exist_ok=True)
    
def get_settings() -> Settings:
    """
    Функция-зависимость для FastAPI. Она позволяет получать доступ
    к настройкам в любом месте, где это нужно (например, в эндпоинтах).
    """
    return settings