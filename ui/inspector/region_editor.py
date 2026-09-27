"""
屏幕区域编辑器
================
P_REGION 参数类型的编辑控件：

* X / Y / 宽 / 高 四个数字框分开填写（可手动输入，也可用变量）；
* 「框选区域」按钮：先倒计时（给用户切换窗口的反应时间），
  再全屏框选，松手后自动回填四个数字——与「图像点击」的抓图取图同一套机制。

存储格式仍是 "x,y,w,h" 字符串（空 = 全屏），运行时 parse_region 无需改动。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .. import icons, theme
from ..dialogs import CaptureOverlay, CountdownOverlay
from ..widgets import NoWheelComboBox, NoWheelSpinBox


def _fmt(x: int, y: int, w: int, h: int) -> str:
    return f"{x},{y},{w},{h}"


def _parse(text) -> Optional[tuple]:
    try:
        parts = str(text or "").replace("，", ",").replace(" ", "").split(",")
        if len(parts) != 4:
            return None
        x, y, w, h = (int(float(p)) for p in parts)
        return x, y, w, h
    except (TypeError, ValueError):
        return None


class RegionEditor(QWidget):
    """X/Y/宽/高 四栏 + 框选按钮。"""

    changed = Signal()

    def __init__(self, allow_empty: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.allow_empty = allow_empty
        self._overlay: Optional[CaptureOverlay] = None
        self._countdown: Optional[CountdownOverlay] = None
        self._main_win = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        if allow_empty:
            self.chk = QCheckBox("限定屏幕区域（不勾 = 全屏）")
            self.chk.setStyleSheet(f"color:{theme.TEXT}; font-size:12px;")
            self.chk.toggled.connect(self._on_toggle)
            lay.addWidget(self.chk)
        else:
            self.chk = None

        # ---- 四栏数字（竖排） ----
        self.box = QWidget()
        grid = QVBoxLayout(self.box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        self.spins = {}
        for key, label, lo in (("x", "X", -20000), ("y", "Y", -20000),
                               ("w", "宽", 0), ("h", "高", 0)):
            row = QHBoxLayout()
            row.setSpacing(8)
            lb = QLabel(label)
            lb.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:12px;")
            lb.setFixedWidth(24)
            row.addWidget(lb)
            sp = NoWheelSpinBox()
            sp.setRange(lo, 20000)
            sp.valueChanged.connect(self._on_spin)
            row.addWidget(sp, 1)
            grid.addLayout(row)
            self.spins[key] = sp
        lay.addWidget(self.box)

        # ---- 框选行 ----
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_pick = QPushButton("  框选区域")
        self.btn_pick.setObjectName("Primary")
        self.btn_pick.setIcon(icons.glyph_icon("crosshair", "#FFFFFF", 15))
        self.btn_pick.setCursor(Qt.PointingHandCursor)
        self.btn_pick.setToolTip("点击后先倒计时，屏幕变暗后按住左键拖出矩形，自动填入 X/Y/宽/高")
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        self.delay_combo = NoWheelComboBox()
        self.delay_combo.addItem("立即框选", 0)
        self.delay_combo.addItem("3 秒后框选", 3)
        self.delay_combo.addItem("5 秒后框选", 5)
        self.delay_combo.addItem("10 秒后框选", 10)
        self.delay_combo.setCurrentIndex(1)      # 默认 3 秒，留出反应时间
        self.delay_combo.setToolTip("倒计时期间可切换到目标窗口，结束后再开始框选")
        row.addWidget(self.delay_combo, 1)
        lay.addLayout(row)

        self._on_toggle()

    # ------------------------------------------------------------ 读写
    def value(self) -> str:
        if self.chk is not None and not self.chk.isChecked():
            return ""
        return _fmt(self.spins["x"].value(), self.spins["y"].value(),
                    self.spins["w"].value(), self.spins["h"].value())

    def set_value(self, text) -> None:
        r = _parse(text)
        if r is None and not self.allow_empty:
            # 必填区域但没有合法值：默认给主屏大小，避免 0×0 运行报错
            scr = QGuiApplication.primaryScreen()
            if scr is not None:
                dpr = scr.devicePixelRatio()
                g = scr.geometry()
                r = (int(g.x() * dpr), int(g.y() * dpr),
                     int(g.width() * dpr), int(g.height() * dpr))
        for sp in self.spins.values():
            sp.blockSignals(True)
        if r is None:
            for k in ("x", "y", "w", "h"):
                self.spins[k].setValue(0)
            if self.chk is not None:
                self.chk.setChecked(False)
        else:
            x, y, w, h = r
            self.spins["x"].setValue(x)
            self.spins["y"].setValue(y)
            self.spins["w"].setValue(w)
            self.spins["h"].setValue(h)
            if self.chk is not None:
                self.chk.setChecked(True)
        for sp in self.spins.values():
            sp.blockSignals(False)
        self._on_toggle()

    # ------------------------------------------------------------ 内部
    def _on_toggle(self) -> None:
        on = self.chk.isChecked() if self.chk is not None else True
        self.box.setEnabled(on)
        self.btn_pick.setEnabled(on)
        self.delay_combo.setEnabled(on)
        self.changed.emit()

    def _on_spin(self) -> None:
        self.changed.emit()

    # ------------------------------------------------------------ 框选
    def _pick(self) -> None:
        """最小化主窗口 → 倒计时（可选）→ 全屏框选 → 回填四栏。"""
        delay = int(self.delay_combo.currentData() or 0)
        self._main_win = self.window()
        if self._main_win is not None and self._main_win is not self:
            self._main_win.showMinimized()
        if delay <= 0:
            QTimer.singleShot(260, self._do_pick)
            return
        self._countdown = CountdownOverlay(delay)
        self._countdown.finished.connect(self._do_pick)
        self._countdown.cancelled.connect(self._restore)
        self._countdown.start()

    def _do_pick(self) -> None:
        self._overlay = CaptureOverlay()
        bg, scale = CaptureOverlay.grab_virtual_screen()
        self._overlay.set_background(bg, scale)
        self._overlay.captured.connect(self._on_picked)
        self._overlay.cancelled.connect(self._restore)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()
        self._overlay.setFocus(Qt.OtherFocusReason)

    def _on_picked(self, rect) -> None:
        """rect 为选框局部逻辑坐标；换算成屏幕物理像素后回填。"""
        s = self._overlay._scale if self._overlay is not None else 1.0
        o = self._overlay._origin if self._overlay is not None else None
        ox, oy = (o.x(), o.y()) if o is not None else (0, 0)
        x = int((rect.x() + ox) * s)
        y = int((rect.y() + oy) * s)
        w = int(rect.width() * s)
        h = int(rect.height() * s)
        if self.chk is not None:
            self.chk.setChecked(True)
        for sp in self.spins.values():
            sp.blockSignals(True)
        self.spins["x"].setValue(x)
        self.spins["y"].setValue(y)
        self.spins["w"].setValue(w)
        self.spins["h"].setValue(h)
        for sp in self.spins.values():
            sp.blockSignals(False)
        self._restore()
        self.changed.emit()

    def _restore(self) -> None:
        win = self._main_win
        self._main_win = None
        if win is not None and win is not self:
            try:
                # 只清除最小化位：最大化/普通尺寸都保持原状
                if win.isMinimized():
                    win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
                win.raise_()
                win.activateWindow()
            except Exception:
                pass
