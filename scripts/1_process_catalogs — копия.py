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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# === 1. ЛОГИКА ПАРСИНГА (из твоего 1_parse_rusmark.py) ===

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
    """Очистка подполей (сохранена оригинальная логика)"""
    if tag == '700':
        subfields = dict(re.findall(r'\^([A-Z])([^^]+)', value))
        last_name = subfields.get('A', '').strip()
        initials = subfields.get('B', '').strip()
        full_name = subfields.get('G', '').strip()
        desc = subfields.get('C', '').strip()
        result = last_name
        if initials:
            result += f" {initials}"
        if full_name:
            result += f" ({full_name})"
        if desc:
            result += f", {desc}"
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
    """Парсинг блока Rusmark с приоритетами заголовков"""
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
            
            if tag not in fields:
                fields[tag] = []
            fields[tag].append(value)

    # Логика определения Названия (Title)
    title_str = None
    
    # 1. Поле 200
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
                
                # Издательские данные
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
                
    # 2. Поле 601
    if (not title_str or not title_str.strip()) and '601' in fields:
        for val in fields['601']:
            subfields = dict(re.findall(r'\^([A-Z])([^^]*)', val))
            parts = []
            for code in ['P', 'E', 'D', 'S']:
                if val_part := subfields.get(code, '').strip():
                    parts.append(val_part)
            title_str = ', '.join(parts)
            if title_str.strip(): break

    # 3. Поле 461
    if (not title_str or not title_str.strip()) and '461' in fields:
        for val in fields['461']:
            subfields = dict(re.findall(r'\^([A-Za-z])([^^]*)', val))
            parts = []
            for key in ['c', 'e', 'd', 'f', 'g']:
                val_part = subfields.get(key, '').strip() or subfields.get(key.upper(), '').strip()
                if val_part: parts.append(val_part)
            title_str = ', '.join(parts)
            if title_str.strip(): break

    if title_str:
        record['title'] = title_str
        
    return record

def process_rusmark_content(content: str) -> List[Dict]:
    blocks = content.strip().split("*****")
    parsed_records = []
    for block in blocks:
        if not block.strip(): continue
        record = parse_marc_record(block)
        if record: parsed_records.append(record)
    return parsed_records

# === 2. ИМПОРТ В SQL ===

def import_to_postgres(data: List[Dict], table_name="unit"):
    if not data: return
    try:
        conn = psycopg2.connect(
            dbname=settings.DB_NAME, user=settings.DB_USER,
            password=settings.DB_PASS, host=settings.DB_HOST
        )
        cur = conn.cursor()
        
        # Создаем таблицу
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                title TEXT, author TEXT, subject TEXT,
                grnti TEXT, bbk TEXT, author_sign TEXT,
                systematic_code TEXT, owners TEXT, pdf_url TEXT, pdf_ocr TEXT
            )
        """)
        
        # Вставка
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
        logger.info(f"✅ SQL: Добавлено {len(data)} записей в '{table_name}'")
    except Exception as e:
        logger.error(f"❌ SQL Error: {e}")

# === 3. ИНДЕКСАЦИЯ ОПИСАНИЙ ===

def ingest_metadata_rag(data: List[Dict], source_name: str):
    rag = RAGSystem()
    count = 0
    for item in data:
        desc = f"Книга: {item.get('title', '')}\nАвтор: {item.get('author', '')}\n" \
               f"Рубрика: {item.get('subject', '')}\nББК: {item.get('bbk', '')}"
        
        rag.add_document(text=desc, source=source_name, title=item.get('title', 'Unknown'))
        count += 1
    logger.info(f"✅ RAG: Проиндексировано {count} описаний")

def main():
    print("🚀 ШАГ 1: Обработка каталогов")
    input_folder = settings.CATALOG_DIR
    
    if not os.path.exists(input_folder):
        print(f"❌ Папка не найдена: {input_folder}")
        return

    files = [f for f in os.listdir(input_folder) if f.lower().endswith(".txt")]
    if not files:
        print(f"⚠️ Нет .txt файлов в {input_folder}")
        return

    for filename in files:
        fpath = os.path.join(input_folder, filename)
        print(f"\n📄 Файл: {filename}")
        
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            # 1. Парсинг
            parsed_data = process_rusmark_content(content)
            print(f"   ↳ Найдено записей: {len(parsed_data)}")
            
            # 2. JSON бэкап
            with open(fpath.replace(".txt", ".json"), "w", encoding="utf-8") as f:
                json.dump(parsed_data, f, ensure_ascii=False, indent=2)

            # 3. SQL
            table_name = re.sub(r'[^a-z0-9_]', '', os.path.splitext(filename)[0].lower())
            if not table_name: table_name = "unit"
            import_to_postgres(parsed_data, table_name)
            
            # 4. RAG
            ingest_metadata_rag(parsed_data, filename)
            
        except Exception as e:
            logger.error(f"❌ Ошибка {filename}: {e}")

if __name__ == "__main__":
    main()