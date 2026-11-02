import json
import os

APP_NAME = "SnapOCR"
APP_TITLE = "SnapOCR - 本地离线截图OCR"

HOTKEY = "ctrl+alt+q"  # 全局截图热键，可在下方修改，如 "ctrl+alt+o"
AUTO_COPY = True  # 识别后自动复制到剪贴板
CJK_COMPACT = True  # 智能排版：去除中文字符间的多余空格
HISTORY_LIMIT = 200  # 历史记录保留条数

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
BG_ALPHA = 0.4  # 窗口背景壁纸不透明度（0-1，40 即 40%）

TRANSLATE_HOTKEY = "ctrl+alt+t"  # 截屏翻译全局热键
TRANSLATE_TARGET_DEFAULT = "zh-Hans"  # 默认目标语言
TRANSLATE_LANGS = {  # 显示名 -> Edge 翻译接口语言代码
    "中文（简体）": "zh-Hans",
    "中文（繁体）": "zh-Hant",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
    "Français": "fr",
    "Deutsch": "de",
    "Español": "es",
    "Русский": "ru",
    "Tiếng Việt": "vi",
    "ไทย": "th",
}

# ---- OCR 引擎设置（设置对话框可改，存 settings.json） ----
# 识别语言 -> RapidOCR Rec.lang_type（首次使用非中文语言时会自动下载对应模型）
OCR_LANGS = {
    "简体中文": "ch",
    "繁体中文": "chinese_cht",
    "English": "en",
    "日本語": "japan",
    "한국어": "korean",
}
OCR_LANG = "ch"  # 识别语言（Rec 模型）
OCR_USE_CLS = False  # 角度分类：识别旋转/倒置文本时开启（每行多一次推理）
OCR_ENHANCE = True  # 图像增强：深色背景自动反色 + 低对比度 CLAHE 增强
OCR_MERGE_PARA = False  # 段落合并：把相邻文本行合并为自然段（Umi-OCR 段落还原）
OCR_QR = True  # 兜底二维码识别：未识别到文字时尝试解码二维码
OCR_GPU = True  # GPU 加速：自动检测 CUDA / DirectML，无 GPU 时回退 CPU
OCR_FILTER_KW = False  # 过滤水印/关键词（Umi-OCR 忽略区域的简化版：按文本内容过滤）
OCR_FILTER_KEYWORDS = ""  # 过滤关键词，逗号分隔，命中行不进入结果
OCR_TABLE = True  # 表格识别：框选表格区域，识别并导出 Excel（PaddleOCR 表格场景）
OCR_PDF = True  # PDF 整档识别：拖入/选择 PDF 逐页渲染识别（Umi-OCR / OCRmyPDF）
OCR_PIN = True  # 截图贴图：截图后钉在桌面置顶显示（Umi-OCR 贴图功能）

# ---- 用户设置持久化（目前仅自定义快捷键） ----
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_settings(data: dict) -> None:
    """合并写入用户设置。"""
    merged = {**_load_settings(), **data}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)


# ---- 长截图 ----
HOTKEY_LONG = "ctrl+alt+l"  # 长截图全局热键
LONGSHOT_SCROLL_TICKS = 3  # 每次注入的滚轮格数（一格约滚 3 行）
LONGSHOT_DELAY = 0.5  # 每次滚动后的等待秒数（等页面渲染稳定）
LONGSHOT_MAX_FRAMES = 200  # 最多采集帧数上限
LONGSHOT_MAX_HEIGHT = 30000  # 拼接结果最大高度（像素）

# 用户自定义快捷键（settings.json）覆盖上方默认值；必须放在所有热键定义之后
_settings = _load_settings()
HOTKEY = _settings.get("hotkey_capture", HOTKEY)
TRANSLATE_HOTKEY = _settings.get("hotkey_translate", TRANSLATE_HOTKEY)
HOTKEY_LONG = _settings.get("hotkey_long", HOTKEY_LONG)

# OCR 设置同样支持 settings.json 持久化
OCR_LANG = _settings.get("ocr_lang", OCR_LANG)
if OCR_LANG not in OCR_LANGS.values():
    OCR_LANG = "ch"
OCR_USE_CLS = bool(_settings.get("ocr_use_cls", OCR_USE_CLS))
OCR_ENHANCE = bool(_settings.get("ocr_enhance", OCR_ENHANCE))
OCR_MERGE_PARA = bool(_settings.get("ocr_para", OCR_MERGE_PARA))
OCR_QR = bool(_settings.get("ocr_qr", OCR_QR))
OCR_GPU = bool(_settings.get("ocr_gpu", OCR_GPU))
OCR_FILTER_KW = bool(_settings.get("ocr_filter_kw", OCR_FILTER_KW))
OCR_FILTER_KEYWORDS = str(_settings.get("ocr_filter_keywords", OCR_FILTER_KEYWORDS))
OCR_TABLE = bool(_settings.get("ocr_table", OCR_TABLE))
OCR_PDF = bool(_settings.get("ocr_pdf", OCR_PDF))
OCR_PIN = bool(_settings.get("ocr_pin", OCR_PIN))

# ---- PDF 识别 ----
PDF_RENDER_SCALE = 2.0  # PDF 页面渲染倍率（1.0=72dpi，2.0≈144dpi，越高越清晰越慢）
