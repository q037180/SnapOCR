# -*- coding: utf-8 -*-
"""生成 Windows 免安装 7z 绿色包 + SHA-256 校验文件。

打包的是 PyInstaller onedir 产物 dist/SnapOCR/（exe + 依赖目录），
不是单文件 exe：解压一次后启动不再自解压 160 MB，冷启动明显更快。

运行：venv/Scripts/python.exe tools/make_portable_7z.py
输出：
  dist/SnapOCR-v1.0.0-win64.7z
  dist/SnapOCR-v1.0.0-win64.7z.sha256
  dist/SnapOCR.exe.sha256
"""
from __future__ import annotations

import hashlib
import os

import py7zr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
EXE = os.path.join(DIST, "SnapOCR.exe")  # 单文件版，仅用于附带生成校验值
PORTABLE_DIR = os.path.join(DIST, "SnapOCR")  # PyInstaller onedir 产物
PORTABLE_EXE = os.path.join(PORTABLE_DIR, "SnapOCR.exe")
ARCHIVE = os.path.join(DIST, "SnapOCR-v1.0.0-win64.7z")
NOTE = os.path.join(DIST, "使用说明.txt")
PRESET = 7  # LZMA2 字典更大，对内置 ONNX 模型更有效；打包慢一些但下载体积更小

NOTE_TEXT = """SnapOCR v1.0.0 · Windows 10/11 x64 绿色版（onedir）
====================================================

1. 解压后进入 SnapOCR 文件夹，双击 SnapOCR.exe 即可运行。
   无需安装、无需 Python、无需联网；识别模型已内置，OCR 全程离线。
   本版本为 onedir 结构（主程序 + _internal 依赖目录），
   请勿把 exe 单独拷贝出来使用；整个文件夹一起移动即可。

2. 首次运行可能弹出 SmartScreen「Windows 已保护你的电脑」：
   本程序暂未做代码签名，点「更多信息」→「仍要运行」即可。
   运行前建议用 Release 页的 .sha256 文件核对完整性。

3. 全局热键：Ctrl+Alt+Q 截图识别 / Ctrl+Alt+T 截屏翻译 / Ctrl+Alt+L 长截图
   热键可在「设置」里改；托盘菜单与窗口按钮同样可用。

4. 只有「截屏翻译」会联网（必应翻译 / MyMemory），OCR 本身不联网。

5. 卸载：直接删除本文件夹。
   个人配置位于 %APPDATA%\\SnapOCR\\settings.json，需要时一并删除。

项目地址：https://github.com/q037180/SnapOCR
问题反馈：https://github.com/q037180/SnapOCR/issues
许可：MIT
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksum(path, name):
    digest = sha256(path)
    out = path + ".sha256"
    with open(out, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(f"{digest}  {name}\n")
    print("checksum", os.path.basename(path), digest)
    return out


def dir_size(path):
    return sum(
        os.path.getsize(os.path.join(dp, fn))
        for dp, _, fns in os.walk(path)
        for fn in fns
    )


def main():
    if not os.path.isfile(PORTABLE_EXE):
        raise SystemExit(
            f"找不到 {PORTABLE_EXE}，请先构建 onedir 版本：\n"
            "  pyinstaller SnapOCR-portable.spec --noconfirm "
            "--workpath build/portable --distpath dist"
        )

    with open(NOTE, "w", encoding="utf-8-sig", newline="\r\n") as fp:
        fp.write(NOTE_TEXT)

    print("packing onedir dir", dir_size(PORTABLE_DIR) // 1024 // 1024, "MB ...")
    tmp = ARCHIVE + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    filters = [{"id": py7zr.FILTER_LZMA2, "preset": PRESET}]
    with py7zr.SevenZipFile(tmp, "w", filters=filters) as z:
        z.writeall(PORTABLE_DIR, "SnapOCR")
        z.write(NOTE, "SnapOCR/使用说明.txt")
    os.remove(NOTE)

    print("archive", os.path.getsize(tmp) // 1024 // 1024, "MB")
    with py7zr.SevenZipFile(tmp, "r") as z:
        names = z.getnames()
        print("entries:", len(names), "has exe:", "SnapOCR/SnapOCR.exe" in names)
    os.replace(tmp, ARCHIVE)  # 打包成功才替换，避免中途失败丢掉上一版

    write_checksum(ARCHIVE, os.path.basename(ARCHIVE))
    if os.path.isfile(EXE):
        write_checksum(EXE, os.path.basename(EXE))


if __name__ == "__main__":
    main()
