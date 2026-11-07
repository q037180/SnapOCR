# -*- coding: utf-8 -*-
"""一致性测试：防止「代码改了、文档没改」这类漂移。

项目里踩过三次同一类坑，都是靠人肉发现的：
  1. 版本号写死在 tools/make_portable_7z.py 里（默认 v1.0.0），和实际代码版本脱节；
  2. 下载表里 zip 写成 155 MB，和同表的 120 / 163 MB 口径不一致；
  3. 发布文档教人一次加 4–5 个掘金标签，而平台只允许 1 个。

所以这里把「能被机器检查的事实」全部锁死：版本号在 5 个文件里必须一致、
发布链接必须指向当前版本、README 和落地页引用的图片必须真实存在、
assets/ 与 docs/assets/ 必须逐字节相同。

跑法（不需要 pytest，标准库即可）：
    python -m unittest discover -s tests -v
    python tests/test_consistency.py
"""
from __future__ import annotations

import filecmp
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import APP_VERSION  # noqa: E402

SITE = "https://q037180.github.io/SnapOCR"
VER = APP_VERSION.strip()


def read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class VersionSingleSource(unittest.TestCase):
    """APP_VERSION 是全项目唯一的版本号来源。"""

    def test_changelog_top_entry(self):
        m = re.search(r"^##\s*\[(\d+\.\d+\.\d+)\]", read("CHANGELOG.md"), re.M)
        self.assertIsNotNone(m, "CHANGELOG.md 里找不到 `## [x.y.z]` 形式的版本标题")
        self.assertEqual(m.group(1), VER, "CHANGELOG 最新版本与 app/config.py 的 APP_VERSION 不一致")

    def test_winget_manifests(self):
        base = "launch/winget/manifests/q/q037180/SnapOCR"
        if not os.path.isdir(os.path.join(ROOT, base)):
            self.skipTest("没有 winget 清单")
        version_dirs = [d for d in os.listdir(os.path.join(ROOT, base)) if re.fullmatch(r"\d+\.\d+\.\d+", d)]
        self.assertIn(VER, version_dirs, f"winget 清单目录里没有 {VER}，只有 {version_dirs}")
        inst = read(f"{base}/{VER}/q037180.SnapOCR.installer.yaml")
        self.assertIn(f"PackageVersion: {VER}", inst)
        self.assertIn(f"/v{VER}/", inst, "winget InstallerUrl 没指向当前版本")
        sha = re.search(r"InstallerSha256:\s*([0-9a-fA-F]{64})", inst)
        self.assertIsNotNone(sha, "winget installer 的 InstallerSha256 缺失或格式不对")

    def test_scoop_manifest(self):
        p = "launch/scoop/snapocr.json"
        if not os.path.exists(os.path.join(ROOT, p)):
            self.skipTest("没有 scoop 清单")
        body = read(p)
        self.assertIn(f'"version": "{VER}"', body, "scoop 清单 version 与 APP_VERSION 不一致")
        self.assertIn(f"/v{VER}/", body, "scoop 清单下载地址没指向当前版本")


class DownloadLinks(unittest.TestCase):
    """README 和落地页的下载链接必须指向当前版本，不能残留旧版本。"""

    def _assert_only_current(self, rel: str) -> None:
        body = read(rel)
        found = set(re.findall(r"releases/download/(v\d+\.\d+\.\d+)/", body))
        stale = {v for v in found if v != f"v{VER}"}
        self.assertEqual(stale, set(), f"{rel} 里还残留旧版本下载链接：{sorted(stale)}")

    def test_readme(self):
        self._assert_only_current("README.md")

    def test_landing_page(self):
        self._assert_only_current("docs/index.html")


class ImagesResolve(unittest.TestCase):
    """文档里引用的图片必须真实存在——外链失效是沉默故障，用户只看到空白。"""

    def test_readme_pages_urls_point_to_existing_files(self):
        body = read("README.md")
        names = set(re.findall(re.escape(SITE) + r"/assets/([\w.\-]+)", body))
        self.assertTrue(names, "README 里没有识别到 Pages 图片链接")
        missing = [n for n in sorted(names) if not os.path.exists(os.path.join(ROOT, "docs", "assets", n))]
        self.assertEqual(missing, [], f"README 引用了 docs/assets/ 里不存在的图片：{missing}")

    def test_landing_page_relative_images(self):
        body = read("docs/index.html")
        names = set(re.findall(r'src="assets/([\w.\-]+)"', body))
        self.assertTrue(names, "落地页里没有识别到 assets/ 相对路径图片")
        missing = [n for n in sorted(names) if not os.path.exists(os.path.join(ROOT, "docs", "assets", n))]
        self.assertEqual(missing, [], f"落地页引用了 docs/assets/ 里不存在的图片：{missing}")


class AssetsInSync(unittest.TestCase):
    """assets/ 是源，docs/assets/ 是 Pages 图床，同一张图必须逐字节相同。"""

    def test_mirror_is_byte_identical(self):
        src, dst = os.path.join(ROOT, "assets"), os.path.join(ROOT, "docs", "assets")
        if not os.path.isdir(src):
            self.skipTest("没有 assets/")
        exts = {".png", ".gif", ".jpg", ".jpeg", ".webp"}
        drift = []
        for name in sorted(os.listdir(src)):
            if os.path.splitext(name)[1].lower() not in exts:
                continue
            d = os.path.join(dst, name)
            if not os.path.exists(d) or not filecmp.cmp(os.path.join(src, name), d, shallow=False):
                drift.append(name)
        self.assertEqual(drift, [], f"这些图与 docs/assets/ 不同步：{drift}（跑 tools/sync_assets.py）")


class PackageFiles(unittest.TestCase):
    """打包脚本引用的文件必须存在，否则 CI 会在 PyInstaller 阶段失败。"""

    def test_spec_icons_exist(self):
        for spec in ("SnapOCR.spec", "SnapOCR-portable.spec"):
            body = read(spec)
            for icon in re.findall(r'icon="([^"]+)"', body):
                self.assertTrue(os.path.exists(os.path.join(ROOT, icon)), f"{spec} 引用的图标不存在：{icon}")

    def test_bundled_app_asset_exists(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "app", "assets", "bg.png")),
                        "app/assets/bg.png 缺失，主窗口背景会静默降级")


if __name__ == "__main__":
    unittest.main(verbosity=2)
