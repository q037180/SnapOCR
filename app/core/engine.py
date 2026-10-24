"""RapidOCR 引擎封装：懒加载 + 按阅读顺序整理识别结果。"""
from __future__ import annotations

import re
import threading

# 中文汉字区段 + 常用中文标点，用于智能排版判断
_CJK_CLASS = (
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"，。、；：？！…—～·「」『』【】（）《》〈〉\u201c\u201d\u2018\u2019]"
)
_CJK_SPACE_RE = re.compile(
    r"(?<=" + _CJK_CLASS + r")[ \t]+(?=" + _CJK_CLASS + r")"
)


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
    if min_side >= 320:
        return arr
    scale = min(3.0, 320.0 / min_side)
    return cv2.resize(arr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


# 引擎初始化锁：保证 RapidOCR 全局只被初始化一次
_LOAD_LOCK = threading.Lock()


class OCREngine:
    """懒加载的 RapidOCR 引擎，首次调用时才初始化（约 1-3 秒）。"""

    def __init__(self) -> None:
        self._engine = None

    def warmup(self) -> None:
        self._ensure_loaded()

    def _ensure_loaded(self):
        # 双检锁：预热线程与识别线程可能并发首次初始化，
        # 无锁会双重创建 RapidOCR（重复下载模型/互相覆盖甚至崩溃）
        if self._engine is None:
            with _LOAD_LOCK:
                if self._engine is None:
                    from rapidocr import RapidOCR  # 延迟导入，加快启动

                    # Det.limit_type=max + 960：检测输入最长边压到 960。
                    # 全屏 1080p 实测 16s → 7.3s（约 2 倍提速），文本召回基本无损；
                    # 框选小区域（最长边 < 960）不受影响。识别(rec)仍从原图裁剪，清晰度不变。
                    # Global.max_side_len 放宽到 4096：避免预处理整体缩图，小字不糊。
                    # use_cls=False：屏幕文本几乎都是正向，跳过角度分类模型省一次推理
                    # （旋转/竖排文本场景可改回 True）
                    self._engine = RapidOCR(params={
                        "Global.max_side_len": 4096,
                        "Global.use_cls": False,
                        "Det.limit_type": "max",
                        "Det.limit_side_len": 960,
                    })
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
        arr = _upscale_small(arr)
        result = self._ensure_loaded()(arr)
        return format_result(result)


_engine: OCREngine | None = None


def get_engine() -> OCREngine:
    global _engine
    if _engine is None:
        _engine = OCREngine()
    return _engine


def format_result(result) -> str:
    """兼容不同版本返回格式，整理成贴近原文排版的多行文本。"""
    if result is None:
        return ""
    items: list = []
    if hasattr(result, "txts"):  # rapidocr v2+ 返回 RapidOCROutput 对象
        txts = result.txts
        boxes = result.boxes
        if txts is None or len(txts) == 0:
            return ""
        for box, text in zip(boxes if boxes is not None else [], txts):
            items.append(_box_item(box, str(text)))
    else:  # 旧版返回 [[box, text, score], ...]
        for row in result:
            items.append(_box_item(row[0], str(row[1])))
    return _group_lines(items)


def _box_item(box, text: str):
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return (sum(ys) / 4.0, max(ys) - min(ys), min(xs), text)


def _group_lines(items) -> str:
    """按 y 坐标聚成行、行内按 x 排序，尽量还原原文排版。"""
    if not items:
        return ""
    items.sort(key=lambda it: (it[0], it[2]))
    lines: list[list] = []
    cur: list = []
    cur_ys: list[float] = []
    last_h = 0.0
    for cy, h, left, text in items:
        # 用相邻行高而非全局平均：大小字号混排时，全局均值会让小字行被并进大字行
        tol = max(h, last_h) * 0.6
        if cur_ys and abs(cy - sum(cur_ys) / len(cur_ys)) > tol:
            lines.append(cur)
            cur, cur_ys = [], []
        cur.append((left, text))
        cur_ys.append(cy)
        last_h = h
    if cur:
        lines.append(cur)
    return "\n".join(" ".join(t for _, t in sorted(line)) for line in lines)
