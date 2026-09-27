"""
模块库面板（左侧）
====================
按分类罗列全部功能积木。支持搜索过滤、分类折叠、拖拽到画布、双击快速添加。
"""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from core.registry import CATEGORIES, REGISTRY

from . import icons, theme
from .widgets import Card, ModuleChip, SearchBox, NODE_MIME


class CategoryHeader(QWidget):
    """分类标题行：色点 + 名称 + 数量 + 折叠箭头。"""

    toggled = Signal(str)

    def __init__(self, name: str, count: int, color: str, parent=None) -> None:
        super().__init__(parent)
        self.name = name
        self.color = color
        self.count = count
        self.collapsed = False
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(7)
        self.arrow = QLabel()
        self.arrow.setFixedSize(12, 12)
        self._refresh_arrow()
        lay.addWidget(self.arrow)
        self.title = QLabel(name)
        self.title.setStyleSheet(
            f"font-size:12.5px; font-weight:700; color:{theme.TEXT};")
        lay.addWidget(self.title)
        self.cnt = QLabel(str(count))
        # 数量徽标统一用中性配色：分类色只体现在模块图标上，标题行更干净
        self.cnt.setStyleSheet(
            f"font-size:11px; color:{theme.TEXT_SUB}; background:{theme.PANEL_SOFT};"
            f"border:1px solid {theme.BORDER}; border-radius:8px; padding:1px 7px;")
        lay.addWidget(self.cnt)
        lay.addStretch(1)

    def _refresh_arrow(self) -> None:
        self.arrow.setPixmap(icons.glyph_pixmap(
            "chevron_right" if self.collapsed else "chevron_down",
            theme.TEXT_MUTED, 12, 1.9))

    def mousePressEvent(self, e) -> None:                 # noqa: N802
        self.collapsed = not self.collapsed
        self._refresh_arrow()
        self.toggled.emit(self.name)


class ModulePalette(Card):
    """左侧功能模块库。"""

    module_added = Signal(str)          # 双击模块 → 追加到流程
    drag_began = Signal()
    node_dropped = Signal(str)          # 画布节点拖回这里 → 从流程删除（uid）

    def __init__(self, parent=None) -> None:
        super().__init__("功能模块", "拖到画布")
        self.setMinimumWidth(224)
        self.setAcceptDrops(True)       # 接受画布节点拖入 = 删除该步骤

        self.search = SearchBox("搜索模块，如 图像 / 输入 / 循环")
        self.search.changed.connect(self._apply_filter)
        self.body_layout.addWidget(self.search)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 4, 4, 8)
        self.inner_layout.setSpacing(2)
        self.scroll.setWidget(self.inner)
        self.body_layout.addWidget(self.scroll, 1)

        self._headers: Dict[str, CategoryHeader] = {}
        self._containers: Dict[str, QWidget] = {}
        self._chips: List[ModuleChip] = []

        # ---- 拖回删除提示浮层：画布节点拖入本面板时显示 ----
        self._drop_hint = QLabel("🗑  松开以删除该步骤", self)
        self._drop_hint.setObjectName("PaletteDropHint")
        self._drop_hint.setAlignment(Qt.AlignCenter)
        self._drop_hint.setStyleSheet(
            f"color:{theme.ERR}; background:{theme.ERR_SOFT};"
            f"border:2px dashed {theme.ERR}; border-radius:10px;"
            f"font-size:13px; font-weight:700;")
        self._drop_hint.hide()
        self._drop_hint_active = False

        self._build()

    def _place_drop_hint(self) -> None:
        m = 10
        w = self.width() - m * 2
        h = 44
        self._drop_hint.setGeometry(m, self.height() - h - m, w, h)
        self._drop_hint.raise_()

    def resizeEvent(self, e) -> None:                       # noqa: N802
        super().resizeEvent(e)
        if self._drop_hint_active:
            self._place_drop_hint()

    # ------------------------------------------------------------------ 拖放
    # 画布节点拖回本面板 = 从流程中删除该步骤
    def dragEnterEvent(self, e) -> None:                    # noqa: N802
        if e.mimeData().hasFormat(NODE_MIME):
            e.acceptProposedAction()
            self._drop_hint_active = True
            self._place_drop_hint()
            self._drop_hint.show()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:                     # noqa: N802
        if e.mimeData().hasFormat(NODE_MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:                    # noqa: N802
        self._hide_drop_hint()

    def dropEvent(self, e) -> None:                         # noqa: N802
        md = e.mimeData()
        if md.hasFormat(NODE_MIME):
            self._hide_drop_hint()
            uid = bytes(md.data(NODE_MIME)).decode("utf-8")
            self.node_dropped.emit(uid)
            e.acceptProposedAction()
        else:
            e.ignore()

    def _hide_drop_hint(self) -> None:
        self._drop_hint_active = False
        self._drop_hint.hide()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        grouped = REGISTRY.by_category()
        for cat in CATEGORIES:
            mods = [m for m in grouped.get(cat, []) if not m.type_id.startswith("_")]
            if not mods:
                continue
            hexc = theme.cat_color(cat)
            soft = theme.cat_soft(cat)
            header = CategoryHeader(cat, len(mods), hexc)
            header.toggled.connect(self._toggle_category)
            self._headers[cat] = header
            self.inner_layout.addWidget(header)

            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(2, 0, 0, 6)
            hl.setSpacing(1)
            for spec in mods:
                chip = ModuleChip(spec.type_id, spec.name, spec.desc or "",
                                  spec.badge or "•", hexc, soft,
                                  glyph=spec.glyph or "")
                chip.activated.connect(self.module_added.emit)
                chip.drag_started.connect(self.drag_began.emit)
                hl.addWidget(chip)
                self._chips.append(chip)
            self._containers[cat] = holder
            self.inner_layout.addWidget(holder)
        self.inner_layout.addStretch(1)

    def _toggle_category(self, cat: str) -> None:
        holder = self._containers.get(cat)
        if holder:
            holder.setVisible(not holder.isVisible())

    # ------------------------------------------------------------------ 过滤
    def _apply_filter(self, kw: str) -> None:
        kw = (kw or "").strip().lower()
        for chip in self._chips:
            hit = (not kw) or kw in chip._name.lower() or kw in chip.type_id.lower()  # noqa: SLF001
            chip.setVisible(hit)
        for cat, holder in self._containers.items():
            # 用 isVisibleTo 忽略容器自身的隐藏状态——否则"清空过滤"时
            # chip.isVisible() 因父容器还藏着而恒为 False，分类永远展不开
            visible = any(c.isVisibleTo(holder) for c in
                          holder.findChildren(ModuleChip))
            holder.setVisible(visible)
            hdr = self._headers.get(cat)
            if hdr:
                hdr.setVisible(visible)
                if kw:
                    hdr.collapsed = False
                    hdr._refresh_arrow()                       # noqa: SLF001
                    holder.setVisible(visible)
