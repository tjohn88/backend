# =============================================================================
# Файл: app/core/llm_client.py
# Назначение: Универсальный клиент для отправки запросов к разным LLM.
# =============================================================================

import logging
import httpx
import os
from typing import List, Dict, Any, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Универсальный клиент для работы с LLM.
    Поддерживает локальный сервер, OpenRouter и SberChat (GigaChat).
    """
    def __init__(self):
        settings = get_settings()
        self.provider = settings.LLM_PROVIDER
        headers = {}
        self.ssl_verify = True # По умолчанию SSL-проверка включена

        # Конфигурация в зависимости от провайдера
        if self.provider == "openrouter":
            self.base_url = "https://openrouter.ai/api/v1"
            self.model_name = "z-ai/glm-4.5-air:free"
            if not settings.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY не найден в .env файле.")
            headers["Authorization"] = f"Bearer {settings.OPENROUTER_API_KEY}"
            logger.info(f"LLM Клиент настроен для OpenRouter (модель: {self.model_name}).")

        elif self.provider == "local":
            self.base_url = settings.LLM_BASE_URL
            self.model_name = settings.LLM_MODEL_NAME
            logger.info(f"LLM Клиент настроен для локальной модели ({self.model_name}).")

        elif self.provider == "agentrouter":
            self.base_url = "https://agentrouter.org/v1"
            self.model_name = "gpt-5"
            if not settings.AGENTROUTER_API_KEY:
                raise ValueError("AGENTROUTER_API_KEY не найден в .env файле.")
            headers["Authorization"] = f"Bearer {settings.AGENTROUTER_API_KEY}"
            logger.info(f"LLM Клиент настроен для AGENTRouter (модель: {self.model_name}).")

        elif self.provider == "sberchat":
            self.base_url = "https://gigachat.devices.sberbank.ru/api/v1"
            self.model_name = "GigaChat"
            cert_path = './russian_trusted_root_ca.cer'

            if not settings.GIGACHAT_ACCESS_TOKEN:
                raise ValueError("GIGACHAT_ACCESS_TOKEN не найден в .env. Запустите 'python get_sber_token.py'.")
            if not os.path.exists(cert_path):
                raise FileNotFoundError(f"Сертификат для GigaChat не найден: {cert_path}")
            
            headers["Authorization"] = f"Bearer {settings.GIGACHAT_ACCESS_TOKEN}"
            self.ssl_verify = cert_path
            logger.info(f"LLM Клиент настроен для SberChat (GigaChat).")

        else:
            raise ValueError(f"Неизвестный LLM_PROVIDER: '{self.provider}'. Допустимые значения: 'local', 'openrouter', 'sberchat', 'agentrouter'.")

        logger.info(f"Используемый API Key: {settings.AGENTROUTER_API_KEY[:8] if settings.AGENTROUTER_API_KEY else 'N/A'}...")
        
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url, 
            headers=headers, 
            timeout=300.0, 
            verify=self.ssl_verify
        )

    # --- Основной метод для общения с LLM ---
    async def chat_completion(
        self, 
        messages: List[Dict[str, Any]], 
        temperature: float = 0.7, 
        max_tokens: int = 500
    ) -> str:
        """Выполняет запрос к LLM и возвращает текстовый ответ."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Оставляем без стоп-токенов, так как модель начинает с анализа
            # "stop": ["<|end|>", "<think>", "</think>", "analysis:", "thinking:", "<|channel|>analysis"]
        }
        
        try:
            endpoint = "/chat/completions"
            if self.provider == 'local':
                endpoint = "/v1/chat/completions"
            
            response = await self.http_client.post(endpoint, json=payload)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка API запроса к LLM: {e.response.text}")
            return f"Ошибка API: {e.response.text}"
        except Exception as e:
            logger.error(f"Неожиданная ошибка в LLM клиенте: {e}")
            return f"Ошибка клиента: {str(e)}"

    async def close(self):
        """Закрывает HTTP-клиент."""
        await self.http_client.aclose()


# Глобальный экземпляр для FastAPI (чтобы не создавать клиент при каждом запросе)
_llm_client: Optional[LLMClient] = None

async def get_llm_client() -> LLMClient:
    """Зависимость для FastAPI, которая предоставляет LLM клиент."""
    global _llm_client
    # Пересоздаем клиент, если он не совпадает с настройками
    if _llm_client is None or _llm_client.provider != get_settings().LLM_PROVIDER:
        if _llm_client:
            await _llm_client.close()
        _llm_client = LLMClient()
    return _llm_client

async def close_llm_client():
    """Функция для корректного закрытия соединения при остановке сервера."""
    global _llm_client
    if _llm_client:
        await _llm_client.close()
        _llm_client = None