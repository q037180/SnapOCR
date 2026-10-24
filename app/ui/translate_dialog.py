"""翻译窗口：原文（可编辑）→ 后台线程翻译 → 译文预览/复制/导出。

可独立使用，也可由“截屏翻译”预填文本并自动翻译。
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app import config
from app.core.exporter import export_text
from app.core.translator import translate_text


class TranslateWorker(QThread):
    """后台翻译线程，避免阻塞界面。"""

    done = Signal(str)
    fail = Signal(str)

    def __init__(self, text: str, target: str) -> None:
        super().__init__()
        self._text = text
        self._target = target

    def run(self) -> None:
        try:
            self.done.emit(translate_text(self._text, self._target))
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))


class TranslateDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"翻译 - {config.APP_NAME}")
        self.resize(560, 460)
        self._worker: TranslateWorker | None = None

        # 统一浅色卡片风：与主窗口蓝色主题一致
        self.setStyleSheet(
            "QDialog { background: #f5f7fa; }"
            "QLabel { color: #444; background: transparent; }"
            "QPlainTextEdit { background: white; border: 1px solid #d0d7de;"
            " border-radius: 6px; padding: 6px 8px; font-size: 10pt;"
            " selection-background-color: #2f6fed; }"
            "QPlainTextEdit:focus { border: 1px solid #2f6fed; }"
            "QComboBox { background: white; border: 1px solid #d0d7de;"
            " border-radius: 4px; padding: 4px 8px; }"
            "QComboBox:hover, QComboBox:focus { border: 1px solid #2f6fed; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel("原文（可编辑，自动检测语言）："))
        self.src = QPlainTextEdit()
        self.src.setPlaceholderText("输入、粘贴文本，或用“截屏翻译”识别后自动填入...")
        layout.addWidget(self.src, 2)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("目标语言："))
        self.cmb = QComboBox()
        self.cmb.addItems(list(config.TRANSLATE_LANGS.keys()))
        default_label = next(
            k for k, v in config.TRANSLATE_LANGS.items()
            if v == config.TRANSLATE_TARGET_DEFAULT
        )
        self.cmb.setCurrentText(default_label)
        row.addWidget(self.cmb)
        row.addStretch(1)
        self.btn = QPushButton("翻 译")
        self.btn.setMinimumWidth(96)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet(
            "QPushButton { background: #2f6fed; color: white; border: none;"
            " border-radius: 5px; padding: 6px 18px; font-weight: bold; }"
            "QPushButton:hover { background: #2559c8; }"
            "QPushButton:pressed { background: #1e47a3; }"
            "QPushButton:disabled { background: #9db9f0; }"
        )
        row.addWidget(self.btn)
        self.btn_copy = QPushButton("复制译文")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setStyleSheet(
            "QPushButton { background: white; color: #2f6fed; border: 1px solid #2f6fed;"
            " border-radius: 5px; padding: 6px 14px; }"
            "QPushButton:hover { background: #eef3fe; }"
            "QPushButton:pressed { background: #dde9fd; }"
        )
        row.addWidget(self.btn_copy)
        self.btn_export = QPushButton("导出...")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet(
            "QPushButton { background: white; color: #2f6fed; border: 1px solid #2f6fed;"
            " border-radius: 5px; padding: 6px 14px; }"
            "QPushButton:hover { background: #eef3fe; }"
            "QPushButton:pressed { background: #dde9fd; }"
        )
        row.addWidget(self.btn_export)
        layout.addLayout(row)

        layout.addWidget(QLabel("译文："))
        self.dst = QPlainTextEdit()
        self.dst.setReadOnly(True)
        self.dst.setPlaceholderText("译文将显示在这里...")
        layout.addWidget(self.dst, 3)

        self.status = QLabel("就绪")
        self.status.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(self.status)

        self.btn.clicked.connect(self._translate_current)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_export.clicked.connect(self._export)

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setStyleSheet(f"color: {'#d33' if error else '#666'}; font-size: 9pt;")
        self.status.setText(text)

    def open_with(self, text: str) -> None:
        """预填原文；非空时自动翻译。"""
        if text:
            self.src.setPlainText(text)
            self._translate_current()
        elif not self.isVisible():
            self._set_status("输入或粘贴文本后点击翻译")

    def _translate_current(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        text = self.src.toPlainText().strip()
        if not text:
            self._set_status("请先输入要翻译的文本", error=True)
            return
        target = config.TRANSLATE_LANGS[self.cmb.currentText()]
        self.btn.setEnabled(False)
        self._set_status("翻译中...")
        self._worker = TranslateWorker(text, target)
        self._worker.done.connect(self._on_done)
        self._worker.fail.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, text: str) -> None:
        self.btn.setEnabled(True)
        self.dst.setPlainText(text)
        self._set_status("翻译完成")

    def _on_fail(self, msg: str) -> None:
        self.btn.setEnabled(True)
        self._set_status(f"翻译失败：{msg}", error=True)

    def _copy(self) -> None:
        text = self.dst.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self._set_status("译文已复制到剪贴板")

    def _export(self) -> None:
        """把译文导出为 txt / docx / pdf。"""
        text = self.dst.toPlainText().strip()
        if not text:
            self._set_status("暂无译文可导出", error=True)
            return
        default = os.path.join(os.path.expanduser("~"), "译文.docx")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出译文", default,
            "Word 文档 (*.docx);;文本文件 (*.txt);;PDF 文档 (*.pdf)",
        )
        if not path:
            return
        try:
            export_text(path, text)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"导出失败：{exc}", error=True)
            return
        self._set_status(f"已导出 {os.path.basename(path)}")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
            self._translate_current()
            return
        super().keyPressEvent(event)
