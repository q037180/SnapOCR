# -*- coding: utf-8 -*-
"""自动制作演示 GIF：离屏渲染真实界面帧，用 Pillow 合成 docs/assets/demo-features.gif。

展示新功能流程：PDF 整档识别（进度）→ 历史结果 → 截图贴图 → 导出 Markdown。
需在桌面会话下运行（窗口文本光栅化需要正常字体引擎）：
    python tools/make_demo_gif.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QProgressDialog

from app.ui.main_window import MainWindow
from app.ui.pin_window import PinWindow

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "assets", "demo-features.gif")

CAPTIONS = [
    "SnapOCR：本地离线截图 OCR（新功能演示）",
    "① PDF 整档识别：拖入 PDF 逐页识别，进度可取消",
    "② 识别结果自动进入历史，多页按页分组",
    "③ 截图贴图：钉在桌面置顶，滚轮缩放 / Ctrl+滚轮调透明度",
    "④ 导出所选：txt / docx / pdf / Markdown 一键导出",
]

HILIGHT = "QPushButton { border: 2px solid #e8443a; border-radius: 4px; font-weight: bold; }"


def grab(widget) -> Image.Image:
    """QWidget → PIL Image（经 QBuffer PNG 编码，避免 stride 对齐问题）。"""
    import io

    from PySide6.QtCore import QBuffer

    img: QImage = widget.grab().toImage()
    qbuf = QBuffer()
    qbuf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(qbuf, "PNG")
    buf = io.BytesIO(bytes(qbuf.data()))
    qbuf.close()
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def fake_doc_pixmap() -> QPixmap:
    """画一张假「文档页」给贴图窗口当素材。"""
    pm = QPixmap(300, 200)
    pm.fill(QColor("white"))
    p = QPainter(pm)
    p.setPen(QColor("#222"))
    f = QFont()
    f.setPixelSize(16)
    p.setFont(f)
    p.drawText(20, 40, "PDF OCR Test")
    f.setPixelSize(12)
    p.setFont(f)
    p.drawText(20, 75, "Hello SnapOCR 2026")
    p.drawText(20, 100, "表格识别与贴图功能已就绪")
    p.setPen(QColor("#2f6fed"))
    p.drawRect(18, 22, 200, 92)
    p.end()
    return pm


def frame(win, focus_btn=None, overlay=None) -> Image.Image:
    """主窗口帧：可选高亮按钮 / 叠加子窗口截图。"""
    for b in (win.btn_capture, win.btn_translate, win.btn_long,
              win.btn_table, win.btn_pin, win.btn_pdf, win.btn_settings):
        b.setStyleSheet("")
    if focus_btn is not None:
        focus_btn.setStyleSheet(HILIGHT)
        focus_btn.repaint()
    base = grab(win)
    if overlay is not None:
        ov = grab(overlay)
        x = (base.width - ov.width) // 2
        y = (base.height - ov.height) // 2
        base.paste(ov, (x, y))
    return base


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def add_caption(img: Image.Image, text: str) -> Image.Image:
    """底部加说明条。"""
    W = img.width
    bar_h = 44
    out = Image.new("RGB", (W, img.height + bar_h), "#1f2430")
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.rectangle([0, img.height, W, img.height + bar_h], fill="#2f6fed")
    f = load_font(20)
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, img.height + (bar_h - 20) / 2 - 2), text,
           font=f, fill="white")
    return out


def main() -> None:
    app = QApplication.instance() or QApplication([])
    win = MainWindow(preload=False)
    win.show()
    app.processEvents()

    frames: list[Image.Image] = []

    # ① 空主窗口（提示条可见）
    frames.append(frame(win, win.btn_pdf))

    # ② PDF 识别进度
    dlg = QProgressDialog("正在识别 第 2 / 3 页...", "取消", 0, 3, win)
    dlg.setWindowTitle("PDF 整档识别")
    dlg.setValue(2)
    dlg.show()
    app.processEvents()
    frames.append(frame(win, win.btn_pdf, overlay=dlg))
    dlg.close()
    dlg.deleteLater()

    # ③ 历史结果（先清空，避免把真实历史录进演示 GIF）
    win.list.clear()
    demo_text = "== 第 1 页 ==\nPDF OCR Test\nHello SnapOCR 2026\n表格识别与贴图功能已就绪"
    win.list.addItem(demo_text)
    win.list.addItem("== 第 2 页 ==\nSnapOCR 支持简中 / 繁中 / 英 / 日 / 韩 五种语言")
    win.list.setCurrentRow(0)
    app.processEvents()
    frames.append(frame(win, None))

    # ④ 贴图窗口叠加
    pin = PinWindow(fake_doc_pixmap())
    pin.show()
    pin.move(QPoint(80, 200))
    app.processEvents()
    frames.append(frame(win, win.btn_pin, overlay=pin))
    pin.close()
    pin.deleteLater()

    # ⑤ 高亮导出按钮
    frames.append(frame(win, win.btn_export))

    win.close()
    save_gif(frames, CAPTIONS, OUT)


def save_gif(frames: list, captions: list[str], out: str, duration: int = 1800) -> None:
    """统一尺寸 + 说明条 + 保存 GIF。"""
    W = min(900, max(f.width for f in frames))
    norm = []
    for f in frames:
        s = W / f.width
        f = f.resize((W, int(f.height * s)), Image.LANCZOS)
        norm.append(f)
    H = max(f.height for f in norm)
    final = []
    for i, f in enumerate(norm):
        pad = Image.new("RGB", (W, H), "#f5f7fa")
        pad.paste(f, (0, (H - f.height) // 2))
        final.append(add_caption(pad, captions[i]))

    os.makedirs(os.path.dirname(out), exist_ok=True)
    final[0].save(
        out, save_all=True, append_images=final[1:],
        duration=duration, loop=0, optimize=True,
    )
    size_kb = os.path.getsize(out) // 1024
    print(f"OK: {out}（{len(final)} 帧，{size_kb} KB）")


def make_pin_gif(app) -> None:
    """贴图操作演示：出现 → 滚轮放大 → Ctrl+滚轮调透明度。"""
    out = os.path.join(ROOT, "assets", "demo-pin.gif")
    caps = [
        "截图贴图：框选后钉在桌面，默认 125% 置顶显示",
        "滚轮缩放：125% → 175%",
        "继续放大：175% → 250%，按比例放大不模糊",
        "Ctrl+滚轮调透明度：100% → 80% → 60%，不遮挡下方内容",
        "双击或右键关闭，可同时钉多张贴图",
    ]
    frames = []
    pin = PinWindow(fake_doc_pixmap())
    pin.show()
    pin.move(QPoint(300, 250))
    app.processEvents()
    frames.append(grab(pin))
    for z in (1.75, 2.5):
        pin._set_zoom(z)
        app.processEvents()
        frames.append(grab(pin))
    for op in (0.8, 0.6):
        pin.setWindowOpacity(op)
        app.processEvents()
        frames.append(grab(pin))
    pin.close()
    pin.deleteLater()
    save_gif(frames, caps, out, duration=1600)


def make_batch_gif(app) -> None:
    """拖拽文件夹批量识别演示：历史列表逐条增长。"""
    out = os.path.join(ROOT, "assets", "demo-batch.gif")
    caps = [
        "拖拽整个文件夹到主窗口：自动递归收集全部图片（上限 500 张）",
        "批量识别中：合同扫描件.png（1/4）",
        "逐张识别进入历史，按文件名分组",
        "发票、白板、快递单一网打尽",
        "识别完成：搜索、复制、导出与其他记录完全一致",
    ]
    win = MainWindow(preload=False)
    win.show()
    app.processEvents()
    win.list.clear()  # 清空真实历史，演示数据不混淆隐私
    frames = [frame(win, None)]
    names = ["合同扫描件.png", "发票_001.jpg", "会议白板.png", "快递单.jpg"]
    for i, n in enumerate(names):
        win.list.addItem(f"== {n} ==\n（第 {i + 1} 张识别结果预览文本）")
        win.list.setCurrentRow(win.list.count() - 1)
        app.processEvents()
        frames.append(frame(win, win.btn_capture if i == 0 else None))
    win.close()
    win.deleteLater()
    save_gif(frames, caps, out, duration=1600)


def make_table_gif(app) -> None:
    """表格识别演示：高亮按钮 + 结果矩阵对话框。"""
    out = os.path.join(ROOT, "assets", "demo-table.gif")
    caps = [
        "表格识别：框选表格区域，自动识别为行列矩阵",
        "预览结果：可编辑单元格后一键保存 Excel（xlsx）",
    ]
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    win = MainWindow(preload=False)
    win.show()
    app.processEvents()
    win.list.clear()  # 清空真实历史，演示数据不混淆隐私

    # 独立无边框窗口：不画进主窗口截图，由 frame() 居中叠加
    tab = QTableWidget(3, 3, None)
    tab.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
    tab.setWindowTitle("表格识别结果")
    data = [["商品", "数量", "金额"], ["苹果", "12", "36.0"], ["香蕉", "20", "40.0"]]
    for r in range(3):
        for c in range(3):
            tab.setItem(r, c, QTableWidgetItem(data[r][c]))
    tab.resize(360, 220)
    tab.show()
    app.processEvents()
    f1 = frame(win, win.btn_table, overlay=tab)

    # 第二帧：放大视角（只放对话框）
    tab.resize(420, 260)
    app.processEvents()
    f2 = grab(tab)
    tab.close()
    tab.deleteLater()
    win.close()
    win.deleteLater()
    save_gif([f1, f2], caps, out, duration=1800)


if __name__ == "__main__":
    a = QApplication.instance() or QApplication([])
    main()
    make_pin_gif(a)
    make_batch_gif(a)
    make_table_gif(a)
