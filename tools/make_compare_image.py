# -*- coding: utf-8 -*-
"""生成投稿用对比图：深色 IDE 截图「原图 vs SnapOCR 真实 _enhance() 输出」。

右图不是示意图，而是直接调用 app/core/engine.py 的 _enhance() 得到的像素结果，
可复现、可核对，不会伪造任何 OCR 识别结果。

运行：venv/Scripts/python.exe tools/make_compare_image.py
输出：assets/compare-dark-ui.png
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.core.engine import _enhance

OUT = os.path.join(ROOT, "assets", "compare-dark-ui.png")
FONT = "C:/Windows/Fonts/msyh.ttc"
FONTB = "C:/Windows/Fonts/msyhbd.ttc"
MONO = "C:/Windows/Fonts/consola.ttf"

C_TITLE = "#1a1d23"
C_BODY = "#5b6270"
C_LINE = "#dfe3e9"
C_ACCENT = "#c0392b"


def f(path, size):
    return ImageFont.truetype(path, size)


def make_dark_ide(w=600, h=368):
    """画一张带语法高亮的深色 IDE 截图（含中文注释）。"""
    img = Image.new("RGB", (w, h), "#1e1e1e")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 34], fill="#252526")
    d.rectangle([14, 4, 168, 34], fill="#1e1e1e")
    d.text((26, 8), "engine.py   ●", font=f(FONT, 13), fill="#d4d4d4")
    d.text((w - 92, 9), "SnapOCR", font=f(FONTB, 12), fill="#6a9955")
    d.line([(0, 34), (w, 34)], fill="#3a3a3a", width=1)
    d.rectangle([0, 35, 42, h], fill="#1e1e1e")
    d.line([(42, 35), (42, h)], fill="#2b2b2b", width=1)

    K = "#c586c0"   # keyword
    F = "#dcdcaa"   # function
    S = "#ce9178"   # string
    C = "#6a9955"   # comment
    N = "#b5cea8"   # number
    T = "#d4d4d4"   # plain
    B = "#9cdcfe"   # variable
    lines = [
        [("def ", K), ("enhance_capture", F), ("(image):", T)],
        [("# 深色主题截图先反色，再送去识别", C)],
        [("gray = ", T), ("cv2", B), (".cvtColor(image, cv2.COLOR_BGR2GRAY)", T)],
        [("if ", K), ("np.mean", F), ("(gray) < ", T), ("100", N), (":", T)],
        [("image = ", T), ("cv2", B), (".bitwise_not(image)", T)],
        [("if ", K), ("np.std", F), ("(gray) < ", T), ("45", N), (":", T)],
        [("image = ", T), ("clahe", F), ("(image)", T), ("  ", T), ("# 低对比度再增强", C)],
        [("return ", K), ("ocr", B), (".run(image)", T)],
        [("", T)],
        [("# 识别结果自动进历史，关键词随时搜回", C)],
        [("history", B), (".append(", T), ("result", B), (")", T)],
    ]
    mono = f(MONO, 14)
    cjk = f(FONT, 14)  # consola 无中文字形，中文注释需单独换字体，否则渲染成方块
    for i, tokens in enumerate(lines):
        y = 46 + i * 27
        d.text((12, y + 3), f"{i + 1:>2}", font=f(MONO, 11), fill="#6e7681")
        x = 56
        for text, color in tokens:
            if text:
                font = cjk if any(ord(ch) > 127 for ch in text) else mono
                d.text((x, y), text, font=font, fill=color)
                x += int(d.textlength(text, font=font))
    d.rectangle([0, h - 22, w, h], fill="#007acc")
    d.text((10, h - 19), "main*   Python 3.12   UTF-8   Ln 4, Col 17", font=f(FONT, 11), fill="#ffffff")
    return img


def enhanced(img):
    bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    out = _enhance(bgr)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def main():
    W, H = 1400, 820
    canvas = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(canvas)

    d.text((50, 30), "深色主题截图，为什么要先反色？", font=f(FONTB, 31), fill=C_TITLE)
    d.text((50, 78), "检测模型更习惯黑字白底。SnapOCR 在送去识别之前，自动完成这一步。",
           font=f(FONT, 16), fill=C_BODY)

    src = make_dark_ide()
    dst = enhanced(src)

    d.text((50, 128), "原始截图 · 深色 IDE / 暗色网页", font=f(FONTB, 16), fill=C_TITLE)
    d.text((750, 128), "SnapOCR 送入识别前 · 自动反色 + 对比度增强", font=f(FONTB, 16), fill=C_TITLE)
    canvas.paste(src, (50, 160))
    canvas.paste(dst, (750, 160))
    d.rectangle([50, 160, 650, 528], outline=C_LINE, width=2)
    d.rectangle([750, 160, 1350, 528], outline=C_LINE, width=2)

    d.line([(664, 344), (732, 344)], fill=C_ACCENT, width=2)
    d.polygon([(732, 344), (722, 339), (722, 349)], fill=C_ACCENT)
    d.text((698, 312), "_enhance()", font=f(MONO, 12), fill=C_ACCENT, anchor="mm")

    cards = [
        ("01  自动判断亮度", "整图平均灰度 < 100 判定为深色截图，\n自动反色，不需要手工预处理。"),
        ("02  低对比再增强", "灰度标准差 < 45 时在 LAB 的 L 通道\n跑 CLAHE，救回浅灰字与水印字。"),
        ("03  结果能搜回来", "每次识别存入历史，关键词过滤、\n浮窗预览、再次复制、一键导出。"),
    ]
    for i, (title, body) in enumerate(cards):
        x = 50 + i * 450
        d.rounded_rectangle([x, 566, x + 420, 716], radius=10, fill="#f7f8fa", outline=C_LINE, width=1)
        d.text((x + 20, 586), title, font=f(FONTB, 17), fill=C_TITLE)
        d.multiline_text((x + 20, 622), body, font=f(FONT, 14), fill=C_BODY, spacing=8)

    d.line([(50, 752), (1350, 752)], fill=C_LINE, width=1)
    d.text((50, 768), "右图由项目内 app/core/engine.py 的 _enhance() 直接生成，非示意图 · 未展示任何 OCR 识别结果",
           font=f(FONT, 12), fill="#8a919d")
    d.text((1350, 768), "SnapOCR v1.0.0 · MIT", font=f(FONT, 12), fill="#8a919d", anchor="ra")

    canvas.save(OUT, optimize=True)
    print("saved", OUT, canvas.size, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
