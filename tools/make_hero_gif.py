# -*- coding: utf-8 -*-
"""生成约 15 秒的串联演示 GIF，供 README 首屏与社区投稿使用。

素材全部来自仓库内已有的真实录屏 GIF，不伪造界面、不伪造识别结果：
  demo.gif          截图识别（5.0s）
  preview-hover.gif 历史搜索与预览（8.6s）
中间插入章节卡，末尾定格，使总时长约 15 秒。

运行：venv/Scripts/python.exe tools/make_hero_gif.py
输出：assets/hero-15s.gif
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "hero-15s.gif")
FONT = "C:/Windows/Fonts/msyh.ttc"
FONTB = "C:/Windows/Fonts/msyhbd.ttc"

W, H = 800, 516
BAR = 46
BG = "#f5f6f8"
BAR_BG = "#1f2430"


def f(path, size):
    return ImageFont.truetype(path, size)


def frame_from(img, caption):
    img = img.convert("RGB")
    box_w, box_h = W - 24, H - BAR - 20
    img.thumbnail((box_w, box_h), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(img, ((W - img.width) // 2, BAR + (H - BAR - img.height) // 2))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W, BAR], fill=BAR_BG)
    d.text((18, 12), caption, font=f(FONT, 15), fill="#ffffff")
    d.text((W - 18, 14), "SnapOCR", font=f(FONTB, 14), fill="#8ab4f8", anchor="ra")
    return canvas


def card(caption, subtitle):
    canvas = Image.new("RGB", (W, H), BAR_BG)
    d = ImageDraw.Draw(canvas)
    d.text((W // 2, H // 2 - 26), caption, font=f(FONTB, 30), fill="#ffffff", anchor="mm")
    d.text((W // 2, H // 2 + 24), subtitle, font=f(FONT, 16), fill="#9aa5b5", anchor="mm")
    return canvas


def collect(path, caption):
    out = []
    with Image.open(path) as im:
        n = getattr(im, "n_frames", 1)
        for i in range(n):
            im.seek(i)
            out.append((frame_from(im.copy(), caption), max(40, im.info.get("duration", 100))))
    return out


def main():
    frames = []
    durations = []

    seg1 = collect(os.path.join(ROOT, "assets", "demo.gif"),
                   "① Ctrl+Alt+Q 框选，松开即复制到剪贴板")
    frames.append(card("深色 IDE 截图，也能直接框走", "深色自动反色 · 低对比 CLAHE 增强"))
    durations.append(800)
    for im, ms in seg1:
        frames.append(im)
        durations.append(ms)

    seg2 = collect(os.path.join(ROOT, "assets", "preview-hover.gif"),
                   "② 识别结果自动进历史，随时搜回来 / 导出")
    for im, ms in seg2:
        frames.append(im)
        durations.append(ms)

    frames.append(card("免费 · 开源 MIT · 识别全程离线", "github.com/q037180/SnapOCR"))
    durations.append(600)

    total = sum(durations)
    print("frames:", len(frames), "duration:", round(total / 1000, 2), "s")

    palette = frames[0].quantize(colors=128, method=Image.Quantize.FASTOCTREE)
    pframes = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in frames]
    pframes[0].save(
        OUT, save_all=True, append_images=pframes[1:],
        duration=durations, loop=0, optimize=True, disposal=2,
    )
    print("saved", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
