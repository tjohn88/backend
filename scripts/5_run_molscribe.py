import os
import sys
import json
import torch

# Добавляем путь к склонированному репозиторию MolScribe, чтобы импорты работали
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'MolScribe')))

try:
    from molscribe import MolScribe
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Возможно, не все зависимости из requirements.txt установлены.")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Настройки
RESULTS_DIR = "outputs/chem_results/json" # Папка с JSON от DeepSeek
WEIGHTS_DIR = "MolScribe/weights"

def find_weights():
    if not os.path.exists(WEIGHTS_DIR):
        os.makedirs(WEIGHTS_DIR, exist_ok=True)
        return None
    for f in os.listdir(WEIGHTS_DIR):
        if f.endswith(".pth") or f.endswith(".ckpt"):
            return os.path.join(WEIGHTS_DIR, f)
    return None

MOLSCRIBE_WEIGHTS = find_weights()

def process_chemistry():
    print("--- [ШАГ 2] Запуск химического распознавания (MolScribe) ---")
    
    if not MOLSCRIBE_WEIGHTS:
        print(f"❌ Файл весов (.pth или .ckpt) не найден в папе {WEIGHTS_DIR}")
        print("Пожалуйста, скачайте swin_base_char_aux_1m680k.pth с HuggingFace и положите его туда.")
        return

    print(f"🔎 Используются веса: {MOLSCRIBE_WEIGHTS}")

    # 1. Инициализация (в molenv это будет Torch 1.13)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Используем устройство: {device}")
    
    try:
        model = MolScribe(MOLSCRIBE_WEIGHTS, device=device)
    except Exception as e:
        print(f"❌ Ошибка инициализации MolScribe: {e}")
        return

    # 2. Ищем JSON файлы, созданные DeepSeek на первом шаге
    json_files = [f for f in os.listdir(RESULTS_DIR) if f.endswith(".json")]
    
    if not json_files:
        print(f"⚠️ Нет JSON файлов в {RESULTS_DIR}. Сначала запустите Шаг 1 в основной среде!")
        return

    for json_file in json_files:
        path = os.path.join(RESULTS_DIR, json_file)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"Обработка результатов для: {json_file}")
        
        updated = False
        for page in data:
            for struct in page.get('structures', []):
                # Пробуем оба варианта ключа: 'path' и 'image_path'
                img_p = struct.get('path') or struct.get('image_path')
                
                if img_p and os.path.exists(img_p):
                    try:
                        print(f"  Распознаю: {img_p}")
                        output = model.predict_image_file(img_p)
                        if output and 'smiles' in output:
                            struct['smiles'] = output['smiles']
                            updated = True
                    except Exception as e:
                        print(f"  ⚠️ Ошибка на {img_p}: {e}")
        
        if updated:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"✅ Файл обновлен: {path}")

if __name__ == "__main__":
    process_chemistry()
