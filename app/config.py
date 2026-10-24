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
