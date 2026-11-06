"""全屏截图遮罩：拖拽选区，Esc 取消，双击全屏识别。"""
from __future__ import annotations

import mss
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QRubberBand, QWidget


def virtual_geometry() -> QRect:
    """所有屏幕的并集（逻辑坐标），多屏时覆盖整个虚拟桌面。"""
    rect = QRect()
    for screen in QGuiApplication.screens():
        rect = rect.united(screen.geometry())
    if rect.isNull():
        screen = QGuiApplication.primaryScreen()
        rect = screen.geometry() if screen is not None else QRect(0, 0, 1920, 1080)
    return rect


def grab_virtual_screen() -> tuple[QImage, tuple[int, int]]:
    """用 mss 抓取整个虚拟桌面（物理像素）。

    返回 (带 devicePixelRatio 的 QImage, 虚拟桌面左上角的物理坐标)：
    mss.monitors[0] 是所有显示器并集，副屏在主屏左侧/上方时坐标可能为负。
    """
    with mss.mss() as sct:
        mon = sct.monitors[0]
        raw = sct.grab(mon)
    img = QImage(raw.bgra, raw.width, raw.height, raw.width * 4, QImage.Format_ARGB32).copy()
    geo = virtual_geometry()
    if geo.width() > 0:
        # 统一缩放比：单屏时等于真实 DPR；混合 DPI 多屏只能取等效值
        img.setDevicePixelRatio(raw.width / geo.width())
    return img, (int(mon["left"]), int(mon["top"]))


class CaptureOverlay(QWidget):
    captured = Signal(QImage)
    regionSelected = Signal(int, int, int, int)  # mss 物理像素区域 (x, y, w, h)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self._geo = virtual_geometry()
        self._shot, self._origin_phys = grab_virtual_screen()
        self._pixmap = QPixmap.fromImage(self._shot)
        self._origin = QPoint()
        self._rubber = QRubberBand(QRubberBand.Rectangle, self)
        self._rubber.setStyleSheet(
            "background-color: rgba(47,111,237,60); border: 1px solid #2f6fed;"
        )

    def start(self) -> None:
        self.setGeometry(self._geo)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.PopupFocusReason)

    # ---- 绘制：暗色遮罩 + 选区保持原始亮度 + 尺寸提示 ----
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self._rubber.isVisible():
            r = self._rubber.geometry()
            dpr = self._shot.devicePixelRatio()
            src = QRect(
                int(r.x() * dpr), int(r.y() * dpr),
                int(r.width() * dpr), int(r.height() * dpr),
            )
            p.drawPixmap(r, self._pixmap, src)
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawText(
                r.adjusted(0, 0, -6, -6),
                Qt.AlignBottom | Qt.AlignRight,
                f"{r.width()} x {r.height()}",
            )

    # ---- 鼠标/键盘交互 ----
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._origin = e.position().toPoint()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._rubber.isVisible():
            self._rubber.setGeometry(
                QRect(self._origin, e.position().toPoint()).normalized()
            )

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton or not self._rubber.isVisible():
            return
        rect = self._rubber.geometry()
        if rect.width() < 8 or rect.height() < 8:
            self._rubber.hide()
            return
        self._finish(rect)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._finish(QRect(QPoint(0, 0), self.size()))

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self._rubber.hide()
            self.close()
            self.cancelled.emit()

    def mss_region(self, rect: QRect) -> tuple[int, int, int, int]:
        """逻辑选区 → mss 物理像素区域 (x, y, w, h)，坐标相对截图左上角。

        四周外扩 4 物理像素：贴边文字被裁掉一半常导致整行漏识别。
        """
        dpr = self._shot.devicePixelRatio()
        # 虚拟桌面原点可能不在 (0,0)（副屏在主屏左侧/上方），要换算成相对截图的偏移
        off_x = self._origin_phys[0] - int(self._geo.x() * dpr)
        off_y = self._origin_phys[1] - int(self._geo.y() * dpr)
        src = QRect(
            int(rect.x() * dpr) + off_x, int(rect.y() * dpr) + off_y,
            int(rect.width() * dpr), int(rect.height() * dpr),
        )
        src = src.adjusted(-4, -4, 4, 4).intersected(self._shot.rect())
        return src.x(), src.y(), src.width(), src.height()

    def _finish(self, rect: QRect) -> None:
        x, y, w, h = self.mss_region(rect)
        crop = self._shot.copy(QRect(x, y, w, h))
        # 长截图需要绝对物理坐标（mss 的 monitor 参数），补回虚拟桌面原点
        abs_x = x + self._origin_phys[0]
        abs_y = y + self._origin_phys[1]
        self.close()
        self.captured.emit(crop)
        self.regionSelected.emit(abs_x, abs_y, w, h)
