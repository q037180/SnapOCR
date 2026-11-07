# launch/ 使用说明

这个目录是**对外文案与发布记录**，不是程序的一部分。9 个文件容易搞混，按用途分三类：

## 一、先看这个（当前状态与下一步）

| 文件 | 用途 |
| --- | --- |
| **`READY-TO-POST.md`** | **主入口。** 顶部是各渠道实时状态表 + 下一步动作；下面按渠道给了可直接复制的标题、正文、摘要、回评话术。任何发布动作先开这个。 |

## 二、还没发的内容（有存货，别丢）

| 文件 | 内容 | 计划渠道 |
| --- | --- | --- |
| `post-tech-1.md` | 技术长文：10 万行导出从 419 秒降到 3.4 秒（讲 docx 直接拼 `w:p`） | 掘金 / 知乎专栏 / 博客园 |
| `post-tech-2.md` | 技术长文：退出码 127、消失的窗口、纯色截图（讲 onefile 解压失败与多屏 DPI） | V2EX「分享创造」/ 掘金 |
| `post-zh.md` | 中文投稿短文（600 字版），适合审核制渠道 | 小众软件投稿 / 公众号 |
| `post-en.md` | 英文版，Show HN 与 Reddit 各一份措辞 | Hacker News / r/opensource |
| `listings.md` | 「提交一次、长期有量」的收录站文案（AlternativeTo、Awesome 列表等） | 各收录站 |

## 三、参考与历史记录（写完就不用再改）

| 文件 | 用途 |
| --- | --- |
| `LAUNCH-PLAN.md` | 最早的 14 天首发计划（2026-11-04 制定），保留作背景，**其中的顺序已被现实推翻**（V2EX 当时不可达，改发掘金） |
| `VIRAL-COPY.md` | 爆款文案包，与 `READY-TO-POST.md` 重叠度较高，以 READY-TO-POST 为准 |
| `EXPOSURE-SETUP.md` | 仓库侧曝光配置的记录（图床选型实测、Social Preview、Pages、topics），是一次性动作的存档 |

## 四、可以机器执行的清单

| 路径 | 用途 |
| --- | --- |
| `winget/` | winget 清单源文件，已提交 PR [#473681](https://github.com/microsoft/winget-pkgs/pull/473681)；后续发版同步改这里的版本号与哈希 |
| `scoop/snapocr.json` | Scoop 清单，尚未提 PR |

> 发版时记得改三处：`app/config.py` 的 `APP_VERSION`、`launch/winget/.../<版本>/`、`launch/scoop/snapocr.json`。
> 漏改会被 `python -m unittest discover -s tests` 直接测出来（`test_consistency`）。
