"""
顶部控制条
============
文件操作 / 示例菜单 / 拾取坐标 / 运行控制按钮（统一尺寸的胶囊按钮组）。
流程本身在「流程设计」面板的标签页里管理（见 ui/flowtabs.py）。
用信号与主窗口解耦：主窗口只需 connect 这些信号，不用关心内部怎么排布。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPushButton, QWidget)

from . import icons, theme
from .samples_popup import SamplesPopup

BTN_W, BTN_H = 100, 32          # 全部按钮统一尺寸（逻辑像素）


def _vline() -> QFrame:
    f = QFrame()
    f.setObjectName("VDivider")
    f.setFixedWidth(1)
    f.setFixedHeight(24)
    return f


class TopBar(QWidget):
    """主窗口顶部控制条。"""

    new_clicked = Signal()
    open_clicked = Signal()
    save_clicked = Signal()
    save_as_clicked = Signal()
    sample_selected = Signal(str)          # 参数为示例文件路径；samples.BLANK = 空白流程
    run_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    pick_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(9)

        # ---- 文件操作 ----
        self.btn_new = self._btn("新建", "new", self.new_clicked)
        self.btn_open = self._btn("打开", "open", self.open_clicked)
        self.btn_save = self._btn("保存", "save", self.save_clicked)
        self.btn_save_as = self._btn("另存", "saveas", self.save_as_clicked)
        self.btn_samples = self._btn("示例流程", "list", None)
        for b in (self.btn_new, self.btn_open, self.btn_save,
                  self.btn_save_as, self.btn_samples):
            lay.addWidget(b)

        # 自定义弹出面板：分组 + 搜索，代替原生长菜单
        self._samples_popup = SamplesPopup(self)
        self._samples_popup.selected.connect(self.sample_selected)
        self.btn_samples.clicked.connect(
            lambda: self._samples_popup.show_at(self.btn_samples))

        lay.addStretch(1)

        # ---- 工具 ----
        self.btn_pick = self._btn("拾取坐标", "crosshair", self.pick_clicked,
                                  obj="TopPick", icon_color="#37CBE9")
        self.btn_pick.setToolTip("倒计时后全屏单击取点，坐标自动复制到剪贴板")
        lay.addWidget(self.btn_pick)

        lay.addWidget(_vline())

        # ---- 运行控制 ----
        self.btn_run = self._btn("运行", "play", self.run_clicked,
                                 obj="TopRun", icon_color="#032530")
        self.btn_pause = self._btn("暂停", "pause", self.pause_clicked,
                                   icon_color=theme.TEXT_SUB)
        self.btn_pause.setEnabled(False)
        self.btn_stop = self._btn("停止", "stop", self.stop_clicked,
                                  obj="TopStop", icon_color="#FF7B6E")
        self.btn_stop.setEnabled(False)
        for b in (self.btn_run, self.btn_pause, self.btn_stop):
            lay.addWidget(b)

    # ------------------------------------------------------------------
    def _btn(self, text: str, glyph: str, signal, obj: str = "TopBtn",
             icon_color: str = None) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName(obj)
        b.setIcon(icons.glyph_icon(glyph, icon_color or theme.TEXT_SUB, 15))
        b.setIconSize(QSize(15, 15))
        b.setFixedSize(BTN_W, BTN_H)                # 长宽统一
        b.setCursor(Qt.PointingHandCursor)
        if signal is not None:
            b.clicked.connect(signal.emit)
        return b

    # ------------------------------------------------------------------ 外部状态
    def set_running(self, running: bool) -> None:
        """切换运行态下按钮可用性。"""
        self.btn_run.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_pause.setEnabled(running)
        self.btn_new.setEnabled(not running)
        self.btn_open.setEnabled(not running)
        self.btn_samples.setEnabled(not running)

    def set_paused(self, paused: bool) -> None:
        self.btn_pause.setText("继续" if paused else "暂停")
        self.btn_pause.setIcon(icons.glyph_icon(
            "play" if paused else "pause", theme.TEXT_SUB, 15))
