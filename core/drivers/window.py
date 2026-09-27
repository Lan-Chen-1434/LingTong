"""
窗口控制驱动
==============
窗口激活 / 最大化 / 最小化 / 关闭 / 列表查询。
基于 pygetwindow（Windows），失败时降级为 Win32 API 或 AppleScript；
无依赖环境下安全返回 False。
"""
from __future__ import annotations

import time
from typing import List

from ..platform import IS_WIN, IS_MAC, activate_window, active_window_title, list_window_titles


class WindowDriver:
    """窗口激活 / 最大化 / 查找。"""

    def _gw(self):
        try:
            import pygetwindow as gw
            return gw
        except Exception:
            return None

    def list_titles(self) -> List[str]:
        gw = self._gw()
        if gw:
            try:
                return [t for t in gw.getAllTitles() if t and t.strip()]
            except Exception:
                pass
        # fallback 跨平台
        return list_window_titles()

    def find(self, keyword: str, exact: bool = False):
        gw = self._gw()
        if not gw:
            return None
        try:
            titles = gw.getWindowsWithTitle(keyword)
        except Exception:
            return None
        if not titles:
            return None
        if exact:
            for w in titles:
                if w.title == keyword:
                    return w
        return titles[0]

    def activate(self, keyword: str, exact: bool = False, wait: float = 0.4) -> bool:
        # Windows 优先 pygetwindow
        if IS_WIN:
            w = self.find(keyword, exact)
            if w is not None:
                try:
                    if getattr(w, "isMinimized", False):
                        w.restore()
                    w.activate()
                    time.sleep(wait)
                    return True
                except Exception:
                    try:
                        import ctypes
                        ctypes.windll.user32.SetForegroundWindow(w._hWnd)  # type: ignore[attr-defined]
                        time.sleep(wait)
                        return True
                    except Exception:
                        pass
        # 跨平台 fallback
        return activate_window(keyword, exact=exact, wait=wait)

    def maximize(self, keyword: str) -> bool:
        w = self.find(keyword)
        if w is None:
            return False
        try:
            w.maximize()
            return True
        except Exception:
            return False

    def minimize(self, keyword: str) -> bool:
        w = self.find(keyword)
        if w is None:
            return False
        try:
            w.minimize()
            return True
        except Exception:
            return False

    def close(self, keyword: str) -> bool:
        w = self.find(keyword)
        if w is None:
            return False
        try:
            w.close()
            return True
        except Exception:
            return False

    def active_title(self) -> str:
        gw = self._gw()
        if gw:
            try:
                return gw.getActiveWindowTitle() or ""
            except Exception:
                pass
        return active_window_title()
