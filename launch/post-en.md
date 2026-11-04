# English launch post (Show HN / Reddit)

> Assets: `assets/compare-dark-ui.png` (dark-capture before/after), `assets/hero-15s.gif` (~15 s demo)
> Repo: https://github.com/q037180/SnapOCR
> Releases: https://github.com/q037180/SnapOCR/releases

## Show HN

**Title**

```
Show HN: SnapOCR – offline screenshot OCR that pre-processes dark UI captures
```

**Body**

```
I built a small Windows OCR tool because two things kept annoying me.

Most screenshot OCR (including the built-in Windows Snipping Tool text actions and PowerToys Text Extractor) works fine on white pages, but dark IDE / dark-mode captures often lose entire lines: detection models are mostly trained on dark text on light backgrounds. SnapOCR measures mean gray level, inverts the capture when it is below 100, applies CLAHE on the LAB L channel when contrast is low (std < 45), and upscales small crops 2-3x -- all before handing the image to RapidOCR / PP-OCRv6. Five language models are bundled and recognition is fully offline.

The second thing: the clipboard remembers one item. Every recognition in SnapOCR goes into a searchable history with hover preview, one-click re-copy, and export to txt / docx / pdf / md / xlsx.

Also included: a folder batch queue, page-by-page PDF OCR, table -> xlsx, scrolling long-shot stitching, pinned always-on-top captures, and 11-language screen translation. Hotkeys are Ctrl+Alt+Q / T / L and are rebindable.

Honest limitations, since they matter here:
- Windows 10/11 x64 is the only platform with a binary. Linux/macOS run from source; global hotkeys need sudo or Accessibility permission, and scrolling long-shot is Win32-only.
- The exe is not code-signed, so SmartScreen will complain on first run. SHA-256 checksums are on the release page.
- The single-file build is 160 MB and unpacks on every launch; the 7z portable build uses a normal onedir layout (exe + dependency folder), so it starts faster and never self-extracts.
- OCR never touches the network. Only the optional translation feature sends recognized text to Bing Translator / MyMemory. No auto-updater yet.

Stack: Python 3.12, PySide6, RapidOCR + onnxruntime, OpenCV. MIT licensed. ~7 s for a full 1080p screen on CPU, near-instant for small regions.

I would especially like feedback on dark-capture accuracy. If a screenshot fails, the most useful report is the original crop (sensitive data removed), the expected text, and your Windows version.

Repo / Releases / Issues links above. Happy to answer questions about the preprocessing pipeline.
```

**Show HN notes**

- Prefix must be exactly `Show HN: `. Post to news.ycombinator.com/submit as a story pointing at the repo.
- Post in the US morning (roughly 21:00–23:00 Beijing time). Do not ask for upvotes, do not paste marketing copy.
- Stay around for at least two hours to answer comments. The first five replies matter more than the post itself.
- If the README is the linked page, the English section is now standalone and readable — no need to scroll through Chinese first.

## Reddit

**Title (r/Windows, r/opensource)**

```
I made an offline screenshot OCR tool that handles dark IDE screenshots and keeps a searchable history (Windows, MIT)
```

**Title (r/Python, if you post there — lead with the stack)**

```
PySide6 + RapidOCR: a local screenshot OCR tool with automatic dark-capture preprocessing
```

**Body**

```
Most of my screens are dark — editor, terminal, docs — and built-in OCR tools tend to miss lines on dark backgrounds. So I added a preprocessing step before recognition: invert when mean gray < 100, CLAHE on the LAB L channel when contrast is low, upscale small crops. Then RapidOCR / PP-OCRv6 runs locally with bundled models; nothing is uploaded.

The other half is a searchable history for every recognition, because the clipboard only keeps the last one. Also has folder batch OCR, PDF page-by-page OCR, table -> xlsx, long-shot stitching, pinned captures and screen translation.

Caveats up front: Windows-only binary (Linux/macOS from source with hotkey limitations), unsigned exe (SmartScreen on first run, SHA-256 provided), 160 MB single-file build unpacks on each launch so there's an onedir 7z portable build too, translation is the only networked feature, no auto-updater.

Repo: https://github.com/q037180/SnapOCR
Releases: https://github.com/q037180/SnapOCR/releases

Would love dark-screenshot samples where it fails — original crop + expected text is the most useful bug report.
```

**Reddit notes**

- Read each subreddit's self-promotion rules first; several require a developer flair or a weekly thread.
- Do not cross-post the same text to three subreddits on the same day.
- Attach `compare-dark-ui.png` as the image post where the sub allows images.
- Reply to every comment in the first 24 hours.
