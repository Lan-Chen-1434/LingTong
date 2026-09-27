"""
变量位编辑行
==============
按 VarSlot 声明组装「变量名称 + 变量类型 + 值」：

* 输入变量：三个子项都有——值编辑器随类型变化（TypedValueEditor）；
* 输出变量：只有变量名称 + 变量类型（类型是模块固有的，只读展示）。

类型可编辑的变量位（如「设置 / 运算变量」）用一个下拉框选择类型，
选择后值编辑器立即重建为新类型的录入方式。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from core import vartypes as vt
from core.models import FlowNode
from core.spec import VarSlot

from .. import theme
from ..widgets import NoWheelComboBox, wrap_tooltip
from .param_row import _label
from .var_editors import TypedValueEditor


#: 匹配纯变量引用 {{name}} 的正则（用于显示时解包）
_BRACES_RE = re.compile(r"^\{\{\s*([A-Za-z_]\w*)\s*\}\}$")


def _unwrap_braces(text: str) -> str:
    """把 {{变量名}} 解包成纯变量名；复杂表达式保持原样。"""
    m = _BRACES_RE.match(text.strip())
    return m.group(1) if m else text


def _wrap_braces(text: str) -> str:
    """纯变量名自动包成 {{变量名}}；已含 {{ 或非合法变量名保持原样。"""
    t = text.strip()
    if "{{" in t or "}}" in t:
        return t
    if re.fullmatch(r"[A-Za-z_]\w*", t):
        return f"{{{{{t}}}}}"
    return t


def _type_chip(text: str) -> QLabel:
    """固定类型的只读展示块（看起来像输入框但不可编辑，避免误以为是可选项）。"""
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color:{theme.TEXT_SUB}; font-size:12.5px; background:{theme.PANEL_SOFT};"
        f"border:1px solid {theme.BORDER}; border-radius:6px; padding:5px 9px;")
    return lb


#: 「类型可自动推导」的变量位在下拉框里提供的哨兵选项
_AUTO_TYPE_LABEL = "自动（跟随变量）"


class VarSlotRow(QWidget):
    """一个输入 / 输出变量位的编辑行。"""

    changed = Signal()

    def __init__(self, slot: VarSlot, node: FlowNode, flow=None, parent=None) -> None:
        super().__init__(parent)
        self.slot = slot
        self.node = node
        self.flow = flow
        self._type_combo: Optional[NoWheelComboBox] = None
        self._auto_type = False
        self._type_chip_box: Optional[QVBoxLayout] = None
        self._chip: Optional[QLabel] = None
        self._value_editor: Optional[TypedValueEditor] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        card = QFrame()
        card.setObjectName("Panel")
        card.setStyleSheet(
            f"QFrame#Panel {{ background:{theme.PANEL_SOFT};"
            f"border:1px solid {theme.BORDER}; border-radius:8px; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 10)
        cl.setSpacing(6)
        lay.addWidget(card)

        head = QLabel(slot.label + ("（输入）" if slot.direction == "in" else "（输出）"))
        head.setStyleSheet(f"font-size:12.5px; font-weight:700; color:{theme.TEXT};")
        if slot.desc:
            head.setToolTip(wrap_tooltip(slot.desc))
        cl.addWidget(head)

        # ---- 变量名称 ----
        if slot.name_param:
            cl.addWidget(_label("变量名称", "后续步骤用 {{变量名}} 引用"))
            raw_name = str(node.params.get(slot.name_param, "") or "")
            if slot.direction == "in" and slot.name_is_ref:
                # 输入变量 = 变量引用：显示时去掉 {{}}，底层自动补回
                self.name_edit = QLineEdit(_unwrap_braces(raw_name))
                self.name_edit.setPlaceholderText("直接输入变量名，如 score_list")
            else:
                self.name_edit = QLineEdit(raw_name)
                self.name_edit.setPlaceholderText("英文/数字/下划线")
            self.name_edit.textChanged.connect(self._fire)
            cl.addWidget(self.name_edit)
        else:
            self.name_edit = None

        # ---- 变量类型（输入变量展示；输出变量仅在类型动态推导时展示） ----
        if slot.direction == "in":
            cl.addWidget(_label("变量类型", slot.desc))
            if slot.type_param:
                # 类型可选：下拉框，切换后值编辑器跟着重建；
                # 类型还能动态推导的变量位（如循环「数据来源」）额外提供「自动」选项
                self._type_combo = NoWheelComboBox()
                self._auto_type = slot.vtype_fn is not None or \
                    slot.vtype_ctx_fn is not None
                if self._auto_type:
                    self._type_combo.addItem(_AUTO_TYPE_LABEL)
                self._type_combo.addItems([vt.label_of(t) for t in vt.VT_ORDER])
                raw = str(node.params.get(slot.type_param, "") or "").strip()
                if self._auto_type and (not raw or raw.startswith("自动")):
                    self._type_combo.setCurrentIndex(0)
                else:
                    self._type_combo.setCurrentText(
                        vt.label_of(raw) if raw else vt.label_of(slot.vtype))
                self._type_combo.currentTextChanged.connect(self._on_type_changed)
                cl.addWidget(self._type_combo)
            else:
                # 类型固定 / 随参数动态推导：只读展示
                self._type_chip_box = QVBoxLayout()
                self._type_chip_box.setContentsMargins(0, 0, 0, 0)
                cl.addLayout(self._type_chip_box)
                self._refresh_type_chip()
        else:
            if slot.type_param:
                # 输出变量允许自选类型（如截图提取内容：字符串 / 表格）
                cl.addWidget(_label("变量类型", slot.desc))
                self._type_combo = NoWheelComboBox()
                choices = slot.type_choices or [vt.label_of(t) for t in vt.VT_ORDER]
                self._type_combo.addItems(choices)
                raw = str(node.params.get(slot.type_param, "") or "").strip()
                self._type_combo.setCurrentText(
                    vt.label_of(raw) if raw else vt.label_of(slot.vtype))
                self._type_combo.currentTextChanged.connect(self._on_type_changed)
                cl.addWidget(self._type_combo)
                self._type_chip_box = None
            elif slot.vtype_fn is not None or slot.vtype_ctx_fn is not None:
                # 类型随参数/上下文动态推导（如循环「当前项」）：展示推导结果
                self._type_combo = None
                self._type_chip_box = QVBoxLayout()
                self._type_chip_box.setContentsMargins(0, 0, 0, 0)
                cl.addLayout(self._type_chip_box)
                self._refresh_type_chip()
            else:
                # 类型固定（如调用程序「程序输出」）：只读展示
                self._type_combo = None
                cl.addWidget(_label("变量类型", slot.desc))
                self._type_chip_box = QVBoxLayout()
                self._type_chip_box.setContentsMargins(0, 0, 0, 0)
                cl.addLayout(self._type_chip_box)
                self._refresh_type_chip()

        # ---- 值（仅输入变量）----
        if slot.direction == "in" and slot.value_param:
            cl.addWidget(_label("值", "字符串可直接输入；数字支持公式；列表/字典/表格点「编辑内容」"))
            self._value_editor = TypedValueEditor(self.current_vtype())
            self._value_editor.set_value(node.params.get(slot.value_param))
            self._value_editor.changed.connect(self._fire)
            cl.addWidget(self._value_editor)

    def _fire(self, *args) -> None:
        """带参数的 Qt 信号统一收敛成无参 changed（防 TypeError 静默丢值）。"""
        self.changed.emit()

    # ------------------------------------------------------------------
    def current_vtype(self) -> str:
        return self.slot.current_vtype(self.node.params, self.flow)

    def _source_type_label(self) -> str:
        """检测循环「数据来源」的变量类型标签（用于当前项 chip 显示优化）。"""
        pick = str(self.node.params.get("src_type") or "").strip()
        if pick and not pick.startswith("自动"):
            return pick
        src = str(self.node.params.get("dataset") or "").strip()
        m = _BRACES_RE.match(src)
        if not m or self.flow is None:
            return ""
        name = m.group(1)
        for n in getattr(self.flow, "nodes", []) or []:
            if getattr(n, "type_id", "") == "data.set_var":
                np = getattr(n, "params", {}) or {}
                if np.get("name") == name:
                    return str(np.get("vtype") or "")
        return ""

    def _refresh_type_chip(self) -> None:
        if self._type_chip_box is None:
            return
        while self._type_chip_box.count():
            item = self._type_chip_box.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        label = vt.label_of(self.current_vtype())
        # 循环「当前项」遍历字典时，用更直观的「键值对」替代「字典」
        if self.slot.label == "当前项" and label == "字典":
            if self._source_type_label() == "字典":
                label = "键值对"
        if self.slot.type_param:
            suffix = ""
        elif self.slot.vtype_fn is not None or self.slot.vtype_ctx_fn is not None:
            suffix = "（自动推导）"
        else:
            suffix = "（固定）"
        self._chip = _type_chip(f"{label}{suffix}")
        self._type_chip_box.addWidget(self._chip)

    def _on_type_changed(self, text: str) -> None:
        """用户改了类型：同步到底层参数（存中文标签，流程文件可读）+ 重建值编辑器。"""
        if self.slot.type_param:
            # 「自动（跟随变量）」统一存成「自动」，动态推导函数据此回退
            self.node.params[self.slot.type_param] = \
                "自动" if text.startswith("自动") else text
        if self._value_editor is not None:
            self._value_editor.set_vtype(self.current_vtype())
        self.changed.emit()

    # ------------------------------------------------------------------
    def write_to(self, params: Dict[str, Any]) -> None:
        """把界面状态写回 node.params。"""
        s = self.slot
        if s.name_param and self.name_edit is not None:
            if s.direction == "in" and s.name_is_ref:
                params[s.name_param] = _wrap_braces(self.name_edit.text())
            else:
                params[s.name_param] = self.name_edit.text()
        if s.type_param and self._type_combo is not None:
            text = self._type_combo.currentText()
            params[s.type_param] = "自动" if text.startswith("自动") else text
        if s.direction == "in" and s.value_param and self._value_editor is not None:
            params[s.value_param] = self._value_editor.value()

    def refresh_visibility(self, params: Dict[str, Any]) -> None:
        """条件显隐 + 固定/动态类型展示刷新（参数变化后由 Inspector 调用）。"""
        ok = True
        if self.slot.visible_when:
            for dep, allowed in self.slot.visible_when.items():
                if str(params.get(dep, "")) not in [str(a) for a in allowed]:
                    ok = False
                    break
        self.setVisible(ok)
        self._refresh_type_chip()
