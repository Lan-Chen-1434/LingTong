"""
参数面板
==========
根据选中模块的参数定义自动生成表单——新增模块无需写任何界面代码。
分层：param_row（控件）→ sections（分组）→ Inspector（组装面板）。

面板分区（按需出现）：
  输入变量 —— 模块声明了 VarSlot("in") 才显示；变量名称 + 变量类型 + 值
  输出变量 —— 模块声明了 VarSlot("out") 才显示；变量名称 + 变量类型（无值）
  参数设置 —— 其余普通参数
  运行控制 —— 失败重试 / 超时（所有模块统一）
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QScrollArea, QVBoxLayout, QWidget)

from core.models import FlowNode

from .. import icons, theme
from ..widgets import Card, EmptyHint
from .param_row import ParamRow, PixelPickRow
from .sections import CollapsibleSection
from .var_slot import VarSlotRow

# 通用运行控制参数（异常策略/重试/超时）固定归到折叠区
_CTRL_PARAMS = ("on_error", "retry", "retry_interval", "timeout")


class Inspector(Card):
    """右侧参数面板。"""

    params_changed = Signal()

    def __init__(self, base_dir: str, parent=None) -> None:
        super().__init__("步骤参数", "选中左侧步骤后设置")
        self.base_dir = base_dir
        self.node: Optional[FlowNode] = None
        self.flow = None                       # 由 MainWindow 注入，供变量类型推导
        self.rows: Dict[str, ParamRow] = {}
        self.var_rows: List[VarSlotRow] = []

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.inner = QWidget()
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(2, 4, 6, 10)
        self.inner_layout.setSpacing(12)
        self.scroll.setWidget(self.inner)
        self.body_layout.addWidget(self.scroll, 1)
        self.setMinimumWidth(280)

        self.empty = EmptyHint("未选中步骤", "在中间画布上点一下某个步骤，\n这里就会显示它的全部参数。")
        self.inner_layout.addWidget(self.empty)

        self.head_widget = QWidget()
        self.head_layout = QVBoxLayout(self.head_widget)
        self.head_layout.setContentsMargins(0, 0, 0, 0)
        self.head_layout.setSpacing(8)
        self.inner_layout.insertWidget(0, self.head_widget)
        self.head_widget.setVisible(False)

    # ------------------------------------------------------------------
    def show_node(self, node: Optional[FlowNode]) -> None:
        self.node = node
        self._clear()
        if node is None:
            self.empty.setVisible(True)
            self.head_widget.setVisible(False)
            self.set_hint("选中左侧步骤后设置")
            return
        self.empty.setVisible(False)
        self.head_widget.setVisible(True)
        spec = node.spec
        self.set_title("步骤参数")
        self.set_hint(spec.name if spec else node.type_id)

        self._build_head(node, spec)
        self._build_meta(node)

        var_names = spec.var_param_names() if spec else set()
        main_params = [p for p in spec.params
                       if p.name not in _CTRL_PARAMS and p.name not in var_names] if spec else []
        ctrl_params = [p for p in spec.params if p.name in _CTRL_PARAMS] if spec else []

        idx = 2
        # ---- 输入变量（仅声明了的模块显示）----
        in_slots = spec.input_slots() if spec else []
        if in_slots:
            sec_in = CollapsibleSection("输入变量", True)
            for slot in in_slots:
                row = VarSlotRow(slot, node, self.flow)
                row.changed.connect(self._on_param_changed)
                self.var_rows.append(row)
                sec_in.content_layout.addWidget(row)
            self.inner_layout.insertWidget(idx, sec_in)
            idx += 1

        # ---- 输出变量（仅声明了的模块显示）----
        out_slots = spec.output_slots() if spec else []
        if out_slots:
            sec_out = CollapsibleSection("输出变量", True)
            for slot in out_slots:
                row = VarSlotRow(slot, node, self.flow)
                row.changed.connect(self._on_param_changed)
                self.var_rows.append(row)
                sec_out.content_layout.addWidget(row)
            self.inner_layout.insertWidget(idx, sec_out)
            idx += 1

        # ---- 普通参数 ----
        if main_params:
            sec = CollapsibleSection("参数设置", True)
            # 声明了 picker 的模块（如像素颜色判断）在分区顶部放拾取行
            if any(getattr(p, "picker", "") == "pixel" for p in main_params):
                pick_row = PixelPickRow(node)
                pick_row.picked_values.connect(self._on_picked_values)
                sec.content_layout.addWidget(pick_row)
            for p in main_params:
                row = ParamRow(p, node, self.base_dir)
                row.changed.connect(self._on_param_changed)
                self.rows[p.name] = row
                sec.content_layout.addWidget(row)
            self.inner_layout.insertWidget(idx, sec)
            idx += 1

        sec2 = CollapsibleSection("运行控制（失败重试 / 超时）", False)
        for p in ctrl_params:
            row = ParamRow(p, node, self.base_dir)
            row.changed.connect(self._on_param_changed)
            self.rows[p.name] = row
            sec2.content_layout.addWidget(row)
        self.inner_layout.insertWidget(idx, sec2)
        idx += 1

        # ---- 使用示例（模块声明了才显示；每行一条，可选中复制）----
        if spec and spec.examples:
            sec_ex = CollapsibleSection("使用示例", False)
            for i, text in enumerate(spec.examples, 1):
                line = QLabel(f"{i}. {text}")
                line.setWordWrap(True)
                line.setTextInteractionFlags(Qt.TextSelectableByMouse)
                line.setStyleSheet(
                    f"color:{theme.TEXT_SUB}; font-size:12px; background:{theme.PANEL_SOFT};"
                    f"border:1px solid {theme.BORDER}; border-radius:6px; padding:6px 8px;")
                sec_ex.content_layout.addWidget(line)
            self.inner_layout.insertWidget(idx, sec_ex)

        self._refresh_visibility()
        # 切换步骤后回到面板顶部，避免停留在上一次滚动的位置
        self.scroll.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------------
    def _build_head(self, node: FlowNode, spec) -> None:
        """顶部的模块名片（徽章 + 名称 + 说明）。"""
        head = QFrame()
        cat = spec.category if spec else "通用工具"
        head.setStyleSheet(f"QFrame {{ background:{theme.cat_soft(cat)}; border-radius:9px; }}")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(11, 9, 11, 9)
        hl.setSpacing(10)
        badge = QLabel()
        if spec and spec.glyph:
            badge.setPixmap(icons.ICON_CACHE.icon(
                spec.glyph, theme.cat_color(cat), theme.cat_soft(cat), 30))
        else:
            badge.setPixmap(icons.BADGE_CACHE.badge(
                spec.badge if spec else "•", theme.cat_color(cat), theme.cat_soft(cat), 30))
        hl.addWidget(badge)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(spec.name if spec else node.type_id)
        t.setStyleSheet(f"font-size:13.5px; font-weight:700; color:{theme.TEXT};")
        col.addWidget(t)
        d = QLabel(spec.desc if spec else "")
        d.setWordWrap(True)
        d.setStyleSheet(f"font-size:11.5px; color:{theme.TEXT_SUB};")
        col.addWidget(d)
        hl.addLayout(col, 1)
        self.head_layout.addWidget(head)

    def _build_meta(self, node: FlowNode) -> None:
        """启用开关 + 备注输入。"""
        meta = QWidget()
        ml = QVBoxLayout(meta)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(8)

        en = QCheckBox("启用此步骤")
        en.setChecked(node.enabled)
        en.setStyleSheet(f"color:{theme.TEXT}; font-size:12.5px; font-weight:600;")
        en.toggled.connect(self._set_enabled)
        ml.addWidget(en)

        from .param_row import _label
        ml.addWidget(_label("备注", "只用于说明，不影响执行；会显示在画布卡片上"))
        note = QLineEdit(node.note)
        note.setPlaceholderText("例如：登录后等待首页加载")
        note.textChanged.connect(self._set_note)
        ml.addWidget(note)
        self.head_layout.addWidget(meta)

    # ------------------------------------------------------------------
    def _clear(self) -> None:
        """清空面板内容。

        两处都要清：inner_layout 里 index≥2 的参数分组，
        以及 head_layout 里的「模块名片 + 启用/备注」——漏掉后者
        就会在连续切换步骤时不断向下堆叠（正是之前暴露的 bug）。
        """
        self.rows.clear()
        self.var_rows.clear()
        while self.inner_layout.count() > 2:
            item = self.inner_layout.takeAt(2)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        while self.head_layout.count():
            item = self.head_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _set_enabled(self, value: bool) -> None:
        if self.node:
            self.node.enabled = bool(value)
            self.params_changed.emit()

    def _set_note(self, text: str) -> None:
        if self.node:
            self.node.note = text
            self.params_changed.emit()

    def _on_picked_values(self, values: dict) -> None:
        """picker 拾取结果回填：写入对应参数行（兄弟参数，如 坐标 Y / 目标颜色）。"""
        if self.node is None or not values:
            return
        for name, value in values.items():
            row = self.rows.get(name)
            if row is not None:
                row.set_value(value)
            else:
                self.node.params[name] = value
        self._on_param_changed()

    def _on_param_changed(self) -> None:
        if self.node is None:
            return
        for name, row in self.rows.items():
            self.node.params[name] = row.param.coerce(row.value())
        for row in self.var_rows:
            row.write_to(self.node.params)
        self._refresh_visibility()
        self.params_changed.emit()

    def _refresh_visibility(self) -> None:
        if self.node is None:
            return
        spec = self.node.spec
        if spec is None:
            return
        visible = {p.name for p in spec.visible_params(self.node.params)}
        for name, row in self.rows.items():
            row.setVisible(name in visible)
        for row in self.var_rows:
            row.refresh_visibility(self.node.params)
