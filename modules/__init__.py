"""
AutoRPA 功能模块库
====================
导入本包即完成所有功能积木的注册（依赖 registry 的装饰器副作用）。
新增模块只需在本目录添加文件并在下方 import，UI 会自动出现对应积木。
"""
from __future__ import annotations

from . import (data_ops, flow_ops, image_ops, keyboard_ops, mouse_ops,
               process_ops, utils_ops, window_ops)          # noqa: F401

__all__ = [
    "image_ops", "mouse_ops", "keyboard_ops",
    "window_ops", "data_ops", "flow_ops", "utils_ops", "process_ops",
]
