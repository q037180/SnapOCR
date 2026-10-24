"""历史条目悬浮预览浮窗：长悬浮或双击条目时浮现完整内容。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout


class PreviewPopup(QFrame):
    """无边框深色浮窗，展示完整文本；鼠标移入可停留选中，移出或超时自动隐藏。"""

    WIDTH = 456
    MAX_HEIGHT = 380
    TEXT_WIDTH = WIDTH - 26  # 去除左右边距

    def __init__(self) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(
            "QFrame { background: #23262d; border: 1px solid #2f6fed; border-radius: 8px; }"
        )
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.PlainText)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._label.setStyleSheet(
            "QLabel { background: transparent; color: #e9ecf3; font-size: 13px; }"
        )

        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        area.setWidget(self._label)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.addWidget(area)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_text(self, text: str, global_pos, timeout_ms: int = 6000) -> None:
        """在 global_pos 附近浮现完整文本，超时自动隐藏。"""
        if not text:
            return
        self._label.setText(text)
        self._label.setFixedWidth(self.TEXT_WIDTH)
        self._label.adjustSize()
        self.setFixedSize(self.WIDTH, min(self._label.height() + 22, self.MAX_HEIGHT))
        # 保持在屏幕可见范围内
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = global_pos.x() + 18
        y = global_pos.y() + 14
        if x + self.width() > avail.right():
            x = global_pos.x() - self.width() - 12
        if y + self.height() > avail.bottom():
            y = avail.bottom() - self.height() - 8
        self.move(max(avail.left() + 8, x), max(avail.top() + 8, y))
        self.show()
        self.raise_()
        self._hide_timer.start(timeout_ms)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hide_timer.stop()  # 鼠标移入浮窗：保持显示（文本可选中复制）
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.hide()
        super().leaveEvent(event)
