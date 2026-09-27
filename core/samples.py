"""
内置示例流程
==============
示例流程以文件形式存放在 examples/<示例名>/<示例名>.arpa
（文件夹结构参考 flows/<流程名>/，见 core/paths.py），本模块负责扫描与加载：

* list_examples()  扫描示例文件夹，供「示例流程」菜单动态列出
                   （往 examples/ 里加文件夹，菜单自动多一项）；
* load_example()   加载指定示例文件。

每个示例的 .arpa 里写清 description，菜单悬停时会显示（运行前的注意事项）。
"""
from __future__ import annotations

import os
from typing import List, Tuple

from .models import Flow
from .paths import EXAMPLES_DIR

#: 「空白流程」菜单项的标识（不是文件路径）
BLANK = "__blank__"


def list_examples() -> List[Tuple[str, str, str]]:
    """扫描 examples/ 下的示例流程，返回 [(文件路径, 名称, 描述)]，按名称排序。"""
    out: List[Tuple[str, str, str]] = []
    if os.path.isdir(EXAMPLES_DIR):
        for name in sorted(os.listdir(EXAMPLES_DIR)):
            d = os.path.join(EXAMPLES_DIR, name)
            fp = os.path.join(d, f"{name}.arpa")
            if not os.path.isdir(d) or not os.path.isfile(fp):
                continue
            desc = ""
            try:
                desc = Flow.load(fp).description or ""
            except Exception:
                pass
            out.append((fp, name, desc))
    return out


def load_example(path: str) -> Flow:
    """加载示例流程文件。"""
    return Flow.load(path)
