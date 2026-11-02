"""设置对话框：侧边栏分类式布局（参考 Umi-OCR 设置页）。

- 快捷键：三个全局热键录制
- 识别：语言 / 角度分类 / 图像增强 / 段落合并 / GPU 加速
- 功能：二维码兜底 / 表格识别 / 水印关键词过滤
所有设置保存到 settings.json，识别相关变更即时生效（引擎自动重载）。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
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
    def __init__(self, cur: tuple[str, str, str], ocr: dict, parent=None) -> None:
        """ocr: {lang, use_cls, enhance, para, qr, table, gpu, filter_kw,
                 filter_keywords, langs: {显示名: 代码}}"""
        super().__init__(parent)
        self._langs: dict = ocr.get("langs", {})
        self.setWindowTitle("设置")
        self.resize(560, 460)
        self.setStyleSheet(
            "QDialog { background: #f5f7fa; }"
            "QLabel { color: #444; background: transparent; }"
            "QKeySequenceEdit { background: white; border: 1px solid #d0d7de;"
            " border-radius: 4px; padding: 4px 8px; }"
            "QKeySequenceEdit:focus { border: 1px solid #2f6fed; }"
            "QListWidget { background: white; border: 1px solid #d0d7de;"
            " border-radius: 6px; outline: 0; font-weight: bold; color: #555; }"
            "QListWidget::item { padding: 10px 14px; }"
            "QListWidget::item:selected { background: #2f6fed; color: white;"
            " border-radius: 4px; }"
            "#page { background: white; border: 1px solid #d0d7de; border-radius: 6px; }"
            "#pageTitle { font-size: 15px; font-weight: bold; color: #333; }"
            "QComboBox, QLineEdit, QCheckBox { background: white; }"
            "QLineEdit { border: 1px solid #d0d7de; border-radius: 4px; padding: 4px 8px; }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        # 侧边导航 + 页面栈（水平布局）
        h = QHBoxLayout()
        h.setSpacing(10)
        self.nav = QListWidget()
        self.nav.setFixedWidth(96)
        self.nav.addItem("快捷键")
        self.nav.addItem("识别")
        self.nav.addItem("功能")
        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_hotkeys(cur))
        self.stack.addWidget(
            self._page_ocr(
                lang=ocr.get("lang", "ch"),
                use_cls=bool(ocr.get("use_cls", False)),
                enhance=bool(ocr.get("enhance", True)),
                para=bool(ocr.get("para", False)),
                gpu=bool(ocr.get("gpu", True)),
            )
        )
        self.stack.addWidget(
            self._page_features(
                qr=bool(ocr.get("qr", True)),
                table=bool(ocr.get("table", True)),
                filter_kw=bool(ocr.get("filter_kw", False)),
                filter_keywords=str(ocr.get("filter_keywords", "")),
                pdf=bool(ocr.get("pdf", True)),
                pin=bool(ocr.get("pin", True)),
            )
        )
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        h.addWidget(self.nav)
        h.addWidget(self.stack, 1)
        lay.addLayout(h, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @staticmethod
    def _page(title: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        v = QVBoxLayout(page)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        v.addWidget(t)
        return page, v

    def _page_hotkeys(self, cur: tuple[str, str, str]) -> QWidget:
        page, v = self._page("快捷键")
        tip = QLabel("点击输入框后直接按下新的组合键；建议含 Ctrl/Alt，避免与系统冲突。")
        tip.setWordWrap(True)
        v.addWidget(tip)
        form = QFormLayout()
        form.setSpacing(8)
        self.ed_capture = QKeySequenceEdit(QKeySequence(cur[0]))
        self.ed_translate = QKeySequenceEdit(QKeySequence(cur[1]))
        self.ed_long = QKeySequenceEdit(QKeySequence(cur[2]))
        form.addRow("截图识别：", self.ed_capture)
        form.addRow("截屏翻译：", self.ed_translate)
        form.addRow("长截图：", self.ed_long)
        v.addLayout(form)
        v.addStretch(1)
        return page

    def _page_ocr(
        self, lang: str, use_cls: bool, enhance: bool, para: bool, gpu: bool
    ) -> QWidget:
        page, v = self._page("识别")
        form = QFormLayout()
        form.setSpacing(8)
        self.cmb_lang = QComboBox()
        for name, code in self._langs.items():
            self.cmb_lang.addItem(name, code)
        idx = self.cmb_lang.findData(lang)
        self.cmb_lang.setCurrentIndex(max(idx, 0))
        form.addRow("识别语言：", self.cmb_lang)
        v.addLayout(form)

        self.cb_cls = QCheckBox("识别旋转 / 倒置文本（角度分类，稍慢）")
        self.cb_cls.setChecked(use_cls)
        self.cb_enhance = QCheckBox("图像增强（深色背景反色 + 低对比度增强）")
        self.cb_enhance.setChecked(enhance)
        self.cb_para = QCheckBox("段落合并（多行合并为自然段）")
        self.cb_para.setChecked(para)
        self.cb_gpu = QCheckBox("GPU 加速（自动检测 CUDA / DirectML，无 GPU 回退 CPU）")
        self.cb_gpu.setChecked(gpu)
        for cb in (self.cb_cls, self.cb_enhance, self.cb_para, self.cb_gpu):
            cb.setStyleSheet("QCheckBox { padding: 2px 0; }")
            v.addWidget(cb)
        v.addStretch(1)
        return page

    def _page_features(
        self,
        qr: bool,
        table: bool,
        filter_kw: bool,
        filter_keywords: str,
        pdf: bool = True,
        pin: bool = True,
    ) -> QWidget:
        page, v = self._page("功能")
        self.cb_qr = QCheckBox("二维码识别（未识别到文字时自动兜底）")
        self.cb_qr.setChecked(qr)
        self.cb_table = QCheckBox("表格识别（框选表格区域，导出 Excel）")
        self.cb_table.setChecked(table)
        self.cb_pdf = QCheckBox("PDF 整档识别（拖入 PDF 逐页识别，Umi-OCR 同款）")
        self.cb_pdf.setChecked(pdf)
        self.cb_pin = QCheckBox("截图贴图（截图后钉在桌面置顶显示，滚轮缩放）")
        self.cb_pin.setChecked(pin)
        for cb in (self.cb_qr, self.cb_table, self.cb_pdf, self.cb_pin):
            v.addWidget(cb)

        self.cb_filter = QCheckBox("过滤水印 / 关键词（命中的文字行不进入结果）")
        self.cb_filter.setChecked(filter_kw)
        v.addWidget(self.cb_filter)
        kw_tip = QLabel("过滤关键词（逗号分隔，不区分大小写）：")
        v.addWidget(kw_tip)
        self.ed_keywords = QLineEdit(filter_keywords)
        self.ed_keywords.setPlaceholderText("例如：水印, internal use only")
        self.ed_keywords.setAlignment(Qt.AlignLeft)
        v.addWidget(self.ed_keywords)
        v.addStretch(1)
        return page

    # ---- 结果读取 ----
    def hotkeys(self) -> tuple[str, str, str]:
        """返回 keyboard 库格式的三个热键字符串。"""
        return (
            _seq_to_hotkey(self.ed_capture),
            _seq_to_hotkey(self.ed_translate),
            _seq_to_hotkey(self.ed_long),
        )

    def ocr_options(self) -> dict:
        """返回对话框中的全部识别/功能设置。"""
        return {
            "lang": self.cmb_lang.currentData() or "ch",
            "use_cls": self.cb_cls.isChecked(),
            "enhance": self.cb_enhance.isChecked(),
            "para": self.cb_para.isChecked(),
            "qr": self.cb_qr.isChecked(),
            "table": self.cb_table.isChecked(),
            "gpu": self.cb_gpu.isChecked(),
            "filter_kw": self.cb_filter.isChecked(),
            "filter_keywords": self.ed_keywords.text().strip(),
            "pdf": self.cb_pdf.isChecked(),
            "pin": self.cb_pin.isChecked(),
        }
