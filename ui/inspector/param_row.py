"""
参数编辑控件
==============
ImageListEditor   模板图列表编辑器（缩略图 + 抓图/选文件/清空）
ParamRow          单参数编辑行，按参数类型自动选择合适的控件

新增参数类型 = 在 ParamRow._build 里加一个分支，Inspector 无需改动。
"""
from __future__ import annotations

import os
from typing import Any, Callable, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from core.models import FlowNode
from core.spec import (P_BOOL, P_COLOR, P_FILE, P_FLOAT, P_FOLDER, P_IMAGE,
                       P_KEY, P_NUMBER, P_REGION, P_SELECT, P_TEXT, P_TEXTAREA)

from .. import icons, theme
from ..dialogs import HotkeyEdit, PointPickOverlay, RegionCaptureDialog
from ..widgets import (NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox,
                       wrap_tooltip)
from .region_editor import RegionEditor


def _label(text: str, help_text: str = "") -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:12px;")
    if help_text:
        lb.setToolTip(wrap_tooltip(help_text))
    return lb


class ImageListEditor(QWidget):
    """模板图列表编辑器。"""

    changed = Signal()

    def __init__(self, base_dir: str, node: FlowNode, parent=None) -> None:
        super().__init__(parent)
        self.base_dir = base_dir                 # 当前流程的工作区文件夹
        self.node = node
        self._paths: List[str] = []
        self._cap_dlg = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(4)
        lay.addLayout(self.list_box)

        self.empty_label = QLabel("还没添加模板图")
        self.empty_label.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:11.5px;"
            f"border:1px dashed {theme.BORDER_STRONG}; border-radius:7px; padding:10px;")
        self.empty_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_label)

        row = QHBoxLayout()
        row.setSpacing(6)
        b1 = QPushButton("  抓图取图")
        b1.setObjectName("Primary")
        b1.setIcon(icons.glyph_icon("crosshair", "#FFFFFF", 15))
        b1.setToolTip("从屏幕上框选一块区域，直接存成模板图")
        b1.clicked.connect(self._capture)
        b2 = QPushButton("  选文件")
        b2.setIcon(icons.glyph_icon("open", theme.TEXT_SUB, 15))
        b2.clicked.connect(self._add_files)
        b3 = QPushButton("  清空")
        b3.setIcon(icons.glyph_icon("trash", theme.TEXT_SUB, 15))
        b3.clicked.connect(self._clear)
        row.addWidget(b1, 1)
        row.addWidget(b2)
        row.addWidget(b3)
        lay.addLayout(row)

    # ------------------------------------------------------------------
    def _resolve(self, p: str) -> str:
        """展示用：相对路径（input/image/...）解析成绝对路径。"""
        from core import paths
        return paths.resolve(self.base_dir, p)

    @property
    def _image_dir(self) -> str:
        return os.path.join(self.base_dir, "input", "image")

    def set_paths(self, paths: List[str]) -> None:
        self._paths = list(paths or [])
        self._rebuild()

    def paths(self) -> List[str]:
        return list(self._paths)

    def _rebuild(self) -> None:
        while self.list_box.count():
            item = self.list_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for p in self._paths:
            self.list_box.addWidget(self._make_row(p))
        self.empty_label.setVisible(not self._paths)

    def _make_row(self, path: str) -> QWidget:
        row = QFrame()
        row.setObjectName("Panel")
        row.setStyleSheet(
            f"QFrame#Panel {{ background:{theme.PANEL_SOFT};"
            f"border:1px solid {theme.BORDER}; border-radius:7px; }}")
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(44, 30)
        thumb.setStyleSheet(
            f"border-radius:4px; background:{theme.PANEL_SOFT};"
            f"border:1px solid {theme.BORDER};")
        thumb.setAlignment(Qt.AlignCenter)
        real = self._resolve(path)
        pm = QPixmap(real)
        if not pm.isNull():
            thumb.setPixmap(pm.scaled(44, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            thumb.setText("?")
        h.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(0)
        name = QLabel(os.path.basename(path))
        name.setStyleSheet(f"font-size:11.5px; color:{theme.TEXT};")
        name.setToolTip(real)
        info.addWidget(name)
        size = QLabel(f"{pm.width()}×{pm.height()}" if not pm.isNull() else "文件缺失")
        size.setStyleSheet(f"font-size:10.5px; color:{theme.TEXT_MUTED};")
        info.addWidget(size)
        h.addLayout(info, 1)

        rm = QToolButton()
        rm.setIcon(icons.glyph_icon("close", theme.TEXT_MUTED, 13))
        rm.setAutoRaise(True)
        rm.setCursor(Qt.PointingHandCursor)
        rm.setToolTip("移除")
        rm.clicked.connect(lambda: self._remove(path))
        h.addWidget(rm)
        return row

    def _remove(self, path: str) -> None:
        if path in self._paths:
            self._paths.remove(path)
            self._rebuild()
            self.changed.emit()

    def _clear(self) -> None:
        self._paths.clear()
        self._rebuild()
        self.changed.emit()

    def _add_files(self) -> None:
        from core import paths
        start = self._image_dir if os.path.isdir(self._image_dir) else self.base_dir
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择模板图片", start,
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        for f in files:
            # 流程引用的图片统一收进本流程 input/image，参数里存相对路径
            stored = paths.ingest_image(self.base_dir, f)
            if stored not in self._paths:
                self._paths.append(stored)
        if files:
            self._rebuild()
            self.changed.emit()

    def _capture(self) -> None:
        """打开抓图对话框。

        关键：不能用 exec() 模态——模态会拦截整个应用的鼠标输入，
        导致全屏选框收不到拖拽事件。改用 WindowModal + open()，
        只挡住主窗口，抓图覆盖层（独立顶层窗口）不受影响。
        """
        from PySide6.QtWidgets import QDialog

        if self._cap_dlg is not None:
            try:
                self._cap_dlg.close()
            except Exception:
                pass
        from core import paths
        dlg = RegionCaptureDialog(self._image_dir, self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)

        def _done(code: int) -> None:
            self._cap_dlg = None
            if code == QDialog.Accepted and dlg.saved_path:
                stored = paths.rel_or_abs(self.base_dir, dlg.saved_path)
                if stored not in self._paths:
                    self._paths.append(stored)
                self._rebuild()
                self.changed.emit()

        dlg.finished.connect(_done)
        self._cap_dlg = dlg
        dlg.open()


class ParamRow(QWidget):
    """单个参数的编辑行。"""

    changed = Signal()

    def __init__(self, param, node: FlowNode, base_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.param = param
        self.node = node
        self.base_dir = base_dir
        self.editor: Optional[QWidget] = None
        self._getter: Callable[[], Any] = lambda: None
        self._setter: Callable[[Any], None] = lambda v: None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(_label(param.label, param.help))
        self._build(lay, param, node)
        if param.placeholder and param.ptype == P_TEXT:
            self.editor.setPlaceholderText(param.placeholder)
        if param.help and self.editor is not None:
            # 悬停在输入框上也能看到说明（不只参数名标签）
            self.editor.setToolTip(wrap_tooltip(param.help))

    def _fire(self, *args) -> None:
        """把带参数的 Qt 信号统一收敛成无参的 changed 信号。

        PySide6 不允许 textChanged(str) 直接 connect 无参信号的 emit，
        会抛 TypeError 导致参数变更静默丢失——必须经过这里转发。
        """
        self.changed.emit()

    # --------------------------------------------------------------- 构建
    def _build(self, lay: QVBoxLayout, p, node: FlowNode) -> None:
        val = node.params.get(p.name, p.default)

        if p.ptype == P_TEXTAREA:
            ed = QPlainTextEdit()
            ed.setPlainText("" if val is None else str(val))
            ed.setPlaceholderText(p.placeholder)
            ed.setMinimumHeight(62)
            ed.setMaximumHeight(150)
            ed.textChanged.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = lambda: ed.toPlainText()
            self._setter = lambda v: ed.setPlainText("" if v is None else str(v))

        elif p.ptype == P_NUMBER:
            ed = NoWheelSpinBox()
            ed.setRange(int(p.minimum), int(p.maximum))
            ed.setValue(int(val or 0))
            if p.suffix:
                ed.setSuffix(" " + p.suffix)
            ed.valueChanged.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.value
            self._setter = lambda v: ed.setValue(int(v or 0))

        elif p.ptype == P_FLOAT:
            ed = NoWheelDoubleSpinBox()
            ed.setRange(float(p.minimum), float(p.maximum))
            ed.setDecimals(2 if p.step < 1 else 1)
            ed.setSingleStep(p.step)
            ed.setValue(float(val or 0))
            if p.suffix:
                ed.setSuffix(" " + p.suffix)
            ed.valueChanged.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.value
            self._setter = lambda v: ed.setValue(float(v or 0))

        elif p.ptype == P_BOOL:
            ed = QCheckBox("开启")
            ed.setChecked(bool(val))
            ed.setStyleSheet(f"color:{theme.TEXT}; font-size:12px;")
            ed.toggled.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.isChecked
            self._setter = lambda v: ed.setChecked(bool(v))

        elif p.ptype == P_SELECT:
            ed = NoWheelComboBox()
            ed.addItems(p.choices or [])
            if val is not None and str(val) in (p.choices or []):
                ed.setCurrentText(str(val))
            ed.currentTextChanged.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.currentText
            self._setter = lambda v: ed.setCurrentText(str(v))

        elif p.ptype == P_REGION:
            ed = RegionEditor(allow_empty=p.allow_empty)
            ed.set_value(val)
            ed.changed.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.value
            self._setter = ed.set_value

        elif p.ptype == P_KEY:
            ed = HotkeyEdit()
            ed.setText("" if val is None else str(val))
            ed.textChanged.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.text
            self._setter = lambda v: ed.setText(str(v))

        elif p.ptype == P_IMAGE:
            ed = ImageListEditor(self.base_dir, node)
            ed.set_paths(val if isinstance(val, list) else ([val] if val else []))
            ed.changed.connect(self._fire)
            lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.paths
            self._setter = ed.set_paths

        elif p.ptype in (P_FILE, P_FOLDER):
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            ed = QLineEdit("" if val is None else str(val))
            ed.setPlaceholderText(p.placeholder)
            ed.textChanged.connect(self._fire)
            h.addWidget(ed, 1)
            btn = QPushButton("…")
            btn.setFixedWidth(34)
            btn.clicked.connect(lambda: self._pick(ed, p.ptype))
            h.addWidget(btn)
            lay.addWidget(wrap)
            self.editor = ed
            self._getter = ed.text
            self._setter = lambda v: ed.setText(str(v))

        elif p.ptype == P_COLOR:
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(6)
            ed = QLineEdit("" if val is None else str(val))
            ed.textChanged.connect(self._fire)
            h.addWidget(ed, 1)
            sw = QPushButton()
            sw.setFixedSize(34, 28)
            sw.setCursor(Qt.PointingHandCursor)
            sw.clicked.connect(lambda: self._pick_color(ed, sw))
            h.addWidget(sw)
            self._sync_swatch(ed.text(), sw)
            ed.textChanged.connect(lambda t: self._sync_swatch(t, sw))
            lay.addWidget(wrap)
            self.editor = ed
            self._getter = ed.text
            self._setter = lambda v: ed.setText(str(v))

        else:                                   # P_TEXT 及默认
            ed = QLineEdit("" if val is None else str(val))
            ed.setPlaceholderText(p.placeholder)
            ed.textChanged.connect(self._fire)
            # ---- 带 browse_mode 的文本框也支持浏览按钮 ----
            if p.browse_mode:
                wrap = QWidget()
                h = QHBoxLayout(wrap)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(6)
                h.addWidget(ed, 1)
                btn = QPushButton("…")
                btn.setFixedWidth(34)
                btn.clicked.connect(lambda: self._pick_browse(ed, p.browse_mode))
                h.addWidget(btn)
                lay.addWidget(wrap)
            else:
                lay.addWidget(ed)
            self.editor = ed
            self._getter = ed.text
            self._setter = lambda v: ed.setText("" if v is None else str(v))

    # --------------------------------------------------------------- 工具
    def _pick(self, line: QLineEdit, ptype: str) -> None:
        if ptype == P_FOLDER:
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", self.base_dir)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", self.base_dir)
        if path:
            line.setText(path)

    def _pick_browse(self, line: QLineEdit, mode: str) -> None:
        """browse_mode 的浏览弹窗：file / folder / save。"""
        if mode == "folder":
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", self.base_dir)
        elif mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, "保存文件", self.base_dir)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", self.base_dir)
        if path:
            line.setText(path)

    def _pick_color(self, line: QLineEdit, swatch: QPushButton) -> None:
        c = QColorDialog.getColor(QColor(line.text() or "#FF0000"), self, "选择颜色")
        if c.isValid():
            line.setText(c.name().upper())

    @staticmethod
    def _sync_swatch(text: str, swatch: QPushButton) -> None:
        c = QColor(text)
        if not c.isValid():
            c = QColor("#FFFFFF")
        swatch.setStyleSheet(
            f"background:{c.name()}; border:1px solid {theme.BORDER_STRONG};"
            f"border-radius:6px;")

    def value(self) -> Any:
        return self._getter()

    def set_value(self, v: Any) -> None:
        self._setter(v)


class PixelPickRow(QWidget):
    """「拾取坐标和颜色」独立行：放在「参数设置」分区顶部。

    点击后最小化主窗口 → 全屏单击取点 → 发出 picked_values({参数名: 值})，
    由 Inspector 回填 坐标 X / 坐标 Y / 目标颜色 等兄弟参数行。
    """

    picked_values = Signal(dict)

    def __init__(self, node: FlowNode, parent=None) -> None:
        super().__init__(parent)
        self.node = node
        self._overlay: Optional[PointPickOverlay] = None
        self._pick_bg: Optional[QPixmap] = None
        self._pick_main_win = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        btn = QPushButton("  拾取坐标和颜色")
        btn.setObjectName("Primary")
        btn.setIcon(icons.glyph_icon("crosshair", "#FFFFFF", 15))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("点击后到屏幕上单击目标位置，自动填入 坐标 X / 坐标 Y / 目标颜色")
        btn.clicked.connect(self._pick)
        lay.addWidget(btn)

    # ------------------------------------------------------------ 取点
    def _pick(self) -> None:
        """最小化主窗口 → 全屏单击取点 → 回填坐标和目标颜色。"""
        self._pick_main_win = self.window()
        if self._pick_main_win is not None and self._pick_main_win is not self:
            self._pick_main_win.showMinimized()
        QTimer.singleShot(320, self._open_overlay)

    def _open_overlay(self) -> None:
        self._overlay = PointPickOverlay()
        bg, scale = PointPickOverlay.grab_virtual_screen()
        self._pick_bg = bg
        self._overlay.set_background(bg, scale)
        self._overlay.picked.connect(self._on_picked)
        self._overlay.cancelled.connect(self._restore)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()
        self._overlay.setFocus(Qt.OtherFocusReason)

    def _on_picked(self, pt) -> None:
        s = self._overlay._scale if self._overlay is not None else 1.0
        o = self._overlay._origin if self._overlay is not None else None
        ox, oy = (o.x(), o.y()) if o is not None else (0, 0)
        x = int((pt.x() + ox) * s)
        y = int((pt.y() + oy) * s)
        values: dict = {}
        # 「坐标来自变量」时 X/Y 填的是变量名，不覆盖，只取颜色
        if not self.node.params.get("use_var_coord"):
            values["x"] = x
            values["y"] = y
        bg = self._pick_bg
        if bg is not None and not bg.isNull():
            img = bg.toImage()
            bx, by = int(pt.x() * s), int(pt.y() * s)     # 底图坐标 = 局部坐标 × 缩放
            if 0 <= bx < img.width() and 0 <= by < img.height():
                values["color"] = img.pixelColor(bx, by).name().upper()
        self._restore()
        if values:
            self.picked_values.emit(values)

    def _restore(self) -> None:
        win = self._pick_main_win
        self._pick_main_win = None
        self._overlay = None
        self._pick_bg = None
        if win is not None and win is not self:
            try:
                if win.isMinimized():
                    win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
                win.raise_()
                win.activateWindow()
            except Exception:
                pass
