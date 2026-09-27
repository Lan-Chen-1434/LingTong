"""
类型化变量值编辑器
====================
按变量类型给出最直观的录入方式（需求：只有列表 / 字典 / 表格才弹「编辑内容」）：

* 字符串  —— 多行内容框，直接输入，支持 {{变量}}；
* 数字    —— 单行输入框，可填数值或运算公式（如 {{count}} + 1）；
* 布尔    —— 下拉框，只有 True / False 两项；
* 一维列表 —— 「编辑内容」弹窗：单列行表；
* 二维列表 —— 「编辑内容」弹窗：多行多列网格；
* 字典    —— 「编辑内容」弹窗：名称 / 值两列；
* 表格    —— 「编辑内容」弹窗：带表头的数据网格（表头可改名）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from core import vartypes as vt

from .. import theme
from ..widgets import NoWheelComboBox


# ==================================================================== 结构化内容编辑对话框
class StructEditDialog(QDialog):
    """列表 / 字典 / 表格的内容编辑对话框（exec() 模态，与抓图无关，可安全模态）。"""

    def __init__(self, vtype: str, value: Any, parent=None) -> None:
        super().__init__(parent)
        self.vtype = vt.vtype_of(vtype)
        self.setWindowTitle(f"编辑内容 · {vt.label_of(self.vtype)}")
        self.setMinimumSize(460, 340)
        self.resize(520, 400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        tip = QLabel(self._tip())
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:11.5px;")
        lay.addWidget(tip)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setStyleSheet(
            f"QTableWidget {{ background:{theme.PANEL}; border:1px solid {theme.BORDER_STRONG};"
            f"border-radius:6px; gridline-color:{theme.BORDER}; }}"
            f"QHeaderView::section {{ background:{theme.PANEL_SOFT}; color:{theme.TEXT_SUB};"
            f"border:none; border-bottom:1px solid {theme.BORDER}; padding:4px 6px; font-size:12px; }}"
            f"QHeaderView::section:hover {{ background:{theme.PRIMARY_SOFT}; }}")
        lay.addWidget(self.table, 1)

        # 表头双击编辑（表格/二维列表）
        if self.vtype in (vt.VT_TABLE, vt.VT_LIST2D):
            self.table.horizontalHeader().sectionDoubleClicked.connect(self._edit_header)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._mk_btn(bar, "＋ 添加行", self._add_row)
        self._mk_btn(bar, "－ 删除行", self._del_row)
        if self.vtype in (vt.VT_LIST2D, vt.VT_TABLE):
            self._mk_btn(bar, "＋ 添加列", self._add_col)
            self._mk_btn(bar, "－ 删除列", self._del_col)
        if self.vtype == vt.VT_TABLE:
            self._mk_btn(bar, "✎ 列改名", self._rename_col)
        self._mk_btn(bar, "从文本导入", self._import_text)
        self._mk_btn(bar, "清空", self._clear)
        bar.addStretch(1)
        lay.addLayout(bar)

        box = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        box.button(QDialogButtonBox.Ok).setText("确定")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.button(QDialogButtonBox.Ok).setObjectName("Primary")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        self._fill(value)

    # ------------------------------------------------------------ 构建
    def _tip(self) -> str:
        return {
            vt.VT_LIST1D: "一行一项。单元格支持 {{变量}}，纯数字会自动按数字存储。",
            vt.VT_LIST2D: "多行多列的网格。双击表头可修改列名。单元格支持 {{变量}}，纯数字会自动按数字存储。",
            vt.VT_DICT: "每行一对「名称 = 值」。值支持 {{变量}}，纯数字会自动按数字存储。",
            vt.VT_TABLE: "第一行是表头（列名），双击表头可直接修改列名。单元格支持 {{变量}}。",
        }.get(self.vtype, "")

    def _mk_btn(self, lay: QHBoxLayout, text: str, fn) -> QPushButton:
        b = QPushButton(text)
        b.setStyleSheet("padding:4px 10px; font-size:12px;")
        b.clicked.connect(fn)
        lay.addWidget(b)
        return b

    def _fill(self, value: Any) -> None:
        val = vt.normalize_value(self.vtype, value)
        t = self.table
        if self.vtype == vt.VT_LIST1D:
            t.setColumnCount(1)
            t.setHorizontalHeaderLabels(["值"])
            t.setRowCount(len(val))
            for i, v in enumerate(val):
                t.setItem(i, 0, QTableWidgetItem("" if v is None else str(v)))
        elif self.vtype == vt.VT_LIST2D:
            cols = max((len(r) for r in val), default=1) or 1
            t.setColumnCount(cols)
            t.setHorizontalHeaderLabels([f"列{i + 1}" for i in range(cols)])
            t.setRowCount(len(val))
            for i, row in enumerate(val):
                for j in range(cols):
                    v = row[j] if j < len(row) else ""
                    t.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
        elif self.vtype == vt.VT_DICT:
            t.setColumnCount(2)
            t.setHorizontalHeaderLabels(["名称", "值"])
            t.setRowCount(len(val))
            for i, (k, v) in enumerate(val.items()):
                t.setItem(i, 0, QTableWidgetItem(str(k)))
                t.setItem(i, 1, QTableWidgetItem("" if v is None else str(v)))
        else:  # TABLE
            cols: List[str] = []
            for r in val:
                for k in r.keys():
                    if k not in cols:
                        cols.append(str(k))
            if not cols:
                cols = ["列1"]
            t.setColumnCount(len(cols))
            t.setHorizontalHeaderLabels(cols)
            t.setRowCount(len(val))
            for i, r in enumerate(val):
                for j, c in enumerate(cols):
                    v = r.get(c, "")
                    t.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
        if t.rowCount() == 0:
            t.setRowCount(3 if self.vtype != vt.VT_DICT else 2)

    # ------------------------------------------------------------ 读回
    def value(self) -> Any:
        t = self.table

        def cell(i: int, j: int) -> str:
            it = t.item(i, j)
            return it.text() if it else ""

        if self.vtype == vt.VT_LIST1D:
            return [cell(i, 0) for i in range(t.rowCount())
                    if cell(i, 0).strip() != ""]
        if self.vtype == vt.VT_LIST2D:
            rows = []
            for i in range(t.rowCount()):
                row = [cell(i, j) for j in range(t.columnCount())]
                if any(c.strip() for c in row):
                    rows.append(row)
            return rows
        if self.vtype == vt.VT_DICT:
            d: Dict[str, Any] = {}
            for i in range(t.rowCount()):
                k = cell(i, 0).strip()
                if k:
                    d[k] = cell(i, 1)
            return d
        # TABLE
        cols = []
        for j in range(t.columnCount()):
            h = t.horizontalHeaderItem(j)
            cols.append((h.text() if h else f"列{j + 1}").strip() or f"列{j + 1}")
        rows = []
        for i in range(t.rowCount()):
            row = {cols[j]: cell(i, j) for j in range(t.columnCount())}
            if any(str(v).strip() for v in row.values()):
                rows.append(row)
        return rows

    # ------------------------------------------------------------ 行/列操作
    def _add_row(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)

    def _del_row(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows and self.table.rowCount() > 0:
            rows = [self.table.rowCount() - 1]
        for r in rows:
            self.table.removeRow(r)

    def _add_col(self) -> None:
        c = self.table.columnCount()
        self.table.insertColumn(c)
        if self.vtype == vt.VT_TABLE:
            name, ok = QInputDialog.getText(self, "添加列", "列名：", text=f"列{c + 1}")
            self.table.setHorizontalHeaderItem(
                c, QTableWidgetItem(name.strip() if (ok and name.strip()) else f"列{c + 1}"))
        else:
            self.table.setHorizontalHeaderItem(c, QTableWidgetItem(f"列{c + 1}"))

    def _del_col(self) -> None:
        cols = sorted({i.column() for i in self.table.selectedIndexes()}, reverse=True)
        if not cols and self.table.columnCount() > 1:
            cols = [self.table.columnCount() - 1]
        if self.table.columnCount() - len(cols) < 1:
            QMessageBox.information(self, "提示", "至少保留一列。")
            return
        for c in cols:
            self.table.removeColumn(c)

    def _rename_col(self) -> None:
        col = self.table.currentColumn()
        if col < 0:
            col = 0
        self._edit_header(col)

    def _edit_header(self, col: int) -> None:
        """双击表头或点击「列改名」时弹出输入框修改列名。"""
        h = self.table.horizontalHeaderItem(col)
        old = h.text() if h else f"列{col + 1}"
        name, ok = QInputDialog.getText(self, "修改列名", "新的列名：", text=old)
        if ok and name.strip():
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(name.strip()))

    def _clear(self) -> None:
        self.table.setRowCount(0)

    def _import_text(self) -> None:
        """从纯文本导入：JSON / 逐行 / 逗号·制表符分隔 / "k = v" 均可。"""
        text, ok = QInputDialog.getMultiLineText(
            self, "从文本导入",
            "支持 JSON、每行一项、逗号/制表符分隔、或「名称 = 值」行格式：")
        if not ok or not text.strip():
            return
        try:
            val = vt.normalize_value(self.vtype, text)
        except Exception as exc:                            # noqa: BLE001
            QMessageBox.warning(self, "导入失败", f"无法解析文本：{exc}")
            return
        self._fill(val)


# ==================================================================== 类型化值编辑器
class TypedValueEditor(QWidget):
    """按变量类型选择录入控件。结构化类型只显示摘要 + 「编辑内容」按钮。"""

    changed = Signal()

    def __init__(self, vtype: str, value: Any = None, parent=None) -> None:
        super().__init__(parent)
        self._vtype = vt.VT_STRING
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)
        self._getter = lambda: None
        self._setter = lambda v: None
        self._struct_value: Any = None
        self.set_vtype(vtype)
        if value is not None:
            self.set_value(value)

    def _fire(self, *args) -> None:
        """带参数的 Qt 信号（textChanged(str) 等）统一收敛成无参 changed。"""
        self.changed.emit()

    # ------------------------------------------------------------ 类型切换
    def vtype(self) -> str:
        return self._vtype

    def set_vtype(self, vtype: str) -> None:
        """切换类型并重建编辑器；值重置为新类型默认值。"""
        self._vtype = vt.vtype_of(vtype)
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        t = self._vtype
        if t == vt.VT_STRING:
            ed = QPlainTextEdit()
            ed.setPlaceholderText("直接输入内容，支持 {{变量}}")
            ed.setMinimumHeight(62)
            ed.setMaximumHeight(140)
            ed.textChanged.connect(self.changed.emit)
            self._lay.addWidget(ed)
            self._getter = ed.toPlainText
            self._setter = lambda v: ed.setPlainText("" if v is None else str(v))

        elif t == vt.VT_NUMBER:
            ed = QLineEdit()
            ed.setPlaceholderText("数值或运算公式，如 100 或 {{count}} + 1")
            ed.textChanged.connect(self._fire)
            self._lay.addWidget(ed)
            self._getter = ed.text
            self._setter = lambda v: ed.setText("" if v is None else str(v))

        elif t == vt.VT_BOOL:
            ed = NoWheelComboBox()
            ed.addItems(["True", "False"])
            ed.currentTextChanged.connect(self._fire)
            self._lay.addWidget(ed)
            self._getter = lambda: ed.currentText() == "True"
            self._setter = lambda v: ed.setCurrentText("True" if vt.coerce_bool(v) else "False")

        else:  # 结构化：摘要 + 编辑内容按钮
            self._struct_value = vt.default_value(t)
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            self._summary = QLabel()
            self._summary.setStyleSheet(
                f"color:{theme.TEXT_SUB}; font-size:12px; background:{theme.PANEL_SOFT};"
                f"border:1px solid {theme.BORDER}; border-radius:6px; padding:5px 9px;")
            h.addWidget(self._summary, 1)
            btn = QPushButton("编辑内容")
            btn.setObjectName("Primary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._edit_struct)
            h.addWidget(btn)
            self._lay.addWidget(wrap)
            hint = QLabel("点击「编辑内容」在表格里逐行填写")
            hint.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11px;")
            self._lay.addWidget(hint)
            self._getter = lambda: self._struct_value
            self._setter = self._set_struct
            self._refresh_summary()

    # ------------------------------------------------------------ 结构化编辑
    def _set_struct(self, v: Any) -> None:
        self._struct_value = vt.normalize_value(self._vtype, v)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        self._summary.setText(f"{vt.label_of(self._vtype)} · {vt.brief(self._vtype, self._struct_value)}")
        tip = str(self._struct_value)
        self._summary.setToolTip(tip if len(tip) <= 300 else tip[:300] + "…")

    def _edit_struct(self) -> None:
        dlg = StructEditDialog(self._vtype, self._struct_value, self)
        if dlg.exec() == QDialog.Accepted:
            self._struct_value = dlg.value()
            self._refresh_summary()
            self.changed.emit()

    # ------------------------------------------------------------ 读写
    def value(self) -> Any:
        return self._getter()

    def set_value(self, v: Any) -> None:
        self._setter(v)
