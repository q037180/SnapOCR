# -*- mode: python ; coding: utf-8 -*-
# SnapOCR 单文件打包配置：pyinstaller SnapOCR.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("app/assets", "app/assets"),  # 主窗口背景壁纸
]
datas += collect_data_files("rapidocr")  # config.yaml / default_models.yaml 等
hiddenimports = collect_submodules("rapidocr")  # 动态加载的模型子包

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy"],
    noarchive=False,
    optimize=1,
)

# Anaconda 环境会把旧版 VC 运行库与旧版 ICU（icuuc73）打进包顶层，
# 覆盖 PySide6 6.x 需要的新版 CRT/ICU，导致 Qt6Core 报“找不到指定的程序”。
# 排除顶层这些系统级 DLL，让 System32 里的新版运行库接管；子目录内的保留。
_CRT = {
    "ucrtbase.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "concrt140.dll", "vccorlib140.dll", "vcomp140.dll", "vcamp140.dll",
}


def _banned_top_level(entry) -> bool:
    dest = entry[0].replace("\\", "/")
    if "/" in dest:
        return False  # 子目录内的（如 PySide6/MSVCP140.dll）保留
    base = dest.rsplit("/", 1)[-1].lower()
    return base in _CRT or base.startswith("api-ms-win-") or base.startswith("icu")


a.binaries = [x for x in a.binaries if not _banned_top_level(x)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SnapOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 程序，不弹黑窗口
    icon="assets/icon.ico",
)
