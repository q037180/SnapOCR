# SnapOCR 首发执行清单（2026-11-04 起，两周）

> 目标不是 star，是 **1 次有效曝光 + 10 个真实用户反馈**。
> 本文里「已完成」是本次已经落地的文件；「需要你做」是必须本人登录/授权才能完成的动作。

## 状态更新（2026-11-05 线上 API 实测）

下面 §0 / §1 里标「需要你做」的两项**早已完成**，本文原状态已过期，以这里为准：

| 项 | 线上实测结果 |
| --- | --- |
| §0 About description | 已填，正是本文给的那句英文；topics 已有 16 个 |
| §0 Website / homepage | 原为 `null`，2026-11-05 已补为 Releases 页 |
| §1 Release 资产 | 5 个全部已上传（7z 119,010,521 B / 两个 .sha256 / compare-dark-ui.png / hero-15s.gif），Release body 已是新版 |
| README 引用的资产 | 12 个 URL 逐个请求全部返回 206，无死链 |
| §2 实际发帖 | **仍是 0，这是唯一剩下的动作** |

因此不要再补物料、不要再改 README。定稿见 [`READY-TO-POST.md`](READY-TO-POST.md)：复制 → 粘贴 → 发布。

新增风险：搜索「SnapOCR」前 5 条结果里没有本仓库，至少 4 个同名项目，其中 ocrtool.io 的商业版**已经把「深色背景自动反色 + 多次预处理 + 完全离线」写成自家卖点**。品牌词被占、差异点被抢先占位，所以投稿标题一律痛点前置，不要以 SnapOCR 开头，用仓库链接锚定身份。

## 0. 先改仓库门面（5 分钟，需要你本人操作）

GitHub 仓库页 → 右侧 **About** → 齿轮：

**Description（直接复制这行）**

```
Offline screenshot OCR for dark IDEs and dark-mode pages — auto-inverts dark captures and keeps every result in a searchable history. Windows, MIT.
```

中文备选（如果更想面向中文读者）：

```
深色 IDE / 暗色网页截图 OCR，自动反色增强，识别结果可搜索回溯；Windows 离线运行，MIT。
```

- **Website**：填 Releases 页 `https://github.com/q037180/SnapOCR/releases`，或留空
- **Topics 追加**：`dark-mode`、`screenshot-ocr`、`text-extractor`、`clipboard`、`pp-ocr`
- 顺手把 README 里首屏的 `hero-15s.gif` 相对链接确认一下：GitHub 上点击可打开；如果国内图片代理读不了，把这一行换成 Release 资产 URL

> 这一步我没有你的 GitHub 写权限，本机也没有 `gh` CLI，只能把文案备好给你粘贴。

## 1. 上传 Release 资产（需要你本人操作）

编辑 `v1.0.0` Release（或新建 `v1.0.1`），把下面这些文件拖进 Assets：

| 文件 | 用途 |
| --- | --- |
| `dist/SnapOCR-v1.0.0-win64.7z` | onedir 绿色包，解压一次、启动免自解压 |
| `dist/SnapOCR-v1.0.0-win64.7z.sha256` | 绿色包校验值 |
| `dist/SnapOCR.exe.sha256` | 单文件 exe 校验值 |
| `assets/compare-dark-ui.png` | 投稿首图（深色截图真实前后对比） |
| `assets/hero-15s.gif` | 15 秒串联演示，供帖子/视频使用 |

把两个 SHA-256 明文贴进 Release 说明，方便用户核对。校验值以 `.sha256` 文件为准。

## 2. 渠道清单（按顺序，不要一天全发）

| 顺序 | 平台 / 入口 | 用哪份稿 | 时间 | 备注 |
| --- | --- | --- | --- | --- |
| D1 | V2EX → 「分享创造」节点 | `post-zh.md` 标题 1 | 20:00–22:00 | 第一人称，链接只留仓库 + Releases；发完守 2 小时回评论 |
| D2 | 小众软件投稿 | `post-zh.md` 压到 300 字 + 3 图 | 白天 | 按「名称 / 平台 / 体积 / 授权 / 官网」列字段 |
| D4 | 知乎（回答已有 OCR 相关问题，或写文章） | `post-zh.md` 深色截图那段 | 晚上 | 先正经答题，工具介绍放后半，避免软文判定 |
| D5 | 公众号 | `post-zh.md` + 15s GIF 转 MP4 | — | 「两个痛点 + 一张对比图 + 下载方式」 |
| D7 | Hacker News → Show HN | `post-en.md` | 北京时间 21:00–23:00 | 标题前缀必须 `Show HN: `；发完守 2 小时 |
| D9 | Reddit r/Windows、r/opensource | `post-en.md` Reddit 版 | 隔天分开发 | 先读各版 self-promotion 规则，有的要求周帖/开发者 flair |
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

## 5. 本次已完成 / 仍需你做

**已完成（本次落地）**

- `README.md`：首屏一句话差异化 + 两个独有场景、删除全部「Umi-OCR 同款」措辞、补齐可独立阅读的英文 README、SmartScreen 说明、平台声明收窄为 Windows、7z 绿色包与 SHA-256 说明、修掉「打包发布」死链
- `assets/compare-dark-ui.png`：深色截图 vs `_enhance()` 真实输出的对比图（不伪造识别结果）
- `assets/hero-15s.gif`：14.97 秒串联演示
- `launch/post-zh.md` / `launch/post-en.md`：中英文投稿短文与各平台改写提示
- `SnapOCR-portable.spec` + `tools/make_portable_7z.py`：onedir 绿色版构建与 7z 打包、SHA-256 生成
- `tools/make_compare_image.py` / `tools/make_hero_gif.py`：素材可复现
- 本清单

**仍需你做**

- 填 About description / topics（§0）
- 上传 Release 资产（§1）
- 注册或登录各平台、实际发帖（我没有你的账号，也不替你对外发言）
- 代码签名证书（需购买 / 申请，签名后再发版可消除 SmartScreen 提示）
- macOS / Linux 官方二进制（需对应平台的构建机或 CI；本次按「收窄平台声明」处理）
- 实际给 Umi-OCR 提 issue / PR

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
