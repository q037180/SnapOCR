"""免费翻译：必应中国翻译接口为主，MyMemory 兜底，无需 API Key。

接口说明：
- 必应：GET https://cn.bing.com/translator 解析会话参数（IG / iid / token / key），
  POST https://cn.bing.com/ttranslatev3 翻译。自动检测源语言、质量好、无配额。
- 兜底：GET https://api.mymemory.translated.net/get（单次 ≤500 字节，超长自动分块，
  按字符集粗略猜测源语言）。仅用标准库，无额外依赖。
"""
from __future__ import annotations

import gzip
import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_BING_PAGE = "https://cn.bing.com/translator"
_BING_API = "https://cn.bing.com/ttranslatev3"
_MYM_API = "https://api.mymemory.translated.net/get"

_BING_TTL = 300.0  # 必应会话参数缓存时长（秒）
_MAX_CHARS = 5000  # 超长文本分段阈值
_MYM_CHUNK_BYTES = 480  # MyMemory 单次请求字节上限（接口限 500）

_LANG_MAP = {"zh-Hans": "zh-CN", "zh-Hant": "zh-TW"}  # 必应码 -> MyMemory 码

_lock = threading.Lock()
_bing_session: dict | None = None
_bing_time = 0.0


def _read_all(r) -> bytes:
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw


def _guess_lang(text: str) -> str:
    """按字符集粗略猜测源语言（供 MyMemory 兜底使用）。"""
    if any("\u3040" <= ch <= "\u30ff" for ch in text):  # 平假名/片假名
        return "ja"
    if any("\uac00" <= ch <= "\ud7af" for ch in text):  # 谚文
        return "ko"
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):  # 汉字
        return "zh-CN"
    return "en"


def _fetch_bing_session(timeout: float) -> dict:
    """从必应翻译首页解析 IG / iid / token / key。"""
    req = urllib.request.Request(
        _BING_PAGE,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        page = _read_all(r).decode("utf-8", "replace")
    ig = re.search(r'IG:"([^"]+)"', page)
    iid = re.search(r'data-iid="(translator\.[0-9]+)"', page) or re.search(
        r'data-iid="([^"]+)"', page
    )
    key = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)"', page)
    if not (ig and iid and key):
        raise RuntimeError("解析必应翻译会话参数失败，请检查网络")
    return {
        "ig": ig.group(1),
        "iid": iid.group(1),
        "key": key.group(1),
        "token": key.group(2),
    }


def _bing_translate(text: str, to_lang: str, from_lang: str | None, timeout: float) -> str:
    """必应中国翻译；会话参数缓存复用，失效自动刷新并重试一次。"""
    global _bing_session, _bing_time
    with _lock:
        session = _bing_session
        if session is None or time.time() - _bing_time > _BING_TTL:
            session = _fetch_bing_session(timeout)
            _bing_session, _bing_time = session, time.time()
        last: Exception | None = None
        for attempt in (1, 2):
            url = _BING_API + "?" + urllib.parse.urlencode(
                {"IG": session["ig"], "iid": session["iid"]}
            )
            form = urllib.parse.urlencode(
                {
                    "fromLang": from_lang if from_lang else "auto-detect",
                    "text": text,
                    "to": to_lang,
                    "token": session["token"],
                    "key": session["key"],
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=form,
                method="POST",
                headers={
                    "User-Agent": _UA,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": _BING_PAGE,
                    "Origin": "https://cn.bing.com",
                    "Accept": "*/*",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    result = json.loads(_read_all(r).decode("utf-8", "replace"))
            except Exception as exc:  # noqa: BLE001
                last = exc
            else:
                try:
                    return str(result[0]["translations"][0]["text"])
                except (KeyError, IndexError, TypeError) as exc:
                    last = exc
            # 会话参数可能过期，刷新后重试
            try:
                session = _fetch_bing_session(timeout)
                _bing_session, _bing_time = session, time.time()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"必应翻译请求失败：{last}") from exc
        raise RuntimeError(f"必应翻译请求失败：{last}")


def _split_bytes(text: str, limit: int) -> list[str]:
    """按 UTF-8 字节数在行边界分块；单片超限按字符硬切。"""
    parts: list[str] = []
    buf = ""
    for para in text.splitlines(keepends=True):
        if len((buf + para).encode("utf-8")) <= limit:
            buf += para
            continue
        if buf:
            parts.append(buf)
            buf = ""
        if len(para.encode("utf-8")) <= limit:
            buf = para
            continue
        cur = ""
        for ch in para:
            if len((cur + ch).encode("utf-8")) > limit:
                parts.append(cur)
                cur = ch
            else:
                cur += ch
        buf = cur
    if buf:
        parts.append(buf)
    return parts


def _mymemory_once(text: str, src: str, tgt: str, timeout: float) -> str:
    url = _MYM_API + "?" + urllib.parse.urlencode(
        {"q": text, "langpair": f"{src}|{tgt}"}
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(_read_all(r).decode("utf-8", "replace"))
    translated = str(data.get("responseData", {}).get("translatedText", "") or "")
    if (
        str(data.get("responseStatus")) != "200"
        or not translated
        or "MYMEMORY WARNING" in translated.upper()
    ):
        raise RuntimeError(f"MyMemory 接口异常：{translated or data}")
    return html.unescape(translated)


def _mymemory_translate(text: str, to_lang: str, from_lang: str | None, timeout: float) -> str:
    src = _LANG_MAP.get(from_lang, from_lang) if from_lang else _guess_lang(text)
    tgt = _LANG_MAP.get(to_lang, to_lang)
    if src == tgt:
        return text
    out: list[str] = []
    for i, chunk in enumerate(_split_bytes(text, _MYM_CHUNK_BYTES)):
        body, tail = chunk, ""
        while body.endswith("\n"):
            tail += "\n"
            body = body[:-1]
        body = body.strip()
        if not body:
            out.append(chunk)
            continue
        if i:
            time.sleep(0.2)  # 轻微限速，避免触发匿名配额
        out.append(_mymemory_once(body, src, tgt, timeout) + tail)
    return "".join(out)


def translate_text(
    text: str, to_lang: str, from_lang: str | None = None, timeout: float = 15
) -> str:
    """翻译文本并返回译文：必应为主，失败时 MyMemory 分块兜底。"""
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) > _MAX_CHARS:
        # 超长文本按段落粗略分段顺序翻译后拼接
        parts: list[str] = []
        buf = ""
        for para in text.splitlines(keepends=True):
            if len(buf) + len(para) > _MAX_CHARS:
                if buf:
                    parts.append(buf)
                buf = para if len(para) <= _MAX_CHARS else ""
                if not buf:
                    parts.append(para[:_MAX_CHARS])
                    parts.append(para[_MAX_CHARS:])
            else:
                buf += para
        if buf:
            parts.append(buf)
        return "\n".join(
            _translate_with_fallback(p.strip(), to_lang, from_lang, timeout)
            for p in parts
            if p.strip()
        )
    return _translate_with_fallback(text, to_lang, from_lang, timeout)


def _translate_with_fallback(
    text: str, to_lang: str, from_lang: str | None, timeout: float
) -> str:
    try:
        return _bing_translate(text, to_lang, from_lang, timeout)
    except Exception:  # noqa: BLE001
        try:
            return _mymemory_translate(text, to_lang, from_lang, timeout)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"翻译失败（主/备接口均不可用）：{exc}") from exc
