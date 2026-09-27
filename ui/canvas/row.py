"""
画布数据行
============
一行 = 一个可见节点。包含扁平化后的树位置信息与预计算几何，
绘制与命中测试都直接读这些字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QRectF

from core.models import FlowNode

# ---------------------------------------------------------------- 几何常量
ROW_H = 58            # 卡片高度
GAP = 8               # 卡片间距
STEP = ROW_H + GAP
INDENT = 26           # 每层缩进
PAD_TOP = 16
PAD_LEFT = 14
CHEVRON_ZONE = 24     # 折叠箭头占位宽度

STATUS_COLORS = {
    "ok": "#22C07A",
    "fail": "#F25549",
    "skip": "#F7A524",
    "running": "#00A9CE",
}


@dataclass
class Row:
    node: FlowNode
    depth: int
    parent: Optional[FlowNode]
    index: int
    y: float = 0.0
    card: QRectF = field(default_factory=QRectF)
    chevron: Optional[QRectF] = None
    subtree_end: Optional[int] = None   # 子树最后一个行号（用于画容器底纹）
