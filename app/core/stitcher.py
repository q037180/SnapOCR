"""长截图：注入滚轮滚动页面，逐帧抓取并按重叠区域拼接。

自动滚动注入使用 Win32 mouse_event，仅 Windows 支持；
其他平台运行时给出明确提示（拼接算法本身跨平台）。
"""
from __future__ import annotations

import sys
import threading

import cv2
import mss
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app import config

_WHEEL_DELTA = 120  # Windows 标准滚轮一格的 delta，负值向下滚
_MOUSEEVENTF_WHEEL = 0x0800
_NOMOTION_DIFF = 8.0  # 整帧已存在时，两帧允许的平均灰度差
_OVERLAP_DIFF = 18.0  # 重叠区允许的平均灰度差（含 1px 亚像素偏移/抗锯齿噪声）
_DIFF_PIXEL = 32  # 单像素差到多少算「明显不同」
# 允许「明显不同」的像素占比：视频画面、滚动条滑块、走秒的时钟这类局部动态内容
# 永远对不齐，按均值判定会被整体否决（以前直接整帧追加 → 长图出现重复段落）。
_DYN_AREA_RATIO = 0.30
_DYN_COL_RATIO = 0.5  # 某一列里超过这个比例明显不同 → 本轮该列可疑
_DYN_COL_MEDIAN = 0.06  # 逐列差异比例的中位数低于它 = 大部分列完全对得上
_DYN_VOTES = 2  # 连续几轮可疑后把该列排除出校验（并同时屏蔽匹配）
_MAX_CANDIDATES = 4  # 模板匹配峰值的候选数：周期性内容会出现多个等分峰值
_SHRINK = 4  # 粗搜索的缩小倍数
# 相关系数的下限。注意它只用来「排序+粗筛」，真正判定靠重叠区的像素复核：
# 页面里有一块固定位置的视频时，相关系数会被噪点压到 0.5 左右，
# 若仍按 0.75 卡关就会整帧追加（长图里出现一整段重复内容）。
_MIN_SCORE = 0.35


def _diff_stats(a: np.ndarray, b: np.ndarray, ignore=None) -> tuple[float, float, float]:
    """(平均灰度差, 明显差异像素占比, 差异列的「中位数比例」)。

    第三个指标是关键：对得齐的时候，绝大多数列几乎完全一致，只有视频/滚动条
    那几列对不上，所以逐列差异比例的中位数接近 0；对不齐时整体都差，中位数很高。
    比「整体面积占比」更能把「局部动态内容」和「整段错位」区分开。
    ignore 是逐列布尔数组，对应位置不参与统计。
    """
    if a.shape != b.shape:
        return 255.0, 1.0, 1.0
    d = cv2.absdiff(a, b)
    if ignore is not None and ignore.size == a.shape[1] and bool(ignore.any()):
        keep = ~ignore
        if not keep.any():
            return 0.0, 0.0, 0.0
        d = d[:, keep]
    if d.ndim == 3:
        big = d.max(axis=2)
    else:
        big = d
    mean = float(np.mean(d))
    bad = big > _DIFF_PIXEL
    col_ratio = bad.mean(axis=0) if bad.size else np.ones(1)
    return mean, float(bad.mean()), float(np.median(col_ratio))


def _top_candidates(res: np.ndarray, k: int, suppress: int) -> list[tuple[float, tuple]]:
    """取相关系数图的 top-k 峰值。

    周期性内容（代码行、表格行）会让多个位置同分，minMaxLoc 只给第一个，
    于是重叠量算错、甚至被误判成「页面已到底」。取出多个候选后逐个做像素复核。
    """
    out: list[tuple[float, tuple]] = []
    if res.size == 0:
        return out
    work = res.copy()
    for _ in range(k):
        _, score, _, loc = cv2.minMaxLoc(work)
        out.append((float(score), loc))
        y0 = max(0, loc[1] - suppress)
        y1 = min(work.shape[0], loc[1] + suppress + 1)
        work[y0:y1, :] = -1.0
    return out


if sys.platform == "win32":
    import ctypes

    _user32 = ctypes.windll.user32
else:
    _user32 = None  # 非 Windows：无滚轮注入能力，长截图启动时提示


def _shrink(gray: np.ndarray, k: int):
    """按 k×k 块取均值缩小。随机噪点（视频画面）在缩小后趋于常数，
    而排版内容的结构还在——粗搜索因此不会被动态区域带偏。"""
    h, w = gray.shape[:2]
    h2, w2 = (h // k) * k, (w // k) * k
    if h2 < k or w2 < k:
        return None
    return cv2.resize(gray[:h2, :w2], (w2 // k, h2 // k), interpolation=cv2.INTER_AREA)


def _refine(region: np.ndarray, tpl: np.ndarray, approx: int, radius: int):
    """在粗搜索结果附近用全分辨率细分，返回 (行号, 得分)。"""
    h = region.shape[0]
    y0 = max(0, approx - radius)
    y1 = min(h, approx + radius + tpl.shape[0])
    if y1 - y0 < tpl.shape[0]:
        return None
    res = cv2.matchTemplate(region[y0:y1], tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return y0 + loc[1], float(score)


def _stitch(
    acc: np.ndarray,
    frame: np.ndarray,
    *,
    strip: int = 100,
    threshold: float = 0.75,
    ignore: np.ndarray | None = None,
) -> tuple[np.ndarray, str, tuple | None]:
    """返回 (新累计图, 模式, 用于动态列统计的对齐片段)。

    ignore 是逐列布尔数组：视频画面/滚动条滑块这类固定位置的动态区域，
    既不该参与匹配，也不该否决拼接结果。
    """
    a_h, f_h = acc.shape[0], frame.shape[0]
    if a_h < strip or f_h < strip or a_h < 8 or f_h < 8:
        return np.vstack([acc, frame]), "append", None
    tpl = cv2.cvtColor(frame[:strip], cv2.COLOR_BGR2GRAY)
    if float(tpl.std()) < 1.0:
        # 纯色（无纹理）顶部条：matchTemplate 会处处得 1.0，loc 退化成 (0,0)，
        # 被误判成「整帧已存在」→ 连续 3 帧后长截图提前结束。直接追加兜底。
        return np.vstack([acc, frame]), "append", None
    search_zone = min(a_h, f_h + 150)
    region = cv2.cvtColor(acc[a_h - search_zone:], cv2.COLOR_BGR2GRAY)
    use_ignore = (
        ignore is not None
        and ignore.size == region.shape[1]
        and bool(ignore.any())
    )
    if use_ignore:
        # 屏蔽列填成常数：对 TM_CCOEFF_NORMED 的方差没有贡献，等价于「无视」
        fill_r = int(np.median(region))
        region = region.copy()
        region[:, ignore] = fill_r
        tpl = tpl.copy()
        tpl[:, ignore] = int(np.median(tpl))

    # 先在缩小图上粗搜：顶部条正好压着视频/动画时，全分辨率相关系数会被噪点
    # 拖垮（实测整帧直接 append，长图里出现一整段重复内容）。缩小后噪点被平均掉，
    # 排版结构仍在，粗搜能锁住正确位置，再用全分辨率在小窗口内细化。
    positions: list[tuple[float, int]] = []  # (得分, 模板顶行在 region 中的行号)
    rs, ts = _shrink(region, _SHRINK), _shrink(tpl, _SHRINK)
    if rs is not None and ts is not None and ts.size > 0 and float(ts.std()) >= 1.0:
        res = cv2.matchTemplate(rs, ts, cv2.TM_CCOEFF_NORMED)
        for score, loc in _top_candidates(res, _MAX_CANDIDATES, max(2, strip // _SHRINK)):
            got = _refine(region, tpl, loc[1] * _SHRINK, _SHRINK * 2)
            if got is not None:
                positions.append((got[1], got[0]))  # (得分, 行号)
            else:
                positions.append((score, loc[1] * _SHRINK))
    else:  # 图太小无法缩小：退回全分辨率直搜一次
        if float(tpl.std()) >= 1.0:
            res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
            positions.extend((s, loc[1]) for s, loc in _top_candidates(res, 1, strip // 2))

    best = None  # (质量, 平均差, 是否可接受, 重叠量, 对齐片段)
    gate = min(threshold, _MIN_SCORE)
    for score, p in positions:
        p = int(p)
        if not np.isfinite(score) or score < gate:
            continue
        overlap = int(max(0, search_zone - p))  # 新帧顶部在累计图中已有的像素数
        if overlap <= 0:
            continue
        tail = int(min(overlap, f_h))
        pair = (acc[a_h - tail:], frame[:tail])
        mean, ratio, col_med = _diff_stats(pair[0], pair[1], ignore if use_ignore else None)
        # 平均差够小 / 明显差异面积不大 / 多数列几乎完全一致 —— 都算拼得上
        ok = (
            mean <= _OVERLAP_DIFF
            or ratio <= _DYN_AREA_RATIO
            or col_med <= _DYN_COL_MEDIAN
        )
        cand = (0 if ok else 1, mean, ok, overlap, pair)
        # 平均差打平时选重叠更小的那个：周期性内容每个峰值都像素相同，
        # 挑最小的重叠才不会把一个正常滚动误判成「页面已到底」
        key = (cand[0], round(mean, 2), overlap)
        if best is None or key < best[0]:
            best = (key, cand)
    if best is None:
        return np.vstack([acc, frame]), "append", None
    _, mean, ok, overlap, pair = best[1]
    if not ok:
        return np.vstack([acc, frame]), "append", pair
    if overlap >= f_h:
        # 模板匹配说整帧都已存在：再用整段像素严格复核一次，避免周期性内容误判
        if mean <= _NOMOTION_DIFF:
            return acc, "nomotion", None
        return np.vstack([acc, frame]), "append", pair
    return np.vstack([acc, frame[overlap:]]), "overlap", pair


def _stitch_step(
    acc: np.ndarray, frame: np.ndarray, *, strip: int = 100, threshold: float = 0.75
) -> tuple[np.ndarray, str]:
    """把新帧拼接到累计图上，返回 (新累计图, 模式)。纯函数，便于单测。

    用新帧顶部 strip 像素在累计图尾部搜索最佳匹配位置，取相关系数的前几个峰值
    逐个做像素复核后择优选一个：
    - 重叠区对得上：按重叠部分拼接（overlap）；整帧都已存在时返回原累计图（nomotion）。
    - 都对不上：整帧追加兜底（append）。
    """
    out, mode, _ = _stitch(acc, frame, strip=strip, threshold=threshold)
    return out, mode


class Stitcher:
    """有状态的拼接器：在无状态算法之上维护「动态列」屏蔽表。

    连续几轮都对不上的像素列（视频、滚动条、时钟）会被永久排除出校验，
    这样页面里的动态内容不会让整段拼接失败。
    """

    def __init__(self, strip: int = 100, threshold: float = 0.75) -> None:
        self._strip = strip
        self._threshold = threshold
        self._votes: np.ndarray | None = None
        self._ignore: np.ndarray | None = None

    @property
    def ignore(self) -> np.ndarray | None:
        """当前被判为动态、不参与校验的列（调试/测试用）。"""
        return self._ignore

    def push(self, acc: np.ndarray, frame: np.ndarray) -> tuple[np.ndarray, str]:
        out, mode, pair = _stitch(
            acc, frame, strip=self._strip, threshold=self._threshold, ignore=self._ignore
        )
        if pair is not None:
            self._learn(pair[0], pair[1])
        return out, mode

    def _learn(self, a: np.ndarray, b: np.ndarray) -> None:
        """按对齐片段统计「哪几列总是对不上」。"""
        if a.shape != b.shape or a.shape[1] == 0:
            return
        d = cv2.absdiff(a, b)
        big = d.max(axis=2) if d.ndim == 3 else d
        cols = big.shape[1]
        if self._votes is None or self._votes.size != cols:
            self._votes = np.zeros(cols, np.int32)
            self._ignore = None
        bad = np.count_nonzero(big > _DIFF_PIXEL, axis=0) / max(1, big.shape[0])
        dirty = bad > _DYN_COL_RATIO
        self._votes[dirty] += 1
        self._votes[~dirty] = 0
        mask = self._votes >= _DYN_VOTES
        if float(mask.mean()) > 0.5:
            # 过半列都被判成动态：那不是局部动态内容，是页面整体换了
            # （或者被上一次的错误对齐带偏了）。清空重学，别把整幅图屏蔽掉。
            self._votes[:] = 0
            mask = np.zeros(cols, bool)
        self._ignore = mask if bool(mask.any()) else None



class StitchWorker(QThread):
    """滚动采集线程：开始后自动下滚拼接，stop() 随时可停。"""

    progress = Signal(str)
    done = Signal(QImage)
    fail = Signal(str)

    def __init__(self, region: tuple[int, int, int, int]) -> None:
        super().__init__()
        self._region = region
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        if _user32 is None:
            self.fail.emit("长截图自动滚动目前仅支持 Windows（需要注入滚轮事件）")
            return
        try:
            image = self._capture()
        except Exception as exc:  # noqa: BLE001
            self.fail.emit(str(exc))
            return
        if image is None:
            self.fail.emit("未采集到画面")
        else:
            self.done.emit(image)

    def _capture(self) -> QImage | None:
        left, top, width, height = self._region
        monitor = {"left": left, "top": top, "width": width, "height": height}
        cx, cy = left + width // 2, top + height // 2
        user32 = ctypes.windll.user32
        acc: np.ndarray | None = None
        no_motion = 0
        frames = 0
        st = Stitcher()
        with mss.mss() as sct:
            while frames < config.LONGSHOT_MAX_FRAMES and not self._stop.is_set():
                raw = sct.grab(monitor)
                frame = cv2.cvtColor(np.asarray(raw), cv2.COLOR_BGRA2BGR)
                if acc is None:
                    acc = frame
                    mode = "first"
                else:
                    acc, mode = st.push(acc, frame)
                frames += 1
                self.progress.emit(f"已采集 {frames} 帧 · 高度 {acc.shape[0]}px")
                if mode == "nomotion":
                    no_motion += 1
                    if no_motion >= 3:
                        break  # 连续无新内容：已到页面底部
                else:
                    no_motion = 0
                if self._stop.is_set() or acc.shape[0] >= config.LONGSHOT_MAX_HEIGHT:
                    break
                # 把光标移到选区中央并注入滚轮下滚
                user32.SetCursorPos(cx, cy)
                for _ in range(config.LONGSHOT_SCROLL_TICKS):
                    user32.mouse_event(_MOUSEEVENTF_WHEEL, 0, 0, -_WHEEL_DELTA, 0)
                self._stop.wait(config.LONGSHOT_DELAY)
        if acc is None:
            return None
        h, w = acc.shape[:2]
        # 必须立即 copy：QImage 不持有 numpy 内存
        return QImage(acc.data, w, h, w * 3, QImage.Format_BGR888).copy()
