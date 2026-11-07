"""主窗口 + 托盘：历史记录、热键截图、截屏翻译、长截图、快捷键设置、自动复制。"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCursor,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPixmap,
    QImage,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.engine import compact_cjk, get_engine
from app.core.exporter import (
    ensure_text_suffix,
    ensure_xlsx_suffix,
    export_text,
    export_xlsx,
)
from app.core.pdf_ocr import PdfWorker
from app.ui.capture_overlay import CaptureOverlay
from app.ui.longshot import LongShotBar, LongShotDialog
from app.ui.pin_window import PinWindow
from app.ui.preview_popup import PreviewPopup
from app.ui.settings_dialog import SettingsDialog
from app.ui.translate_dialog import TranslateDialog

if TYPE_CHECKING:  # 仅用于类型标注；cv2/mss 在首次长截图时才真正导入
    from app.core.stitcher import StitchWorker


def make_icon() -> QIcon:
    """程序化生成托盘图标，避免二进制资源。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2f6fed"))
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(24)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "OCR")
    p.end()
    return QIcon(pm)


def _load_bg() -> QPixmap:
    """app/assets/bg.png，缺失时返回空 QPixmap（回退纯色背景）。"""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "bg.png"
    )
    return QPixmap(path)


def _running(worker) -> bool:
    """线程是否还在跑；C++ 对象已被销毁时不能调用 isRunning()（会抛 RuntimeError）。"""
    try:
        return worker is not None and worker.isRunning()
    except RuntimeError:
        return False


def _retire(worker) -> None:
    """线程结束后释放 C++ 对象。

    不能在 done 槽里直接丢引用：run() 里 emit 之后才 return，这一刻线程可能
    仍处于 running 状态，析构会触发 "QThread: Destroyed while thread is still
    running" 直接 abort。统一等 finished 再 deleteLater。
    """
    if worker is None:
        return
    try:
        if worker.isFinished():
            worker.deleteLater()
        else:
            worker.finished.connect(worker.deleteLater)
    except RuntimeError:
        pass


class BgCentral(QWidget):
    """壁纸背景中央控件：按窗口尺寸 cover 贴合（等比放大裁切、居中、无变形），不透明度取自 config.BG_ALPHA。"""

    def __init__(self, bg: QPixmap) -> None:
        super().__init__()
        self._bg = bg
        self._scaled: tuple[tuple[int, int], QPixmap] | None = None

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._bg.isNull():
            super().paintEvent(event)
            return
        w, h = self.width(), self.height()
        if self._scaled is None or self._scaled[0] != (w, h):
            # 按当前窗口尺寸缩放并缓存（cover：等比放大铺满后居中裁切）
            s = max(w / self._bg.width(), h / self._bg.height())
            self._scaled = (
                (w, h),
                self._bg.scaled(
                    int(self._bg.width() * s) + 1,
                    int(self._bg.height() * s) + 1,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                ),
            )
        pm = self._scaled[1]
        painter = QPainter(self)
        painter.setOpacity(config.BG_ALPHA)
        painter.drawPixmap((w - pm.width()) // 2, (h - pm.height()) // 2, pm)
        painter.end()
        super().paintEvent(event)


class EnginePreloader(QThread):
    """后台预热 OCR 模型，让首次截图秒出结果。"""

    fail = Signal(str)

    def run(self) -> None:
        try:
            get_engine().warmup()
        except Exception as exc:  # noqa: BLE001
            # 模型缺失/磁盘不可写/下载失败：不吞掉，交给主窗口提示
            self.fail.emit(str(exc))


class OcrWorker(QThread):
    done = Signal(str)
    fail = Signal(str)
    progress = Signal(int, int, str)  # (已完成, 总数, 当前文件名)，仅批量识别用

    def __init__(self, image=None, files: list[tuple[str, bytes]] | None = None,
                 paths: list[str] | None = None) -> None:
        super().__init__()
        self._image = image
        self._files = files or []  # 拖拽的图片文件 [(文件名, 字节)]
        self._paths = paths or []  # 批量识别：只传路径，由线程逐张读取
        self._cancelled = False

    def cancel(self) -> None:
        """请求停止（退出程序时用）：逐张处理，下一次循环检查即返回。"""
        self._cancelled = True

    def run(self) -> None:
        try:
            if self._paths:
                # 逐张读盘：内存峰值从「全部图片之和」降到「单张 + 结果文本」
                parts: list[str] = []
                total = len(self._paths)
                multi = total > 1
                for i, path in enumerate(self._paths):
                    if self._cancelled:
                        return
                    name = os.path.basename(path)
                    self.progress.emit(i + 1, total, name)
                    try:
                        with open(path, "rb") as f:
                            data = f.read()
                    except OSError as exc:
                        parts.append(
                            f"== {name} ==\n[读取失败] {exc}" if multi
                            else f"[读取失败] {name}：{exc}"
                        )
                        continue
                    text = get_engine().recognize_bytes(data)
                    parts.append(f"== {name} ==\n{text}" if multi else text)
                self.done.emit("\n\n".join(parts))
            elif self._files:
                parts = []
                multi = len(self._files) > 1
                for name, data in self._files:
                    if self._cancelled:
                        return
                    text = get_engine().recognize_bytes(data)
                    parts.append(f"== {name} ==\n{text}" if multi else text)
                self.done.emit("\n\n".join(parts))
            else:
                self.done.emit(get_engine().recognize_image(self._image))
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))


class ExportWorker(QThread):
    """后台导出：大批量 PDF/docx 在主线程同步渲染会把界面冻住。"""

    done = Signal(str)  # 输出路径
    fail = Signal(str)

    def __init__(self, path: str, text: str) -> None:
        super().__init__()
        self._path = path
        self._text = text

    def run(self) -> None:
        try:
            export_text(self._path, self._text)
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))
        else:
            self.done.emit(self._path)


class TableWorker(QThread):
    """表格识别线程：返回行列矩阵。"""

    done = Signal(list)  # list[list[str]]
    fail = Signal(str)

    def __init__(self, image) -> None:
        super().__init__()
        self._image = image

    def run(self) -> None:
        try:
            import numpy as np
            from PySide6.QtGui import QImage

            img = self._image.convertToFormat(QImage.Format_BGR888)
            h, w, stride = img.height(), img.width(), img.bytesPerLine()
            raw = np.frombuffer(bytes(img.constBits()), np.uint8)
            if stride == w * 3:
                arr = raw.reshape(h, w, 3)
            else:
                arr = raw.reshape(h, stride)[:, : w * 3].reshape(h, w, 3)
            self.done.emit(get_engine().recognize_table(arr))
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))


class HotkeyBridge(QObject):
    """keyboard 回调在监听线程，通过信号切回 Qt 主线程。"""

    triggered = Signal()


class MainWindow(QMainWindow):
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}

    def __init__(self, preload: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(f"{config.APP_TITLE} · v{config.APP_VERSION}")
        self.resize(640, 540)
        self.setAcceptDrops(True)  # 拖拽图片文件批量识别（Umi-OCR 批量 OCR）
        self._overlay: CaptureOverlay | None = None
        self._worker: OcrWorker | None = None
        self._table_worker: TableWorker | None = None
        self._pdf_worker: PdfWorker | None = None
        self._pdf_dlg: QProgressDialog | None = None
        self._pins: list[PinWindow] = []  # 贴图窗口可同时存在多个
        self._translate_dlg: TranslateDialog | None = None
        self._capture_translate = False  # 本次框选是否用于截屏翻译
        self._capture_long = False  # 本次框选是否用于长截图
        self._capture_table = False  # 本次框选是否用于表格识别
        self._capture_pin = False  # 本次框选是否用于截图贴图
        self._longshot_worker: StitchWorker | None = None
        self._longshot_bar: LongShotBar | None = None
        self._longshot_dlg: LongShotDialog | None = None
        self._preview: PreviewPopup | None = None
        self._history_bad = 0  # 读取时跳过的损坏记录数；-1 表示整个文件无法解析
        self._history: list[dict] = self._load_history()
        self._history_sig = self._history_signature()
        # 最后一次「注册成功」的热键组合：重注册失败时回滚到它，而不是回滚到刚改坏的值
        self._active_hotkeys: tuple[str, str, str] = (
            config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG
        )
        self._batch_files: list[str] = []  # 批量识别待处理队列
        self._batch_worker: OcrWorker | None = None
        self._export_worker: ExportWorker | None = None
        self._export_dlg: QProgressDialog | None = None
        self._export_cancelled = False
        self._quit_waiting: list = []  # 退出时还在跑的线程，全部结束后才真正 quit

        self._build_ui()
        self._build_tray()
        self._preload_wanted = preload
        self._preload: EnginePreloader | None = None
        self._services_started = False
        # 热键注册（keyboard 库约 0.5s）和模型预热都不在构造里做：
        # 由 main() 在窗口首次绘制之后调用 start_services()，窗口才能秒开

    def start_services(self) -> None:
        """窗口显示之后再做后台活儿：注册全局热键 + 预热 OCR 模型（幂等）。"""
        if self._services_started:
            return
        self._services_started = True
        QTimer.singleShot(0, self._deferred_start)

    def _deferred_start(self) -> None:
        self._register_hotkey()
        if self._hotkey_error:
            self.statusBar().showMessage(self._hotkey_error, 15000)
        if self._preload_wanted and self._preload is None:
            self._preload = EnginePreloader()
            self._preload.fail.connect(self._on_preload_fail)
            self._preload.start()

    def _on_preload_fail(self, msg: str) -> None:
        """预热失败要让人知道：否则首次识别才发现模型加载不了。"""
        self.statusBar().showMessage(f"识别模型预热失败：{msg}（首次识别会重新尝试）", 15000)

    # ---- UI ----
    # Umi-OCR 风格：扁平卡片 + 圆角 + 蓝色主色调，标签页组织功能
    STYLE = """
    QTabWidget::pane { border: 1px solid rgba(60,60,60,45); border-radius: 6px;
        background: rgba(255,255,255,150); top: -1px; }
    QTabBar::tab { padding: 6px 18px; margin-right: 4px; border-radius: 6px;
        color: #555; background: transparent; }
    QTabBar::tab:selected { background: rgba(255,255,255,220); color: #1e6fe8;
        font-weight: bold; border: 1px solid rgba(60,60,60,45); }
    QTabBar::tab:hover:!selected { background: rgba(255,255,255,120); }
    QPushButton { background: rgba(255,255,255,220); border: 1px solid rgba(60,60,60,60);
        border-radius: 6px; padding: 6px 14px; }
    QPushButton:hover { border-color: #1e6fe8; color: #1e6fe8; }
    QLineEdit { background: rgba(255,255,255,210); border: 1px solid rgba(60,60,60,60);
        border-radius: 6px; padding: 5px 8px; }
    QListWidget { background: rgba(255,255,255,190); border: 1px solid rgba(60,60,60,50);
        border-radius: 6px; alternate-background-color: rgba(243,248,255,180); }
    QListWidget::item { padding: 3px; }
    QListWidget::item:selected { background: rgba(47,111,237,70); color: #1a1a1a; }
    QStatusBar { background: rgba(255,255,255,160); color: #666; }
    """

    def _build_ui(self) -> None:
        central = BgCentral(_load_bg())
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)

        # Umi-OCR 标签页框架：截图识别 / 批量识别，右上角窗口置顶开关
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.btn_topmost = QPushButton("置顶")
        self.btn_topmost.setCheckable(True)
        self.btn_topmost.setCursor(Qt.PointingHandCursor)
        self.btn_topmost.setFixedHeight(26)
        self.btn_topmost.setToolTip("窗口置顶显示（Umi-OCR 同款）")
        self.btn_topmost.toggled.connect(self._on_topmost_toggled)
        self.tabs.setCornerWidget(self.btn_topmost, Qt.TopRightCorner)
        outer.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_capture_page(), "🔍 截图识别")
        self._batch_page = self._build_batch_page()
        self.tabs.addTab(self._batch_page, "📦 批量识别")

        self.setStyleSheet(self.STYLE)
        self.setCentralWidget(central)

        self.btn_capture.clicked.connect(self.start_capture)
        self.btn_translate.clicked.connect(lambda: self.start_capture(translate=True))
        self.btn_long.clicked.connect(lambda: self.start_capture(long=True))
        self.btn_table.clicked.connect(self._start_table_capture)
        self.btn_pin.clicked.connect(lambda: self.start_capture(pin=True))
        self.btn_pdf.clicked.connect(self._start_pdf_ocr)
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_copy.clicked.connect(self._copy_selected)
        self.btn_export.clicked.connect(self._export_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_clear.clicked.connect(self._clear_history)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        # 单击条目浮窗预览完整内容（替代原长悬浮，避免误触发）
        self.list.itemClicked.connect(self._on_item_clicked)
        self.btn_batch_add.clicked.connect(self._on_batch_add)
        self.btn_batch_clear.clicked.connect(self._on_batch_clear)
        self.btn_batch_start.clicked.connect(self._on_batch_start)
        self._refresh_list()
        if self._history_bad:
            if self._history_bad > 0:
                msg = f"历史记录有 {self._history_bad} 条内容损坏，已跳过（原文件保留）"
            else:
                msg = "历史记录文件无法解析，已从空历史启动（原文件未改动）"
            self.statusBar().showMessage(msg, 12000)

    def _build_capture_page(self) -> QWidget:
        """标签页 1：截图识别（提示 + 功能按钮 + 历史记录）。"""
        page = QWidget()
        layout = QVBoxLayout(page)

        self.tip = QLabel(self._tip_html())
        self.tip.setWordWrap(True)
        self.tip.setTextFormat(Qt.RichText)
        self.tip.setStyleSheet(
            "QLabel { background: rgba(255,255,255,185);"
            " border: 1px solid rgba(60,60,60,50); border-radius: 6px;"
            " padding: 8px 10px; }"
        )
        layout.addWidget(self.tip)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索历史记录...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh_list)
        layout.addWidget(self.search)

        row = QHBoxLayout()
        self.btn_capture = QPushButton("立即截图")
        self.btn_translate = QPushButton("截屏翻译")
        self.btn_long = QPushButton("长截图")
        self.btn_table = QPushButton("识别表格")
        self.btn_pin = QPushButton("截图贴图")
        self.btn_pdf = QPushButton("PDF识别")
        self.btn_settings = QPushButton("设置")
        self.btn_capture.setStyleSheet("font-weight: bold;")
        for b in (
            self.btn_capture, self.btn_translate, self.btn_long,
            self.btn_table, self.btn_pin, self.btn_pdf,
        ):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.btn_settings)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_copy = QPushButton("复制所选")
        self.btn_export = QPushButton("导出所选...")
        self.btn_delete = QPushButton("删除所选")
        self.btn_clear = QPushButton("清空历史")
        for b in (self.btn_copy, self.btn_export, self.btn_delete, self.btn_clear):
            row2.addWidget(b)
        row2.addStretch(1)
        layout.addLayout(row2)

        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(True)
        layout.addWidget(self.list, 1)
        return page

    def _build_batch_page(self) -> QWidget:
        """标签页 2：批量识别（Umi-OCR 批量OCR 页：文件队列 + 开始识别）。"""
        page = QWidget()
        layout = QVBoxLayout(page)

        hint = QLabel(
            "把图片文件或整个文件夹<b>拖进本窗口</b>加入队列（自动递归收集，上限 500 张），"
            "或点「添加图片...」选择文件；点击「开始识别」逐张识别，结果进入历史记录。"
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.RichText)
        hint.setStyleSheet(
            "QLabel { background: rgba(255,255,255,185);"
            " border: 1px solid rgba(60,60,60,50); border-radius: 6px;"
            " padding: 8px 10px; }"
        )
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.btn_batch_add = QPushButton("添加图片...")
        self.btn_batch_start = QPushButton("开始识别")
        self.btn_batch_start.setStyleSheet("font-weight: bold;")
        self.btn_batch_clear = QPushButton("清空列表")
        self.batch_status = QLabel("队列空闲")
        row.addWidget(self.btn_batch_add)
        row.addWidget(self.btn_batch_start)
        row.addWidget(self.btn_batch_clear)
        row.addStretch(1)
        row.addWidget(self.batch_status)
        layout.addLayout(row)

        self.batch_list = QListWidget()
        self.batch_list.setWordWrap(True)
        self.batch_list.setAlternatingRowColors(True)
        self.batch_list.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        layout.addWidget(self.batch_list, 1)
        return page

    def _on_topmost_toggled(self, checked: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        if self.isVisible():
            self.show()
        self.btn_topmost.setText("已置顶" if checked else "置顶")

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self)
        menu = QMenu()
        act_capture = QAction("立即截图", menu)
        act_translate = QAction("截屏翻译", menu)
        act_longshot = QAction("长截图", menu)
        act_table = QAction("识别表格", menu)
        act_pin = QAction("截图贴图", menu)
        act_pdf = QAction("PDF识别...", menu)
        act_show = QAction("显示历史窗口", menu)
        act_settings = QAction("设置...", menu)
        act_quit = QAction("退出", menu)
        act_capture.triggered.connect(self.start_capture)
        act_translate.triggered.connect(lambda: self.start_capture(translate=True))
        act_longshot.triggered.connect(lambda: self.start_capture(long=True))
        act_table.triggered.connect(self._start_table_capture)
        act_pin.triggered.connect(lambda: self.start_capture(pin=True))
        act_pdf.triggered.connect(self._start_pdf_ocr)
        act_show.triggered.connect(self._show_window)
        act_settings.triggered.connect(self._open_settings)
        act_quit.triggered.connect(self._quit)
        act_autocopy = QAction("识别后自动复制", menu)
        act_autocopy.setCheckable(True)
        act_autocopy.setChecked(config.AUTO_COPY)
        act_autocopy.toggled.connect(
            lambda checked: setattr(config, "AUTO_COPY", checked)
        )
        act_compact = QAction("中文智能排版（去多余空格）", menu)
        act_compact.setCheckable(True)
        act_compact.setChecked(config.CJK_COMPACT)
        act_compact.toggled.connect(
            lambda checked: setattr(config, "CJK_COMPACT", checked)
        )
        menu.addAction(act_capture)
        menu.addAction(act_translate)
        menu.addAction(act_longshot)
        menu.addAction(act_table)
        menu.addAction(act_pin)
        menu.addAction(act_pdf)
        menu.addAction(act_show)
        menu.addAction(act_autocopy)
        menu.addAction(act_compact)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(config.APP_NAME)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _register_hotkey(self) -> bool:
        """注册全局热键，返回是否全部成功；失败原因写入 self._hotkey_error。"""
        self._hotkey_error = ""
        try:
            import keyboard
        except Exception as exc:  # noqa: BLE001
            self._hotkey_error = f"全局热键不可用（{exc}），请用按钮/托盘菜单触发"
            return False

        def _bind(hotkey: str, bridge: "HotkeyBridge") -> bool:
            try:
                keyboard.add_hotkey(hotkey, bridge.triggered.emit)
                return True
            except Exception:  # noqa: BLE001
                return False

        self._hotkey_bridge = HotkeyBridge()
        self._hotkey_bridge.triggered.connect(self.start_capture)
        ok1 = _bind(config.HOTKEY, self._hotkey_bridge)

        # 截屏翻译热键：框选 → 识别 → 自动弹出翻译
        self._hotkey_tr_bridge = HotkeyBridge()
        self._hotkey_tr_bridge.triggered.connect(
            lambda: self.start_capture(translate=True)
        )
        ok2 = _bind(config.TRANSLATE_HOTKEY, self._hotkey_tr_bridge)

        # 长截图热键：框选 → 滚动采集 → 拼接预览
        self._hotkey_long_bridge = HotkeyBridge()
        self._hotkey_long_bridge.triggered.connect(
            lambda: self.start_capture(long=True)
        )
        ok3 = _bind(config.HOTKEY_LONG, self._hotkey_long_bridge)

        if not (ok1 and ok2 and ok3):
            self._hotkey_error = self._hotkey_fail_text()
            return False
        self._active_hotkeys = (
            config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG
        )
        return True

    @staticmethod
    def _hotkey_fail_text() -> str:
        """按平台给排查方向：Windows 用户看到「Linux 需 root」只会更困惑。"""
        if sys.platform == "win32":
            return "全局热键注册失败：可能与其他程序冲突，请在设置里换一个组合"
        if sys.platform == "darwin":
            return (
                "全局热键注册失败：请在「系统设置 → 隐私与安全性 → 辅助功能」"
                "中允许本程序，或换一个组合"
            )
        return "全局热键注册失败：Linux 需要 root 权限，或该组合已被其他程序占用"

    # ---- 截图流程 ----
    def _overlay_alive(self) -> bool:
        """遮罩是否还在（被 Alt+F4 关掉后 Python 包装对象已失效，必须清掉引用）。"""
        if self._overlay is None:
            return False
        try:
            return self._overlay.isVisible()
        except RuntimeError:
            self._overlay = None
            self._capture_translate = False
            self._capture_long = False
            self._capture_table = False
            self._capture_pin = False
            return False

    def _longshot_alive(self) -> bool:
        """长截图控制条是否还在（同上，避免异常关闭后永久卡住截图功能）。"""
        if self._longshot_bar is None:
            return False
        try:
            return self._longshot_bar.isVisible()
        except RuntimeError:
            self._longshot_bar = None
            return False

    def _new_overlay(self):
        """创建截图遮罩；抓屏失败（远程桌面断开、显示驱动异常）时给提示而不是崩在槽里。"""
        try:
            return CaptureOverlay()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, config.APP_NAME, f"截屏失败：{exc}")
            return None

    def start_capture(self, translate: bool = False, long: bool = False,
                      pin: bool = False) -> None:
        if pin and not config.OCR_PIN:
            QMessageBox.information(
                self, config.APP_NAME, "截图贴图未开启，请在「设置 → 功能」中勾选。"
            )
            return
        if self._overlay_alive():
            return
        if not self._check_ocr_busy():
            return
        if self._longshot_alive():
            self.statusBar().showMessage("长截图会话进行中，请先完成或取消", 3000)
            return
        self._capture_translate = translate
        self._capture_long = long
        self._capture_pin = pin
        self._capture_table = False
        self._overlay = self._new_overlay()
        if self._overlay is None:
            return
        if long:
            self._overlay.regionSelected.connect(self._on_region_selected)
        else:
            self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._on_capture_cancelled)
        self._overlay.start()

    def _check_ocr_busy(self) -> bool:
        """任一 OCR 类线程运行中返回 False 并提示。"""
        for name, w in (
            ("上一次识别", self._worker),
            ("表格识别", self._table_worker),
            ("PDF 识别", self._pdf_worker),
            ("批量识别", self._batch_worker),
            ("长截图", self._longshot_worker),
        ):
            if _running(w):
                self.statusBar().showMessage(f"{name}进行中，请稍候", 3000)
                return False
        return True

    def _start_table_capture(self) -> None:
        """表格识别：未开启时引导到设置。"""
        if not config.OCR_TABLE:
            QMessageBox.information(
                self, config.APP_NAME, "表格识别未开启，请在「设置 → 功能」中勾选。"
            )
            return
        if self._overlay_alive():
            return
        if not self._check_ocr_busy():
            return
        if self._longshot_alive():
            self.statusBar().showMessage("长截图会话进行中，请先完成或取消", 3000)
            return
        self._capture_translate = False
        self._capture_long = False
        self._capture_pin = False
        self._capture_table = True
        self._overlay = self._new_overlay()
        if self._overlay is None:
            self._capture_table = False
            return
        self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._on_capture_cancelled)
        self._overlay.start()

    def _on_capture_cancelled(self) -> None:
        self._overlay = None
        self._capture_translate = False
        self._capture_long = False
        self._capture_table = False
        self._capture_pin = False

    def _on_captured(self, image) -> None:
        self._overlay = None
        if self._capture_pin:
            # 截图贴图：钉在桌面置顶显示，不进入 OCR 流程
            self._capture_pin = False
            self._add_pin(QPixmap.fromImage(image))
            return
        translate = self._capture_translate
        self._capture_translate = False
        if self._capture_table:
            self._capture_table = False
            self.statusBar().showMessage("表格识别中...")
            self._table_worker = TableWorker(image)
            self._table_worker.done.connect(self._on_table_done)
            self._table_worker.fail.connect(self._on_ocr_fail)
            self._table_worker.start()
            return
        self.statusBar().showMessage("识别中...")
        self._worker = OcrWorker(image)
        # 翻译标志在连接时绑定：避免与图片队列识别共用状态导致串扰
        self._worker.done.connect(lambda text, tr=translate: self._on_ocr_done(text, tr))
        self._worker.fail.connect(self._on_ocr_fail)
        self._worker.start()

    def _add_pin(self, pixmap: QPixmap) -> None:
        """创建一个新的贴图窗口并清理已关闭的旧窗口。"""
        alive: list[PinWindow] = []
        for p in self._pins:
            try:
                if p.isVisible():
                    alive.append(p)
            except RuntimeError:
                # 贴图窗口带 WA_DeleteOnClose，关闭后 C++ 对象已销毁，
                # 残留的 Python 包装对象再调 isVisible() 会抛 RuntimeError
                continue
        self._pins = alive
        pin = PinWindow(pixmap)
        pin.setAttribute(Qt.WA_DeleteOnClose)
        self._pins.append(pin)
        pin.move(QCursor.pos())
        pin.show()
        self.statusBar().showMessage(
            "贴图已创建：拖动移动 / 滚轮缩放 / Ctrl+滚轮调透明度 / 双击关闭", 5000
        )

    # ---- PDF 整档识别 ----
    def _start_pdf_ocr(self) -> None:
        if not config.OCR_PDF:
            QMessageBox.information(
                self, config.APP_NAME, "PDF 识别未开启，请在「设置 → 功能」中勾选。"
            )
            return
        if self._overlay_alive() or not self._check_ocr_busy():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要识别的 PDF", "", "PDF 文档 (*.pdf)"
        )
        if not path:
            return
        self._pdf_ocr_path(path)

    def _on_pdf_progress(self, page: int, total: int) -> None:
        if self._pdf_dlg is not None:
            self._pdf_dlg.setMaximum(total)
            self._pdf_dlg.setValue(page)
            self._pdf_dlg.setLabelText(f"正在识别第 {page} / {total} 页...")

    def _on_pdf_done(self, text: str) -> None:
        self._close_pdf_dlg()
        self._on_ocr_done(text)

    def _on_pdf_fail(self, msg: str) -> None:
        self._close_pdf_dlg()
        self.statusBar().clearMessage()
        QMessageBox.warning(self, config.APP_NAME, f"PDF 识别失败：{msg}")

    def _on_pdf_cancelled(self) -> None:
        self._close_pdf_dlg()
        self.statusBar().showMessage("PDF 识别已取消", 4000)

    def _on_pdf_cancel_clicked(self) -> None:
        if self._pdf_worker is not None:
            self._pdf_worker.cancel()
        self.statusBar().showMessage("正在取消 PDF 识别...", 3000)

    def _close_pdf_dlg(self) -> None:
        if self._pdf_dlg is not None:
            dlg = self._pdf_dlg
            self._pdf_dlg = None
            # 先断开 canceled：reset() 在某些平台会触发 canceled，
            # 那会在识别成功时误调 worker.cancel() 并覆盖状态栏文字
            try:
                dlg.canceled.disconnect()
            except (RuntimeError, TypeError):
                pass
            dlg.reset()
            dlg.close()
        self.statusBar().clearMessage()

    def _on_ocr_done(self, text: str, translate: bool = False) -> None:
        self.statusBar().clearMessage()
        text = text.strip()
        if not text:
            self.tray.showMessage(
                config.APP_NAME, "未识别到文字", QSystemTrayIcon.Information, 2000
            )
            return
        if config.CJK_COMPACT:
            text = compact_cjk(text)
        if translate:
            # 截屏翻译：识别结果送入翻译窗口并自动翻译（原图文仍记入历史）
            self._add_history(text)
            self._open_translate(text)
            return
        if config.AUTO_COPY:
            QApplication.clipboard().setText(text)
            self.tray.showMessage(
                config.APP_NAME, f"已复制 {len(text)} 个字符", QSystemTrayIcon.Information, 2000
            )
        self._add_history(text)

    def _on_ocr_fail(self, msg: str) -> None:
        self.statusBar().clearMessage()
        QMessageBox.warning(self, config.APP_NAME, f"OCR 失败：{msg}")

    # ---- 表格识别 ----
    def _on_table_done(self, rows: list) -> None:
        self.statusBar().clearMessage()
        rows = [
            ["" if c is None else str(c) for c in r]
            for r in rows
            if isinstance(r, (list, tuple))
            and any(c is not None and str(c).strip() for c in r)
        ]
        if not rows:
            self.tray.showMessage(
                config.APP_NAME, "未识别到表格内容", QSystemTrayIcon.Information, 2000
            )
            return
        tsv = "\n".join("\t".join(row) for row in rows)
        self._add_history(tsv)
        QApplication.clipboard().setText(tsv)
        default = os.path.join(
            os.path.expanduser("~"),
            f"表格识别_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "保存表格为 Excel", default, "Excel 工作簿 (*.xlsx)"
        )
        if path:
            path = ensure_xlsx_suffix(path)
            try:
                export_xlsx(path, rows)
                self.tray.showMessage(
                    config.APP_NAME,
                    f"表格已导出 {os.path.basename(path)}（内容已复制）",
                    QSystemTrayIcon.Information, 2500,
                )
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, config.APP_NAME, f"导出失败：{exc}")
        else:
            self.tray.showMessage(
                config.APP_NAME, "表格内容已复制到剪贴板", QSystemTrayIcon.Information, 2000
            )

    # ---- 长截图 ----
    def _on_region_selected(self, x: int, y: int, w: int, h: int,
                            logical=None) -> None:
        self._overlay = None
        self._capture_translate = False
        self._capture_long = False
        from app.core.stitcher import StitchWorker  # 延迟导入：cv2 + mss 约 0.35s

        self._longshot_worker = StitchWorker((x, y, w, h))
        self._longshot_worker.progress.connect(self._on_longshot_progress)
        self._longshot_worker.done.connect(self._on_longshot_done)
        self._longshot_worker.fail.connect(self._on_longshot_fail)
        # 控制条按逻辑坐标摆位：物理坐标在 125%/150% 缩放下会偏到别处
        bar = LongShotBar((x, y, w, h), logical)
        bar.startClicked.connect(self._on_longshot_start)
        bar.stopClicked.connect(self._on_longshot_stop)
        bar.cancelClicked.connect(self._on_longshot_cancel)
        self._longshot_bar = bar
        bar.show()
        self.statusBar().showMessage(
            "长截图：点控制条「开始」滚动采集，滚到页面底部会自动结束", 5000
        )

    def _on_longshot_start(self) -> None:
        w = self._longshot_worker
        if w is None or _running(w):
            return
        w.start()
        try:
            if self._longshot_bar is not None:
                self._longshot_bar.set_running(True)
        except RuntimeError:  # 控制条刚被关掉
            self._longshot_bar = None

    def _on_longshot_stop(self) -> None:
        if self._longshot_worker is not None:
            self._longshot_worker.stop()

    def _on_longshot_progress(self, text: str) -> None:
        try:
            if self._longshot_bar is not None:
                self._longshot_bar.set_status(text)
        except RuntimeError:  # 控制条刚被关掉
            self._longshot_bar = None

    def _on_longshot_done(self, image: QImage) -> None:
        w = self._longshot_worker
        self._longshot_worker = None
        self._close_longshot_bar()
        _retire(w)
        self._open_longshot_dialog(image)

    def _on_longshot_fail(self, msg: str) -> None:
        w = self._longshot_worker
        self._longshot_worker = None
        self._close_longshot_bar()
        _retire(w)
        self.tray.showMessage(
            config.APP_NAME, f"长截图失败：{msg}", QSystemTrayIcon.Warning, 3000
        )

    def _on_longshot_cancel(self) -> None:
        w = self._longshot_worker
        self._close_longshot_bar()
        if w is None:
            return
        # 断开信号：取消后线程剩余结果不再弹窗
        try:
            w.progress.disconnect()
            w.done.disconnect()
            w.fail.disconnect()
        except (RuntimeError, TypeError):
            pass
        if _running(w):
            w.stop()
            if not w.wait(5000):
                # 还卡在 mss 抓屏里：不能丢引用，否则 QThread 运行中被销毁会崩进程。
                # 保留引用，等它自己结束后再回收。
                self._longshot_worker = w
                w.finished.connect(lambda: self._on_longshot_worker_finished(w))
                _retire(w)
                self.statusBar().showMessage("长截图正在退出采集，请稍候", 5000)
                return
        self._longshot_worker = None

    def _on_longshot_worker_finished(self, w) -> None:
        if self._longshot_worker is w:
            self._longshot_worker = None

    def _close_longshot_bar(self) -> None:
        """关闭控制条；已经销毁（被 Alt+F4）时安静跳过，不能让槽抛异常。"""
        bar = self._longshot_bar
        self._longshot_bar = None
        if bar is None:
            return
        try:
            bar.dismiss()
        except RuntimeError:
            pass

    def _open_longshot_dialog(self, image: QImage) -> None:
        if self._longshot_dlg is not None:
            self._longshot_dlg.close()
            self._longshot_dlg = None
        dlg = LongShotDialog(image)
        dlg.ocrRequested.connect(self._on_longshot_ocr)
        dlg.finished.connect(self._on_longshot_dlg_finished)
        self._longshot_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _on_longshot_dlg_finished(self) -> None:
        self._longshot_dlg = None

    def _on_longshot_ocr(self, image: QImage, translate: bool) -> None:
        if not self._check_ocr_busy():
            return
        self.statusBar().showMessage("识别中...")
        self._worker = OcrWorker(image)
        self._worker.done.connect(
            lambda text, tr=translate: self._on_ocr_done(text, tr)
        )
        self._worker.fail.connect(self._on_ocr_fail)
        self._worker.start()

    # ---- 翻译 ----
    def _open_translate(self, text: str = "") -> None:
        """打开翻译窗口；带文本时自动翻译。"""
        if self._translate_dlg is None:
            self._translate_dlg = TranslateDialog(self)
        self._translate_dlg.open_with(text)
        self._translate_dlg.show()
        self._translate_dlg.raise_()
        self._translate_dlg.activateWindow()

    # ---- 快捷键设置 ----
    def _tip_html(self) -> str:
        """顶部提示卡：快捷键动态取自 config（设置后自动更新）。"""
        return (
            f"按 <b>{config.HOTKEY.upper()}</b> 截图识别复制　·　"
            f"<b>{config.TRANSLATE_HOTKEY.upper()}</b> 截屏翻译　·　"
            f"<b>{config.HOTKEY_LONG.upper()}</b> 滚动长截图<br>"
            "<span style='color:#555'>"
            "框选后自动识别 / Esc 取消 / 「设置」可改快捷键与识别选项 / "
            "拖拽图片、文件夹到「批量识别」页排队识别 / 拖入 PDF 整档识别 / 长截图可识别并翻译</span>"
        )

    def _open_settings(self) -> None:
        dlg = SettingsDialog(
            (config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG),
            {
                "lang": config.OCR_LANG,
                "use_cls": config.OCR_USE_CLS,
                "enhance": config.OCR_ENHANCE,
                "para": config.OCR_MERGE_PARA,
                "qr": config.OCR_QR,
                "table": config.OCR_TABLE,
                "gpu": config.OCR_GPU,
                "filter_kw": config.OCR_FILTER_KW,
                "filter_keywords": config.OCR_FILTER_KEYWORDS,
                "pdf": config.OCR_PDF,
                "pin": config.OCR_PIN,
                "langs": config.OCR_LANGS,
            },
            self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        hk, htr, hlong = dlg.hotkeys()
        if not (hk and htr and hlong):
            QMessageBox.warning(self, config.APP_NAME, "快捷键不能为空")
            return
        if len({hk, htr, hlong}) != 3:
            QMessageBox.warning(self, config.APP_NAME, "三个快捷键不能相同")
            return
        illegal = [
            name
            for name, value in (
                ("截图识别", hk), ("截屏翻译", htr), ("长截图", hlong)
            )
            if not config.is_valid_hotkey(value)
        ]
        if illegal:
            QMessageBox.warning(
                self, config.APP_NAME,
                "以下快捷键不合法：" + "、".join(illegal)
                + "\n\n请使用「Ctrl / Alt / Shift 等修饰键 + 一个普通键」的组合，"
                  "例如 Ctrl+Alt+Q。\n单键（如 A）会劫持全系统按键，因此不允许。",
            )
            return
        opts = dlg.ocr_options()
        engine_changed = (
            opts["lang"] != config.OCR_LANG
            or opts["use_cls"] != config.OCR_USE_CLS
            or opts["gpu"] != config.OCR_GPU
        )
        config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG = hk, htr, hlong
        config.OCR_LANG = opts["lang"]
        config.OCR_USE_CLS = opts["use_cls"]
        config.OCR_ENHANCE = opts["enhance"]
        config.OCR_MERGE_PARA = opts["para"]
        config.OCR_QR = opts["qr"]
        config.OCR_TABLE = opts["table"]
        config.OCR_GPU = opts["gpu"]
        config.OCR_FILTER_KW = opts["filter_kw"]
        config.OCR_FILTER_KEYWORDS = opts["filter_keywords"]
        config.OCR_PDF = opts["pdf"]
        config.OCR_PIN = opts["pin"]
        # 先试注册：注册失败会自动回滚 config 里的热键，避免把不可用的组合写进磁盘
        hotkeys_ok = self._reregister_hotkeys_safely()
        saved_ok = True
        try:
            config.save_settings(
                {
                    "hotkey_capture": config.HOTKEY,
                    "hotkey_translate": config.TRANSLATE_HOTKEY,
                    "hotkey_long": config.HOTKEY_LONG,
                    "ocr_lang": opts["lang"],
                    "ocr_use_cls": opts["use_cls"],
                    "ocr_enhance": opts["enhance"],
                    "ocr_para": opts["para"],
                    "ocr_qr": opts["qr"],
                    "ocr_table": opts["table"],
                    "ocr_gpu": opts["gpu"],
                    "ocr_filter_kw": opts["filter_kw"],
                    "ocr_filter_keywords": opts["filter_keywords"],
                    "ocr_pdf": opts["pdf"],
                    "ocr_pin": opts["pin"],
                }
            )
        except (OSError, TypeError, ValueError) as exc:
            saved_ok = False
            QMessageBox.warning(
                self, config.APP_NAME,
                f"设置保存失败（本次修改仍然生效，但重启后会丢失）：{exc}",
            )
        self.tip.setText(self._tip_html())
        if engine_changed:
            get_engine().reload()
        if not hotkeys_ok:
            self.statusBar().showMessage("设置已保存，但快捷键未生效（已恢复原设置）", 6000)
        elif not saved_ok:
            self.statusBar().showMessage("设置已生效，但未能写入磁盘（重启后会恢复原设置）", 6000)
        elif engine_changed:
            self.statusBar().showMessage("识别设置已更新，引擎已重载", 3000)
        else:
            self.statusBar().showMessage("设置已保存", 3000)

    def _reregister_hotkeys_safely(self) -> bool:
        """重新注册全局热键；失败自动恢复上一次成功的组合并提示，返回是否成功。"""
        old = self._active_hotkeys

        def _unhook() -> None:
            try:
                import keyboard

                keyboard.unhook_all()
            except Exception:  # noqa: BLE001
                pass

        _unhook()
        if self._register_hotkey():
            return True
        err = self._hotkey_error
        _unhook()
        config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG = old
        self._register_hotkey()  # 把原来的组合重新挂上
        QMessageBox.warning(
            self, config.APP_NAME,
            f"{err or '快捷键注册失败'}\n已自动恢复为原来的快捷键。",
        )
        return False

    # ---- 历史记录 ----
    def _load_history(self) -> list[dict]:
        """读取历史；跳过结构不合法的记录。

        只有「合法 JSON 但元素结构不对」时最危险：以前会让窗口构造抛异常，
        表现为双击程序没有任何窗口。这里逐条校验，坏记录直接跳过并计数。
        """
        self._history_bad = 0
        try:
            with open(config.HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except Exception:  # noqa: BLE001  文件被截断/编码损坏
            self._history_bad = -1
            return []
        if not isinstance(data, list):
            self._history_bad = -1
            return []
        clean: list[dict] = []
        for it in data:
            if not isinstance(it, dict):
                self._history_bad += 1
                continue
            text = it.get("text")
            if not isinstance(text, str) or not text.strip():
                self._history_bad += 1
                continue
            ts = it.get("time")
            clean.append({
                "time": ts if isinstance(ts, str) and ts else "未知时间",
                "text": text,
            })
        return clean

    @staticmethod
    def _history_signature():
        """磁盘历史文件的 (mtime, size)，用于判断「有没有被别的进程改过」。"""
        try:
            st = os.stat(config.HISTORY_FILE)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _save_history(self) -> bool:
        """原子写入历史，失败时提示而不是抛进 Qt 槽里静默消失。"""
        tmp = config.HISTORY_FILE + ".tmp"
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, config.HISTORY_FILE)  # 同分区原子替换，写入中断不会留半截文件
            self._history_sig = self._history_signature()
            return True
        except (OSError, TypeError, ValueError) as exc:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            self.statusBar().showMessage(f"历史保存失败：{exc}", 8000)
            return False

    @staticmethod
    def _history_key(item: dict) -> tuple[str, str]:
        return (str(item.get("time", "")), str(item.get("text", "")))

    def _merge_disk_history(self) -> None:
        """与磁盘现有记录合并（按「时间 + 文本」去重）。

        `_add_history` 是「内存全量重写」模型：万一真的跑了两个进程，
        后写的一方会把先写的记录抹掉。单实例锁是第一道防线，这里是第二道。
        """
        try:
            with open(config.HISTORY_FILE, encoding="utf-8") as f:
                disk = json.load(f)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(disk, list):
            return
        known = {self._history_key(it) for it in self._history}
        extra: list[dict] = []
        for it in disk:
            if not isinstance(it, dict):
                continue
            text = it.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            ts = it.get("time")
            entry = {"time": ts if isinstance(ts, str) and ts else "未知时间", "text": text}
            key = self._history_key(entry)
            if key not in known:
                known.add(key)
                extra.append(entry)
        if extra:
            self._history = sorted(
                self._history + extra, key=lambda it: it["time"], reverse=True
            )

    def _add_history(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._history.insert(
            0, {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "text": text}
        )
        if self._history_signature() != self._history_sig:
            # 磁盘被别人改过（例如真的多开了）才需要读回来合并；
            # 常规路径不读盘，避免大历史每次都多一次全量 JSON 解析
            self._merge_disk_history()
        del self._history[config.HISTORY_LIMIT:]
        self._save_history()
        self._refresh_list()

    def _refresh_list(self) -> None:
        kw = self.search.text().strip().lower()
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        for i, item in enumerate(self._history):
            # 第二道兜底：即使内存里混进了坏记录也不能让刷新抛异常
            text = item.get("text") if isinstance(item, dict) else None
            if not isinstance(text, str):
                continue
            if kw and kw not in text.lower():
                continue
            ts = item.get("time")
            if not isinstance(ts, str) or not ts:
                ts = "未知时间"
            preview = text.replace("\n", " ⏎ ")
            if len(preview) > 80:
                preview = preview[:80] + "…"
            it = QListWidgetItem(f"{ts}    {preview}")
            it.setData(Qt.UserRole, i)
            self.list.addItem(it)
        self.list.setUpdatesEnabled(True)

    # ---- 单击/双击预览完整内容 ----
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """单击条目：浮窗预览完整内容（点击触发，不再长悬浮）。"""
        self._show_preview(item, QCursor.pos(), 8000)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._copy_selected()
        self._show_preview(item, QCursor.pos(), 8000)

    def _show_preview(self, item: QListWidgetItem, global_pos, timeout_ms: int) -> None:
        idx = item.data(Qt.UserRole)
        if not isinstance(idx, int) or not (0 <= idx < len(self._history)):
            return
        if self._preview is None:
            self._preview = PreviewPopup()
        self._preview.show_text(self._history[idx]["text"], global_pos, timeout_ms)

    def _copy_selected(self) -> None:
        rows = sorted({i.data(Qt.UserRole) for i in self.list.selectedIndexes()})
        if not rows:
            return
        texts = [self._history[i]["text"] for i in rows if 0 <= i < len(self._history)]
        QApplication.clipboard().setText("\n".join(texts))
        self.tray.showMessage(
            config.APP_NAME, f"已复制 {len(texts)} 条记录", QSystemTrayIcon.Information, 1500
        )

    def _export_selected(self) -> None:
        """把选中的历史记录导出为 txt / docx / pdf / md（后台线程，界面不冻结）。"""
        if _running(self._export_worker):
            self.statusBar().showMessage("导出进行中，请稍候", 3000)
            return
        rows = sorted({i.data(Qt.UserRole) for i in self.list.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, config.APP_NAME, "请先在列表中选择要导出的记录")
            return
        texts = [self._history[i]["text"] for i in rows if 0 <= i < len(self._history)]
        text = "\n".join(texts)
        default = os.path.join(os.path.expanduser("~"), "SnapOCR导出.txt")
        path, selected = QFileDialog.getSaveFileName(
            self, "导出所选记录", default,
            "文本文件 (*.txt);;Word 文档 (*.docx);;PDF 文档 (*.pdf);;"
            "Markdown (*.md)",
        )
        if not path:
            return
        path = ensure_text_suffix(path, selected)
        if os.path.splitext(path)[1].lower() in (".pdf", ".docx") and len(text) > 200_000:
            # 渲染是 CPU 密集的：先打招呼，用户可以选择换 txt 或耐心等
            if QMessageBox.question(
                self, config.APP_NAME,
                f"导出内容约 {len(text) // 10000} 万字，生成该格式可能需要数十秒。\n"
                "导出在后台进行，期间界面仍可操作（可点进度框取消）。\n\n是否继续？",
            ) != QMessageBox.Yes:
                return
        self._export_cancelled = False
        self._export_dlg = QProgressDialog("正在导出，请稍候...", "取消", 0, 0, self)
        self._export_dlg.setWindowTitle("导出")
        self._export_dlg.setWindowModality(Qt.WindowModal)
        self._export_dlg.setMinimumDuration(400)  # 快速导出不闪一下框
        self._export_dlg.setMinimumWidth(320)
        self._export_dlg.canceled.connect(self._on_export_cancel)
        self._export_worker = ExportWorker(path, text)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.fail.connect(self._on_export_fail)
        self._export_worker.start()

    def _close_export_dlg(self) -> None:
        if self._export_dlg is not None:
            dlg = self._export_dlg
            self._export_dlg = None
            # 先断开 canceled：reset()/close() 在某些平台会触发 canceled，
            # 那会把「导出成功」误判成「用户取消」从而删掉刚生成的文件
            try:
                dlg.canceled.disconnect()
            except (RuntimeError, TypeError):
                pass
            dlg.reset()
            dlg.close()

    def _on_export_cancel(self) -> None:
        # 渲染无法中途打断：先标记，完成后把半成品文件删掉
        self._export_cancelled = True
        self.statusBar().showMessage("正在取消导出：结束后会删除未完成的文件", 5000)

    def _on_export_done(self, path: str) -> None:
        cancelled = self._export_cancelled
        self._close_export_dlg()
        if cancelled:
            try:
                os.remove(path)
            except OSError:
                pass
            self.statusBar().showMessage("已取消导出", 4000)
            return
        self.tray.showMessage(
            config.APP_NAME, f"已导出 {os.path.basename(path)}",
            QSystemTrayIcon.Information, 2000,
        )

    def _on_export_fail(self, msg: str) -> None:
        cancelled = self._export_cancelled
        self._close_export_dlg()
        if cancelled:
            self.statusBar().showMessage("已取消导出", 4000)
            return
        QMessageBox.warning(self, config.APP_NAME, f"导出失败：{msg}")

    def _delete_selected(self) -> None:
        rows = sorted(
            {i.data(Qt.UserRole) for i in self.list.selectedIndexes()}, reverse=True
        )
        if not rows:
            return
        for i in rows:
            del self._history[i]
        self._save_history()
        self._refresh_list()

    def _clear_history(self) -> None:
        if not self._history:
            return
        if QMessageBox.question(self, config.APP_NAME, "确定清空全部历史记录？") == QMessageBox.Yes:
            self._history.clear()
            self._save_history()
            self._refresh_list()

    # ---- 拖拽图片文件/PDF/文件夹批量识别 ----
    @staticmethod
    def _collect_images_from_dir(path: str) -> list[str]:
        """递归收集文件夹内所有图片（Umi-OCR 批量导入，上限 500 张防误拖大目录）。"""
        found: list[str] = []
        for root, _dirs, names in os.walk(path):
            for n in names:
                if os.path.splitext(n)[1].lower() in MainWindow.IMAGE_EXTS:
                    found.append(os.path.join(root, n))
                    if len(found) >= 500:
                        return found
        return found

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in self.IMAGE_EXTS or ext == ".pdf" or os.path.isdir(path):
                event.acceptProposedAction()
                return

    def dropEvent(self, event) -> None:  # noqa: N802
        """Umi-OCR 批量OCR 风格：图片/文件夹拖入只加入批量队列；PDF 仍立即识别。"""
        dirs: list[str] = []
        pdfs: list[str] = []
        images: list[str] = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if os.path.isdir(path):
                dirs.append(path)
            elif ext == ".pdf":
                pdfs.append(path)
            elif ext in self.IMAGE_EXTS:
                images.append(path)
        if not (dirs or pdfs or images):
            return
        for d in dirs:
            images.extend(self._collect_images_from_dir(d))
        if images:
            self._queue_batch(images)

        # 拖入了 PDF：一次识别一个，优先处理 PDF
        if pdfs:
            if not config.OCR_PDF:
                QMessageBox.information(
                    self, config.APP_NAME,
                    "PDF 识别未开启，请在「设置 → 功能」中勾选。",
                )
                return
            if len(pdfs) > 1:
                self.statusBar().showMessage("一次只能识别一个 PDF，已取第一个", 4000)
            if not self._check_ocr_busy():
                return
            self._pdf_ocr_path(pdfs[0])

    # ---- 批量识别（Umi-OCR 批量OCR 页风格）----
    def _queue_batch(self, paths: list[str]) -> None:
        """把图片加入批量队列（去重，上限 500 张）。"""
        known = set(self._batch_files)
        added = 0
        for p in paths:
            if p not in known and os.path.splitext(p)[1].lower() in self.IMAGE_EXTS:
                self._batch_files.append(p)
                known.add(p)
                added += 1
            if len(self._batch_files) >= 500:
                self.statusBar().showMessage("已达批量上限 500 张，超出部分已忽略", 4000)
                break
        self._refresh_batch_list()
        if added:
            self.tabs.setCurrentWidget(self._batch_page)
            self.batch_status.setText(f"队列 {len(self._batch_files)} 张，待识别")

    def _refresh_batch_list(self) -> None:
        self.batch_list.setUpdatesEnabled(False)
        self.batch_list.clear()
        for p in self._batch_files:
            self.batch_list.addItem(p)
        self.batch_list.setUpdatesEnabled(True)

    def _on_batch_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加要识别的图片", "",
            "图片文件 (%s);;全部文件 (*)"
            % " ".join("*" + e for e in sorted(self.IMAGE_EXTS)),
        )
        if paths:
            self._queue_batch(paths)

    def _on_batch_clear(self) -> None:
        if _running(self._batch_worker):
            return
        self._batch_files.clear()
        self._refresh_batch_list()
        self.batch_status.setText("队列空闲")

    def _on_batch_start(self) -> None:
        if not self._batch_files:
            self.batch_status.setText("队列为空，先拖入图片或点「添加图片...」")
            return
        if not self._check_ocr_busy():
            return
        # 只把路径交给线程，由它逐张读盘：500 张 1080p 以前会在 GUI 线程
        # 一次性读掉 600MB 并卡住 1 秒，现在内存峰值只有「单张 + 结果文本」
        paths = list(self._batch_files)
        self.batch_status.setText(f"批量识别中（{len(paths)} 张）...")
        self.btn_batch_start.setEnabled(False)
        self._batch_worker = OcrWorker(paths=paths)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.done.connect(self._on_batch_done)
        self._batch_worker.fail.connect(self._on_batch_fail)
        self._batch_worker.start()

    def _on_batch_progress(self, done: int, total: int, name: str) -> None:
        self.batch_status.setText(f"批量识别中 {done}/{total}：{name}")

    def _on_batch_done(self, text: str) -> None:
        self.btn_batch_start.setEnabled(True)
        self._on_ocr_done(text)
        self._batch_files.clear()
        self._refresh_batch_list()
        self.batch_status.setText("批量识别完成，结果已进入历史记录")

    def _on_batch_fail(self, msg: str) -> None:
        self.btn_batch_start.setEnabled(True)
        self.batch_status.setText("批量识别失败")
        QMessageBox.warning(self, config.APP_NAME, f"OCR 失败：{msg}")

    def _pdf_ocr_path(self, path: str) -> None:
        """对指定 PDF 启动识别（拖拽与文件对话框共用）。"""
        if self._overlay_alive() or not self._check_ocr_busy():
            return
        self.statusBar().showMessage(f"PDF 识别中：{os.path.basename(path)}")
        self._pdf_dlg = QProgressDialog("正在识别...", "取消", 0, 1, self)
        self._pdf_dlg.setWindowTitle("PDF 识别")
        self._pdf_dlg.setMinimumDuration(0)
        self._pdf_dlg.setMinimumWidth(320)
        self._pdf_dlg.canceled.connect(self._on_pdf_cancel_clicked)
        self._pdf_dlg.show()
        self._pdf_worker = PdfWorker(path, config.PDF_RENDER_SCALE)
        self._pdf_worker.progress.connect(self._on_pdf_progress)
        self._pdf_worker.done.connect(self._on_pdf_done)
        self._pdf_worker.fail.connect(self._on_pdf_fail)
        self._pdf_worker.cancelled.connect(self._on_pdf_cancelled)
        self._pdf_worker.start()

    # ---- 窗口/托盘行为 ----
    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_from_second_instance(self) -> None:
        """第二个进程启动时：把已存在的窗口带到前台，而不是开第二个实例。

        存在多个窗口（贴图、翻译框）时只处理主窗口，不打断贴图。
        """
        self._show_window()
        if self.isMinimized():
            self.showNormal()
        self.tray.showMessage(
            config.APP_NAME, "已在运行，已为你切回窗口", QSystemTrayIcon.Information, 2000
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                config.APP_NAME,
                "已最小化到托盘，热键继续可用",
                QSystemTrayIcon.Information,
                2000,
            )

    def _quit(self) -> None:
        try:
            import keyboard

            keyboard.unhook_all()
        except Exception:  # noqa: BLE001
            pass
        # 先请求所有能取消的线程收手：长截图停止注入滚轮、
        # PDF 逐页检查、批量识别逐张检查
        if _running(self._longshot_worker):
            self._longshot_worker.stop()
        if _running(self._pdf_worker):
            self._pdf_worker.cancel()
        if _running(self._batch_worker):
            self._batch_worker.cancel()

        pending = [
            w for w in (
                self._longshot_worker, self._pdf_worker, self._table_worker,
                self._batch_worker, self._preload, self._export_worker,
                self._worker, self._translate_worker(),
            ) if _running(w)
        ]
        # 正常收尾给 3 秒（所有线程共享这个预算，避免挨个 wait 叠加成十几秒）；
        # 还没结束就登记下来，等它们全部结束后再退出。绝不能直接 quit：
        # 销毁运行中的 QThread 会让进程 abort（实测退出码 127），
        # 而批量 500 张 / 首次下载模型都远超这个时间。
        deadline = time.monotonic() + 3.0
        still = []
        for w in pending:
            left = max(0, int((deadline - time.monotonic()) * 1000))
            if not w.wait(left):
                still.append(w)
        if still:
            self._quit_waiting = list(still)
            for w in still:
                w.finished.connect(lambda w=w: self._on_quit_finished(w))
            self.statusBar().showMessage("后台任务正在结束，完成后自动退出", 8000)
            return
        QApplication.quit()

    def _on_quit_finished(self, w) -> None:
        """等所有未结束的线程都结束，再真正退出。"""
        self._quit_waiting = [x for x in self._quit_waiting if x is not w]
        if not self._quit_waiting:
            QApplication.quit()

    def _translate_worker(self):
        dlg = self._translate_dlg
        if dlg is None:
            return None
        try:
            return dlg.active_worker()
        except RuntimeError:
            return None
