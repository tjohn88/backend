import re
import json

INPUT_FILE = "csl.TXT"
OUTPUT_FILE = "csl.json"

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

    # --- TITLE LOGIC ---
    title_str = None
    # 1. #200 — если ^A есть
    if '200' in fields:
        for val in fields['200']:
            subfields = dict(re.findall(r'\^([A-Z])([^^]*)', val))
            title = subfields.get('A', '').strip()
            note = subfields.get('E', '').strip()
            author = subfields.get('F', '').strip()
            if title:
                title_str = title
                if note:
                    title_str += f" : {note}"
                if author:
                    title_str += f" / {author}"
                city = fields210.get('A', '').strip() if fields210 else ''
                publ = fields210.get('C', '').strip() if fields210 else ''
                year = fields210.get('D', '').strip() if fields210 else ''
                pub_parts = []
                if city:
                    pub_parts.append(city)
                if publ:
                    pub_parts.append(publ)
                pub_info = ' : '.join(pub_parts)
                if year:
                    pub_info += f", {year}"
                if pub_info:
                    title_str += f". - {pub_info}."
                break
    # 2. Если ^A нет — #601 (^P, ^E, ^D и т.д.)
    if (not title_str or not title_str.strip()) and '601' in fields:
        for val in fields['601']:
            subfields = dict(re.findall(r'\^([A-Z])([^^]*)', val))
            p = subfields.get('P', '').strip()
            e = subfields.get('E', '').strip()
            d = subfields.get('D', '').strip()
            s = subfields.get('S', '').strip()
            parts = [p]
            if e:
                parts.append(e)
            if d:
                parts.append(d)
            if s:
                parts.append(s)
            title_str = ', '.join(filter(None, parts))
            if title_str.strip():
                break
    # 3. Если и там нет — #461 (^c/^C, ^e/^E, ^d/^D, ^f/^F и т.д.)
    if (not title_str or not title_str.strip()) and '461' in fields:
        for val in fields['461']:
            subfields = dict(re.findall(r'\^([A-Za-z])([^^]*)', val))
            c = subfields.get('c', '').strip() or subfields.get('C', '').strip()
            e = subfields.get('e', '').strip() or subfields.get('E', '').strip()
            d = subfields.get('d', '').strip() or subfields.get('D', '').strip()
            f = subfields.get('f', '').strip() or subfields.get('F', '').strip()
            g = subfields.get('g', '').strip() or subfields.get('G', '').strip()
            parts = [c]
            if e:
                parts.append(e)
            if d:
                parts.append(d)
            if f:
                parts.append(f)
            if g:
                parts.append(g)
            title_str = ', '.join(filter(None, parts))
            if title_str.strip():
                break

    if title_str:
        record['title'] = title_str
    return record

def main():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = content.strip().split("*****")
    parsed = []
    for block in blocks:
        record = parse_marc_record(block)
        if record:
            parsed.append(record)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    print(f"✅ Готово! Записей: {len(parsed)} → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
