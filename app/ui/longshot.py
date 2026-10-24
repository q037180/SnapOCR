"""长截图 UI：滚动采集控制条 + 结果预览对话框。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class LongShotBar(QWidget):
    """长截图控制条：贴近选区悬浮，未运行[开始][取消]，运行中[停止][取消]。"""

    startClicked = Signal()
    stopClicked = Signal()
    cancelClicked = Signal()

    def __init__(self, region: tuple[int, int, int, int]) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        x, y, w, h = region

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        self.status = QLabel("框选完成，点击「开始」滚动采集")
        self.btn_start = QPushButton("开始")
        self.btn_stop = QPushButton("停止")
        self.btn_cancel = QPushButton("取消")
        for b in (self.btn_start, self.btn_stop, self.btn_cancel):
            b.setCursor(Qt.PointingHandCursor)
        self.btn_stop.hide()
        lay.addWidget(self.status)
        lay.addWidget(self.btn_start)
        lay.addWidget(self.btn_stop)
        lay.addWidget(self.btn_cancel)
        self.btn_start.clicked.connect(self.startClicked.emit)
        self.btn_stop.clicked.connect(self.stopClicked.emit)
        self.btn_cancel.clicked.connect(self.cancelClicked.emit)
        self.setStyleSheet(
            "QWidget { background: rgba(245,247,250,235); border: 1px solid rgba(60,60,60,70);"
            " border-radius: 6px; }"
            " QLabel { border: none; }"
            " QPushButton { background: #2f6fed; color: white; border: none;"
            " border-radius: 4px; padding: 4px 12px; }"
            " QPushButton:hover { background: #2559c8; }"
        )

        # 位置：默认在选区下方，放不下则移到选区上方，并夹在屏幕内
        self.adjustSize()
        scr = QGuiApplication.primaryScreen().availableGeometry()
        bx = min(max(x, scr.left()), scr.right() - self.width() + 1)
        by = y + h + 8
        if by + self.height() > scr.bottom():
            by = max(scr.top(), y - self.height() - 8)
        self.move(bx, by)

    def set_running(self, running: bool) -> None:
        self.btn_start.setVisible(not running)
        self.btn_stop.setVisible(running)
        self.status.setText(
            "采集中…滚动到底部会自动结束，或点「停止」" if running else "已停止"
        )

    def set_status(self, text: str) -> None:
        self.status.setText(text)


class LongShotDialog(QDialog):
    """长截图预览：滚动查看整图，可保存 PNG / 复制 / 识别并复制 / 识别并翻译。"""

    ocrRequested = Signal(QImage, bool)  # (长图, 是否送翻译)

    def __init__(self, image: QImage) -> None:
        super().__init__(None, Qt.Window)
        self._image = image
        self.setWindowTitle(f"长截图预览（{image.width()} x {image.height()}）")
        self.resize(760, 640)

        lay = QVBoxLayout(self)
        area = QScrollArea()
        area.setWidgetResizable(True)
        label = QLabel()
        label.setPixmap(QPixmap.fromImage(image))
        label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        area.setWidget(label)
        lay.addWidget(area, 1)

        self.status = QLabel(f"尺寸 {image.width()} x {image.height()} px")
        row = QHBoxLayout()
        self.btn_save = QPushButton("保存 PNG")
        self.btn_copy = QPushButton("复制图片")
        self.btn_ocr_copy = QPushButton("识别并复制")
        self.btn_ocr_tr = QPushButton("识别并翻译")
        self.btn_close = QPushButton("关闭")
        for b in (
            self.btn_save, self.btn_copy, self.btn_ocr_copy, self.btn_ocr_tr, self.btn_close
        ):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        self.btn_save.clicked.connect(self._save)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_ocr_copy.clicked.connect(
            lambda: self.ocrRequested.emit(self._image, False)
        )
        self.btn_ocr_tr.clicked.connect(
            lambda: self.ocrRequested.emit(self._image, True)
        )
        self.btn_close.clicked.connect(self.close)
        lay.addLayout(row)
        lay.addWidget(self.status)

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存长截图", os.path.join(os.path.expanduser("~"), "longshot.png"),
            "PNG 图片 (*.png)",
        )
        if not path:
            return
        if self._image.save(path, "PNG"):
            self.status.setText(f"已保存：{path}")
        else:
            QMessageBox.warning(self, "SnapOCR", "保存失败，请检查路径与权限")

    def _copy(self) -> None:
        QApplication.clipboard().setImage(self._image)
        self.status.setText("已复制到剪贴板")
