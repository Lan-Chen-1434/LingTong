"""
AutoRPA 驱动层
================
把"图像识别 / 鼠标键盘 / 剪贴板 / 窗口"这些系统能力封装成稳定接口。
上层模块只调用这里的单例，方便替换实现（如以后接入 UIAutomation）。

单例
----
SCREEN  屏幕截图 + 模板匹配（缓存 400ms，同一步骤多次找图只截一次屏）
INPUT   鼠标 + 键盘 + 剪贴板
WINDOW  窗口激活 / 最大化 / 关闭
"""
from __future__ import annotations

from typing import Dict

from .input import HAS_CLIP, InputDriver
from .screen import HAS_CV2, HAS_PIL, HAS_PYAUTOGUI, MatchResult, ScreenDriver
from .window import WindowDriver

SCREEN = ScreenDriver(cache_ms=400)
INPUT = InputDriver()
WINDOW = WindowDriver()

__all__ = [
    "SCREEN", "INPUT", "WINDOW",
    "ScreenDriver", "InputDriver", "WindowDriver", "MatchResult",
    "check_dependencies",
]


def check_dependencies() -> Dict[str, bool]:
    """自检：返回各能力所依赖的库是否可用。"""
    return {
        "OpenCV (图像识别)": HAS_CV2,
        "pyautogui (鼠标键盘)": HAS_PYAUTOGUI,
        "Pillow (截图)": HAS_PIL,
        "pyperclip (剪贴板)": HAS_CLIP,
    }
