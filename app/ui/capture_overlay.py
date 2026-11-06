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


def _grab_all() -> tuple[QImage, tuple[int, int], list, dict]:
    """一次抓完整块虚拟桌面，顺带拿到各显示器信息（只开一次 mss，省一次抓屏）。"""
    with mss.mss() as sct:
        union = sct.monitors[0]
        mons = list(sct.monitors[1:]) or [union]
        raw = sct.grab(union)
    img = QImage(raw.bgra, raw.width, raw.height, raw.width * 4, QImage.Format_ARGB32).copy()
    geo = virtual_geometry()
    if geo.width() > 0:
        # 统一缩放比：单屏时等于真实 DPR；混合 DPI 多屏只能取等效值
        img.setDevicePixelRatio(raw.width / geo.width())
    return img, (int(union["left"]), int(union["top"])), mons, union


def grab_virtual_screen() -> tuple[QImage, tuple[int, int]]:
    """用 mss 抓取整个虚拟桌面（物理像素）。

    返回 (带 devicePixelRatio 的 QImage, 虚拟桌面左上角的物理坐标)：
    mss.monitors[0] 是所有显示器并集，副屏在主屏左侧/上方时坐标可能为负。
    """
    img, origin, _, _ = _grab_all()
    return img, origin


def screen_boxes(mons=None, union=None) -> list[tuple[QRect, QRect]]:  # noqa: ANN001
    """每个屏幕的 (逻辑矩形, 该屏在截图内的物理矩形)。

    混合 DPI 的多屏不能用一个统一缩放比：100% 的屏按 1.25 倍拉伸、125% 的屏
    反而被压回来，接缝处就会错位（文字发虚、左右半屏对不上）。所以逐屏配对，
    每块屏用自己的物理/逻辑比例来缩放，接缝才是严丝合缝的。

    配对靠归一化坐标的最小距离：Qt 与 mss 的屏幕顺序不保证一致。
    """
    geo = virtual_geometry()
    if geo.width() <= 0 or geo.height() <= 0:
        return []
    if mons is None or union is None:
        try:
            with mss.mss() as sct:
                union = sct.monitors[0]
                mons = list(sct.monitors[1:]) or [union]
        except Exception:  # noqa: BLE001 抓不到就退回统一缩放比
            return []
    if not mons:
        return []
    ux, uy = float(union["left"]), float(union["top"])
    uw = float(union["width"]) or 1.0
    uh = float(union["height"]) or 1.0
    screens = [s.geometry() for s in QGuiApplication.screens()]

    def norm_phys(m) -> tuple[float, float, float, float]:  # noqa: ANN001
        return (
            (float(m["left"]) - ux) / uw,
            (float(m["top"]) - uy) / uh,
            float(m["width"]) / uw,
            float(m["height"]) / uh,
        )

    boxes: list[tuple[QRect, QRect]] = []
    used: set[int] = set()
    for m in mons:
        phys = QRect(
            int(m["left"] - union["left"]), int(m["top"] - union["top"]),
            int(m["width"]), int(m["height"]),
        )
        nx, ny, nw, nh = norm_phys(m)
        best, best_d = -1, 9e9
        for i, g in enumerate(screens):
            if i in used:
                continue
            gx, gy, gw, gh = (
                (g.x() - geo.x()) / geo.width(), (g.y() - geo.y()) / geo.height(),
                g.width() / geo.width(), g.height() / geo.height(),
            )
            d = (gx - nx) ** 2 + (gy - ny) ** 2 + (gw - nw) ** 2 + (gh - nh) ** 2
            if d < best_d:
                best, best_d = i, d
        if best >= 0 and best_d < 0.02:  # 归一化后位置形状都对得上才认
            used.add(best)
            boxes.append((screens[best], phys))
    return boxes


class CaptureOverlay(QWidget):
    captured = Signal(QImage)
    # mss 物理像素区域 (x, y, w, h) + 逻辑矩形（Qt 控件摆位用，HiDPI 下二者不同）
    regionSelected = Signal(int, int, int, int, object)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self._geo = virtual_geometry()
        self._shot, self._origin_phys, mons, union = _grab_all()
        # 逐屏配对：每块屏画自己的那一块，接缝才对得齐（混合 DPI 时尤其明显）
        self._boxes = screen_boxes(mons, union)
        # 绘制用的副本：dpr 归零，源矩形就是原始物理像素，
        # 否则 Qt 会按统一 dpr 缩放，把逐屏的精确比例又抹平回去
        self._flat = self._shot.copy()
        self._flat.setDevicePixelRatio(1.0)
        self._pixmap = QPixmap.fromImage(self._flat)
        self._origin = QPoint()
        self._finished = False  # 已产出结果/已取消：closeEvent 不再补发 cancelled
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
        boxes = getattr(self, "_boxes", None)
        if boxes:
            for logical, phys in boxes:
                # 每块屏：源=该屏的物理像素块，目标=该屏的逻辑矩形
                p.drawPixmap(logical.translated(-self._geo.topLeft()), self._pixmap, phys)
        else:
            # 拿不到逐屏信息：整幅铺满（与旧行为一致，统一比例）
            p.drawPixmap(self.rect(), self._pixmap, self._pixmap.rect())
        p.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self._rubber.isVisible():
            r = self._rubber.geometry()
            p.drawPixmap(r, self._pixmap, self._phys_rect(r))
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
            self._finished = True  # 主动取消：closeEvent 不要再补发一次
            self.close()
            self.cancelled.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        """被 Alt+F4 / 窗口管理器关掉时也要通知主窗口。

        以前只有 Esc 会发 cancelled，其它方式关闭后主窗口的 _overlay 仍指向
        已销毁的 C++ 对象，于是「立即截图」此后永久无响应（只能重启程序）。
        """
        if not self._finished:
            self._finished = True
            self.cancelled.emit()
        super().closeEvent(event)

    def _legacy_phys_rect(self, rect: QRect) -> QRect:
        """统一缩放比的换算：拿不到逐屏配对信息时的兜底。"""
        dpr = self._shot.devicePixelRatio()
        # 虚拟桌面原点可能不在 (0,0)（副屏在主屏左侧/上方），要换算成相对截图的偏移
        off_x = self._origin_phys[0] - int(self._geo.x() * dpr)
        off_y = self._origin_phys[1] - int(self._geo.y() * dpr)
        return QRect(
            int(rect.x() * dpr) + off_x, int(rect.y() * dpr) + off_y,
            int(rect.width() * dpr), int(rect.height() * dpr),
        )

    def _phys_rect(self, rect: QRect) -> QRect:
        """逻辑选区 → 截图内的物理像素矩形。

        按屏分别换算再求并集：混合 DPI 时单一缩放比会让跨屏选区的右半边偏几像素，
        裁出来的图边缘有接缝、文字发虚。
        """
        boxes = getattr(self, "_boxes", None)
        if not boxes:
            return self._legacy_phys_rect(rect)
        abs_rect = rect.translated(self._geo.topLeft())
        out = QRect()
        for logical, phys in boxes:
            if logical.width() <= 0 or logical.height() <= 0:
                continue
            inter = abs_rect.intersected(logical)
            if inter.isEmpty():
                continue
            sx = phys.width() / logical.width()
            sy = phys.height() / logical.height()
            piece = QRect(
                phys.x() + int(round((inter.x() - logical.x()) * sx)),
                phys.y() + int(round((inter.y() - logical.y()) * sy)),
                max(1, int(round(inter.width() * sx))),
                max(1, int(round(inter.height() * sy))),
            )
            out = piece if out.isNull() else out.united(piece)
        return self._legacy_phys_rect(rect) if out.isNull() else out

    def mss_region(self, rect: QRect) -> tuple[int, int, int, int]:
        """逻辑选区 → mss 物理像素区域 (x, y, w, h)，坐标相对截图左上角。

        四周外扩 4 物理像素：贴边文字被裁掉一半常导致整行漏识别。
        """
        src = self._phys_rect(rect).adjusted(-4, -4, 4, 4).intersected(self._shot.rect())
        return src.x(), src.y(), src.width(), src.height()

    def _finish(self, rect: QRect) -> None:
        x, y, w, h = self.mss_region(rect)
        crop = self._shot.copy(QRect(x, y, w, h))
        # 长截图需要绝对物理坐标（mss 的 monitor 参数），补回虚拟桌面原点
        abs_x = x + self._origin_phys[0]
        abs_y = y + self._origin_phys[1]
        # 控制条是 Qt 控件，要用逻辑坐标：125% 缩放下物理坐标会让它偏移到别处
        logical = QRect(rect).translated(self._geo.topLeft())
        self._finished = True
        self.close()
        self.captured.emit(crop)
        self.regionSelected.emit(abs_x, abs_y, w, h, logical)
