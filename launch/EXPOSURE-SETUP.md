# 曝光准备：已完成 / 你只需点这几下

> 生成于 2026-11-07。面向「别人第一次听说 SnapOCR」这条链路：
> **看见 → 点进来 → 图片能显示 → 下得动 → 装得上**。
> 线上数据基线（2026-11-07 10:55）：stars 2 / forks 0 / issues 0，14 天独立访客 **3**，
> 外部引荐流量 0，v1.0.3 发布 19h 的 7z 下载 7 次。**瓶颈是还没发帖，不是文案不够。**

## 一、已完成（都在仓库里）

| 项 | 文件 | 作用 |
| --- | --- | --- |
| README 13 张图改走 Pages 图床 | `README.md`、`docs/assets/` | 四通道各采样 4 次：相对路径 **0/4**、`raw.githubusercontent.com` 绝对 **0/4**、原 `release-assets` 4/4 但带 SAS 签名参数转存必挂、**Pages 4/4 且 0.6 s**。统一改用 Pages，不依赖旧 tag、不依赖 SAS 签名 |
| 首屏下载双链接 + SHA-256 | `README.md` 安装段、顶部导航 | 官方直链实测 `000`（代理对该域名 502），镜像放在首屏而不是折叠的「下载很慢」说明里 |
| 推广稿配图改 Pages 图床 + 本地图包清单 | `READY-TO-POST.md` §1、`VIRAL-COPY.md` §6 | 解决掘金外链图「转存失败」把提示文本写进正文；外链用干净的 Pages URL |
| Social Preview 1280×640 | `assets/social-preview.png`、`tools/make_social_preview.py` | 分享卡片从灰色默认图换成真实产品图；脚本可复现 |
| GitHub Pages 落地页 | `docs/index.html`、`docs/.nojekyll`、`docs/assets/`（1.7 MB） | 中英元数据 + JSON-LD + 双下载链接 + FAQ，可被搜索引擎收录；不依赖任何外部 CDN |
| winget 四件套 | `launch/winget/manifests/q/q037180/SnapOCR/1.0.3/` | `winget install q037180.SnapOCR`；用 exe，因为 winget 不支持 7z |
| Scoop 清单 | `launch/scoop/snapocr.json` | 用 7z 绿色包，含 `checkver` / `autoupdate`，后续发版自动跟随 |
| 收录投稿稿 | `launch/listings.md` | HelloGitHub / AlternativeTo / awesome-\* / 中文站点的复制即用文案与提交步骤 |
| 技术长文 ×2 | `launch/post-tech-1.md`、`launch/post-tech-2.md` | 把 QA 报告里 40 项修复拆成可发的稿子，数字全部核对过报告原文 |

## 二、线上已设置

- GitHub 仓库 `description` 改为中英双语（中文搜索词进了仓库元数据）
- `topics` 补到 20 个
- GitHub Pages 从 `main / docs` 发布，**已构建成功**：https://q037180.github.io/SnapOCR/ （`status: built`，首页与图片实测 206 / 0.6 s）
- 因此 `docs/assets/` 同时兼任 README 与推广稿的图床，共 11 张、7.3 MB

> `description` 原值（需要回退时用）：
> `Offline screenshot OCR for dark IDEs and dark-mode pages — auto-inverts dark captures and keeps every result in a searchable history. Windows, MIT.`

## 三、需要你本人做的（按优先级）

### 1. 传 Social Preview（2 分钟，唯一一张图）

https://github.com/q037180/SnapOCR/settings → 「Social preview」→ **Upload an image** → 选 `assets/social-preview.png` → Save。

不传的话，上面所有链接在微信 / 掘金 / Twitter / Slack 里分享时仍是一张灰的默认卡片。

### 2. 发第一帖（唯一真正改变 unique=3 的动作）

用 `READY-TO-POST.md` §1（掘金，21:00–22:00）：

- 首图用编辑器**本地上传** `assets/compare-dark-ui.png`，别贴外链；
- 发完守 1–2 小时，每条评论带一个具体追问；
- 48 小时内把链接、曝光、下载、反馈数填回 `LAUNCH-PLAN.md` §3 的记录表。

`launch/` 里的稿子已经够了，**不要再加新平台，先发这一帖**。两周后仍不达标，按 `LAUNCH-PLAN.md` §3 的判断：问题在楔子场景（深色截图是不是真痛点），换钩子重发一轮，别急着加功能。

### 3. 可选：让搜索引擎收录落地页

Pages 已上线并通过验证。想拿长尾搜索流量，到 Google Search Console / 百度搜索资源平台提交
https://q037180.github.io/SnapOCR/ （百度需要站长验证，属于可选项）。
页面已带中文 title/description、canonical 与 JSON-LD `SoftwareApplication`，不需要再改 HTML。

### 4. 提交被动分发渠道（一次投入、长期有量，穿插在发帖之后做）

按 `launch/listings.md`：HelloGitHub 月刊 → winget PR → AlternativeTo → Scoop bucket → awesome-\* 列表。
**一次只投一个**，别同日群发同一段话。

### 5. 一直没做、但会持续吃掉转化

代码签名证书。未签名的 exe 首次运行会弹 SmartScreen，下载了却不敢装的人不会留下反馈。README 和落地页都写了绕开方法，但这只是止血。

## 四、验证命令

```bash
# 本地预览落地页
python -m http.server 8000 --directory docs     # 打开 http://localhost:8000

# 校验 winget 清单
winget validate --manifest launch/winget/manifests/q/q037180/SnapOCR/1.0.3

# 校验 Scoop 清单
scoop install launch/scoop/snapocr.json

# 重生成 Social Preview
python tools/make_social_preview.py
```

## 五、别做的事

- 别在正文求 star、别写「神器 / 重磅」；技术社区对这两件事的反弹比对广告还大。
- 别同日把同一段文字发到多个平台，会被判搬运、也会影响推荐。
- 别为了曝光改产品定位。README 里「诚实的多语言 / 联网声明」是信任资产，比一次热榜值钱。
