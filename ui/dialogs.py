"""
对话框：屏幕抓图（取模板图）与快捷键录制。
"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QGuiApplication,
                           QKeySequence, QPainter, QPen, QPixmap)
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .widgets import NoWheelComboBox


class HotkeyEdit(QLineEdit):
    """点一下再按组合键，自动录成 "ctrl+shift+a"。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("点击后按下组合键，如 Ctrl+Shift+A")
        self.setClearButtonEnabled(True)

    def keyPressEvent(self, e) -> None:                   # noqa: N802
        k = e.key()
        if k in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
                 Qt.Key_unknown, Qt.Key_CapsLock):
            return
        if k in (Qt.Key_Backspace, Qt.Key_Delete):
            self.clear()
            return
        mods = e.modifiers()
        parts: List[str] = []
        if mods & Qt.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.AltModifier:
            parts.append("alt")
        if mods & Qt.ShiftModifier:
            parts.append("shift")
        if mods & Qt.MetaModifier:
            parts.append("win")
        seq = QKeySequence(k).toString().lower()
        if k == Qt.Key_Return or k == Qt.Key_Enter:
            seq = "enter"
        elif k == Qt.Key_Escape:
            seq = "esc"
        elif k == Qt.Key_Space:
            seq = "space"
        elif k == Qt.Key_Tab:
            seq = "tab"
        if seq and seq not in ("ctrl", "alt", "shift", "win"):
            parts.append(seq)
        self.setText("+".join(parts))
        e.accept()


class CountdownOverlay(QWidget):
    """抓图前的倒计时浮层：给用户留出切换窗口的时间。

    固定在屏幕顶部中央，顶层显示；点击立即开始，Esc 取消。
    """

    finished = Signal()
    cancelled = Signal()

    def __init__(self, seconds: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setFixedSize(300, 128)
        self._left = max(1, int(seconds))
        self._done = False

        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - 150, scr.top() + 60)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.show()
        self.raise_()
        self._timer.start(1000)

    def _finish(self, ok: bool) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.close()
        if ok:
            self.finished.emit()
        else:
            self.cancelled.emit()

    def _tick(self) -> None:
        self._left -= 1
        if self._left <= 0:
            self._finish(True)
        else:
            self.update()

    def keyPressEvent(self, e) -> None:                   # noqa: N802
        if e.key() == Qt.Key_Escape:
            self._finish(False)

    def mousePressEvent(self, e) -> None:                 # noqa: N802
        # 点击卡片 = 不等了，立即开始
        self._finish(True)

    def paintEvent(self, e) -> None:                      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        body = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(10, 16, 34, 235)))
        p.drawRoundedRect(body, 14, 14)
        p.setPen(QPen(QColor("#22D3EE"), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body, 14, 14)

        f = theme.font(34)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(QColor("#5EEAD4")))
        p.drawText(QRectF(0, 12, self.width(), 52), Qt.AlignCenter, str(self._left))

        p.setFont(theme.font(10))
        p.setPen(QPen(QColor("#AFC3EA")))
        p.drawText(QRectF(0, 70, self.width(), 20), Qt.AlignCenter,
                   "即将开始框选，请切换到目标窗口")
        p.setPen(QPen(QColor(120, 140, 190, 150)))
        p.setFont(theme.font(8))
        p.drawText(QRectF(0, 94, self.width(), 18), Qt.AlignCenter,
                   "点击此卡片立即开始 · Esc 取消")
        p.end()


class CaptureOverlay(QWidget):
    """全屏选框，用来截取一块屏幕区域当模板图。

    底图在 show() **之前**由 grab_virtual_screen() 用 Qt 原生抓屏合成，
    避免抓到选框自己，也绕开 ImageGrab 在部分机器上失效的问题。
    """

    captured = Signal(QRect)          # 选框局部坐标（相对本窗口）
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        # 覆盖整个虚拟桌面
        geo = QRect()
        for sc in QGuiApplication.screens():
            geo = geo.united(sc.geometry())
        self._origin = geo.topLeft()
        self.setGeometry(geo)

        self._bg: Optional[QPixmap] = None
        self._scale = 1.0             # 底图物理像素 / 窗口逻辑像素
        self._start: Optional[QPoint] = None
        self._cur: Optional[QPoint] = None
        self._sel: Optional[QRect] = None

    # ------------------------------------------------------------ 底图
    @staticmethod
    def grab_virtual_screen():
        """用 Qt 抓全部屏幕并合成一张物理像素的底图。返回 (QPixmap, scale)。"""
        screens = QGuiApplication.screens()
        if not screens:
            return None, 1.0
        geo = QRect()
        for sc in screens:
            geo = geo.united(sc.geometry())
        dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        w = max(1, int(geo.width() * dpr))
        h = max(1, int(geo.height() * dpr))
        result = QPixmap(w, h)
        result.fill(QColor(8, 12, 24))
        p = QPainter(result)
        for sc in screens:
            pm = sc.grabWindow(0)
            g = sc.geometry()
            p.drawPixmap(QRect(int((g.x() - geo.x()) * dpr),
                               int((g.y() - geo.y()) * dpr),
                               int(g.width() * dpr), int(g.height() * dpr)), pm)
        p.end()
        return result, dpr

    def set_background(self, pixmap: Optional[QPixmap], scale: float = 1.0) -> None:
        self._bg = pixmap
        self._scale = scale or 1.0

    def crop_pixmap(self, sel_local: QRect) -> Optional[QPixmap]:
        """按窗口局部坐标从底图裁出物理像素的选中区域。"""
        if self._bg is None:
            return None
        s = self._scale
        phys = QRect(int(sel_local.x() * s), int(sel_local.y() * s),
                     int(sel_local.width() * s), int(sel_local.height() * s))
        return self._bg.copy(phys)

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, e) -> None:                      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        full = self.rect()
        if self._bg is not None:
            p.drawPixmap(full, self._bg)
        p.fillRect(full, QColor(15, 22, 36, 110))

        sel = self._current_sel()
        if sel and sel.width() > 0 and sel.height() > 0:
            if self._bg is not None:
                src = QRect(int(sel.x() * self._scale), int(sel.y() * self._scale),
                            int(sel.width() * self._scale), int(sel.height() * self._scale))
                p.drawPixmap(sel, self._bg, src)
            p.setPen(QPen(QColor(theme.PRIMARY), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sel)
            # 角标
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(theme.PRIMARY)))
            for corner in (sel.topLeft(), sel.topRight(), sel.bottomLeft(), sel.bottomRight()):
                p.drawEllipse(QRectF(corner.x() - 3.5, corner.y() - 3.5, 7, 7))
            # 尺寸提示
            tip = f"{sel.width()} × {sel.height()}   ({sel.x() + self._origin.x()}, {sel.y() + self._origin.y()})"
            f = theme.font(9)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(tip) + 18
            ty = sel.top() - 30 if sel.top() > 40 else sel.bottom() + 8
            tx = min(max(6, sel.left()), self.width() - tw - 6)
            p.setBrush(QBrush(QColor(30, 40, 58, 235)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(tx, ty, tw, 24), 6, 6)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(QRectF(tx, ty, tw, 24), Qt.AlignCenter, tip)
        else:
            guide = ("拖动鼠标框选要识别的界面元素     ·     "
                     "Esc 取消     ·     框得越紧凑，识别越准")
            f = theme.font(11)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(guide) + 44
            box = QRectF((self.width() - tw) / 2, 42, tw, 44)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(20, 28, 44, 235)))
            p.drawRoundedRect(box, 10, 10)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(box, Qt.AlignCenter, guide)

        # 十字准线
        if self._cur and not sel:
            p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
            p.drawLine(0, self._cur.y(), self.width(), self._cur.y())
            p.drawLine(self._cur.x(), 0, self._cur.x(), self.height())
        p.end()

    def _current_sel(self) -> Optional[QRect]:
        if self._start is None or self._cur is None:
            return None
        return QRect(self._start, self._cur).normalized()

    # ------------------------------------------------------------ 事件
    def mousePressEvent(self, e) -> None:                 # noqa: N802
        if e.button() == Qt.LeftButton:
            self._start = e.position().toPoint()
            self._cur = self._start
            self.update()

    def mouseMoveEvent(self, e) -> None:                  # noqa: N802
        self._cur = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, e) -> None:               # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        sel = self._current_sel()
        if sel is None or sel.width() < 4 or sel.height() < 4:
            self._start = self._cur = None
            self.update()
            return
        self.captured.emit(sel)          # 发送窗口局部坐标，由对话框从底图裁切
        self.close()

    def keyPressEvent(self, e) -> None:                   # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()


class PointPickOverlay(CaptureOverlay):
    """全屏单击取点：交互参考框选区域，但只取一个点而不是拖框。

    点击左键即拾取并发出 picked（窗口局部逻辑坐标），Esc 取消。
    """

    picked = Signal(QPoint)

    def paintEvent(self, e) -> None:                      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        full = self.rect()
        if self._bg is not None:
            p.drawPixmap(full, self._bg)
        p.fillRect(full, QColor(15, 22, 36, 110))

        if self._cur is not None:
            cur = self._cur
            # 十字准线
            p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
            p.drawLine(0, cur.y(), self.width(), cur.y())
            p.drawLine(cur.x(), 0, cur.x(), self.height())
            # 准星圆点
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(theme.PRIMARY)))
            p.drawEllipse(QRectF(cur.x() - 3.5, cur.y() - 3.5, 7, 7))
            # 跟随光标的坐标气泡
            tip = (f"({cur.x() + self._origin.x()}, {cur.y() + self._origin.y()})"
                   f"    单击拾取 · Esc 取消")
            f = theme.font(10)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(tip) + 28
            tx = min(max(6, cur.x() + 18), self.width() - tw - 6)
            ty = cur.y() - 46 if cur.y() > 64 else cur.y() + 22
            p.setBrush(QBrush(QColor(20, 28, 44, 235)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(tx, ty, tw, 30), 8, 8)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(QRectF(tx, ty, tw, 30), Qt.AlignCenter, tip)
        else:
            guide = "把鼠标移到目标位置，单击拾取坐标     ·     Esc 取消"
            f = theme.font(11)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(guide) + 44
            box = QRectF((self.width() - tw) / 2, 42, tw, 44)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(20, 28, 44, 235)))
            p.drawRoundedRect(box, 10, 10)
            p.setPen(QPen(QColor("#FFFFFF")))
            p.drawText(box, Qt.AlignCenter, guide)
        p.end()

    def mousePressEvent(self, e) -> None:                 # noqa: N802
        if e.button() == Qt.LeftButton:
            self.picked.emit(e.position().toPoint())
            self.close()

    def mouseReleaseEvent(self, e) -> None:               # noqa: N802
        pass

    def _current_sel(self):                               # noqa: N802
        return None


class RegionCaptureDialog(QDialog):
    """抓图对话框：框选 → 预览 → 保存为模板图。

    注意：本对话框必须以非模态（open() + WindowModal）方式打开，
    因为抓图时的全屏选框是独立顶层窗口，模态 exec() 会拦截它的鼠标输入。
    """

    def __init__(self, out_dir: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("抓图取图 · 从屏幕截取模板图")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(430)
        self.out_dir = out_dir
        self.saved_path: Optional[str] = None
        self._rect: Optional[QRect] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        title = QLabel("从屏幕上框选要识别的元素")
        title.setStyleSheet(f"font-size:14px; font-weight:700; color:{theme.TEXT};")
        lay.addWidget(title)
        tip = QLabel("点「开始框选」后屏幕会变暗，按住左键拖出矩形即可。"
                     "建议只框住按钮或图标本身，不要带太多背景，识别会更稳定。")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:12px;")
        lay.addWidget(tip)

        self.preview = QLabel("尚未框选")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(128)
        self.preview.setStyleSheet(
            f"border:1px dashed {theme.BORDER_STRONG}; border-radius:8px;"
            f"background:{theme.PANEL_SOFT}; color:{theme.TEXT_MUTED}; font-size:12px;")
        lay.addWidget(self.preview)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_capture = QPushButton("  开始框选")
        self.btn_capture.setObjectName("Primary")
        self.btn_capture.setIcon(icons.glyph_icon("crosshair", "#FFFFFF", 16))
        self.btn_capture.clicked.connect(self._capture)
        row.addWidget(self.btn_capture)
        self.btn_browse = QPushButton("  也可以选已有图片")
        self.btn_browse.setIcon(icons.glyph_icon("open", theme.TEXT_SUB, 16))
        self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.btn_browse)
        row.addStretch(1)
        lay.addLayout(row)

        # 倒计时选择：留出切换窗口的时间
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lb = QLabel("开始方式")
        lb.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:12px;")
        row2.addWidget(lb)
        self.delay_combo = NoWheelComboBox()
        self.delay_combo.addItem("立即框选", 0)
        self.delay_combo.addItem("3 秒后框选（可切换窗口）", 3)
        self.delay_combo.addItem("5 秒后框选（可切换窗口）", 5)
        self.delay_combo.addItem("10 秒后框选（可切换窗口）", 10)
        self.delay_combo.setCurrentIndex(2)          # 默认 5 秒
        self.delay_combo.setToolTip("选择倒计时时长：倒计时期间你可以 Alt+Tab 切到目标窗口，"
                                    "倒计时结束后屏幕变暗进入框选")
        row2.addWidget(self.delay_combo, 1)
        lay.addLayout(row2)

        lay.addWidget(self._hint("保存后的文件会追加到该步骤的模板图列表里；"
                                 "同一步骤可以放多张图，命中任意一张即可。"))

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton("使用这张图")
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        lay.addLayout(btns)

        # 延迟到窗口显示后再隐藏自己，避免遮住截图
        self._pending: Optional[QRect] = None

    def _hint(self, text: str) -> QLabel:
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11.5px;")
        return lb

    def _capture(self) -> None:
        delay = int(self.delay_combo.currentData() or 0)
        # 先把本工具最小化，用户可以直接对着目标窗口框选
        self._main_win = self.window()
        if self._main_win is not None and self._main_win is not self:
            self._main_win.showMinimized()
        self.hide()
        from PySide6.QtCore import QTimer
        if delay <= 0:
            QTimer.singleShot(260, self._do_capture)
            return
        # 倒计时模式：先显示倒计时浮层，期间用户可切换到目标窗口
        self._cd = CountdownOverlay(delay, self)
        self._cd.finished.connect(self._do_capture)
        self._cd.cancelled.connect(self._on_cancel)
        self._cd.start()

    def _restore_main_window(self) -> None:
        win = getattr(self, "_main_win", None)
        if win is not None and win is not self:
            try:
                # 只清除最小化位：最大化/普通尺寸都保持原状
                if win.isMinimized():
                    win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
                win.raise_()
                win.activateWindow()
            except Exception:
                pass

    def _do_capture(self) -> None:
        self.overlay = CaptureOverlay()
        # 先抓屏再显示选框：避免抓到选框自己，且绕开 ImageGrab 失效的环境
        bg, scale = CaptureOverlay.grab_virtual_screen()
        self.overlay.set_background(bg, scale)
        self.overlay.captured.connect(self._on_captured)
        self.overlay.cancelled.connect(self._on_cancel)
        # 用 show() 而不是 showFullScreen()：多显示器时保持跨屏几何不变形
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        self.overlay.setFocus(Qt.OtherFocusReason)   # 让 Esc 能取消

    def _on_cancel(self) -> None:
        self._restore_main_window()
        self.show()
        self.raise_()

    def _on_captured(self, rect: QRect) -> None:
        """rect 为选框局部坐标；直接从选框底图裁切，所见即所得。"""
        self._rect = rect
        os.makedirs(self.out_dir, exist_ok=True)
        import time
        name = f"tpl_{time.strftime('%m%d_%H%M%S')}_{rect.width()}x{rect.height()}.png"
        path = os.path.join(self.out_dir, name)
        crop = self.overlay.crop_pixmap(rect)
        ok = crop is not None and crop.save(path, "PNG")
        self._restore_main_window()
        self.show()
        self.raise_()
        self.activateWindow()
        if not ok:
            QMessageBox.warning(self, "抓图失败", "截图保存失败，请重试。")
            return
        self.saved_path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self.preview.setPixmap(pm.scaled(400, 120, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
            self.preview.setStyleSheet(
                f"border:1px solid {theme.BORDER}; border-radius:8px;"
                f"background:{theme.PANEL_SOFT};")
        self.btn_ok.setEnabled(True)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择模板图片", self.out_dir,
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        self.saved_path = path
        pm = QPixmap(path)
        if not pm.isNull():
            self.preview.setPixmap(pm.scaled(400, 120, Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
        self.btn_ok.setEnabled(True)
