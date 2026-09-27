"""
键鼠模拟与剪贴板驱动
======================
基于 pyautogui 的鼠标/键盘操作封装。

设计要点
--------
* 中文输入自动降级为"剪贴板 + Ctrl+V"（pyautogui 无法直接键入中文）。
* 所有方法在无 pyautogui 的环境下静默降级，保证 --check 与单元测试可跑。
"""
from __future__ import annotations

import time
from typing import Optional, Sequence, Tuple

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.02
    HAS_PYAUTOGUI = True
except Exception:                                            # pragma: no cover
    pyautogui = None
    HAS_PYAUTOGUI = False

try:
    import pyperclip
    HAS_CLIP = True
except Exception:                                            # pragma: no cover
    pyperclip = None
    HAS_CLIP = False

from ..platform import IS_MAC

_BUTTON = {"左键": "left", "右键": "right", "中键": "middle"}

# macOS 的通用快捷键用 Command（⌘），Windows 用 Ctrl
MOD_KEY = "command" if IS_MAC else "ctrl"

# 跨平台键名归一化：
#   macOS 没有 win 键，win/cmd/command 都落到 command；Qt 在 mac 上把 ⌘
#   报成 Ctrl，因此「ctrl」按通用快捷键习惯指 ⌘，真实 Control 键写 "control"
#   Windows 上 cmd/command 视作 win；"control" 是 ctrl 的显式写法
_KEY_ALIASES = {"control": "ctrl"}
if IS_MAC:
    _KEY_ALIASES.update({"win": "command", "cmd": "command", "command": "command",
                         "ctrl": "command"})
else:
    _KEY_ALIASES.update({"cmd": "win", "command": "win"})


def _norm_key(key: str) -> str:
    k = key.strip().lower()
    return _KEY_ALIASES.get(k, k)


class InputDriver:
    """鼠标 + 键盘 + 剪贴板。"""

    # ------------------------------------------------------- 鼠标
    def position(self) -> Tuple[int, int]:
        if HAS_PYAUTOGUI:
            try:
                p = pyautogui.position()
                return int(p.x), int(p.y)
            except Exception:
                pass
        return (0, 0)

    def move(self, x: int, y: int, duration: float = 0.2) -> None:
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(int(x), int(y), duration=max(0.0, duration))

    def move_rel(self, dx: int, dy: int, duration: float = 0.2) -> None:
        if HAS_PYAUTOGUI:
            pyautogui.moveRel(int(dx), int(dy), duration=max(0.0, duration))

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", clicks: int = 1, interval: float = 0.08,
              duration: float = 0.15) -> None:
        if not HAS_PYAUTOGUI:
            return
        btn = _BUTTON.get(button, button)
        if x is not None and y is not None:
            pyautogui.moveTo(int(x), int(y), duration=max(0.0, duration))
        for i in range(max(1, int(clicks))):
            if i:
                time.sleep(interval)
            pyautogui.click(button=btn)

    def mouse_down(self, button: str = "left") -> None:
        if HAS_PYAUTOGUI:
            pyautogui.mouseDown(button=_BUTTON.get(button, button))

    def mouse_up(self, button: str = "left") -> None:
        if HAS_PYAUTOGUI:
            pyautogui.mouseUp(button=_BUTTON.get(button, button))

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5,
             button: str = "left", hold: float = 0.15) -> None:
        if not HAS_PYAUTOGUI:
            return
        btn = _BUTTON.get(button, button)
        pyautogui.moveTo(int(x1), int(y1), duration=0.2)
        time.sleep(0.05)
        pyautogui.mouseDown(button=btn)
        time.sleep(max(0.0, hold))
        pyautogui.moveTo(int(x2), int(y2), duration=max(0.1, duration))
        time.sleep(0.05)
        pyautogui.mouseUp(button=btn)

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if not HAS_PYAUTOGUI:
            return
        if x is not None and y is not None:
            pyautogui.moveTo(int(x), int(y), duration=0.1)
        pyautogui.scroll(int(amount))

    # ------------------------------------------------------- 键盘
    def press(self, key: str, times: int = 1, interval: float = 0.05) -> None:
        if HAS_PYAUTOGUI:
            for _ in range(max(1, int(times))):
                pyautogui.press(_norm_key(key))
                time.sleep(interval)

    def hotkey(self, keys: Sequence[str]) -> None:
        if HAS_PYAUTOGUI and keys:
            pyautogui.hotkey(*[_norm_key(k) for k in keys if k and k.strip()])

    def key_down(self, key: str) -> None:
        if HAS_PYAUTOGUI:
            pyautogui.keyDown(_norm_key(key))

    def key_up(self, key: str) -> None:
        if HAS_PYAUTOGUI:
            pyautogui.keyUp(_norm_key(key))

    def select_all(self) -> None:
        """全选（mac 自动用 Cmd+A，Windows 用 Ctrl+A）。"""
        self.hotkey([MOD_KEY, "a"])

    def copy(self) -> None:
        """复制（mac 自动用 Cmd+C）。"""
        self.hotkey([MOD_KEY, "c"])

    def paste(self) -> None:
        """粘贴（mac 自动用 Cmd+V）。"""
        self.hotkey([MOD_KEY, "v"])

    def write(self, text: str, interval: float = 0.02) -> None:
        """输入文本。含中文时自动改用剪贴板粘贴。"""
        if not text:
            return
        if text.isascii():
            if HAS_PYAUTOGUI:
                pyautogui.write(text, interval=interval)
            return
        if HAS_CLIP:
            self.paste_via_clipboard(text)
        elif HAS_PYAUTOGUI:
            pyautogui.write(text, interval=interval)

    def paste_via_clipboard(self, text: str) -> None:
        old = self.get_clipboard()
        self.set_clipboard(text)
        time.sleep(0.06)
        self.paste()
        time.sleep(0.06)
        if old:
            self.set_clipboard(old)

    # ------------------------------------------------------- 剪贴板
    def get_clipboard(self) -> str:
        if HAS_CLIP:
            try:
                return pyperclip.paste() or ""
            except Exception:
                return ""
        return ""

    def set_clipboard(self, text: str) -> None:
        if HAS_CLIP:
            try:
                pyperclip.copy(text if isinstance(text, str) else str(text))
            except Exception:
                pass

    def select_all_copy(self, wait: float = 0.25) -> str:
        """Ctrl+A 全选 → Ctrl+C 复制 → 读剪贴板。用于抓取界面文字。"""
        self.set_clipboard("")
        self.hotkey(["ctrl", "a"])
        time.sleep(wait)
        self.hotkey(["ctrl", "c"])
        time.sleep(wait)
        return self.get_clipboard()
