import sys
import os
import json
import re
import psycopg2
import logging
from typing import List, Dict

# Добавляем путь к корню
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.config import settings
from app.services.rag_system import RAGSystem

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. ЛОГИКА ПАРСИНГА
# ==============================================================================

FIELDS = {
    '200': 'title',
    '700': 'author',
    '606': 'subject',
    '964': 'grnti',
    '621': 'bbk',
    '902': 'owners',
    '908': 'author_sign',
    '906': 'systematic_code',
    '955': 'pdf_url'
}

def clean_subfields(tag, value):
    if tag == '700':
        subfields = dict(re.findall(r'\^([A-Z])([^^]+)', value))
        last_name = subfields.get('A', '').strip()
        initials = subfields.get('B', '').strip()
        full_name = subfields.get('G', '').strip()
        desc = subfields.get('C', '').strip()
        result = last_name
        if initials: result += f" {initials}"
        if full_name: result += f" ({full_name})"
        if desc: result += f", {desc}"
        return result.strip(', ')
    elif tag == '955':
        match = re.search(r'\^A([^\^]+)', value)
        return match.group(1).strip() if match else ''
    elif tag == '902':
        match = re.search(r'\^A([^\^]+)', value)
        return match.group(1).strip() if match else ''
    else:
        parts = re.split(r'\^.', value)
        return ' '.join(part.strip() for part in parts if part).strip()

def parse_marc_record(block):
    record = {}
    fields210 = {}
    lines = [line for line in block.strip().split("\n") if line.strip()]
    fields = {}
    
    for line in lines:
        match = re.match(r"#(\d+):\s*(.*)", line)
        if match:
            tag, value = match.groups()
            tag = tag.strip()
            
            if tag == '210':
                subfields = dict(re.findall(r'\^([A-Z])([^^]+)', value))
                fields210 = subfields
            
            value_clean = clean_subfields(tag, value)
            
            if tag in FIELDS:
                key = FIELDS[tag]
                if key in record:
                    record[key] += "; " + value_clean
                else:
                    record[key] = value_clean
            
            if tag not in fields: fields[tag] = []
            fields[tag].append(value)

    # Логика формирования заголовка
    title_str = None
    
    if '200' in fields:
        for val in fields['200']:
            subfields = dict(re.findall(r'\^([A-Z])([^^]*)', val))
            title = subfields.get('A', '').strip()
            note = subfields.get('E', '').strip()
            author = subfields.get('F', '').strip()
            if title:
                title_str = title
                if note: title_str += f" : {note}"
                if author: title_str += f" / {author}"
                city = fields210.get('A', '').strip() if fields210 else ''
                publ = fields210.get('C', '').strip() if fields210 else ''
                year = fields210.get('D', '').strip() if fields210 else ''
                pub_parts = []
                if city: pub_parts.append(city)
                if publ: pub_parts.append(publ)
                pub_info = ' : '.join(pub_parts)
                if year: pub_info += f", {year}"
                if pub_info: title_str += f". - {pub_info}."
                break
                
    if (not title_str or not title_str.strip()) and '601' in fields:
        for val in fields['601']:
            subfields = dict(re.findall(r'\^([A-Z])([^^]*)', val))
            parts = []
            for code in ['P', 'E', 'D', 'S']:
                if val_part := subfields.get(code, '').strip(): parts.append(val_part)
            title_str = ', '.join(parts)
            if title_str.strip(): break

    if (not title_str or not title_str.strip()) and '461' in fields:
        for val in fields['461']:
            subfields = dict(re.findall(r'\^([A-Za-z])([^^]*)', val))
            parts = []
            for key in ['c', 'e', 'd', 'f', 'g']:
                val_part = subfields.get(key, '').strip() or subfields.get(key.upper(), '').strip()
                if val_part: parts.append(val_part)
            title_str = ', '.join(parts)
            if title_str.strip(): break

    if title_str: record['title'] = title_str
    return record

def process_rusmark_content(content: str) -> List[Dict]:
    blocks = content.strip().split("*****")
    parsed_records = []
    for block in blocks:
        if not block.strip(): continue
        record = parse_marc_record(block)
        if record: parsed_records.append(record)
    return parsed_records

# ==============================================================================
# 2. ЭТАПЫ РАБОТЫ
# ==============================================================================

def step_1_convert_to_json():
    print("\n--- ЭТАП 1: КОНВЕРТАЦИЯ RUSMARK -> JSON ---")
    folder = settings.CATALOG_DIR
    
    # Ищем все .txt файлы, игнорируя регистр
    files = [f for f in os.listdir(folder) if f.lower().endswith(".txt")]
    
    if not files:
        print(f"❌ В папке {folder} нет .txt файлов.")
        return

    for filename in files:
        txt_path = os.path.join(folder, filename)
        
        # === ИСПРАВЛЕНИЕ ===
        # Используем splitext, чтобы корректно отбросить .TXT или .txt
        base_name = os.path.splitext(filename)[0]
        json_filename = f"{base_name}.json"
        json_path = os.path.join(folder, json_filename)
        
        print(f"\n📄 Обработка файла: {filename}")
        try:
            with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            data = process_rusmark_content(content)
            print(f"   ✅ Найдено записей: {len(data)}")
            
            if data:
                print("   🧐 ПРИМЕР ПЕРВОЙ ЗАПИСИ:")
                first = data[0]
                for k, v in first.items():
                    print(f"      - {k}: {v}")
            
            # Сохраняем JSON (теперь в новый файл!)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"   💾 Сохранен JSON: {json_filename}")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
    
    print("\n🏁 Этап 1 завершен. Проверьте .json файлы.")

def step_2_import_to_db_and_rag():
    print("\n--- ЭТАП 2: ЗАГРУЗКА JSON -> POSTGRES & RAG ---")
    folder = settings.CATALOG_DIR
    files = [f for f in os.listdir(folder) if f.lower().endswith(".json")]
    
    if not files:
        print(f"❌ В папке {folder} нет .json файлов.")
        return

    print(f"Найдено файлов для импорта: {len(files)}")
    
    for filename in files:
        print(f"\n📦 Импорт файла: {filename}")
        json_path = os.path.join(folder, filename)
        
        # Имя таблицы = имя файла без расширения
        raw_name = os.path.splitext(filename)[0].lower()
        table_name = re.sub(r'[^a-z0-9_]', '', raw_name)
        
        if not table_name:
            print("   ⚠️ Некорректное имя таблицы, пропускаем.")
            continue
            
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            _import_postgres(data, table_name)
            _import_rag(data, source_name=filename)
            
        except Exception as e:
            print(f"   ❌ Критическая ошибка импорта: {e}")

    print("\n🏁 Этап 2 завершен.")

# === Вспомогательные функции ===

def _import_postgres(data, table_name):
    if not data: return
    try:
        conn = psycopg2.connect(
            dbname=settings.DB_NAME, user=settings.DB_USER,
            password=settings.DB_PASS, host=settings.DB_HOST
        )
        cur = conn.cursor()
        
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                title TEXT, author TEXT, subject TEXT,
                grnti TEXT, bbk TEXT, author_sign TEXT,
                systematic_code TEXT, owners TEXT,
                pdf_url TEXT, pdf_ocr TEXT
            )
        """)
        
        cur.execute(f"TRUNCATE {table_name}")
        
        for item in data:
            cur.execute(f"""
                INSERT INTO {table_name} 
                (title, author, subject, grnti, bbk, author_sign, systematic_code, owners, pdf_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                item.get('title'), item.get('author'), item.get('subject'),
                item.get('grnti'), item.get('bbk'), item.get('author_sign'),
                item.get('systematic_code'), item.get('owners'), item.get('pdf_url')
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        print(f"   🐘 Postgres: Записано {len(data)} строк в таблицу '{table_name}'")
    except Exception as e:
        print(f"   ❌ Ошибка Postgres: {e}")

def _import_rag(data, source_name):
    if not data: return
    try:
        rag = RAGSystem()
        count = 0
        for item in data:
            desc_parts = [f"Книга: {item.get('title', 'Без названия')}"]
            if item.get('author'): desc_parts.append(f"Автор: {item.get('author')}")
            if item.get('subject'): desc_parts.append(f"Рубрика: {item.get('subject')}")
            if item.get('bbk'): desc_parts.append(f"ББК: {item.get('bbk')}")
            
            full_text = "\n".join(desc_parts)
            rag.add_document(text=full_text, source=source_name, title=item.get('title', 'Unknown'))
            count += 1
        print(f"   🧠 RAG: Векторизовано {count} описаний")
    except Exception as e:
        print(f"   ❌ Ошибка RAG: {e}")

def main():
    while True:
        print("\n" + "="*40)
        print("📚 МЕНЕДЖЕР КАТАЛОГОВ (Rusmark -> DB/RAG)")
        print("="*40)
        print("1. 📝 Конвертировать Rusmark (TXT) в JSON (для проверки)")
        print("2. 🚀 Загрузить готовые JSON в Базу Данных и RAG")
        print("3. 🚪 Выход")
        
        choice = input("\nВыберите действие (1-3): ").strip()
        
        if choice == "1":
            step_1_convert_to_json()
        elif choice == "2":
            step_2_import_to_db_and_rag()
        elif choice == "3":
            print("До свидания!")
            break
        else:
            print("Неверный выбор.")

if __name__ == "__main__":
    main()