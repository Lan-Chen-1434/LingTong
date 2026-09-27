"""
画布绘制
==========
所有 QPainter 绘制逻辑集中在这里。每个函数都是纯绘制：
给定 (QPainter, 数据, 状态) 画完就走，不改任何数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen)

from core.models import FlowNode

from .. import icons, theme
from .row import (CHEVRON_ZONE, GAP, INDENT, PAD_LEFT, PAD_TOP, ROW_H,
                  STATUS_COLORS, Row)


@dataclass
class CanvasState:
    """绘制时需要的全部"运行态"信息。"""
    selected_uid: Optional[str] = None
    hover_uid: Optional[str] = None
    running_uid: Optional[str] = None
    error_uid: Optional[str] = None
    runtime: Dict[str, str] = field(default_factory=dict)       # uid -> status
    drop: Optional[Tuple[Optional[FlowNode], int, str]] = None  # (parent, index, mode)
    collapsed: set = field(default_factory=set)                 # 折叠的容器 uid
    pulse: float = 0.0                                          # 运行脉冲动画相位 0~1


_FONT_TITLE = theme.font(10)
_FONT_TITLE.setBold(True)
_FONT_SUB = theme.font(8)
_FONT_IDX = theme.font(8)


def draw_all(p: QPainter, width: int, rows: List[Row], state: CanvasState) -> None:
    """完整重绘一张画布。"""
    draw_containers(p, rows)
    draw_guides(p, rows)
    for idx, r in enumerate(rows):
        draw_card(p, r, idx, state)
    draw_drop_hint(p, rows, state.drop, width)


def draw_empty(p: QPainter, width: int) -> None:
    """空画布引导提示。"""
    box = QRectF(PAD_LEFT + 40, 80, max(200.0, width - PAD_LEFT * 2 - 80), 190)
    p.setPen(QPen(QColor(theme.BORDER_STRONG), 1.6, Qt.DashLine))
    p.setBrush(QBrush(QColor(theme.PANEL)))
    p.drawRoundedRect(box, 14, 14)

    pm = icons.BADGE_CACHE.badge("拖", theme.PRIMARY, theme.PRIMARY_SOFT, 46)
    p.drawPixmap(int(box.center().x() - 23), int(box.top() + 26), pm)

    f = theme.font(11)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QPen(QColor(theme.TEXT_SUB)))
    p.drawText(QRectF(box.left(), box.top() + 82, box.width(), 24),
               Qt.AlignCenter, "把左侧的功能模块拖到这里")

    p.setFont(theme.font(9))
    p.setPen(QPen(QColor(theme.TEXT_MUTED)))
    p.drawText(QRectF(box.left() + 16, box.top() + 110, box.width() - 32, 60),
               Qt.AlignHCenter | Qt.TextWordWrap,
               "例如：抓取区域文字 → 判断关键词 → 点击目标图像 → 循环下一页\n"
               "拖到「循环」卡片中间可以把步骤放进循环里")


def draw_containers(p: QPainter, rows: List[Row]) -> None:
    """容器底纹：为循环/条件等块级节点画出带分类色的嵌套底。"""
    p.setPen(Qt.NoPen)
    for r in rows:
        if r.subtree_end is not None and r.subtree_end > 0:
            last = rows[r.subtree_end]
            top = r.card.bottom() - 6
            bot = last.card.bottom() + 6
            x = r.card.left() + 8
            w = r.card.right() - x
            spec = r.node.spec
            cat = spec.category if spec else "通用工具"
            tint = QColor(theme.cat_soft(cat))
            tint.setAlpha(150)
            p.setBrush(QBrush(tint))
            p.drawRoundedRect(QRectF(x, top, w, max(10.0, bot - top)), 9, 9)


def draw_guides(p: QPainter, rows: List[Row]) -> None:
    """缩进引导线。"""
    p.setPen(QPen(QColor(theme.BORDER), 1))
    for r in rows:
        if r.depth > 0:
            gx = PAD_LEFT + (r.depth - 1) * INDENT + CHEVRON_ZONE - 8
            p.drawLine(int(gx), int(r.y + 4), int(gx), int(r.y + ROW_H - 4))


def _travel_light(p: QPainter, rect: QRectF, color: str, head: float,
                  seg: float = 90.0) -> None:
    """沿圆角矩形边框巡游的柔光：光核在边框线上，向四周径向晕开直至透明，
    拖尾沿行进方向逐渐变淡变细。"""
    from PySide6.QtGui import QRadialGradient
    path = QPainterPath()
    path.addRoundedRect(rect, 11, 11)
    total = path.length()
    if total <= 0:
        return
    seg = min(seg, total * 0.25)
    base = QColor(color)
    core = QColor(base).lighter(185)
    blobs = 16
    p.setPen(Qt.NoPen)
    # 从尾部画向头部：头部光球最后落笔、压在最上层
    for i in range(blobs, -1, -1):
        t = 1.0 - i / blobs                    # 头部≈1，尾部≈0
        fade = t ** 1.5
        d = (head * total - seg * i / blobs) % total
        c = path.pointAtPercent(d / total)
        r = 2.0 + 15.0 * fade
        grad = QRadialGradient(c, r)
        grad.setColorAt(0.0, QColor(core.red(), core.green(), core.blue(),
                                    int(235 * fade)))
        grad.setColorAt(0.3, QColor(base.red(), base.green(), base.blue(),
                                    int(140 * fade)))
        grad.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))


def draw_card(p: QPainter, r: Row, idx: int, state: CanvasState) -> None:
    """单个节点卡片。"""
    node = r.node
    is_hidden = node.type_id in ("_else", "_catch")
    spec = node.spec
    cat = spec.category if spec else "通用工具"
    color = theme.cat_color(cat)
    soft = theme.cat_soft(cat)
    selected = (state.selected_uid is not None and state.selected_uid == node.uid)
    running = (state.running_uid == node.uid)
    hover = (state.hover_uid == node.uid)

    p.save()
    if not node.enabled:
        p.setOpacity(0.45)

    card = r.card
    status = state.runtime.get(node.uid)
    # 报错红灯：紧急停止的节点 + 执行失败；黄灯：失败但跳过此步
    is_error = (state.error_uid == node.uid) or status == "fail"
    is_warn = (status == "skip")
    if is_error:
        bg = QColor(theme.PANEL)          # 卡体保持原色，只做边缘高亮
        border = QColor(theme.ERR)
        border.setAlpha(128)              # 50% 透明
    elif is_warn:
        bg = QColor(theme.PANEL)
        border = QColor(theme.WARN)
        border.setAlpha(128)
    elif running:
        bg = QColor(theme.PANEL)
        border = QColor(theme.RUN)
        border.setAlpha(128)
    elif selected:
        bg = QColor(theme.PANEL)
        border = QColor(theme.PRIMARY)
    elif is_hidden:
        bg = QColor(theme.PANEL_SOFT)
        border = QColor(theme.BORDER)
    else:
        bg = QColor(theme.PANEL)
        border = QColor(theme.PRIMARY) if hover else QColor(theme.BORDER)

    # 投影
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 110)))
    p.drawRoundedRect(QRectF(card.left(), card.top() + 1.5,
                             card.width(), card.height()), 11, 11)
    # 卡体
    p.setBrush(QBrush(bg))
    pen_w = 2.5 if selected else (2.0 if (running or is_error or is_warn) else 1.0)
    p.setPen(QPen(border, pen_w))
    p.drawRoundedRect(card, 10, 10)

    # 运行中：呼吸辉光 + 沿边框巡游的流光 + 脉冲边框
    if running:
        import math
        breathe = 0.5 + 0.5 * math.sin(state.pulse * 2 * math.pi * 2)
        glow = QColor(theme.RUN)
        glow.setAlpha(int(0.5 * (60 + 70 * breathe)))   # 50% 透明
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        # 辉光只画边框环带，不罩卡体中间
        outer = QPainterPath()
        outer.addRoundedRect(card.adjusted(-10, -10, 10, 10), 16, 16)
        inner = QPainterPath()
        inner.addRoundedRect(card, 10, 10)
        p.drawPath(outer.subtracted(inner))
        p.setBrush(Qt.NoBrush)
        # 脉冲边框
        pulse_border = QColor(theme.RUN)
        pulse_border.setAlpha(int(0.5 * (120 + 100 * breathe)))   # 50% 透明
        p.setPen(QPen(pulse_border, 1.6 + 0.5 * breathe))
        p.drawRoundedRect(card.adjusted(-2, -2, 2, 2), 11, 11)
        # 高亮流光沿边框线条巡游
        _travel_light(p, card.adjusted(-2, -2, 2, 2), theme.RUN,
                      state.pulse % 1.0)

    # 报错态：红色辉光（不旋转）
    if is_error:
        import math
        breathe = 0.5 + 0.5 * math.sin(state.pulse * 2 * math.pi * 2)
        glow = QColor(theme.ERR)
        glow.setAlpha(int(0.5 * (60 + 70 * breathe)))   # 50% 透明
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        outer = QPainterPath()
        outer.addRoundedRect(card.adjusted(-10, -10, 10, 10), 16, 16)
        inner = QPainterPath()
        inner.addRoundedRect(card, 10, 10)
        p.drawPath(outer.subtracted(inner))
        pulse_border = QColor(theme.ERR)
        pulse_border.setAlpha(int(0.5 * (120 + 100 * breathe)))   # 50% 透明
        p.setPen(QPen(pulse_border, 1.6 + 0.5 * breathe))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(card.adjusted(-2, -2, 2, 2), 11, 11)

    # 跳过态：黄色辉光（失败但选择"跳过此步"，不阻塞流程）
    if is_warn:
        import math
        breathe = 0.5 + 0.5 * math.sin(state.pulse * 2 * math.pi * 2)
        glow = QColor(theme.WARN)
        glow.setAlpha(int(0.5 * (60 + 70 * breathe)))   # 50% 透明
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        outer = QPainterPath()
        outer.addRoundedRect(card.adjusted(-10, -10, 10, 10), 16, 16)
        inner = QPainterPath()
        inner.addRoundedRect(card, 10, 10)
        p.drawPath(outer.subtracted(inner))
        pulse_border = QColor(theme.WARN)
        pulse_border.setAlpha(int(0.5 * (120 + 100 * breathe)))   # 50% 透明
        p.setPen(QPen(pulse_border, 1.6 + 0.5 * breathe))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(card.adjusted(-2, -2, 2, 2), 11, 11)

    # 左侧分类色条
    bar = QRectF(card.left() + 0.5, card.top() + 9, 3.5, card.height() - 18)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(color if node.enabled else theme.TEXT_MUTED)))
    p.drawRoundedRect(bar, 1.75, 1.75)

    # 分类图标（glyph 优先， Fallback 到单字 badge）
    if spec and spec.glyph:
        icon = icons.ICON_CACHE.icon(spec.glyph, color, soft, 30)
    else:
        icon = icons.BADGE_CACHE.badge(spec.badge if spec else "•", color, soft, 30)
    p.drawPixmap(int(card.left() + 13), int(card.top() + (ROW_H - 30) / 2), icon)

    # 折叠箭头
    if r.chevron:
        glyph = "chevron_right" if node.uid in state.collapsed else "chevron_down"
        p.drawPixmap(int(r.chevron.left()), int(r.chevron.top()),
                     icons.glyph_pixmap(glyph, theme.TEXT_MUTED, 16, 2.0))

    # 文字
    text_x = card.left() + 13 + 30 + 11
    right_reserve = 74
    tw = max(60.0, card.right() - text_x - right_reserve)

    p.setFont(_FONT_TITLE)
    p.setPen(QPen(QColor(theme.TEXT if node.enabled else theme.TEXT_SUB)))
    title = node.display_name
    if not node.enabled:
        title += "（已禁用）"
    fm = QFontMetrics(_FONT_TITLE)
    p.drawText(QRectF(text_x, card.top() + 9, tw, 19),
               Qt.AlignLeft | Qt.AlignVCenter,
               fm.elidedText(title, Qt.ElideRight, int(tw)))

    p.setFont(_FONT_SUB)
    p.setPen(QPen(QColor(theme.TEXT_MUTED)))
    fms = QFontMetrics(_FONT_SUB)
    summary = spec.summary(node.params) if spec else ""
    if not summary:
        summary = spec.desc if spec else ""
    if node.note:
        summary = f"📝 {node.note}" + (f"   ·   {summary}" if summary else "")
    if is_error:
        summary = "⚠ 取值失败" + (f"   ·   {summary}" if summary else "")
    elif running:
        summary = "正在执行…" + (f"   ·   {summary}" if summary else "")
    p.drawText(QRectF(text_x, card.top() + 29, tw, 17),
               Qt.AlignLeft | Qt.AlignVCenter,
               fms.elidedText(summary, Qt.ElideRight, int(tw)))

    # 右侧：序号 + 状态点
    p.setFont(_FONT_IDX)
    p.setPen(QPen(QColor(theme.TEXT_MUTED)))
    p.drawText(QRectF(card.right() - 66, card.top() + ROW_H / 2 - 9, 40, 18),
               Qt.AlignRight | Qt.AlignVCenter, f"{idx + 1}")

    dot_c = STATUS_COLORS.get(status or "", None)
    if is_error:
        dot_c = theme.ERR
    elif running:
        dot_c = theme.PRIMARY
    if dot_c:
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(dot_c)))
        p.drawEllipse(QRectF(card.right() - 20, card.top() + ROW_H / 2 - 4.5, 9, 9))
    elif not node.enabled:
        p.setPen(QPen(QColor(theme.TEXT_MUTED), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(card.right() - 20, card.top() + ROW_H / 2 - 4.5, 9, 9))

    p.restore()


def draw_drop_hint(p: QPainter, rows: List[Row], drop, width: int) -> None:
    """拖拽落点指示：横线+圆点，或容器虚线框。"""
    if not drop:
        return
    parent, index, mode = drop

    if mode == "into" and parent is not None:
        for r in rows:
            if r.node is parent:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(theme.PRIMARY), 2.0, Qt.DashLine))
                p.drawRoundedRect(r.card.adjusted(-3, -3, 3, 3), 12, 12)
                inner = QRectF(r.card.left() + 10, r.card.bottom() - 4,
                               r.card.width() - 20, 3)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(theme.PRIMARY)))
                p.drawRoundedRect(inner, 1.5, 1.5)
                return
        return

    siblings = parent.children if parent is not None else None
    x1, x2 = float(PAD_LEFT + CHEVRON_ZONE), float(width - PAD_LEFT)
    y: Optional[float] = None

    anchor = None
    if siblings is not None:
        target_idx = min(index, max(0, len(siblings) - 1))
    else:
        top_count = sum(1 for r in rows if r.parent is None)
        target_idx = min(index, max(0, top_count - 1))
    for r in rows:
        if r.parent is parent and r.index == target_idx:
            anchor = r
            break
    if anchor is not None:
        y = (anchor.card.top() - GAP / 2) if index <= anchor.index \
            else (anchor.card.bottom() + GAP / 2)
        x1, x2 = anchor.card.left(), anchor.card.right()
    if y is None:
        if rows:
            last = rows[-1]
            y = last.card.bottom() + GAP / 2
            x1, x2 = last.card.left(), last.card.right()
        else:
            y = PAD_TOP + ROW_H / 2

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(theme.PRIMARY)))
    p.drawRoundedRect(QRectF(x1, y - 1.5, max(40.0, x2 - x1), 3), 1.5, 1.5)
    p.drawEllipse(QRectF(x1 - 4, y - 4.5, 9, 9))
