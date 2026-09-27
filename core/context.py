"""
AutoRPA 运行时上下文
======================
一次流程执行期间的"共享内存"：日志通道、停止/暂停信号、驱动引用、数据表。
变量插值与条件求值已下沉到 core.variables.VarStore，这里只做接线与转发。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from .drivers import INPUT, SCREEN, WINDOW
from .variables import VarStore


class RunContext:
    """流程执行上下文。各功能模块通过它访问驱动、变量、日志与运行控制。"""

    def __init__(self, flow, logger: Optional[Callable[[str, str], None]] = None,
                 progress: Optional[Callable[[Any, str], None]] = None,
                 base_dir: Optional[str] = None) -> None:
        self.flow = flow
        self.log = logger or (lambda level, msg: None)
        self.progress = progress or (lambda node, status: None)
        self.base_dir = base_dir or os.getcwd()

        # 驱动
        self.screen = SCREEN
        self.input = INPUT
        self.window = WINDOW

        # 数据
        self.data: List[Dict[str, Any]] = []
        self._store = VarStore(warn=lambda m: self.log("warn", m))
        self.vars: Dict[str, Any] = self._store.vars          # 保持直接访问兼容

        # 窗口作用域栈：「窗口内运行」容器压入，内部每个步骤执行前校验激活状态
        self.win_scopes: List[Any] = []

        # 动态占位符：{{clipboard}} / {{mouse_x}} / {{data_count}} …
        self._store.register_special("clipboard", self.input.get_clipboard)
        self._store.register_special("剪贴板", self.input.get_clipboard)
        self._store.register_special("mouse_x", lambda: self.input.position()[0])
        self._store.register_special("鼠标x", lambda: self.input.position()[0])
        self._store.register_special("mouse_y", lambda: self.input.position()[1])
        self._store.register_special("鼠标y", lambda: self.input.position()[1])
        self._store.register_special("active_window", self.window.active_title)
        self._store.register_special("当前窗口", self.window.active_title)
        self._store.register_special("data_count", lambda: len(self.data))
        self._store.register_special("数据行数", lambda: len(self.data))

        # 运行控制
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()                    # set = 继续，clear = 暂停

        # 其它
        self.last_match = None                    # 最近一次找图结果

    # ------------------------------------------------------------ 运行控制
    def check_stop(self) -> None:
        from .exceptions import RunAborted
        while True:
            if self.stop_event.is_set():
                raise RunAborted("流程已被手动停止")
            if self.pause_event.is_set():
                return
            time.sleep(0.08)

    def sleep(self, seconds: float) -> None:
        """可被停止打断的 sleep。"""
        end = time.time() + max(0.0, float(seconds))
        while time.time() < end:
            self.check_stop()
            time.sleep(min(0.08, max(0.0, end - time.time())))

    # ------------------------------------------------------------ 日志
    def info(self, msg: str) -> None:
        self.log("info", self.resolve(msg))

    def warn(self, msg: str) -> None:
        self.log("warn", self.resolve(msg))

    def error(self, msg: str) -> None:
        self.log("error", self.resolve(msg))

    def success(self, msg: str) -> None:
        self.log("ok", self.resolve(msg))

    def debug(self, msg: str) -> None:
        self.log("debug", self.resolve(msg))

    # ------------------------------------------------------------ 变量（转发到 VarStore）
    def set_var(self, name: str, value: Any) -> None:
        self._store.set(name, value)

    def get_var(self, name: str, default: Any = None) -> Any:
        return self._store.get(name, default)

    def add_data(self, row: Dict[str, Any]) -> None:
        self.data.append(row)

    def resolve(self, text: Any, default: str = "") -> str:
        return self._store.resolve(text, default)

    def resolve_asset(self, path: Any) -> str:
        """图片等流程资源路径：相对路径基于流程文件夹解析。"""
        from . import paths
        return paths.resolve(self.base_dir, str(path or ""))

    def resolve_value(self, text: Any) -> Any:
        return self._store.resolve_value(text)

    def eval_condition(self, expr: str, fallback: bool = False) -> bool:
        return self._store.eval_condition(expr, fallback)

    # ------------------------------------------------------------ 找图快捷方法
    def find_image(self, templates: Sequence[str], confidence: float = 0.85,
                   region=None, timeout: float = 0.0, interval: float = 0.4):
        if not templates:
            return None
        res = self.screen.find_any(templates, confidence, region,
                                   timeout=timeout, interval=interval)
        self.last_match = res
        return res

    def screenshot_region(self, region, path: str) -> bool:
        return self.screen.save_crop(region, path)
