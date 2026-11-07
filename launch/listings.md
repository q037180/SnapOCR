# 分发渠道：复制即用的收录文案

> 这些渠道都是「提交一次、长期有量」的被动流量。文件已备好，但**对外提交需要你本人账号**，
> 我不会替你在第三方平台发言。提交前先确认各平台当期规则与入口是否有变。

## 1. winget（Windows 包管理器）

`winget install q037180.SnapOCR` —— 装完出现在 Windows 包管理器搜索结果里。

**已备好**：`launch/winget/manifests/q/q037180/SnapOCR/1.0.3/` 四个 YAML（version / installer / defaultLocale.en-US / locale.zh-CN）。

**为什么用单文件 exe 而不是 7z**：winget 的 `InstallerType` 不支持 7z，所以 installer 指向 `SnapOCR.exe`（portable 类型，`PortableCommandAlias: snapocr`）。启动更快的 7z 绿色包交给 Scoop。

**提交步骤**

1. Fork `microsoft/winget-pkgs`，把上面整个 `1.0.3/` 目录放到 `manifests/q/q037180/SnapOCR/1.0.3/`。
2. 本地校验：`winget validate --manifest <目录>`；再 `winget install --manifest <目录>` 实测一次。
3. PR 标题按仓库模板：`New package: q037180.SnapOCR version 1.0.3`。
4. 校验若提示 schema 版本过旧，按提示把 `ManifestVersion` 调高再跑一次。

**注意**：未签名的 exe 会在首次运行触发 SmartScreen，winget 审核可能要求说明；`README` 与 Release 页已写明，PR 描述里主动提一句。

## 2. Scoop

`scoop bucket add ...` / `scoop install snapocr` —— Scoop 原生支持 7z，直接用绿色包。

**已备好**：`launch/scoop/snapocr.json`（含 `checkver` / `autoupdate`，后续发版可自动跟随 tag）。

**提交步骤**：先试 `ScoopInstaller/Extras` 的 PR（按它的 `bucket/*.json` 命名与 PR 模板）。主 bucket 对未签名、受众窄的桌面工具可能拒收；被拒就自建 bucket（一个 git 仓库 + 这个 json），在 README 里写 `scoop bucket add snapocr https://github.com/q037180/scoop-bucket`，效果一样且不依赖审核。

本地验证：`scoop install snapocr.json` 直接装本地清单，确认 `bin` 与 `extract_dir` 路径正确（7z 内顶层目录名是 `SnapOCR`）。

## 3. HelloGitHub 月刊（中文项目，优先级最高）

专门收录小而美的开源项目，中文曝光效率通常高于技术社区长文。

**投稿文案（复制）**

```
项目名：SnapOCR
地址：https://github.com/q037180/SnapOCR
语言：Python
一句话：按一次热键框选屏幕就取字，深色 IDE 截图自动反色增强，识别过的内容随时能搜回来。

推荐理由：
系统自带 OCR 处理白底黑字没问题，但深色主题截图（代码、报错栈、暗色文档）容易整行漏检。
这个项目在送进识别模型前先判断整体亮度自动反色，再用 CLAHE 提局部对比度；
另一个少见的点是所有识别结果都进本地历史，关键词即时过滤、双击再次复制、可导出 Excel。
内置简体中文模型，默认识别全程离线，不上传截图。Windows 绿色包解压即用，MIT。

配图：<仓库>/assets/compare-dark-ui.png（真实像素对比）
      <仓库>/assets/hero-15s.gif（15 秒串联演示）
      <仓库>/assets/social-preview.png（封面）
```

**入口**：到 `521xueweihan/HelloGitHub` 仓库看当期「项目投稿 / 分享项目」的 issue 模板或官网投稿入口，按模板字段粘贴。**提交前确认入口变化**，别直接发给某个固定 issue 编号。

## 4. AlternativeTo

挂到 Umi-OCR、ShareX、TextSniper、ShareText 等软件的 alternatives 页面，是长期稳定的导流。

**字段（复制）**

```
Name:        SnapOCR
URL:         https://github.com/q037180/SnapOCR
Platforms:   Windows
License:     Open Source (MIT), Free
Category:    OCR / Screenshot Utilities
Short:       Offline screenshot OCR with automatic dark-UI inversion and searchable history.
Description: Press a global hotkey, drag a region, and the recognized text lands on the
             clipboard. Dark IDE / dark-mode captures are inverted and CLAHE-enhanced before
             recognition. Every result is saved to a local searchable history and can be
             exported to txt/docx/pdf/md/xlsx. Batch images, per-page PDF, table-to-Excel,
             long screenshot stitching and screenshot translation included. Bundled Chinese
             model runs fully offline.
Tags:        ocr, screenshot, offline, clipboard, pdf, table, dark-mode
```

提交前读该站的 self-promotion / 新增软件规则，通常需要软件已可公开下载 + 至少一张截图。

## 5. awesome-\* 列表（SEO 长尾）

搜索 `awesome-ocr`、`awesome-windows`、`awesome-python` 等仓库的 OCR 章节，按各列表既有格式加**一行**，不要改格式、不要加整段介绍。

英文列表：

```
- [SnapOCR](https://github.com/q037180/SnapOCR) - Offline screenshot OCR for Windows with automatic dark-UI inversion, searchable result history, PDF/batch/table recognition.
```

中文列表：

```
- [SnapOCR](https://github.com/q037180/SnapOCR) - 离线截图 OCR：深色界面自动反色增强，识别结果进历史可搜索，支持批量 / PDF / 表格转 Excel。
```

一次只投 1–2 个列表，PR 描述写「为什么这个条目符合本列表的收录标准」，别群发同一段话。

## 6. 其它中文站点（复用现成稿）

| 站点 | 用哪份稿 | 注意 |
| --- | --- | --- |
| 少数派 | `READY-TO-POST.md` §1 扩写 | 需要「使用体验 / 场景」视角，不要写成更新日志 |
| 吾爱破解 | `post-zh.md` | 强调离线、无广告、绿色包；按版块规则发帖 |
| IT之家 / 软媒 | `post-zh.md` 精简到 300 字 | 走「软件投稿」入口，附官方下载与授权 |
| 知乎 | `READY-TO-POST.md` §3 | 先正经回答已有 OCR 问题，工具放后半 |
| B站 / 视频号 | `assets/hero-15s.gif` 转竖版 MP4 | 简介放仓库链接，评论区保持开放 |

所有站点的**首图都用本地上传**，不要贴 GitHub 外链（见 `READY-TO-POST.md` §1「配图」）。
