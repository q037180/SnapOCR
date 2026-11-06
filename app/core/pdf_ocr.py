"""PDF 整档识别（参考 Umi-OCR / OCRmyPDF 的 PDF 场景）。

用 PySide6 自带的 QPdfDocument 逐页渲染成位图（无需额外依赖），
再交给 OCR 引擎逐页识别；支持进度上报与取消。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class PdfWorker(QThread):
    """后台线程：PDF 逐页渲染 → OCR → 合并文本。

    done 信号参数为完整文本（多页时带「== 第 N 页 ==」分隔）。
    """

    progress = Signal(int, int)  # (当前页, 总页数)
    done = Signal(str)
    fail = Signal(str)
    cancelled = Signal()  # 用户取消：界面据此关闭进度框

    def __init__(self, path: str, scale: float = 2.0) -> None:
        super().__init__()
        self._path = path
        self._scale = scale
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            from PySide6.QtGui import QColor
            from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

            doc = QPdfDocument()
            if doc.load(self._path) != QPdfDocument.Error.None_:
                self.fail.emit(f"无法打开 PDF：{self._path}")
                return
            total = doc.pageCount()
            if total <= 0:
                self.fail.emit("PDF 没有任何页面")
                return

            parts: list[str] = []
            multi = total > 1
            for i in range(total):
                if self._cancelled:
                    # 必须发信号：否则界面上的进度框没人关，下次识别还会叠加一个
                    self.cancelled.emit()
                    return
                self.progress.emit(i + 1, total)
                size = doc.pagePointSize(i)
                # render(page, imageSize: QSize)：按目标像素尺寸渲染，
                # 2.0 倍 ≈ 144dpi；必须白底填充（默认透明会被 OCR 当黑页）
                target = size.toSize() * self._scale
                image = doc.render(
                    i, target, QPdfDocumentRenderOptions(),
                    QImage.Format_ARGB32, QColor("white"),
                )
                if image.isNull():
                    parts.append(f"== 第 {i + 1} 页（渲染失败）==\n" if multi else "")
                    continue
                text = get_engine_text(image)
                if multi:
                    parts.append(f"== 第 {i + 1} 页 ==\n{text}".rstrip())
                else:
                    parts.append(text)
            self.done.emit("\n\n".join(p for p in parts if p.strip()))
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))


def get_engine_text(image: QImage) -> str:
    """延迟导入引擎，避免模块加载顺序问题。"""
    from app.core.engine import get_engine

    return get_engine().recognize_image(image)
