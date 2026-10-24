"""快捷键设置对话框：QKeySequenceEdit 捕获按键，保存后由主窗口重注册。"""
from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QVBoxLayout,
)


def _seq_to_hotkey(edit: QKeySequenceEdit) -> str:
    """QKeySequence → keyboard 库热键字符串，如 "Ctrl+Alt+Q" -> "ctrl+alt+q"。"""
    ks = edit.keySequence()
    if ks.isEmpty():
        return ""
    return (
        ks.toString(QKeySequence.PortableText)
        .lower()
        .replace("meta", "windows")
    )


class SettingsDialog(QDialog):
    def __init__(self, cur: tuple[str, str, str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.resize(430, 210)
        self.setStyleSheet(
            "QDialog { background: #f5f7fa; }"
            "QLabel { color: #444; background: transparent; }"
            "QKeySequenceEdit { background: white; border: 1px solid #d0d7de;"
            " border-radius: 4px; padding: 4px 8px; }"
            "QKeySequenceEdit:focus { border: 1px solid #2f6fed; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(8)
        tip = QLabel("点击输入框后直接按下新的组合键；建议含 Ctrl/Alt，避免与系统冲突。")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        form = QFormLayout()
        form.setSpacing(8)
        self.ed_capture = QKeySequenceEdit(QKeySequence(cur[0]))
        self.ed_translate = QKeySequenceEdit(QKeySequence(cur[1]))
        self.ed_long = QKeySequenceEdit(QKeySequence(cur[2]))
        form.addRow("截图识别：", self.ed_capture)
        form.addRow("截屏翻译：", self.ed_translate)
        form.addRow("长截图：", self.ed_long)
        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def hotkeys(self) -> tuple[str, str, str]:
        """返回 keyboard 库格式的三个热键字符串。"""
        return (
            _seq_to_hotkey(self.ed_capture),
            _seq_to_hotkey(self.ed_translate),
            _seq_to_hotkey(self.ed_long),
        )
