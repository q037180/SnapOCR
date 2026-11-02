"""截图贴图（参考 Umi-OCR 贴图功能）：

把截图钉在桌面上置顶显示——
- 拖动移动位置 / 滚轮缩放 / Ctrl+滚轮 调透明度
- 右键菜单：缩放、透明度、复制图片、关闭
- 双击关闭
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget


class PinWindow(QWidget):
    """无边框置顶贴图窗口，可同时存在多个。"""

    def __init__(self, image_pixmap: QPixmap) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self._pixmap = image_pixmap
        self._zoom = 1.25  # 默认放大 25%，看得更清楚
        self._opacity = 1.0
        self._drag_pos = None
        self.setWindowOpacity(self._opacity)
        self._apply_size()

    # ---- 显示 ----
    def _apply_size(self) -> None:
        pm = self._pixmap
        w = max(40, int(pm.width() / pm.devicePixelRatio() * self._zoom))
        h = max(40, int(pm.height() / pm.devicePixelRatio() * self._zoom))
        self.resize(w, h)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(self.rect(), self._pixmap)
        p.end()

    # ---- 鼠标交互 ----
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._drag_pos = None

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        self.close()

    def contextMenuEvent(self, e) -> None:  # noqa: N802
        menu = QMenu(self)
        act_copy = menu.addAction("复制图片")
        menu.addSeparator()
        for label, z in (("缩放 100%", 1.0), ("缩放 150%", 1.5), ("缩放 200%", 2.0)):
            act = menu.addAction(label)
            act.triggered.connect(lambda _=False, zz=z: self._set_zoom(zz))
        menu.addSeparator()
        act_close = menu.addAction("关闭贴图 (双击)")
        act = menu.exec(e.globalPos())
        if act == act_copy:
            QApplication.clipboard().setPixmap(self._pixmap)
        elif act == act_close:
            self.close()

    def wheelEvent(self, e) -> None:  # noqa: N802
        """滚轮缩放；Ctrl+滚轮 调透明度。"""
        if e.modifiers() & Qt.ControlModifier:
            self._opacity = min(1.0, max(0.2, self._opacity + (0.05 if e.angleDelta().y() > 0 else -0.05)))
            self.setWindowOpacity(self._opacity)
        else:
            factor = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
            self._set_zoom(self._zoom * factor)

    def _set_zoom(self, zoom: float) -> None:
        self._zoom = min(6.0, max(0.2, zoom))
        self._apply_size()
