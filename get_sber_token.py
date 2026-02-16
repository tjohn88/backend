import requests
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

def get_sber_token():
    """
    Получает токен доступа для GigaChat API и выводит его в консоль.
    """
    auth_data = os.getenv("GIGACHAT_AUTH_DATA")
    if not auth_data:
        print("Ошибка: GIGACHAT_AUTH_DATA не найден в .env файле.")
        return

    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': 'a7aa844d-a430-411d-b0f2-2bc4c2bf08d4', # Пример UID, можно сгенерировать свой
        'Authorization': f'Basic {auth_data}'
    }
    payload = {
        'scope': 'GIGACHAT_API_PERS'
    }
    
    # Путь к сертификату
    cert_path = './russian_trusted_root_ca.cer'

    try:
        # Проверяем, существует ли файл сертификата
        if not os.path.exists(cert_path):
            print(f"Ошибка: Файл сертификата не найден по пути: {cert_path}")
            return

        response = requests.post(url, headers=headers, data=payload, verify=cert_path)
        response.raise_for_status() # Проверка на ошибки HTTP

        token_data = response.json()
        access_token = token_data.get("access_token")

        if access_token:
            print("="*50)
            print("Ваш токен для GigaChat (действует около 30 минут):")
            print(access_token)
            print("="*50)
            print("Скопируйте этот токен и вставьте в файл .env в переменную GIGACHAT_ACCESS_TOKEN")
        else:
            print("Не удалось получить токен. Ответ сервера:")
            print(response.json())

    except requests.exceptions.RequestException as e:
        print(f"Произошла ошибка при запросе к API Сбера: {e}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")


if __name__ == "__main__":
    get_sber_token()