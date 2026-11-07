# 参与开发

## 环境

- Windows 10 / 11 x64（截图遮罩、全局热键、长截图滚轮注入都依赖 Win32，其他平台只能跑部分逻辑）
- Python 3.10+（代码使用 `str | None` 这类 PEP 604 语法）

```bash
git clone https://github.com/q037180/SnapOCR.git
cd SnapOCR
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt
venv/Scripts/python entry.py
```

打包与出图还要额外依赖：

```bash
venv/Scripts/python -m pip install -r requirements-dev.txt
```

## 提交前自检

CI 会在 push / PR 上跑同一套检查，本地先跑一遍能省一轮往返：

```bash
venv/Scripts/python -m compileall -q app tools tests entry.py
venv/Scripts/python -m pyflakes app tools tests entry.py
venv/Scripts/python -m unittest discover -s tests -v
```

一致性测试会拦住几类历史踩过的坑：版本号在各处不一致、下载链接残留旧版本、文档引用了不存在的图片、演示图在 `assets/` 里出现重复副本。

## 几条约定

- **版本号只有一个来源**：`app/config.py` 的 `APP_VERSION`。`CHANGELOG.md` 首条、`packaging/` 下的 winget / scoop 清单必须跟着改，发版 CI 会校验 tag 与它一致。
- **本地打出来的包不能上传到 Release**：PyInstaller 构建是不确定的（嵌入时间戳、依赖解析到的版本都可能不同），同一个版本号在本地和 CI 出的 SHA-256 必然不一样。已发布资产的哈希被 `packaging/winget` 清单引用，替换后 `InstallerSha256` 立刻失配。发版只推 tag，让 `release.yml` 构建。
- **演示图只放 `docs/assets/`**：GitHub Pages 直接服务这个目录，README 里用 `https://q037180.github.io/SnapOCR/assets/xxx.gif` 引用。`tools/make_*.py` 的输出路径已经是这里，重跑脚本即更新，不要再往 `assets/` 拷副本。
- **`assets/` 只放图标**：`icon.svg` 是设计源，`icon.ico` 被两个 `.spec` 引用。
- 注释与文档用中文写，变量名与提交信息的标题用英文短句，正文可以中文。

## 提 PR

- 一个 PR 只做一件事，行为变更请带上「改之前 / 改之后」的对比说明。
- 修 bug 请附复现方式；涉及识别结果的，最好给一张能复现的图片（可以打码）。
- 不要提交 `venv/`、`dist/`、`build/`、`models/`——`.gitignore` 已覆盖。
