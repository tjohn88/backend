import os
import re
import json
import torch
import fitz  # PyMuPDF
import sys
import io
from PIL import Image, ImageDraw
from transformers import AutoModel, AutoTokenizer
from tqdm import tqdm

# --- НАСТРОЙКИ ---
BASE_OUT = "outputs/chem_results"
CONFIG = {
    "model_name": "deepseek-ai/DeepSeek-OCR-2",
    "input_dir": "uploads/input_pdfs",
    "json_dir": os.path.join(BASE_OUT, "json"),     # Финальные данные
    "crops_dir": os.path.join(BASE_OUT, "crops"),   # Вырезанные формулы
    "debug_dir": os.path.join(BASE_OUT, "debug"),   # Картинки с рамками
    "temp_dir": os.path.join(BASE_OUT, "temp"),     # Промежуточные страницы
    "dpi": 300,
    "device": "cuda:0"
}

class ChemPipeline:
    def __init__(self):
        print(f"Инициализация DeepSeek-OCR-2 на {CONFIG['device']}...")
        self.tokenizer = AutoTokenizer.from_pretrained(CONFIG["model_name"], trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            CONFIG["model_name"],
            trust_remote_code=True,
            _attn_implementation='eager',
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map=CONFIG["device"]
        ).eval()

        # Создаем все нужные папки
        os.makedirs(CONFIG["input_dir"], exist_ok=True)
        os.makedirs(CONFIG["json_dir"], exist_ok=True)
        os.makedirs(CONFIG["crops_dir"], exist_ok=True)
        os.makedirs(CONFIG["debug_dir"], exist_ok=True)
        os.makedirs(CONFIG["temp_dir"], exist_ok=True)

    def pdf_to_images(self, pdf_path):
        doc = fitz.open(pdf_path)
        images = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(CONFIG["dpi"]/72, CONFIG["dpi"]/72))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        return images

    def detect_formulas(self, image_path):
        """Запускает модель и перехватывает её текстовый вывод."""
        prompt = "<image>\n<|grounding|>Please identify all equations, formulas, images and text blocks with coordinates."
        
        f = io.StringIO()
        with torch.no_grad():
            with sys_stdout_context(f):
                res = self.model.infer(
                    self.tokenizer,
                    prompt=prompt,
                    image_file=image_path,
                    base_size=1024,
                    image_size=768,
                    crop_mode=True,
                    output_path=CONFIG["temp_dir"], # Логи модели во временную папку
                    save_results=True
                )
        
        final_res = res if res else f.getvalue()
        return final_res

    def extract_crops_and_debug(self, image, ocr_result, pdf_name, page_num):
        if not ocr_result: return []
        
        pattern = r'<\|ref\|>(.*?)<\|/ref\|>\s*<\|det\|>\[\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]\]<\|/det\|>'
        matches = re.findall(pattern, ocr_result)
        
        crops = []
        w, h = image.size
        debug_img = image.copy()
        draw = ImageDraw.Draw(debug_img)
        
        for i, (tag, x1, y1, x2, y2) in enumerate(matches):
            box = (
                int(int(x1) * w / 1000),
                int(int(y1) * h / 1000),
                int(int(x2) * w / 1000),
                int(int(y2) * h / 1000)
            )
            
            color = "red" if tag in ["equation", "formula", "image"] else "blue"
            draw.rectangle(box, outline=color, width=3)
            draw.text((box[0], box[1] - 15), f"{tag}_{i}", fill=color)

            if tag in ["equation", "formula", "image", "figure"]:
                area_ratio = (int(x2)-int(x1)) * (int(y2)-int(y1)) / 1000000
                if area_ratio > 0.99:
                    continue

                # Нарезаем с ОЧЕНЬ щедрым отступом (padding = 150)
                pad = 150
                bx = (max(0, box[0]-pad), max(0, box[1]-pad), min(w, box[2]+pad), min(h, box[3]+pad))
                crop = image.crop(bx)
                
                crop_name = f"{pdf_name}_p{page_num}_{tag}_{i}.jpg"
                crop_path = os.path.join(CONFIG["crops_dir"], crop_name)
                crop.save(crop_path)
                crops.append({"path": crop_path, "box": box, "type": tag})
                print(f"  [+] Вырезано ({tag}): {crop_name}")
        
        debug_path = os.path.join(CONFIG["debug_dir"], f"layout_{pdf_name}_p{page_num}.jpg")
        debug_img.save(debug_path)
        return crops

    def process_all(self):
        pdf_files = [f for f in os.listdir(CONFIG["input_dir"]) if f.endswith(".pdf")]
        for pdf_file in pdf_files:
            results = []
            images = self.pdf_to_images(os.path.join(CONFIG["input_dir"], pdf_file))
            
            for page_num, img in enumerate(images):
                print(f"--- Обработка {pdf_file} [Стр {page_num+1}/{len(images)}] ---")
                temp_path = os.path.join(CONFIG["temp_dir"], f"current_p{page_num}.jpg")
                img.save(temp_path)
                
                ocr_output = self.detect_formulas(temp_path)
                crops = self.extract_crops_and_debug(img, ocr_output, pdf_file, page_num)
                
                results.append({
                    "page": page_num,
                    "text_content": ocr_output,
                    "structures": crops
                })
            
            out_file = os.path.join(CONFIG["json_dir"], f"{pdf_file}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"🏁 Готово! JSON: {out_file}")

class sys_stdout_context:
    def __init__(self, new_target):
        self.new_target = new_target
        self.old_target = sys.stdout
    def __enter__(self):
        sys.stdout = self.new_target
    def __exit__(self, type, value, traceback):
        sys.stdout = self.old_target

if __name__ == "__main__":
    pipeline = ChemPipeline()
    pipeline.process_all()
