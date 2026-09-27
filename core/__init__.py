"""灵瞳核心包：模型 / 注册中心 / 引擎 / 驱动 / 变量（全部不依赖 Qt）。"""
from __future__ import annotations

import os

os.environ.setdefault("PYTHONUTF8", "1")

__version__ = "1.2.4"
APP_NAME = "LingTong"
APP_NAME_CN = "灵瞳"
APP_TAGLINE = "看得懂屏幕的自动化助手"
APP_TITLE = f"{APP_NAME_CN} · {APP_TAGLINE}"

__all__ = ["__version__", "APP_NAME", "APP_NAME_CN", "APP_TAGLINE", "APP_TITLE"]
