import telebot
import asyncio
import logging
import re
import time
import threading
import requests
import io
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pypdf
except ImportError:
    pypdf = None

from telebot import types
from app.core.config import settings
from app.core.llm_client import LLMClient
from app.services.rag_system import RAGSystem
from app.services.sql_service import sql_service

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация
print("--- [DEBUG] Инициализация бота... ---")
bot = telebot.TeleBot(settings.TELEGRAM_TOKEN)
print(f"--- [DEBUG] Бот инициализирован с токеном: {settings.TELEGRAM_TOKEN[:5]}... ---")
rag_system = RAGSystem()

# === Хранение состояний (State Machine на минималках) ===
# user_state[chat_id] = {
#    "mode": "sql" | "rag" | None,
#    "table": "bookss",  # Текущая выбранная таблица
#    "search_field": "author" # Поле для SQL поиска
# }
user_context = {}

def get_user_context(chat_id):
    if chat_id not in user_context:
        # Пытаемся найти первую доступную таблицу
        tables = sql_service.get_available_tables()
        default_table = "bookss" if "bookss" in tables else (tables[0] if tables else "unit")
        
        user_context[chat_id] = {
            "mode": None,
            "table": default_table,
            "search_field": None
        }
    return user_context[chat_id]

def clean_llm_response(text: str) -> str:
    """
    Очистка ответа. Ищет список книг и удаляет все перед ним.
    """
    # 1. Сначала применяем базовую чистку
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<\|.*?\|>", "", text, flags=re.DOTALL)
    
    # 2. Ищем начало списка (1. Автор или 1. Книга)
    match_list = re.search(r'\n1\.\s+Автор:', text)
    if not match_list:
        match_list = re.search(r'\n1\.\s+Книга:', text)
        
    if match_list:
        # Нашли начало списка! Отрезаем всё до него
        list_start = match_list.start()
        header_match = re.search(r'Найдено книг:\s*(\d+)', text[:list_start])
        
        count = "несколько"
        if header_match:
            count = header_match.group(1)
            
        clean_text = f"📚 Найдено книг: {count}\n{text[list_start:]}"
        return clean_text.strip()

    # 3. Ищем "Краткое содержание" (для анализа PDF) - ТОЛЬКО ПО-РУССКИ
    match_summary = re.search(r'(Краткое содержание|Резюме):', text, re.IGNORECASE)
    if match_summary:
        return text[match_summary.start():].strip()

    # 4. Если списка нет, пробуем найти просто русский текст (старый метод)
    text = re.sub(r"^(analysis|thinking|reasoning).*?(?=[А-ЯЁ📚])", "", text, flags=re.DOTALL | re.IGNORECASE)
    
    # Пытаемся найти разделитель "final" или "assistant", если он остался текстом
    if "final" in text.lower():
        parts = text.lower().rpartition("final") # ищем с конца
        if parts[2].strip():
            # Восстанавливаем регистр из оригинала (сложно, берем срез по индексу)
            idx = text.lower().rfind("final")
            potential_answer = text[idx+5:].strip()
            if len(potential_answer) > 20:
                text = potential_answer
                
    elif "assistant" in text.lower():
         parts = text.split("assistant")
         # Берем последнюю часть
         if len(parts) > 1:
             text = parts[-1].strip()


    # Удаляем префиксы
    lines = text.split('\n')
    cleaned_lines = []
    prefix_pattern = r'^(final|answer|response|output|result|reply)[\s:]*'
    
    for line in lines:
        if re.match(prefix_pattern, line.strip(), re.IGNORECASE):
            cleaned_line = re.sub(prefix_pattern, '', line.strip(), flags=re.IGNORECASE)
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines.append(line)
            
    text = '\n'.join(cleaned_lines)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    
    # Финальная проверка на русский
    text = text.strip()
    if text and len(text) > 50:
        match = re.search(r'[А-ЯЁ📚]', text)
        if match:
            text = text[match.start():]
            
    return text.strip()
# ==============================================================================
# КЛАВИАТУРЫ
# ==============================================================================

def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🧠 Задать умный вопрос (RAG)", "🔎 Точный поиск по БД")
    markup.add("🗄️ Выбрать Каталог", "🗑 Сброс")
    return markup

def get_database_selection_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    tables = sql_service.get_available_tables()
    buttons = []
    for table in tables:
        btn_text = f"📚 {table}"
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"set_db:{table}"))
    markup.add(*buttons)
    return markup

def get_search_field_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👤 Автор", callback_data="search:author"),
        types.InlineKeyboardButton("📖 Название", callback_data="search:title"),
        types.InlineKeyboardButton("🏷 Рубрика", callback_data="search:subject"),
        types.InlineKeyboardButton("🔢 ББК", callback_data="search:bbk"),
        types.InlineKeyboardButton("🧬 ГРНТИ", callback_data="search:grnti")
    )
    return markup

# ==============================================================================
# ХЕНДЛЕРЫ
# ==============================================================================

@bot.message_handler(commands=['start'])
def start(message):
    print(f"--- [DEBUG] Получена команда /start от {message.from_user.username} ---")
    ctx = get_user_context(message.chat.id)
    bot.send_message(
        message.chat.id, 
        f"👋 Привет! Я ИИ-библиотекарь.\n"
        f"📂 Текущий каталог: *{ctx['table']}*\n\n"
        f"Выберите режим работы:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "🗑 Сброс")
def menu_reset(message):
    chat_id = message.chat.id
    if chat_id in user_context:
        # Сбрасываем только режим, оставляем выбранную таблицу
        user_context[chat_id]["mode"] = None
        user_context[chat_id]["search_field"] = None
    
    bot.send_message(chat_id, "✅ Состояние сброшено.", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text == "🗄️ Выбрать Каталог")
def menu_select_db(message):
    bot.send_message(message.chat.id, "Выберите каталог:", reply_markup=get_database_selection_menu())

@bot.message_handler(func=lambda m: m.text == "🧠 Задать умный вопрос (RAG)")
def menu_rag_mode(message):
    ctx = get_user_context(message.chat.id)
    ctx["mode"] = "rag"
    bot.send_message(
        message.chat.id, 
        "🧠 *Режим ИИ активирован.*\n"
        "Напишите свой вопрос в свободной форме. Я поищу информацию в текстах книг и попробую ответить.\n"
        "Пример: _О чем книга про кочевников Евразии?_", 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == "🔎 Точный поиск по БД")
def menu_sql_mode(message):
    bot.send_message(message.chat.id, "По какому полю искать?", reply_markup=get_search_field_menu())

# ==============================================================================
# CALLBACKS
# ==============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith(('set_db:', 'search:')))
def handle_callbacks(call):
    chat_id = call.message.chat.id
    ctx = get_user_context(chat_id)
    
    if call.data.startswith("set_db:"):
        table = call.data.split(":")[1]
        ctx["table"] = table
        bot.answer_callback_query(call.id, f"Каталог: {table}")
        bot.edit_message_text(f"✅ Выбран каталог: *{table}*", chat_id, call.message.message_id, parse_mode="Markdown")
        
    elif call.data.startswith("search:"):
        field = call.data.split(":")[1]
        ctx["mode"] = "sql"
        ctx["search_field"] = field
        
        ru_field = {"author": "автора", "title": "название", "bbk": "ББК"}.get(field, field)
        
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, f"🔎 Введите {ru_field} для поиска:")

# ==============================================================================
# ОБРАБОТКА ТЕКСТА
# ==============================================================================

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    print(f"--- [DEBUG] Получено сообщение: '{message.text}' от {message.from_user.username} ---")
    chat_id = message.chat.id
    text = message.text.strip()
    ctx = get_user_context(chat_id)
    
    # 1. Если режим не выбран
    if not ctx["mode"]:
        bot.send_message(chat_id, "Выберите режим в меню 👇", reply_markup=get_main_menu())
        return

    # 2. Режим SQL
    if ctx["mode"] == "sql":
        field = ctx["search_field"]
        table = ctx["table"]
        
        bot.send_chat_action(chat_id, "typing")
        results = sql_service.search_books(field, text, table)
        
        if not results:
            bot.send_message(chat_id, f"❌ В каталоге '{table}' ничего не найдено.")
            return
            
        response = [f"📚 Результаты ({len(results)} шт):"]
        keyboard = types.InlineKeyboardMarkup()
        has_buttons = False
        
        for i, book in enumerate(results, 1):
            row = f"{i}. {book['author']} — {book['title']}"
            
            details = []
            if book.get('author_sign'): details.append(f"Авт.знак: {book['author_sign']}")
            if book.get('bbk'): details.append(f"ББК: {book['bbk']}")
            if book.get('grnti'): details.append(f"ГРНТИ: {book['grnti']}")
            if book.get('systematic_code'): details.append(f"Шифр: {book['systematic_code']}")
            
            if details:
                row += "\n   " + " | ".join(details)
                
            if book.get('owners'):
                row += f"\n   Держатель: {book['owners']}"

            if book['pdf_url'] and book['pdf_url'] != 'None': 
                row += f"\n   Ссылка: {book['pdf_url']}"
            
            response.append(row)
            
            # Если есть текст или ссылка на PDF, добавляем кнопку
            has_text = book.get('has_text')
            pdf_url = book.get('pdf_url')
            
            if has_text or (pdf_url and pdf_url != 'None' and pdf_url.startswith('http')):
                btn_text = f"📝 Анализ кн. {i}"
                callback_data = f"anl:{table}:{book['id']}"
                keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
                has_buttons = True
            
        bot.send_message(chat_id, "\n\n".join(response), reply_markup=keyboard if has_buttons else None)
        
        # Сбрасываем поле после поиска
        ctx["mode"] = None 
        bot.send_message(chat_id, "Поиск завершен. Выберите действие.", reply_markup=get_main_menu())
        return

    # 3. Режим RAG (AI)
    if ctx["mode"] == "rag":
        asyncio.run(process_ai_answer(chat_id, text))

def is_garbage_text(text: str) -> bool:
    """Проверяет, похож ли текст на мусор (мало кириллицы)."""
    if not text or len(text) < 50: return True
    cyrillic_count = len(re.findall(r'[а-яА-ЯёЁ]', text))
    # Если кириллицы меньше 5%, считаем что кодировка битая (для русских книг)
    if cyrillic_count / len(text) < 0.05:
        return True
    return False

def download_pdf_text(url: str) -> str:
    """Скачивает PDF и извлекает текст (fitz -> pypdf)."""
    if not fitz and not pypdf:
        raise ImportError("Библиотеки fitz и pypdf не установлены.")
        
    try:
        # Скачиваем файл
        response = requests.get(url, timeout=30, verify=False)
        response.raise_for_status()
        content = response.content
        
        extracted_text = ""
        
        # 1. Пробуем fitz (PyMuPDF)
        if fitz:
            try:
                with fitz.open(stream=content, filetype="pdf") as doc:
                    pages = []
                    for i, page in enumerate(doc):
                        if i >= 40: break
                        blocks = page.get_text("blocks", sort=True)
                        page_text = "\n".join([b[4] for b in blocks])
                        pages.append(page_text)
                    extracted_text = "\n".join(pages)
            except Exception as e:
                logger.error(f"Fitz extract error: {e}")

        # 2. Если fitz не справился (мусор или пусто), пробуем pypdf
        if is_garbage_text(extracted_text) and pypdf:
            logger.info("Fitz returned garbage/empty. Trying pypdf...")
            try:
                reader = pypdf.PdfReader(io.BytesIO(content))
                pages = []
                for i, page in enumerate(reader.pages):
                    if i >= 40: break
                    pages.append(page.extract_text() or "")
                extracted_text = "\n".join(pages)
            except Exception as e:
                logger.error(f"pypdf extract error: {e}")
        
        # 3. Финальная проверка
        if is_garbage_text(extracted_text):
            logger.warning(f"Failed to extract readable text from {url}")
            return "⚠️ Не удалось извлечь читаемый текст из PDF (проблема с кодировкой или защитой)."
            
        logger.info(f"PDF Text Preview (200 chars): {extracted_text[:200]}")
        return extracted_text

    except Exception as e:
        logger.error(f"Error downloading PDF {url}: {e}")
        raise e

@bot.callback_query_handler(func=lambda call: call.data.startswith('anl:'))
def handle_analyze_pdf(call):
    """Анализирует текст выбранной книги с помощью LLM"""
    try:
        _, table, book_id = call.data.split(':')
        chat_id = call.message.chat.id
        
        bot.answer_callback_query(call.id, "Загружаю текст книги...")
        bot.send_chat_action(chat_id, "typing")
        
        # 1. Получаем текст и URL из БД
        text, url = sql_service.get_book_text(int(book_id), table)
        
        # Если текста нет в БД, пробуем скачать PDF
        if not text and url and url.lower().startswith('http'):
            bot.send_message(chat_id, "📥 Текста нет в базе. Скачиваю PDF с сайта (это займет время)...")
            try:
                text = download_pdf_text(url)
            except Exception as e:
                logger.error(f"Download error: {e}")
                bot.send_message(chat_id, f"⚠️ Не удалось скачать PDF: {e}")
                return

        if not text:
            bot.send_message(chat_id, "⚠️ Не удалось получить текст книги для анализа.")
            return
            
        # Ограничиваем длину текста для анализа
        analyze_text = text[:8000] 
        
        bot.send_message(chat_id, f"📝 Анализирую текст (первые {len(analyze_text)} симв.)... Подождите 1-2 минуты.")
        
        # 2. Формируем запрос к LLM
        prompt = f"""Проанализируй следующий текст из книги и составь краткое содержание (summary) на русском языке.

ТВОЯ ЗАДАЧА:
Напиши краткое содержание книги.
НИКАКОГО АНАЛИЗА ПЕРЕД ОТВЕТОМ.

НАЧИНАЙ ОТВЕТ СРАЗУ С ФРАЗЫ: "Краткое содержание:"

Текст:
{analyze_text}"""


        # 3. Отправляем в LLM (в отдельном потоке, чтобы не блокировать бота)
        def run_analysis():
            asyncio.run(process_ai_analysis(chat_id, prompt))
            
        threading.Thread(target=run_analysis).start()
        
    except Exception as e:
        logger.error(f"Error analyzing PDF: {e}")
        bot.send_message(call.message.chat.id, "⚠️ Произошла ошибка при анализе.")

async def process_ai_analysis(chat_id, prompt):
    """Асинхронная отправка запроса на анализ"""
    llm_client = LLMClient()
    try:
        messages = [{"role": "user", "content": prompt}]
        
        answer = await llm_client.chat_completion(
            messages,
            temperature=0.3,
            max_tokens=1000
        )
        
        # Очищаем ответ
        clean_answer = clean_llm_response(answer)
        
        send_long_message(chat_id, f"📋 **Результат анализа:**\n\n{clean_answer}")
        
    except Exception as e:
        logger.error(f"LLM Error during analysis: {e}")
        bot.send_message(chat_id, "⚠️ Ошибка при обращении к нейросети.")
    finally:
        await llm_client.close()



async def process_ai_answer(chat_id, query):
    bot.send_chat_action(chat_id, "typing")
    
    llm_client = LLMClient() 
    
    wait_msg = bot.send_message(chat_id, "🔎 Анализирую запрос и ищу книги... Это может занять 1-2 минуты.")
    
    try:
        # 1. Используем гибкий поиск
        context = rag_system.search_flexible(query, top_k=5)
        
        # Логирование
        logger.info(f"Query: '{query}'")
        logger.info(f"RAG Context length: {len(context)} chars")
        logger.info(f"RAG Context preview: {context[:400]}...")
        
        # 2. Упрощенный промпт для chatgpt-oss модели
        system_prompt = f"""Ты библиотечный помощник. Пользователь задал вопрос о книгах.

НАЙДЕННЫЕ КНИГИ В КАТАЛОГЕ:
{context}

ТВОЯ ЗАДАЧА:
1. Если в списке выше есть книги, связанные с вопросом пользователя - ПЕРЕЧИСЛИ ИХ.
2. Для каждой книги выведи:
   - Сначала строку "Автор: [имя автора]"
   - Затем СКОПИРУЙ строку после "Книга:" ПОЛНОСТЬЮ, БЕЗ ИЗМЕНЕНИЙ
   - Затем строку "Держатель: [название библиотеки/организации]" (если есть в контексте)
3. Формат ответа:

📚 Найдено книг: [число]

1. Автор: [имя автора]
   [ПОЛНАЯ строка из "Книга: ..."]
   Держатель: [название организации]

2. Автор: [имя автора]
   [ПОЛНАЯ строка из "Книга: ..."]
   Держатель: [название организации]

ПРАВИЛА:
- НЕ переформатируй название книги, НЕ меняй порядок слов.
- КОПИРУЙ текст после "Книга:" точно как написано.
- НЕ выводи рубрику.
- Если держатель не указан в контексте - пропусти эту строку.
- Если в списке НЕТ книг по теме - напиши: "В каталоге нет книг по этой теме."
- НЕ добавляй комментариев, объяснений, приветствий.
- Отвечай ТОЛЬКО на русском языке.
- НАЧИНАЙ ОТВЕТ СРАЗУ С ФРАЗЫ: "📚 Найдено книг:"
- НИКАКОГО АНАЛИЗА ИЛИ РАССУЖДЕНИЙ ПЕРЕД ОТВЕТОМ.
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        # 3. Запрос
        raw_answer = await llm_client.chat_completion(
            messages, 
            temperature=0.2,
            max_tokens=1024
        )
        
        # 4. Логирование
        logger.info(f"Raw LLM response (full): {raw_answer}")
        
        # 5. Очистка
        clean_answer = clean_llm_response(raw_answer)
        
        logger.info(f"Clean response (full): {clean_answer}")
        
        # 6. Проверка
        if len(clean_answer) < 30 and "нет информации" not in clean_answer.lower():
            logger.warning("⚠️ Answer too short!")
            if len(context) > 100 and "нет релевантной информации" not in context:
                # Извлекаем библиографические записи напрямую из контекста
                clean_answer = extract_bibliographic_records(context)
        
        # Удаляем сообщение о ожидании
        if wait_msg:
            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass
        
        # Отправляем с разбивкой на части
        send_long_message(chat_id, clean_answer)
        
    except Exception as e:
        logger.error(f"AI Error: {e}", exc_info=True)
        # Если была ошибка, тоже удаляем сообщение ожидания (если оно есть)
        if wait_msg:
            try:
                bot.delete_message(chat_id, wait_msg.message_id)
            except Exception:
                pass
        bot.send_message(chat_id, "⚠️ Произошла ошибка при генерации ответа.")
    finally:
        await llm_client.close()


def send_long_message(chat_id, text):
    """Отправляет длинное сообщение частями (лимит 4096 символов)."""
    if len(text) <= 4000:
        bot.send_message(chat_id, text)
        return

    # Разбиваем на части
    while text:
        if len(text) <= 4000:
            bot.send_message(chat_id, text)
            break
        
        # Ищем ближайший перенос строки до 4000 символов
        split_point = text.rfind('\n', 0, 4000)
        if split_point == -1:
            split_point = 4000
            
        part = text[:split_point]
        bot.send_message(chat_id, part)
        text = text[split_point:].lstrip()
        time.sleep(0.5)

def extract_bibliographic_records(context: str) -> str:
    """
    Извлекает библиографические записи напрямую из контекста (fallback).
    """
    records = []
    
    # Ищем блоки "Полная библиографическая запись:"
    for block in context.split('[Источник:'):
        if 'Полная библиографическая запись:' in block:
            # Извлекаем текст после метки
            parts = block.split('Полная библиографическая запись:')
            if len(parts) > 1:
                record = parts[1].strip().split('\n')[0]  # Берём первую строку
                if record:
                    records.append(record)
    
    if records:
        result = f"📚 Найдено книг: {len(records)}\n\n"
        for i, record in enumerate(records, 1):
            result += f"{i}. {record}\n\n"
        return result
    
    return "В текущих каталогах нет информации по этому запросу."