"""长截图：注入滚轮滚动页面，逐帧抓取并按重叠区域拼接。"""
from __future__ import annotations

import ctypes
import threading

import cv2
import mss
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app import config

_WHEEL_DELTA = 120  # Windows 标准滚轮一格的 delta，负值向下滚
_MOUSEEVENTF_WHEEL = 0x0800


def _stitch_step(
    acc: np.ndarray, frame: np.ndarray, *, strip: int = 100, threshold: float = 0.75
) -> tuple[np.ndarray, str]:
    """把新帧拼接到累计图上，返回 (新累计图, 模式)。纯函数，便于单测。

    用新帧顶部 strip 像素在累计图尾部搜索最佳匹配位置：
    - score >= threshold：按重叠部分拼接（overlap）；
      若整帧都已存在（页面未滚动）返回原累计图（nomotion）。
    - score < threshold：内容变化过大，整帧追加兜底（append）。
    """
    a_h, f_h = acc.shape[0], frame.shape[0]
    if a_h < strip or f_h < strip or a_h < 8 or f_h < 8:
        return np.vstack([acc, frame]), "append"
    tpl = cv2.cvtColor(frame[:strip], cv2.COLOR_BGR2GRAY)
    search_zone = min(a_h, f_h + 150)
    region = cv2.cvtColor(acc[a_h - search_zone:], cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(region, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    if score < threshold:
        return np.vstack([acc, frame]), "append"
    overlap = max(0, search_zone - loc[1])  # 新帧顶部在累计图中已有的像素数
    if overlap >= f_h:
        return acc, "nomotion"
    return np.vstack([acc, frame[overlap:]]), "overlap"


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
        with mss.mss() as sct:
            while frames < config.LONGSHOT_MAX_FRAMES and not self._stop.is_set():
                raw = sct.grab(monitor)
                frame = cv2.cvtColor(np.asarray(raw), cv2.COLOR_BGRA2BGR)
                if acc is None:
                    acc = frame
                    mode = "first"
                else:
                    acc, mode = _stitch_step(acc, frame)
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
