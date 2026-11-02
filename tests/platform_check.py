# -*- coding: utf-8 -*-
"""跨平台兼容性自检：在 Windows / Linux / macOS 上运行，报告各功能可用性。

用法：python tests/platform_check.py
退出码 0 = 无硬性失败（可能有功能性降级提示）。
"""
from __future__ import annotations

import importlib
import sys

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"

results: list[str] = []
hard_fail = False


def check(name: str, ok: bool, note: str = "") -> None:
    tag = OK if ok else WARN
    line = f"{tag} {name}" + (f" — {note}" if note else "")
    results.append(line)
    print(line)


def try_import(name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(name)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


print(f"平台: {sys.platform}  Python: {sys.version.split()[0]}")

# ---- 依赖 ----
for mod in ("PySide6", "rapidocr", "onnxruntime", "mss", "keyboard",
            "docx", "openpyxl", "cv2", "numpy"):
    ok, err = try_import(mod)
    check(f"依赖 {mod}", ok, err if not ok else "")

# ---- Qt PDF（PDF 整档识别） ----
ok, err = try_import("PySide6.QtPdf")
check("PySide6.QtPdf（PDF 整档识别）", ok, err)

# ---- GUI 冒烟（offscreen，无需显示器） ----
try:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    sys.path.insert(0, __file__.rsplit("tests", 1)[0])
    from app.ui.main_window import MainWindow

    win = MainWindow(preload=False)
    win.close()
    check("GUI 主窗口构建（含全部子模块）", True)
except Exception as exc:  # noqa: BLE001
    check("GUI 主窗口构建（含全部子模块）", False, str(exc))
    hard_fail = True

# ---- 平台特有 ----
if sys.platform == "win32":
    check("长截图自动滚动", True, "Win32 滚轮注入")
    check("全局热键", True, "keyboard 无需特殊权限（部分键可能被系统占用）")
else:
    print(f"{WARN} 长截图自动滚动 — 仅 Windows 支持，其他平台点击后提示并跳过")
    if sys.platform == "linux":
        print(f"{WARN} 全局热键 — keyboard 库需要 root（sudo 运行），否则热键降级为按钮/托盘触发")
    elif sys.platform == "darwin":
        print(f"{WARN} 全局热键 — 需在 系统设置→隐私与安全→辅助功能 中授权终端/应用")
    print(f"{WARN} GPU DirectML — 仅 Windows；Linux/macOS 用 CUDA（需 onnxruntime-gpu）或 CPU")

# ---- GPU provider ----
try:
    import onnxruntime as ort

    provs = ort.get_available_providers()
    print(f"[INFO] onnxruntime providers: {provs}")
except Exception as exc:  # noqa: BLE001
    print(f"[INFO] onnxruntime 检测失败: {exc}")

print()
print("结果：" + ("无硬性失败（平台差异见上方 WARN/INFO 说明）" if not hard_fail else "存在硬性失败"))
sys.exit(1 if hard_fail else 0)
