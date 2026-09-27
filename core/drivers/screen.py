"""
屏幕与图像识别驱动
====================
核心能力：截屏缓存、OpenCV 模板匹配、像素读取、区域裁切保存。

设计要点
--------
* 截图带短生命周期缓存：同一步骤内多次找图只截一次屏（性能关键）。
* 图片读取兼容中文/空格路径（cv2.imread 对非 ASCII 路径会失败，改用 imdecode）。
* 支持多模板候选：命中任意一张即算成功，方便应对皮肤/分辨率差异。
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except Exception:                                            # pragma: no cover
    cv2 = None
    HAS_CV2 = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except Exception:                                            # pragma: no cover
    pyautogui = None
    HAS_PYAUTOGUI = False

try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
except Exception:                                            # pragma: no cover
    ImageGrab = Image = None
    HAS_PIL = False


@dataclass
class MatchResult:
    """一次模板匹配的命中结果。"""

    x: int                 # 命中区域左上角
    y: int
    w: int
    h: int
    score: float           # 相似度 0~1
    template: str = ""     # 命中的模板文件

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2


def _imread_unicode(path: str) -> Optional[np.ndarray]:
    """读取图片，兼容中文/空格路径。"""
    if not os.path.isfile(path):
        return None
    if HAS_CV2:
        try:
            buf = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if img is not None:
                return img
        except Exception:
            pass
    if HAS_PIL:
        try:
            return np.array(Image.open(path).convert("RGB"))[:, :, ::-1]
        except Exception:
            return None
    return None


def _qt_grab(region: Optional[Sequence[int]] = None) -> Optional[np.ndarray]:
    """用 Qt 原生抓屏（ImageGrab 失效时的兜底）。返回 BGR ndarray。"""
    try:
        from PySide6.QtGui import QGuiApplication, QImage
        app = QGuiApplication.instance()
        if app is None:
            return None
        sc = QGuiApplication.primaryScreen()
        if sc is None:
            return None
        pm = sc.grabWindow(0)
        if pm.isNull():
            return None
        if region:
            pm = pm.copy(int(region[0]), int(region[1]), int(region[2]), int(region[3]))
        img = pm.toImage().convertToFormat(QImage.Format_RGB888)
        w, h = img.width(), img.height()
        buf = img.bits()
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, img.bytesPerLine())
        arr = arr[:, : w * 3].reshape(h, w, 3)
        return arr[:, :, ::-1].copy()          # RGB → BGR
    except Exception:
        return None


class ScreenDriver:
    """屏幕截图 + 图像识别。"""

    def __init__(self, cache_ms: int = 0) -> None:
        self.cache_ms = cache_ms
        self._shot: Optional[np.ndarray] = None
        self._shot_ts: float = 0.0
        self._shot_region: Optional[Tuple[int, int, int, int]] = None
        self._tpl_cache: Dict[str, np.ndarray] = {}

    # ------------------------------------------------------------ 截图
    def invalidate(self) -> None:
        self._shot = None
        self._shot_ts = 0.0

    def screenshot(self, region: Optional[Sequence[int]] = None,
                   fresh: bool = False) -> Optional[np.ndarray]:
        """抓屏，返回 BGR ndarray。region = (left, top, width, height)。"""
        rgn = tuple(int(v) for v in region) if region else None
        now = time.time() * 1000
        if (not fresh and self._shot is not None and rgn == self._shot_region
                and now - self._shot_ts < self.cache_ms):
            return self._shot
        if not HAS_PIL:
            return _qt_grab(rgn)
        box = (rgn[0], rgn[1], rgn[0] + rgn[2], rgn[1] + rgn[3]) if rgn else None
        try:
            img = ImageGrab.grab(bbox=box, all_screens=True)
        except TypeError:                     # 老版本 Pillow 不支持 all_screens
            try:
                img = ImageGrab.grab(bbox=box)
            except Exception:
                return _qt_grab(rgn)
        except Exception:
            return _qt_grab(rgn)
        if img is None:
            return _qt_grab(rgn)
        arr = np.array(img.convert("RGB"))[:, :, ::-1].copy()
        if not fresh:
            self._shot, self._shot_ts, self._shot_region = arr, now, rgn
        return arr

    def screen_size(self) -> Tuple[int, int]:
        if HAS_PYAUTOGUI:
            try:
                return pyautogui.size()
            except Exception:
                pass
        if HAS_PIL:
            try:
                return ImageGrab.grab(all_screens=True).size
            except Exception:
                pass
        return (1920, 1080)

    def pixel(self, x: int, y: int) -> Tuple[int, int, int]:
        """返回指定坐标的 RGB。"""
        shot = self.screenshot()
        if shot is None:
            return (-1, -1, -1)
        h, w = shot.shape[:2]
        if not (0 <= x < w and 0 <= y < h):
            return (-1, -1, -1)
        b, g, r = shot[y, x][:3]
        return int(r), int(g), int(b)

    # ------------------------------------------------------------ 模板匹配
    def _template(self, path: str) -> Optional[np.ndarray]:
        if path not in self._tpl_cache:
            img = _imread_unicode(path)
            if img is not None:
                self._tpl_cache[path] = img
        return self._tpl_cache.get(path)

    def find(self, template_path: str, confidence: float = 0.85,
             region: Optional[Sequence[int]] = None, grayscale: bool = True,
             multi: bool = False) -> List[MatchResult]:
        """在屏幕上查找一张模板图，返回全部命中（按相似度降序）。"""
        tpl = self._template(template_path)
        if tpl is None or not HAS_CV2:
            return []
        shot = self.screenshot(region)
        if shot is None:
            return []
        th, tw = tpl.shape[:2]
        sh, sw = shot.shape[:2]
        if th > sh or tw > sw:
            return []
        hay, needle = shot, tpl
        if grayscale:
            hay = cv2.cvtColor(shot, cv2.COLOR_BGR2GRAY)
            needle = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(hay, needle, cv2.TM_CCOEFF_NORMED)
        ox, oy = (region[0], region[1]) if region else (0, 0)
        out: List[MatchResult] = []
        if multi:
            ys, xs = np.where(res >= confidence)
            for y, x in zip(ys, xs):
                out.append(MatchResult(int(x) + ox, int(y) + oy, tw, th,
                                       float(res[y, x]), template_path))
        else:
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= confidence:
                out.append(MatchResult(int(max_loc[0]) + ox, int(max_loc[1]) + oy,
                                       tw, th, float(max_val), template_path))
        out.sort(key=lambda m: -m.score)
        return out

    def find_any(self, templates: Sequence[str], confidence: float = 0.85,
                 region=None, grayscale: bool = True,
                 timeout: float = 0.0, interval: float = 0.5) -> Optional[MatchResult]:
        """在多个候选模板中找"最先命中"的一个；timeout>0 时轮询等待。"""
        deadline = time.time() + max(0.0, timeout)
        while True:
            best: Optional[MatchResult] = None
            for t in templates:
                hits = self.find(t, confidence, region, grayscale)
                if hits:
                    if best is None or hits[0].score > best.score:
                        best = hits[0]
            if best is not None:
                return best
            if time.time() >= deadline:
                return None
            self.invalidate()
            time.sleep(max(0.05, interval))

    def find_all(self, templates: Sequence[str], confidence: float = 0.85,
                 region=None, grayscale: bool = True) -> List[MatchResult]:
        hits: List[MatchResult] = []
        for t in templates:
            hits.extend(self.find(t, confidence, region, grayscale, multi=True))
        return sorted(hits, key=lambda m: (m.y, m.x))

    def save_crop(self, region: Sequence[int], path: str) -> bool:
        """截取屏幕区域并存盘 —— 用于"抓图取模板"。"""
        shot = self.screenshot(region, fresh=True)
        if shot is None:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            ext = os.path.splitext(path)[1].lower() or ".png"
            ok, buf = cv2.imencode(ext, shot) if HAS_CV2 else (False, None)
            if ok:
                buf.tofile(path)
                return True
            if HAS_PIL:
                Image.fromarray(shot[:, :, ::-1]).save(path)
                return True
        except Exception:
            return False
        return False
