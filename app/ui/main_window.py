"""主窗口 + 托盘：历史记录、热键截图、截屏翻译、长截图、快捷键设置、自动复制。"""
from __future__ import annotations

import json
import os
from datetime import datetime

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
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.core.engine import compact_cjk, get_engine
from app.core.exporter import export_text
from app.core.stitcher import StitchWorker
from app.ui.capture_overlay import CaptureOverlay
from app.ui.longshot import LongShotBar, LongShotDialog
from app.ui.preview_popup import PreviewPopup
from app.ui.settings_dialog import SettingsDialog
from app.ui.translate_dialog import TranslateDialog


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

    def run(self) -> None:
        get_engine().warmup()


class OcrWorker(QThread):
    done = Signal(str)
    fail = Signal(str)

    def __init__(self, image) -> None:
        super().__init__()
        self._image = image

    def run(self) -> None:
        try:
            self.done.emit(get_engine().recognize_image(self._image))
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))


class HotkeyBridge(QObject):
    """keyboard 回调在监听线程，通过信号切回 Qt 主线程。"""

    triggered = Signal()


class MainWindow(QMainWindow):
    def __init__(self, preload: bool = True) -> None:
        super().__init__()
        self.setWindowTitle(config.APP_TITLE)
        self.resize(640, 540)
        self._overlay: CaptureOverlay | None = None
        self._worker: OcrWorker | None = None
        self._translate_dlg: TranslateDialog | None = None
        self._capture_translate = False  # 本次框选是否用于截屏翻译
        self._capture_long = False  # 本次框选是否用于长截图
        self._longshot_worker: StitchWorker | None = None
        self._longshot_bar: LongShotBar | None = None
        self._longshot_dlg: LongShotDialog | None = None
        self._preview: PreviewPopup | None = None
        self._hover_item: QListWidgetItem | None = None
        self._hover_pos = None
        self._history: list[dict] = self._load_history()

        self._build_ui()
        self._build_tray()
        self._register_hotkey()

        self._preload: EnginePreloader | None = (
            EnginePreloader() if preload else None
        )
        if self._preload is not None:
            self._preload.start()

    # ---- UI ----
    def _build_ui(self) -> None:
        central = BgCentral(_load_bg())
        layout = QVBoxLayout(central)

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
        self.btn_settings = QPushButton("设置")
        self.btn_capture.setStyleSheet("font-weight: bold;")
        for b in (self.btn_capture, self.btn_translate, self.btn_long):
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
        self.list.setMouseTracking(True)  # 长悬浮预览需要跟踪鼠标
        layout.addWidget(self.list, 1)
        self.search.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,200);"
            " border: 1px solid rgba(60,60,60,60); border-radius: 4px; padding: 4px 6px; }"
        )
        self.list.setStyleSheet(
            "QListWidget { background: rgba(255,255,255,185);"
            " alternate-background-color: rgba(243,248,243,205);"
            " border: 1px solid rgba(60,60,60,50); border-radius: 4px; }"
        )
        self.statusBar().setStyleSheet("QStatusBar { background: rgba(255,255,255,160); }")

        self.setCentralWidget(central)

        self.btn_capture.clicked.connect(self.start_capture)
        self.btn_translate.clicked.connect(lambda: self.start_capture(translate=True))
        self.btn_long.clicked.connect(lambda: self.start_capture(long=True))
        self.btn_settings.clicked.connect(self._open_settings)
        self.btn_copy.clicked.connect(self._copy_selected)
        self.btn_export.clicked.connect(self._export_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_clear.clicked.connect(self._clear_history)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._on_hover_timeout)
        self.list.itemEntered.connect(self._on_item_hovered)
        self._refresh_list()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(), self)
        menu = QMenu()
        act_capture = QAction("立即截图", menu)
        act_translate = QAction("截屏翻译", menu)
        act_longshot = QAction("长截图", menu)
        act_show = QAction("显示历史窗口", menu)
        act_settings = QAction("快捷键设置...", menu)
        act_quit = QAction("退出", menu)
        act_capture.triggered.connect(self.start_capture)
        act_translate.triggered.connect(lambda: self.start_capture(translate=True))
        act_longshot.triggered.connect(lambda: self.start_capture(long=True))
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

    def _register_hotkey(self) -> None:
        import keyboard

        self._hotkey_bridge = HotkeyBridge()
        self._hotkey_bridge.triggered.connect(self.start_capture)
        keyboard.add_hotkey(config.HOTKEY, self._hotkey_bridge.triggered.emit)

        # 截屏翻译热键：框选 → 识别 → 自动弹出翻译
        self._hotkey_tr_bridge = HotkeyBridge()
        self._hotkey_tr_bridge.triggered.connect(
            lambda: self.start_capture(translate=True)
        )
        keyboard.add_hotkey(
            config.TRANSLATE_HOTKEY, self._hotkey_tr_bridge.triggered.emit
        )

        # 长截图热键：框选 → 滚动采集 → 拼接预览
        self._hotkey_long_bridge = HotkeyBridge()
        self._hotkey_long_bridge.triggered.connect(
            lambda: self.start_capture(long=True)
        )
        keyboard.add_hotkey(
            config.HOTKEY_LONG, self._hotkey_long_bridge.triggered.emit
        )

    # ---- 截图流程 ----
    def start_capture(self, translate: bool = False, long: bool = False) -> None:
        if self._overlay is not None:
            return
        if self._worker is not None and self._worker.isRunning():
            self.statusBar().showMessage("上一次识别还在进行中，请稍候", 3000)
            return
        if self._longshot_bar is not None:
            self.statusBar().showMessage("长截图会话进行中，请先完成或取消", 3000)
            return
        self._capture_translate = translate
        self._capture_long = long
        self._overlay = CaptureOverlay()
        if long:
            self._overlay.regionSelected.connect(self._on_region_selected)
        else:
            self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._on_capture_cancelled)
        self._overlay.start()

    def _on_capture_cancelled(self) -> None:
        self._overlay = None
        self._capture_translate = False
        self._capture_long = False

    def _on_captured(self, image) -> None:
        self._overlay = None
        translate = self._capture_translate
        self._capture_translate = False
        self.statusBar().showMessage("识别中...")
        self._worker = OcrWorker(image)
        # 翻译标志在连接时绑定：避免与图片队列识别共用状态导致串扰
        self._worker.done.connect(lambda text, tr=translate: self._on_ocr_done(text, tr))
        self._worker.fail.connect(self._on_ocr_fail)
        self._worker.start()

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

    # ---- 长截图 ----
    def _on_region_selected(self, x: int, y: int, w: int, h: int) -> None:
        self._overlay = None
        self._capture_translate = False
        self._capture_long = False
        self._longshot_worker = StitchWorker((x, y, w, h))
        self._longshot_worker.progress.connect(self._on_longshot_progress)
        self._longshot_worker.done.connect(self._on_longshot_done)
        self._longshot_worker.fail.connect(self._on_longshot_fail)
        bar = LongShotBar((x, y, w, h))
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
        if w is None or w.isRunning():
            return
        w.start()
        if self._longshot_bar is not None:
            self._longshot_bar.set_running(True)

    def _on_longshot_stop(self) -> None:
        if self._longshot_worker is not None:
            self._longshot_worker.stop()

    def _on_longshot_progress(self, text: str) -> None:
        if self._longshot_bar is not None:
            self._longshot_bar.set_status(text)

    def _on_longshot_done(self, image: QImage) -> None:
        self._close_longshot_bar()
        self._longshot_worker = None
        self._open_longshot_dialog(image)

    def _on_longshot_fail(self, msg: str) -> None:
        self._close_longshot_bar()
        self._longshot_worker = None
        self.tray.showMessage(
            config.APP_NAME, f"长截图失败：{msg}", QSystemTrayIcon.Warning, 3000
        )

    def _on_longshot_cancel(self) -> None:
        w = self._longshot_worker
        self._close_longshot_bar()
        self._longshot_worker = None
        if w is not None:
            # 断开信号：取消后线程剩余结果不再弹窗
            try:
                w.progress.disconnect()
                w.done.disconnect()
                w.fail.disconnect()
            except (RuntimeError, TypeError):
                pass
            if w.isRunning():
                w.stop()
                w.wait(3000)

    def _close_longshot_bar(self) -> None:
        if self._longshot_bar is not None:
            self._longshot_bar.close()
            self._longshot_bar = None

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
        if self._worker is not None and self._worker.isRunning():
            self.statusBar().showMessage("识别进行中，请稍候", 3000)
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
            "框选后自动识别 / Esc 取消 / 点「设置」修改快捷键 / 长截图可识别并翻译</span>"
        )

    def _open_settings(self) -> None:
        dlg = SettingsDialog(
            (config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG), self
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
        self._apply_hotkeys(hk, htr, hlong)

    def _apply_hotkeys(self, hk: str, htr: str, hlong: str) -> None:
        """重新注册全局热键；失败自动恢复原设置。"""
        import keyboard

        old = (config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG)
        keyboard.unhook_all()
        config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG = hk, htr, hlong
        try:
            self._register_hotkey()
        except Exception as exc:  # noqa: BLE001
            keyboard.unhook_all()
            config.HOTKEY, config.TRANSLATE_HOTKEY, config.HOTKEY_LONG = old
            self._register_hotkey()
            QMessageBox.warning(
                self, config.APP_NAME, f"快捷键注册失败（已恢复原设置）：{exc}"
            )
            return
        config.save_settings(
            {"hotkey_capture": hk, "hotkey_translate": htr, "hotkey_long": hlong}
        )
        self.tip.setText(self._tip_html())
        self.tray.showMessage(
            config.APP_NAME, "快捷键已更新", QSystemTrayIcon.Information, 2000
        )

    # ---- 历史记录 ----
    def _load_history(self) -> list[dict]:
        try:
            with open(config.HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []

    def _save_history(self) -> None:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._history, f, ensure_ascii=False, indent=1)

    def _add_history(self, text: str) -> None:
        self._history.insert(
            0, {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "text": text}
        )
        del self._history[config.HISTORY_LIMIT:]
        self._save_history()
        self._refresh_list()

    def _refresh_list(self) -> None:
        kw = self.search.text().strip().lower()
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        for i, item in enumerate(self._history):
            if kw and kw not in item["text"].lower():
                continue
            preview = item["text"].replace("\n", " ⏎ ")
            if len(preview) > 80:
                preview = preview[:80] + "…"
            it = QListWidgetItem(f"{item['time']}    {preview}")
            it.setData(Qt.UserRole, i)
            self.list.addItem(it)
        self.list.setUpdatesEnabled(True)

    # ---- 悬浮/双击预览完整内容 ----
    def _on_item_hovered(self, item: QListWidgetItem) -> None:
        """鼠标进入条目：约半秒后浮现完整内容（长悬浮）。"""
        self._hover_item = item
        rect = self.list.visualItemRect(item)
        self._hover_pos = self.list.viewport().mapToGlobal(rect.bottomLeft())
        self._hover_timer.start(500)

    def _on_hover_timeout(self) -> None:
        if self._hover_item is not None:
            self._show_preview(self._hover_item, self._hover_pos, 6000)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._hover_timer.stop()  # 双击已弹出浮窗，避免悬浮超时再次挪动
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
        """把选中的历史记录导出为 txt / docx / pdf。"""
        rows = sorted({i.data(Qt.UserRole) for i in self.list.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, config.APP_NAME, "请先在列表中选择要导出的记录")
            return
        texts = [self._history[i]["text"] for i in rows if 0 <= i < len(self._history)]
        default = os.path.join(os.path.expanduser("~"), "SnapOCR导出.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出所选记录", default,
            "文本文件 (*.txt);;Word 文档 (*.docx);;PDF 文档 (*.pdf)",
        )
        if not path:
            return
        try:
            export_text(path, "\n".join(texts))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, config.APP_NAME, f"导出失败：{exc}")
            return
        self.tray.showMessage(
            config.APP_NAME, f"已导出 {os.path.basename(path)}",
            QSystemTrayIcon.Information, 2000,
        )

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

    # ---- 窗口/托盘行为 ----
    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

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
        # 长截图线程可能正在注入滚轮：先请求停止并等待，避免退出后仍在动鼠标
        if self._longshot_worker is not None and self._longshot_worker.isRunning():
            self._longshot_worker.stop()
            if not self._longshot_worker.wait(30000):
                self._longshot_worker.finished.connect(QApplication.quit)
                return
        # 等待后台线程结束，避免 ONNX 运行时在进程退出时崩溃
        if self._preload is not None and self._preload.isRunning():
            self._preload.wait(10000)
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(10000)
            if self._worker.isRunning():
                # 超大截图识别可能超过 10 秒：先等线程真正结束再退出，
                # 避免线程运行中销毁导致崩溃
                self._worker.finished.connect(QApplication.quit)
                return
        QApplication.quit()
