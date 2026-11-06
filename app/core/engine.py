"""RapidOCR 引擎封装：懒加载 + 图像增强 + 多语言 + 段落排版 + 二维码识别。

升级参考（PaddleOCR / Umi-OCR / EasyOCR 的常见能力）：
- 多语言识别模型（Rec.lang_type：ch / chinese_cht / en / japan / korean）
- 角度分类开关（use_cls，识别旋转/倒置文本）
- 图像增强：深色背景自动反色 + 低对比度 CLAHE 对比度增强
- 低置信度单字符噪声过滤
- 段落合并：多行文本按排版规则合并为自然段
- 二维码兜底识别：无文字时尝试解码二维码
"""
from __future__ import annotations

import bisect
import os
import re
import shutil
import statistics
import threading

from app import config

# 中文汉字区段 + 常用中文标点，用于智能排版判断
_CJK_CLASS = (
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"，。、；：？！…—～·「」『』【】（）《》〈〉\u201c\u201d\u2018\u2019]"
)
_CJK_RE = re.compile(_CJK_CLASS)
_CJK_SPACE_RE = re.compile(
    r"(?<=" + _CJK_CLASS + r")[ \t]+(?=" + _CJK_CLASS + r")"
)

# 段落合并：下一行以项目符号/编号开头时不并入上一段
_BULLET_RE = re.compile(r"^(?:[•·●○■□▪◦*+\-–—]|[(（]?\d{1,3}[.、)）]\s)")
# 句末终止标点：上一行以这些结尾时不再继续合并
_TERMINAL_PUNCT = "。！？；…”!?;]）】」』》"

# 单字符且置信度极低视为检测噪声（表格竖线、乱码碎片等）
_NOISE_SCORE = 0.55


def compact_cjk(text: str) -> str:
    """智能排版：去除中文字符间 OCR 产生的多余空格，压缩连续空行。"""
    text = _CJK_SPACE_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _upscale_small(arr):
    """小尺寸选区放大 2-3 倍再识别，显著提升小字号文本的检出率。"""
    import cv2

    h, w = arr.shape[:2]
    min_side = min(h, w)
    if min_side <= 0:  # 空图/零宽图：原样返回，交给上层判定
        return arr
    if min_side >= 320:
        return arr
    scale = min(3.0, 320.0 / min_side)
    return cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _normalize_bgr(arr):
    """统一成 3 通道 BGR：公开入口可能收到灰度图/带 alpha 的图。"""
    if arr is None or getattr(arr, "size", 0) == 0:
        return arr
    if arr.ndim == 2:
        import cv2

        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.ndim == 3 and arr.shape[2] == 4:
        import cv2

        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
    return arr


def _enhance(arr):
    """截图场景图像增强（参考 Umi-OCR / EasyOCR 预处理经验）：

    1. 深色背景（深色主题截图）自动反色——检测模型对黑字白底更敏感；
    2. 低对比度图像用 CLAHE 增强 L 通道，挽救灰色水印字/低对比 UI 文本。
    """
    import cv2
    import numpy as np

    if arr is None or getattr(arr, "size", 0) == 0 or min(arr.shape[:2]) <= 0:
        return arr
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    out = arr
    if float(np.mean(gray)) < 100:  # 整体偏暗：深色主题/夜间模式截图
        out = cv2.bitwise_not(out)
        gray = cv2.bitwise_not(gray)
    if float(np.std(gray)) < 45:  # 对比度过低：水印字、浅灰 UI 文本
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l = clahe.apply(l)
        out = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    return out


def detect_qrcode(arr) -> list[str]:
    """解码图中的二维码（Umi-OCR 同类能力），返回内容列表。"""
    import cv2

    det = cv2.QRCodeDetector()
    texts: list[str] = []
    try:
        ok, decoded, _, _ = det.detectAndDecodeMulti(arr)
        if ok:
            texts = [d for d in decoded if d]
    except cv2.error:  # 个别尺寸/通道数会触发 cv 内部异常
        texts = []
    if not texts:
        try:
            data, _, _ = det.detectAndDecode(arr)
            if data:
                texts = [data]
        except cv2.error:
            pass
    return texts


def _gpu_params() -> dict:
    """GPU 加速自动检测（EasyOCR 同款思路）：CUDA > DirectML > CPU 回退。

    onnxruntime-gpu 装了才有 CUDAExecutionProvider；
    Windows 上装 onnxruntime-directml 才有 DmlExecutionProvider；
    都没有则返回空参数，安静回退 CPU。
    """
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
    except Exception:  # noqa: BLE001
        return {}
    if "CUDAExecutionProvider" in providers:
        return {"EngineConfig.onnxruntime.use_cuda": True}
    if "DmlExecutionProvider" in providers:
        return {"EngineConfig.onnxruntime.use_dml": True}
    return {}


def _seed_models(models_dir: str) -> None:
    """首次运行把包内自带的模型复制到用户数据目录。

    打包 exe 后 rapidocr 包目录位于临时解压目录，模型存那里会在退出时丢失；
    复制到 %APPDATA% 后持久可用，且后续语言模型下载也落在这里。
    开发环境下等价于把 site-packages 内已下载的模型同步过来。
    """
    try:
        import rapidocr as _rp

        src = os.path.join(os.path.dirname(_rp.__file__), "models")
        if not os.path.isdir(src):
            return
        os.makedirs(models_dir, exist_ok=True)
        for name in os.listdir(src):
            if not name.endswith(".onnx"):
                continue
            dst = os.path.join(models_dir, name)
            if not os.path.exists(dst):
                shutil.copyfile(os.path.join(src, name), dst)
    except Exception:  # noqa: BLE001 复制失败则回落到运行时自动下载
        pass


# 引擎初始化锁：保证 RapidOCR 全局只被初始化一次
_LOAD_LOCK = threading.Lock()


class OCREngine:
    """懒加载的 RapidOCR 引擎，首次调用时才初始化（约 1-3 秒）。"""

    def __init__(self) -> None:
        self._engine = None
        self._params_key: tuple | None = None
        # 版本号：reload() 之后，正在初始化中的线程不要把旧参数的引擎写回缓存
        self._generation = 0

    def warmup(self) -> None:
        self._ensure_loaded()

    def reload(self) -> None:
        """设置（语言/角度分类）变更后重建引擎；下次识别时生效。

        这里**不能**去抢 _LOAD_LOCK：预热线程初始化模型要 1-3 秒且一直持锁，
        主线程若在启动后立刻改设置，会整窗冻结那么久。清空引用是原子的，
        并发安全交给 _ensure_loaded 的双检锁 + generation 校验。
        """
        self._generation += 1
        self._engine = None
        self._params_key = None

    def _ensure_loaded(self):
        # 双检锁：预热线程与识别线程可能并发首次初始化，
        # 无锁会双重创建 RapidOCR（重复下载模型/互相覆盖甚至崩溃）
        lang = config.OCR_LANG
        use_cls = bool(config.OCR_USE_CLS)
        gpu = bool(config.OCR_GPU)
        key = (lang, use_cls, gpu)
        if self._engine is None or self._params_key != key:
            with _LOAD_LOCK:
                if self._engine is None or self._params_key != key:
                    from rapidocr import RapidOCR  # 延迟导入，加快启动

                    gen = self._generation

                    # Det.limit_type=max + 960：检测输入最长边压到 960。
                    # 全屏 1080p 实测 16s → 7.3s（约 2 倍提速），文本召回基本无损；
                    # 框选小区域（最长边 < 960）不受影响。识别(rec)仍从原图裁剪，清晰度不变。
                    # Global.max_side_len 放宽到 4096：避免预处理整体缩图，小字不糊。
                    models_dir = os.path.join(config.DATA_DIR, "models")
                    _seed_models(models_dir)
                    params = {
                        # 模型缓存放到用户数据目录：开发环境和打包 exe 中都持久化，
                        # 避免 PyInstaller 临时目录导致每次启动重新下载模型
                        "Global.model_root_dir": models_dir,
                        "Global.max_side_len": 4096,
                        "Global.use_cls": use_cls,
                        "Det.limit_type": "max",
                        "Det.limit_side_len": 960,
                    }
                    if lang and lang != "ch":
                        # 多语言识别模型（首次使用会自动下载对应模型）
                        params["Rec.lang_type"] = lang
                    if gpu:
                        params.update(_gpu_params())
                    engine = RapidOCR(params=params)
                    if gen == self._generation:
                        # 初始化期间没有触发 reload：写回缓存，后续调用复用
                        self._engine = engine
                        self._params_key = key
                    # 否则说明用户在初始化过程中改了设置：这次构造的引擎只服务
                    # 当前这一次调用，不写回缓存，下次调用按新参数重建
                    return engine
        return self._engine

    def recognize_image(self, image) -> str:
        """image: QImage。直接转 BGR numpy 数组识别，避免 PNG 编解码开销。

        统一转成 Format_BGR888：通道顺序与 OpenCV 一致，透明通道被丢弃
        （与原 PNG + IMREAD_COLOR 路径行为一致）。
        """
        import numpy as np
        from PySide6.QtGui import QImage

        img = image.convertToFormat(QImage.Format_BGR888)
        h, w, stride = img.height(), img.width(), img.bytesPerLine()
        raw = np.frombuffer(bytes(img.constBits()), np.uint8)
        if stride == w * 3:
            arr = raw.reshape(h, w, 3)
        else:  # 行尾有对齐填充时按行切片去除
            arr = raw.reshape(h, stride)[:, : w * 3].reshape(h, w, 3)
        return self.recognize_array(arr)

    def recognize_bytes(self, data: bytes) -> str:
        import cv2
        import numpy as np

        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return ""
        return self.recognize_array(arr)

    def recognize_array(self, arr) -> str:
        arr = _normalize_bgr(arr)
        if arr is None or getattr(arr, "size", 0) == 0:
            return ""  # 空图/读取失败：直接返回空结果，不进模型
        if config.OCR_ENHANCE:
            arr = _enhance(arr)
        arr = _upscale_small(arr)
        result = self._ensure_loaded()(arr)
        text = format_result(result, merge_para=config.OCR_MERGE_PARA)
        if not text and config.OCR_QR:
            codes = detect_qrcode(arr)
            if codes:
                text = "\n".join(f"[二维码] {c}" for c in codes)
        return text

    def recognize_table(self, arr) -> list[list[str]]:
        """表格识别（PaddleOCR 表格场景）：word 级 box 网格化 → 行列矩阵。

        开启 return_word_box 拿到每个字的框，按行聚类、按列间隙切分，
        返回 list[list[str]]（可直接导出 Excel）。非表格区域也能给出近似网格。
        """
        arr = _normalize_bgr(arr)
        if arr is None or getattr(arr, "size", 0) == 0:
            return []
        if config.OCR_ENHANCE:
            arr = _enhance(arr)
        arr = _upscale_small(arr)
        result = self._ensure_loaded()(arr, return_word_box=True)
        return extract_table(result)


_engine: OCREngine | None = None


def get_engine() -> OCREngine:
    global _engine
    if _engine is None:
        _engine = OCREngine()
    return _engine


def _filter_keywords() -> list[str]:
    """用户设置的过滤关键词（水印等），逗号分隔。"""
    if not config.OCR_FILTER_KW:
        return []
    return [k.strip().casefold() for k in config.OCR_FILTER_KEYWORDS.split(",") if k.strip()]


def format_result(result, merge_para: bool = False) -> str:
    """兼容不同版本返回格式，整理成贴近原文排版的多行文本。

    merge_para=True 时把相邻文本行合并为自然段（Umi-OCR 的段落还原模式）。
    """
    if result is None:
        return ""
    keywords = _filter_keywords()
    items: list = []  # (cy, h, left, right, text)
    if hasattr(result, "txts"):  # rapidocr v2+ 返回 RapidOCROutput 对象
        txts = result.txts
        boxes = result.boxes
        scores = getattr(result, "scores", None)
        if txts is None or len(txts) == 0:
            return ""
        for i, (box, text) in enumerate(zip(boxes if boxes is not None else [], txts)):
            text = str(text)
            score = float(scores[i]) if scores is not None and i < len(scores) else 1.0
            if len(text.strip()) <= 1 and score < _NOISE_SCORE:
                continue  # 低置信单字符噪声（表格线、乱码碎片）
            low = text.casefold()
            if any(kw in low for kw in keywords):
                continue  # 水印/关键词过滤
            item = _box_item(box, text)
            if item is not None:
                items.append(item)
    else:  # 旧版返回 [[box, text, score], ...]
        for row in result:
            # 兼容字段不全/类型异常的行，避免个别脏行让整次识别失败
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            try:
                score = float(row[2]) if len(row) > 2 else 1.0
            except (TypeError, ValueError):
                score = 1.0
            text = str(row[1] or "")
            if len(text.strip()) <= 1 and score < _NOISE_SCORE:
                continue
            low = text.casefold()
            if any(kw in low for kw in keywords):
                continue
            item = _box_item(row[0], text)
            if item is not None:
                items.append(item)
    lines = _group_lines(items)
    if merge_para:
        return _merge_paragraphs(lines)
    return "\n".join(_line_text(line) for line in lines)


def _box_item(box, text: str):
    """(行中心 y, 行高, 左, 右, 文本)；框结构不可用时返回 None 由调用方跳过。

    box 可能是 numpy 数组，不能写 `box or []`（数组真值判断会抛 ValueError）；
    旧版/异常数据里也可能出现字符串、缺坐标等结构。
    """
    try:
        pts = [] if box is None else list(box)
        xs = [float(p[0]) for p in pts]
        ys = [float(p[1]) for p in pts]
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    if not xs or not ys:
        return None
    n = float(len(ys)) or 1.0  # 不是 4 点多边形时按实际点数取中心
    return (sum(ys) / n, max(ys) - min(ys), min(xs), max(xs), text)


def _line_text(line) -> str:
    return " ".join(t for _, _, left, _, t in sorted(line, key=lambda it: it[2]))


def _group_lines(items) -> list[list]:
    """按 y 坐标聚成行、行内按 x 排序，尽量还原原文排版。"""
    if not items:
        return []
    items = sorted(items, key=lambda it: (it[0], it[2]))
    lines: list[list] = []
    cur: list = []
    cur_ys: list[float] = []
    last_h = 0.0
    for cy, h, left, right, text in items:
        # 用相邻行高而非全局平均：大小字号混排时，全局均值会让小字行被并进大字行
        tol = max(h, last_h) * 0.6
        if cur_ys and abs(cy - sum(cur_ys) / len(cur_ys)) > tol:
            lines.append(cur)
            cur, cur_ys = [], []
        cur.append((cy, h, left, right, text))
        cur_ys.append(cy)
        last_h = h
    if cur:
        lines.append(cur)
    return lines


def _join_para(a: str, b: str) -> str:
    """段落拼接：中文字符之间直接相连，其余补一个空格。"""
    if a and b and _CJK_RE.match(a[-1]) and _CJK_RE.match(b[0]):
        return a + b
    return a + " " + b


def _should_merge(prev_line, cur_line, block_right: float) -> bool:
    """两行是否合并为同一段（Umi-OCR 段落还原思路）：

    - 下一行不以项目符号/编号开头；
    - 上一行不以句末标点结尾（句子还没说完）；
    - 垂直间距小于约一行高（中间没有空行）；
    - 上一行基本"写满"（右边界接近块内最大右边界），说明是被折行的段落。
    """
    prev_text = _line_text(prev_line).rstrip()
    cur_text = _line_text(cur_line).lstrip()
    if not prev_text or not cur_text:
        return False
    if _BULLET_RE.match(cur_text):
        return False
    if prev_text[-1] in _TERMINAL_PUNCT:
        return False
    p_cy = sum(it[0] for it in prev_line) / len(prev_line)
    p_h = max(it[1] for it in prev_line)
    c_cy = sum(it[0] for it in cur_line) / len(cur_line)
    c_h = max(it[1] for it in cur_line)
    gap = (c_cy - c_h / 2.0) - (p_cy + p_h / 2.0)
    if gap > 0.9 * max(p_h, c_h):
        return False
    p_right = max(it[3] for it in prev_line)
    return p_right >= block_right - 2.0 * p_h


def _merge_paragraphs(lines) -> str:
    """把按行分组的识别结果合并为自然段。"""
    if not lines:
        return ""
    block_right = max(it[3] for line in lines for it in line)
    paras: list[str] = []
    buf = _line_text(lines[0])
    for prev, line in zip(lines, lines[1:]):
        if _should_merge(prev, line, block_right):
            buf = _join_para(buf, _line_text(line))
        else:
            paras.append(buf)
            buf = _line_text(line)
    paras.append(buf)
    return "\n".join(paras)


# ---- 表格识别：word box 网格化 ----

def extract_table(result) -> list[list[str]]:
    """把 return_word_box 的识别结果还原为行列矩阵（导出 Excel 用）。

    word_results 结构：每行一个元组，元组内为 (文本, 置信度, 字框) 的词序列。
    """
    if result is None or not getattr(result, "word_results", None):
        return []
    words: list[tuple] = []  # (left, right, cy, h, text)
    for line_words in result.word_results:
        if not line_words:
            continue
        for w in line_words:
            if not w or not w[0] or w[2] is None:
                continue
            box = w[2]
            if len(box) == 0:  # 空框：跳过（min/max 会抛 ValueError）
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            text = str(w[0]).strip()
            if not text:
                continue
            n = float(len(ys)) or 1.0
            words.append((min(xs), max(xs), sum(ys) / n, max(ys) - min(ys), text))
    if not words:
        return []
    return _grid_from_words(words)


def _cluster_sorted(values, tol: float) -> list[list[float]]:
    """一维聚类：返回按值排序的簇列表。"""
    clusters: list[list[float]] = []
    for v in sorted(values):
        if clusters and v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return clusters


def _cells_from_row(row_words, med_h: float) -> list[list]:
    """把同一行的词按列间隙切成单元格：[[left, right, [文本...]], ...]。

    间隙阈值取「行高中位数 × 0.9」：同一个单元格内的字距远小于行高，
    而相邻列之间的空白通常至少有一行高。
    """
    cells: list[list] = []
    for w in sorted(row_words, key=lambda it: it[0]):
        if cells and w[0] - cells[-1][1] <= _CELL_GAP_RATIO * med_h:
            cells[-1][1] = max(cells[-1][1], w[1])
            cells[-1][2].append(w[4])
        else:
            cells.append([w[0], w[1], [w[4]]])
    return cells


_CELL_GAP_RATIO = 0.9

# 全局「空白缝」判定：某个 x 位置如果全表没有任何一行有文字跨越，它就是列分隔缝。
# 缝宽只取决于「有没有字压在上面」，与字高无关——所以列间距比一个字高还窄的
# 密集表格同样能切对（旧的「行内间隙 > 0.9 倍字高」做不到这一点）。
_MIN_CORRIDOR_PX = 1.5
# 允许少数行（表头标题、跨列表格）压过缝隙；超过这个比例就不算「贯穿全表的缝」
_CORRIDOR_ROW_TOLERANCE = 0.25
# 列数上限：超过说明 word box 噪声太多，切出来的不是表格
_MAX_COLUMNS = 16


def _column_bands(spans, tol: float) -> list[list[float]]:
    """把各行的单元格水平区段并成全局列带（区间合并）。

    以前用「行内间隙中点」当列边界，某行中间缺一格时那道大间隙会在
    中间凭空多切出一列，导致整行数据左移、插进错误的列。改为按实际
    单元格区间做合并：只有真正重叠/相邻的区段才算同一列。
    """
    bands: list[list[float]] = []
    for left, right in sorted(spans):
        for b in bands:
            if left <= b[1] + tol and right >= b[0] - tol:
                b[0], b[1] = min(b[0], left), max(b[1], right)
                break
        else:
            bands.append([left, right])
    # 合并过程中可能让两个列带变近/重叠，再收敛一轮
    bands.sort()
    merged: list[list[float]] = []
    for b in bands:
        if merged and b[0] <= merged[-1][1] + tol:
            merged[-1][1] = max(merged[-1][1], b[1])
        else:
            merged.append(b)
    return merged


def _best_column(bands, left: float, right: float) -> int:
    """单元格归属哪一列：水平重叠最多者优先，否则取中心最近的列。"""
    best, best_overlap = 0, 0.0
    for i, (bl, br) in enumerate(bands):
        overlap = min(right, br) - max(left, bl)
        if overlap > best_overlap:
            best, best_overlap = i, overlap
    if best_overlap > 0:
        return best
    cx = (left + right) / 2.0
    return min(
        range(len(bands)),
        key=lambda i: abs((bands[i][0] + bands[i][1]) / 2.0 - cx),
    )


def _rows_by_y(words, med_h: float) -> list[list[tuple]]:
    """按 y 中心聚成表格行。"""
    if not words:
        return []
    clusters = _cluster_sorted([w[2] for w in words], med_h * 0.6)
    centers = [sum(c) / len(c) for c in clusters]
    rows: list[list[tuple]] = [[] for _ in clusters]
    for w in words:
        rows[min(range(len(centers)), key=lambda i: abs(centers[i] - w[2]))].append(w)
    return rows


def _corridor_bounds(rows, med_h: float) -> list[float]:
    """找出贯穿全表的空白缝，返回列边界（缝中线）列表。

    判定方式是**逐 x 位置**做的：把所有字框的左右边缘当候选点，相邻两点之间
    的横坐标区间如果没有任何一行有文字跨越，就是一道缝。这样列间距再窄也能
    切出来——只要那里真的是空白，跟字高没有关系（旧算法要求间隙大于 0.9 倍
    字高，密集排版的表格会被整片并成一列）。
    """
    rows = [r for r in rows if r]
    if len(rows) < 2:
        return []  # 只有一行时无法验证「全表都没有字」，退回旧算法
    spans: list[tuple[list[float], list[float]]] = []
    for r in rows:
        s = sorted((w[0], w[1]) for w in r)
        spans.append((s, [it[0] for it in s]))
    edges = sorted(
        {w[0] for r in rows for w in r} | {w[1] for r in rows for w in r}
    )
    if len(edges) < 4:
        return []
    min_gap = max(_MIN_CORRIDOR_PX, med_h * 0.10)
    allowed = int(len(rows) * _CORRIDOR_ROW_TOLERANCE)
    bounds: list[float] = []
    for a, b in zip(edges, edges[1:]):
        if b - a < min_gap:
            continue
        covered = 0
        for s, starts in spans:
            i = bisect.bisect_right(starts, a) - 1
            if i >= 0 and s[i][1] > a:  # 这一行有文字压在这个 x 上
                covered += 1
                if covered > allowed:
                    break
        if covered <= allowed:
            bounds.append((a + b) / 2.0)
    if len(bounds) + 1 > _MAX_COLUMNS:
        return []
    return bounds


def _grid_by_bounds(rows, bounds: list[float]) -> list[list[str]]:
    """按全局列边界把每行的词落进对应单元格。"""
    n_cols = len(bounds) + 1
    grid: list[list[str]] = []
    for row in rows:
        cells = [""] * n_cols
        for w in sorted(row, key=lambda it: it[0]):
            left_i = bisect.bisect_right(bounds, w[0])
            right_i = bisect.bisect_right(bounds, w[1])
            if left_i != right_i:
                # 字框跨过了列缝（合并标题「合计」这类）：落到它占的第一列，
                # 否则按中心点归位会被塞进中间那列，导出后看着像错行
                idx = min(n_cols - 1, left_i)
            else:
                idx = min(n_cols - 1, bisect.bisect_right(bounds, (w[0] + w[1]) / 2.0))
            cells[idx] = f"{cells[idx]} {w[4]}".strip() if cells[idx] else w[4]
        if config.CJK_COMPACT:
            cells = [compact_cjk(c) for c in cells]
        grid.append(cells)
    return grid


def _grid_by_row_gaps(rows, med_h: float) -> list[list[str]]:
    """旧算法兜底：行内按间隙切单元格，再用区间合并对齐成全局列带。

    找不到贯穿全表的空白缝时（普通文本、某行文字横跨多列且被识别成一个框）
    才走这里。
    """
    rows_cells = [_cells_from_row(r, med_h) for r in rows]
    spans = [(c[0], c[1]) for cells in rows_cells for c in cells]
    tol = max(med_h * _CELL_GAP_RATIO, 4.0)
    bands = _column_bands(spans, tol)
    n_cols = len(bands)
    grid: list[list[str]] = []
    for cells in rows_cells:
        row = [""] * n_cols
        for left, right, texts in cells:
            text = " ".join(texts)
            if config.CJK_COMPACT:
                # 字级 word_box 会把「姓名」切成「姓」「名」，直接空格拼接会导出成
                # 「姓 名」。这里复用智能排版去掉汉字之间的空格（英文词间空格保留）。
                text = compact_cjk(text)
            idx = _best_column(bands, left, right)
            row[idx] = f"{row[idx]} {text}".strip() if row[idx] else text
        grid.append(row)
    return grid


def _grid_from_words(words) -> list[list[str]]:
    """按 y 聚类成行 → 找全局列缝 → 输出矩阵。

    输出矩阵每行长度都等于列数，缺字的单元格留空串：
    否则把右侧单元格往左顶，导出 Excel 后整列错位。
    """
    med_h = statistics.median(w[3] for w in words) or 1.0
    rows = _rows_by_y(words, med_h)
    bounds = _corridor_bounds(rows, med_h)
    if bounds:
        return _grid_by_bounds(rows, bounds)
    return _grid_by_row_gaps(rows, med_h)

