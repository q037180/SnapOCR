# -*- coding: utf-8 -*-
"""生成 Windows 免安装 7z 绿色包 + zip 包 + SHA-256 校验文件。

打包的是 PyInstaller onedir 产物 dist/SnapOCR/（exe + 依赖目录），
不是单文件 exe：解压一次后启动不再自解压 160 MB，冷启动明显更快。

同时产出一份内容相同的 zip，用于 winget 分发：winget 的 InstallerType
不支持 7z，但支持 zip + NestedInstallerType: portable。之所以不用单文件
exe 交给 winget，是因为 PyInstaller onefile 每次启动都要解压 155 MB 到临时
目录，实测 52 次启动有 7 次以 127（ERROR_PROC_NOT_FOUND）失败。

运行：venv/Scripts/python.exe tools/make_portable_7z.py
输出（版本号取自环境变量 SNAP_OCR_VERSION，默认 v1.0.0）：
  dist/SnapOCR-<version>-win64.7z
  dist/SnapOCR-<version>-win64.7z.sha256
  dist/SnapOCR-<version>-win64.zip
  dist/SnapOCR-<version>-win64.zip.sha256
  dist/SnapOCR.exe.sha256
环境变量 SNAP_OCR_DIST 可覆盖 dist 目录（本地复查用）。
"""
from __future__ import annotations

import hashlib
import os
import zipfile

import py7zr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.environ.get("SNAP_OCR_DIST") or os.path.join(ROOT, "dist")
EXE = os.path.join(DIST, "SnapOCR.exe")  # 单文件版，仅用于附带生成校验值
PORTABLE_DIR = os.path.join(DIST, "SnapOCR")  # PyInstaller onedir 产物
PORTABLE_EXE = os.path.join(PORTABLE_DIR, "SnapOCR.exe")
VERSION = os.environ.get("SNAP_OCR_VERSION", "v1.0.0").strip() or "v1.0.0"
ARCHIVE = os.path.join(DIST, f"SnapOCR-{VERSION}-win64.7z")
ZIP = os.path.join(DIST, f"SnapOCR-{VERSION}-win64.zip")
NOTE = os.path.join(DIST, "使用说明.txt")
PRESET = 7  # LZMA2 字典更大，对内置 ONNX 模型更有效；打包慢一些但下载体积更小

NOTE_TEXT = f"""SnapOCR {VERSION} · Windows 10/11 x64 绿色版（onedir）
====================================================

1. 解压后进入 SnapOCR 文件夹，双击 SnapOCR.exe 即可运行。
   无需安装、无需 Python、不写注册表；内置简体中文识别模型，
   默认识别全程在本机离线完成。首次切换到繁中 / 英 / 日 / 韩时，
   会联网下载对应识别模型（只下载、不上传任何截图或识别文本），
   缓存到 %APPDATA%\\SnapOCR\\models\\，之后离线可用。
   本版本为 onedir 结构（主程序 + _internal 依赖目录），
   请勿把 exe 单独拷贝出来使用；整个文件夹一起移动即可。

2. 首次运行可能弹出 SmartScreen「Windows 已保护你的电脑」：
   本程序暂未做代码签名，点「更多信息」→「仍要运行」即可。
   运行前建议用 Release 页的 .sha256 文件核对完整性。

3. 全局热键：Ctrl+Alt+Q 截图识别 / Ctrl+Alt+T 截屏翻译 / Ctrl+Alt+L 长截图
   热键可在「设置」里改；托盘菜单与窗口按钮同样可用。

4. 会联网的只有两处：首次切换到非简体中文语言时下载识别模型；
   以及「截屏翻译」把识别出的文本发给必应翻译 / MyMemory（可在设置里关闭）。
   OCR 识别本身不联网、不上传。

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


def make_zip():
    """把 onedir 目录原样压成 zip，供 winget 的 zip + nested portable 使用。

    条目路径带顶层 SnapOCR/，与 7z 包保持一致，
    这样 manifest 里写 RelativeFilePath: SnapOCR\\SnapOCR.exe 即可。
    """
    tmp = ZIP + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    # PyInstaller 的 dist/SnapOCR/ 本身不含「使用说明.txt」，要额外写进去；
    # 但如果目录里已经有（比如从已发布的 7z 解压出来复查），就不能再写一遍，
    # 否则 zip 里会出现两个同名条目。
    has_note = os.path.isfile(os.path.join(PORTABLE_DIR, "使用说明.txt"))
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dns, fns in os.walk(PORTABLE_DIR):
            dns.sort()
            for fn in sorted(fns):
                full = os.path.join(dp, fn)
                arc = "SnapOCR/" + os.path.relpath(full, PORTABLE_DIR).replace(os.sep, "/")
                z.write(full, arc)
        if os.path.isfile(NOTE) and not has_note:
            z.write(NOTE, "SnapOCR/使用说明.txt")
    with zipfile.ZipFile(tmp) as z:
        names = z.namelist()
        print("zip entries:", len(names), "has exe:", "SnapOCR/SnapOCR.exe" in names)
    os.replace(tmp, ZIP)
    print("zip", os.path.getsize(ZIP) // 1024 // 1024, "MB")
    write_checksum(ZIP, os.path.basename(ZIP))


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
    has_note = os.path.isfile(os.path.join(PORTABLE_DIR, "使用说明.txt"))
    with py7zr.SevenZipFile(tmp, "w", filters=filters) as z:
        z.writeall(PORTABLE_DIR, "SnapOCR")
        if not has_note:  # 目录里已有就不再写，避免同名条目
            z.write(NOTE, "SnapOCR/使用说明.txt")
    make_zip()  # 要赶在删掉 NOTE 之前，zip 里同样带「使用说明.txt」
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
