# SnapOCR 首发执行清单（2026-11-04 起，两周）

> 目标不是 star，是 **1 次有效曝光 + 10 个真实用户反馈**。
> 当前唯一剩下的动作：按 [`READY-TO-POST.md`](READY-TO-POST.md) 发出第一帖。

## 状态（2026-11-05 21:00 线上实测）

| 项 | 线上实测结果 |
| --- | --- |
| §0 About description / topics / homepage | 已完成：description 与 16 个 topics 已填，homepage 已补为 Releases 页 |
| §1 Release 资产 | 已完成：5 个全部在线（7z 119,010,521 B / 两个 .sha256 / compare-dark-ui.png / hero-15s.gif），body 已改为诚实版 |
| README 引用资产 | 12 个 URL 逐个返回 206，无死链 |
| 二进制可用性 | 7z 绿色包与单文件 exe 各跑一次 `--smoke` 均退出 0；SHA-256 与线上 digest 一致 |
| CI 发版链路 | 已补齐：`3235c95` 起同时构建单文件 exe 与 7z 绿色包，上传 exe + 7z + 2 个 `.sha256` |
| 本地 / 远端 | 已对齐，`HEAD == origin/main == 3235c95`，工作区干净；本机 `git push` 已可直接运行 |
| **§2 实际发帖** | **仍是 0，这是唯一剩下的动作** |
| 网络可达性（21:30 实测） | `v2ex.com`（全站）、Hacker News、Reddit 当前网络不通；掘金、知乎、小众软件、少数派、吾爱破解、博客园、GitHub 全部 200。**首发改掘金**，见 `READY-TO-POST.md` §1 |

不要再补物料、不要再改 README、不要再加功能。定稿见 [`READY-TO-POST.md`](READY-TO-POST.md)：复制 → 粘贴 → 发布。

新增风险：搜索「SnapOCR」前 5 条结果里没有本仓库，至少 4 个同名项目，其中 ocrtool.io 的商业版**已经把「深色背景自动反色 + 多次预处理 + 完全离线」写成自家卖点**。品牌词被占、差异点被抢先占位，所以投稿标题一律痛点前置，不要以 SnapOCR 开头，用仓库链接锚定身份。

## 0. 仓库门面（已完成，留作核对）

GitHub 仓库页 → 右侧 **About** → 齿轮：

**Description（已填的是这行）**

```
Offline screenshot OCR for dark IDEs and dark-mode pages — auto-inverts dark captures and keeps every result in a searchable history. Windows, MIT.
```

- **Website**：`https://github.com/q037180/SnapOCR/releases`
- **Topics**：已含 `dark-mode`、`screenshot-ocr`、`text-extractor`、`clipboard`、`pp-ocr` 等共 16 个

## 1. Release 资产（已完成，留作核对）

`v1.0.1`（2026-11-06）已由 CI 自动产出并挂到 Release：`SnapOCR.exe`（155 MB）、`SnapOCR-v1.0.1-win64.7z`（115 MB）、两个 `.sha256`，校验值与 GitHub 记录的资产 digest 一致。`v1.0.0` 的 Release 保留原样，图片素材仍从它直链引用：

| 文件 | 用途 |
| --- | --- |
| `SnapOCR-v1.0.1-win64.7z` | onedir 绿色包，解压一次、启动免自解压（**对外主推**） |
| `SnapOCR.exe` | 单文件版 |
| `*.sha256` | 对应校验值 |
| `assets/compare-dark-ui.png` | 投稿首图（深色截图真实前后对比，v1.0.0 Release 直链） |
| `assets/hero-15s.gif` | 15 秒串联演示（v1.0.0 Release 直链） |

下次打 tag 发版时，CI 会自动产出 exe + `SnapOCR-<tag>-win64.7z` + 两个 `.sha256`，详见 `.github/workflows/release.yml`。

## 2. 渠道清单（按顺序，不要一天全发）

| 顺序 | 平台 / 入口 | 用哪份稿 | 时间 | 备注 |
| --- | --- | --- | --- | --- |
| **D1（今晚）** | 掘金 → 写文章 | **`READY-TO-POST.md` §1 Markdown 稿** | 21:00–22:00 | 当前网络可达、发文即发布；标题痛点前置，发完守 1–2 小时回评论 |
| D1-备用 | V2EX → 「分享创造」节点 | `READY-TO-POST.md` §1-备用 终稿 | 网络恢复后 | 原首选渠道、受众最契合；稿子已备好，能打开时直接发 |
| D2 | 小众软件投稿 | `READY-TO-POST.md` §2 的 300 字稿 + 3 图 | 白天 | 按「名称 / 平台 / 体积 / 授权 / 官网」列字段 |
| D4 | 知乎（回答已有 OCR 相关问题） | `READY-TO-POST.md` §3 | 晚上 | 先正经答题，工具介绍放后半，避免软文判定 |
| D5 | 公众号 | `post-zh.md` + 15s GIF 转 MP4 | — | 「两个痛点 + 一张对比图 + 下载方式」 |
| 暂缓（网络不通） | Hacker News → Show HN | `READY-TO-POST.md` §4 + `post-en.md` 正文 | 北京时间 21:00–23:00 | 标题前缀必须 `Show HN: `；需先解决网络 |
| 暂缓（网络不通） | Reddit r/Windows、r/opensource | `post-en.md` Reddit 版 | 隔天分开发 | 需先解决网络，并读各版 self-promotion 规则 |
| D11 | B站动态 / 短视频 | hero-15s.gif 转视频加字幕 | — | 简介放仓库链接，评论区别关 |

**节奏**：中文社区先发（反馈快、能改），中间留 1–2 天根据反馈修 README / 修 bug，再发英文社区。一次只发一个主渠道。

## 3. 两周目标与记录表

- **1 次有效曝光** = 有 1 个外部来源带来 ≥20 次 Release 下载，或 ≥5 条非熟人评论
- **10 个真实用户反馈** = issue / 评论 / 私信里包含具体使用场景或具体问题（不含「支持一下」）
- 每次反馈 24 小时内回复；把高频问题写进 README，别急着加功能

| 日期 | 渠道 | 链接 | 曝光 | 下载 | 反馈数 | 改了什么 | 下一步 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |

如果两周结束两项都没达成，问题在「楔子场景」而不是发布量：换一个更窄的场景重写标题，再发一轮，别加功能。

## 4. 借势 Umi-OCR（D11 之后可选）

- 先读 Umi-OCR 仓库的插件机制 / contributing 文档，确认是否接受外部插件或 PR
- 提一个 issue 草稿，标题类似 `[Suggestion] Dark-capture preprocessing + searchable history`，附 `compare-dark-ui.png` 和 `_enhance()` 的实现思路，**先讨论、不求合并**
- 把 `app/core/engine.py` 里 `_enhance()` 的十几行整理成可复用片段作为讨论依据
- 若社区有兴趣再提 PR；没兴趣就当作一次曝光，不强求
- 别写成「我做了个替代品，求合并」，容易被当成引流

## 5. 已完成 / 仍需你做

**已完成（本地文件 + 线上设置）**

- `README.md`：中英双语、首屏差异化、两个独有场景、SmartScreen 说明、平台声明收窄为 Windows、7z 与 SHA-256 说明、诚实的多语言/联网声明
- `assets/compare-dark-ui.png`、`assets/hero-15s.gif` 及可复现脚本
- `launch/READY-TO-POST.md`（发布执行包）、`launch/post-zh.md`、`launch/post-en.md`
- `SnapOCR-portable.spec` + `tools/make_portable_7z.py`：onedir 绿色版构建与 7z 打包、SHA-256 生成，版本号跟随 tag
- `.github/workflows/release.yml`：同时产出单文件 exe 与 7z 绿色包
- `requirements.txt`、`启动.bat`、CI 产物路径等安装/构建问题修复

**仍需你本人做**

- 注册或登录各平台、**实际发帖**（我没有你的社区账号，也不替你对外发言）
- 发完 2 小时内回评论，48 小时内填记录表
- 代码签名证书（需购买 / 申请，签名后再发版可消除 SmartScreen 提示）
- macOS / Linux 官方二进制（需对应平台的构建机或 CI）
- 实际给 Umi-OCR 提 issue / PR（可选）

## 6. 复现命令

```bash
# 素材
venv/Scripts/python.exe tools/make_compare_image.py
venv/Scripts/python.exe tools/make_hero_gif.py

# 绿色包（先 onedir 构建，再打包 + 校验）
venv/Scripts/python.exe -m PyInstaller SnapOCR-portable.spec --noconfirm --workpath build/portable --distpath dist
venv/Scripts/python.exe tools/make_portable_7z.py

# 单文件 exe（原流程）
venv/Scripts/python.exe -m PyInstaller SnapOCR.spec --noconfirm
```
