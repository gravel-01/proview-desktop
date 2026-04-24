import json
import os
from pathlib import Path
import requests
import base64
import sys
import cv2
import numpy as np
from PIL import Image
from dotenv import dotenv_values
from runtime_paths import get_app_data_path, get_env_file_path
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORT_AVAILABLE = True
except ImportError:
    HEIF_SUPPORT_AVAILABLE = False
IMAGE_FILE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".heif"}
ENV_PATH = get_env_file_path()
PROCESSED_DIR = str(get_app_data_path("processed_images", is_dir=True))  # 预处理后的中间图片保存目录
OUTPUT_DIR = str(get_app_data_path("ocr_outputs", is_dir=True)) # 识别结果 MD 文档保存目录


def _safe_log(message: object) -> None:
    """Write logs without crashing on legacy Windows encodings such as GBK."""
    text = str(message)
    try:
        print(text)
        return
    except UnicodeEncodeError:
        pass

    stream = getattr(sys, "stdout", None)
    if stream is None:
        return

    encoding = getattr(stream, "encoding", None) or "utf-8"
    payload = (text + "\n").encode(encoding, errors="backslashreplace")

    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(payload)
        stream.flush()
        return

    stream.write(payload.decode(encoding, errors="replace"))
    stream.flush()


def get_ocr_runtime_settings() -> tuple[str, str]:
    """Read OCR settings from backend/.env first, then fall back to process env."""
    file_env = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    api_url = str(file_env.get("PADDLEOCR_API_URL") or os.getenv("PADDLEOCR_API_URL") or "").strip()
    api_token = str(file_env.get("PADDLE_OCR_TOKEN") or os.getenv("PADDLE_OCR_TOKEN") or "").strip()
    return api_url, api_token

# ==========================================
# 图像预处理模块 (提取自 1.5VL_demo.py)
# ==========================================
def resample_image_by_dpi(image_path, target_dpi=150, default_original_dpi=72):
    """真正的 DPI 转换器：物理缩放像素矩阵"""
    with Image.open(image_path) as img:
        orig_dpi_tuple = img.info.get('dpi')
        original_dpi = orig_dpi_tuple[0] if orig_dpi_tuple else default_original_dpi
            
        scale_factor = target_dpi / original_dpi
        if scale_factor == 1.0:
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
        new_width = int(img.width * scale_factor)
        new_height = int(img.height * scale_factor)
        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        return cv2.cvtColor(np.array(resized_img), cv2.COLOR_RGB2BGR)

def resize_image_for_paddle(image, max_side_len=1920):
    """限制图像的最大边长"""
    h, w = image.shape[:2]
    if max(h, w) > max_side_len:
        if h > w:
            new_h = max_side_len
            new_w = int(w * (max_side_len / h))
        else:
            new_w = max_side_len
            new_h = int(h * (max_side_len / w))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return image

def deskew_image(image):
    """轻量级倾斜校正"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10)
    
    if lines is not None:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -45 < angle < 45:
                angles.append(angle)
        if angles:
            median_angle = np.median(angles)
            if abs(median_angle) > 0.5: 
                h, w = image.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                return cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return image

def enhance_contrast_clahe(image):
    """CLAHE 增强局部对比度"""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    limg = cv2.merge((cl, a, b))
    return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

def remove_moire_pattern(image):
    """去除摩尔纹 (用于屏幕翻拍)"""
    return cv2.GaussianBlur(image, (3, 3), 0)

def preprocess_image_pipeline(input_path, target_dpi=100, is_screen_capture=False):
    """完整的预处理流水线"""
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    base_name = os.path.basename(input_path)
    output_path = os.path.join(PROCESSED_DIR, f"preprocessed_{base_name}")
    
    image = resample_image_by_dpi(input_path, target_dpi=target_dpi)
    image = resize_image_for_paddle(image, max_side_len=1920)
    image = deskew_image(image)
    if is_screen_capture:
        image = remove_moire_pattern(image)
    image = enhance_contrast_clahe(image)

    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(image_rgb)
    pil_img.save(output_path, dpi=(target_dpi, target_dpi))
    
    return output_path

def normalize_ocr_input_file(file_path):
    """Convert HEIC/HEIF uploads into PNG before sending them to OCR."""
    ext = os.path.splitext(file_path)[-1].lower()
    if ext not in {".heic", ".heif"}:
        return file_path

    if not HEIF_SUPPORT_AVAILABLE:
        raise RuntimeError("HEIC/HEIF files require the pillow-heif dependency.")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    converted_path = os.path.join(PROCESSED_DIR, f"{base_name}_heif_converted.png")

    with Image.open(file_path) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(converted_path, format="PNG")

    return converted_path

def get_file_type(file_path):
    ext = os.path.splitext(file_path)[-1].lower()
    if ext == ".pdf": return 0
    elif ext in IMAGE_FILE_EXTENSIONS: return 1
    else: raise ValueError(f"不支持的文件格式: {ext}")

# ==========================================
# 工具主执行函数
# ==========================================
def perform_ocr(image_path: str, use_preprocessing: bool = True, is_screen_capture: bool = False) -> str:
    """执行 OCR 并返回解析出的 Markdown 文本"""
    
    if not os.path.exists(image_path):
        return f"错误: 找不到文件 '{image_path}'，请检查路径是否正确。"

    # 1. 从 backend/.env 读取 OCR 配置，避免依赖启动目录
    api_url, api_token = get_ocr_runtime_settings()
    if not api_url:
        return f"错误: OCR API 地址未配置，请在 {ENV_PATH} 中设置 PADDLEOCR_API_URL。"
    if not api_token:
        return f"错误: OCR API 令牌未配置，请在 {ENV_PATH} 中设置 PADDLE_OCR_TOKEN。"
    # 2. 判断格式与预处理
    normalized_path = normalize_ocr_input_file(image_path)
    file_type = get_file_type(normalized_path)
    api_target_file = normalized_path
    
    try:
        if file_type == 1 and use_preprocessing:
            api_target_file = preprocess_image_pipeline(normalized_path, target_dpi=100, is_screen_capture=is_screen_capture)
            
        # 3. 读取文件并 Base64 编码
        with open(api_target_file, "rb") as file:
            file_data = base64.b64encode(file.read()).decode("ascii")

        # 4. 组装请求
        headers = {
            "Authorization": f"token {api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "file": file_data,
            "fileType": file_type, 
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        # 5. 调用云端 API
        _safe_log(f"[OCR] 调用 OCR API: {api_url}")
        _safe_log(f"[OCR] API Token (前20字符): {api_token[:20] if api_token else 'None'}...")
        _safe_log(f"[OCR] 文件类型: {file_type}")
        _safe_log(f"[OCR] Base64 长度: {len(file_data)}")

        response = requests.post(api_url, json=payload, headers=headers, timeout=60)
        _safe_log(f"[OCR] 响应状态码: {response.status_code}")

        if response.status_code != 200:
            _safe_log(f"[OCR][ERROR] 响应内容: {response.text[:500]}")

        response.raise_for_status()
        result_data = response.json()

        # 6. 提取 Markdown 结果和图片
        markdown_texts = []
        extracted_images = {}  # filename -> base64 data
        if "result" in result_data and "layoutParsingResults" in result_data["result"]:
            for res in result_data["result"]["layoutParsingResults"]:
                md_data = res.get("markdown", {})
                md_text = md_data.get("text", "")
                if md_text:
                    markdown_texts.append(md_text)
                # 提取图片 base64 数据
                images = md_data.get("images", {})
                if isinstance(images, dict):
                    extracted_images.update(images)
                    
        if not markdown_texts:
            return "解析成功，但未能从图片中提取到任何有效文本或 Markdown 内容。"
            
        final_md = "\n\n---\n\n".join(markdown_texts)
        
        # 7. 保存解析出的 Markdown 文档和图片到本地
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        save_path = os.path.join(OUTPUT_DIR, f"{base_name}_ocr_result.md")

        # 保存图片文件（根据官方 demo：图片是 URL，需要下载）
        imgs_dir = os.path.join(OUTPUT_DIR, "imgs")
        os.makedirs(imgs_dir, exist_ok=True)
        saved_images = {}
        for img_name, img_url in extracted_images.items():
            try:
                img_save_path = os.path.join(imgs_dir, os.path.basename(img_name))
                # PaddleOCR 返回的是临时 URL，需要下载
                if isinstance(img_url, str) and (img_url.startswith("http://") or img_url.startswith("https://")):
                    img_response = requests.get(img_url, timeout=15)
                    if img_response.status_code == 200:
                        with open(img_save_path, "wb") as img_f:
                            img_f.write(img_response.content)
                        saved_images[img_name] = img_save_path
                else:
                    # 兼容 base64 格式（如果有的话）
                    with open(img_save_path, "wb") as img_f:
                        img_f.write(base64.b64decode(img_url))
                    saved_images[img_name] = img_save_path
            except Exception as e:
                _safe_log(f"[OCR][WARN] 图片保存失败 {img_name}: {e}")

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(final_md)
            
        return f"【解析成功】Markdown 文档已自动保存至本地: {save_path}\n\n以下是提取的内容:\n\n{final_md}"

    except requests.exceptions.Timeout:
        return "错误: OCR API 请求超时（60秒），请检查网络连接或稍后重试"
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else "未知"
        error_text = e.response.text[:500] if e.response else str(e)
        return f"错误: OCR API 返回 HTTP {status_code} 错误\n详情: {error_text}"
    except requests.exceptions.ConnectionError:
        return f"错误: 无法连接到 OCR API ({api_url})，请检查网络连接"
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        _safe_log(f"[OCR][ERROR] OCR 详细错误:\n{error_detail}")
        return f"错误: OCR 执行失败 - {str(e)}"


def perform_ocr_full(image_path: str, use_preprocessing: bool = True, is_screen_capture: bool = False) -> dict:
    """执行 OCR 并返回完整结果（文本 + 图片 base64）"""
    text_result = perform_ocr(image_path, use_preprocessing, is_screen_capture)

    # 读取保存的图片，转为 base64 供前端使用
    imgs_dir = os.path.join(OUTPUT_DIR, "imgs")
    images_b64 = {}
    if os.path.isdir(imgs_dir):
        for fname in os.listdir(imgs_dir):
            fpath = os.path.join(imgs_dir, fname)
            try:
                with open(fpath, "rb") as f:
                    ext = os.path.splitext(fname)[1].lower().lstrip('.')
                    mime = f"image/{ext}" if ext in ('png', 'jpg', 'jpeg', 'webp') else "image/jpeg"
                    images_b64[fname] = f"data:{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"
            except Exception:
                pass

    return {
        "text": text_result,
        "images": images_b64
    }

# ==========================================
# 工具注册配置
# ==========================================
OCR_TOOL = {
    "name_for_human": "文档和图片OCR解析",
    "name_for_model": "perform_ocr",
    "description_for_model": "光学字符识别(OCR)工具，可以提取图片或PDF中的文字、表格、排版布局信息，并转换为结构化的Markdown格式文本返回。适用于需要大模型理解本地文档内容的场景。",
    "parameters": [
        {
            "name": "image_path",
            "description": "需要识别的本地图片或 PDF 文件的完整路径",
            "required": True,
            "schema": {"type": "string"},
        },
        {
            "name": "use_preprocessing",
            "description": "是否对图片进行预处理增强（倾斜校正、增强等），提升识别准确率，默认True",
            "required": False,
            "schema": {"type": "boolean"},
        },
        {
            "name": "is_screen_capture",
            "description": "原图是否为屏幕翻拍照片（开启后会特殊去除摩尔纹），默认False",
            "required": False,
            "schema": {"type": "boolean"},
        }
    ],
}

if __name__ == "__main__":
    # 本地测试示例
    test_image_path = r".\sample.pdf"  # 替换为你的测试文件路径
    result = perform_ocr(test_image_path, use_preprocessing=True, is_screen_capture=False)
    print(result)
