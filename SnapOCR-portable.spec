# -*- mode: python ; coding: utf-8 -*-
# SnapOCR onedir 绿色版打包配置：
#   pyinstaller SnapOCR-portable.spec --noconfirm --workpath build/portable
# 与 SnapOCR.spec（onefile）的区别：产物是 dist/SnapOCR/ 目录，
# 启动时不需把 160 MB 自解压到临时目录，冷启动明显更快，适合 7z 绿色分发。
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

# 排除顶层旧版 VC 运行库 / ICU，让 System32 里的新版接管（子目录内的保留）
_CRT = {
    "ucrtbase.dll", "vcruntime140.dll", "vcruntime140_1.dll",
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "concrt140.dll", "vccorlib140.dll", "vcomp140.dll", "vcamp140.dll",
}


def _banned_top_level(entry) -> bool:
    dest = entry[0].replace("\\", "/")
    if "/" in dest:
        return False
    base = dest.rsplit("/", 1)[-1].lower()
    return base in _CRT or base.startswith("api-ms-win-") or base.startswith("icu")


a.binaries = [x for x in a.binaries if not _banned_top_level(x)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SnapOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SnapOCR",
)
