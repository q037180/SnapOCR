# -*- coding: utf-8 -*-
"""把 assets/ 里的演示图同步到 docs/assets/（Pages 图床用的就是这一份）。

为什么要这一步：README 的图走 Pages 图床、落地页用相对路径读 docs/assets/，
而 tools/make_*.py 生成图片时只写 assets/。两边一旦不同步，README 看到的是新图、
落地页还是旧图——之前踩过一次，改成脚本 + CI 校验。

用法：
    venv/Scripts/python.exe tools/sync_assets.py          # 同步
    venv/Scripts/python.exe tools/sync_assets.py --check  # 只检查，不同步（CI 用）

只同步「落地页会引用」的位图（png / gif / jpg / webp）；
icon.ico 是打包用的可执行文件图标，icon.svg 是图标源文件，都不进图床。
"""
from __future__ import annotations

import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets")
DST = os.path.join(ROOT, "docs", "assets")
EXTS = {".png", ".gif", ".jpg", ".jpeg", ".webp"}


def main() -> int:
    check_only = "--check" in sys.argv[1:]
    if not os.path.isdir(SRC):
        print(f"找不到源目录：{SRC}")
        return 2
    os.makedirs(DST, exist_ok=True)

    names = sorted(n for n in os.listdir(SRC) if os.path.splitext(n)[1].lower() in EXTS)
    if not names:
        print("assets/ 下没有位图，无事可做")
        return 0

    changed: list[str] = []
    missing: list[str] = []
    for name in names:
        s = os.path.join(SRC, name)
        d = os.path.join(DST, name)
        if os.path.exists(d) and filecmp.cmp(s, d, shallow=False):
            continue
        if not os.path.exists(d):
            missing.append(name)
        else:
            changed.append(name)
        if not check_only:
            shutil.copy2(s, d)

    total = sum(os.path.getsize(os.path.join(SRC, n)) for n in names) / 1e6
    if check_only:
        if changed or missing:
            for n in missing:
                print(f"[缺失] docs/assets/{n}")
            for n in changed:
                print(f"[不一致] docs/assets/{n}")
            print(f"\n{len(missing) + len(changed)} 个文件与 assets/ 不同步，"
                  f"运行 `python tools/sync_assets.py` 修复。")
            return 1
        print(f"[ OK ] docs/assets/ 与 assets/ 一致（{len(names)} 个文件，{total:.1f} MB）")
        return 0

    for n in missing:
        print(f"[复制] {n}")
    for n in changed:
        print(f"[更新] {n}")
    if not (missing or changed):
        print(f"[ OK ] 已是最新（{len(names)} 个文件，{total:.1f} MB）")
    else:
        print(f"\n完成：复制 {len(missing)} 个、更新 {len(changed)} 个，共 {total:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
