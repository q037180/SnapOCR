"""生成 GitHub Social Preview（1280x640）。

用法：python tools/make_social_preview.py
输出：docs/assets/social-preview.png

仓库 Settings -> Social preview -> Upload an image 上传即可。
中文标题用系统微软雅黑；没有字体时退化为 DejaVu（中文会缺字，故不静默通过）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "social-preview.png"
W, H = 1280, 640

FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_REG = "C:/Windows/Fonts/msyh.ttc"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REG
    if not os.path.exists(path):
        path = "C:/Windows/Fonts/msyh.ttc"
    if not os.path.exists(path):
        print("找不到中文字体，终止：", FONT_BOLD, file=sys.stderr)
        raise SystemExit(2)
    return ImageFont.truetype(path, size, index=0)


def gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def shadow(img: Image.Image, box, radius: int = 26, blur: int = 24, alpha: int = 46):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=(20, 40, 80, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    img.paste(layer.convert("RGB"), (0, 0), layer)


def pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str, f: ImageFont.FreeTypeFont):
    tw = d.textbbox((0, 0), text, font=f)[2]
    box = (x, y, x + tw + 40, y + 46)
    d.rounded_rectangle(box, radius=23, fill=(225, 234, 250), outline=(196, 214, 243), width=1)
    d.text((x + 20, y + 8), text, font=f, fill=(38, 74, 140))
    return box[2] + 12


def main() -> None:
    img = gradient(W, H, (247, 250, 255), (226, 235, 249)).convert("RGBA")
    d = ImageDraw.Draw(img)

    # 右上角淡色装饰圆，避免大面积留白发闷
    d.ellipse((980, -190, 1420, 250), fill=(214, 228, 248, 120))
    d.ellipse((1080, -110, 1320, 130), fill=(226, 236, 252, 150))

    # ---- 左侧品牌区 ----
    icon = Image.open(ROOT / "assets" / "icon.png").convert("RGBA").resize((88, 88), Image.LANCZOS)
    img.paste(icon, (72, 58), icon)
    d.text((178, 60), "SnapOCR", font=font(62, True), fill=(20, 33, 61))
    d.text((181, 134), "离线截图 OCR  ·  Windows 10/11", font=font(22), fill=(91, 107, 140))

    d.text((72, 216), "截屏取字，只按一次热键", font=font(42, True), fill=(20, 33, 61))
    d.text((72, 282), "识别过的内容，随时能搜回来", font=font(29), fill=(70, 88, 122))

    x = 72
    for label in ("完全离线", "深色界面反色", "历史全文搜索"):
        x = pill(d, x, 344, label, font(19))
    d.text((72, 410), "识别全程在本机，不上传任何截图", font=font(20), fill=(110, 126, 155))

    d.line([(72, 472), (560, 472)], fill=(198, 212, 234), width=2)
    d.text((72, 500), "github.com/q037180/SnapOCR", font=font(24), fill=(38, 74, 140))
    d.text((72, 542), "免费  ·  开源 MIT  ·  v1.0.3", font=font(20), fill=(110, 126, 155))

    # ---- 右侧真实对比图卡片 ----
    card = (620, 92, 1220, 548)
    shadow(img, (628, 104, 1228, 560))
    d.rounded_rectangle(card, radius=22, fill=(255, 255, 255), outline=(206, 220, 240), width=2)
    src = Image.open(ROOT / "assets" / "compare-dark-ui.png").convert("RGB")
    iw = 560
    ih = round(iw * src.height / src.width)
    src = src.resize((iw, ih), Image.LANCZOS)
    px, py = card[0] + 20, card[1] + 22
    img.paste(src, (px, py))
    d.rounded_rectangle((px, py, px + iw, py + ih), radius=8, outline=(222, 230, 242), width=2)
    d.text((card[0] + 20, card[3] - 52), "深色界面预处理前后 · 真实像素对比",
           font=font(20), fill=(110, 126, 155))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"OK {OUT} {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
