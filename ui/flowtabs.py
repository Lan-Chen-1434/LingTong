"""
流程标签页
============
「流程设计」面板顶部的多标签栏：一个标签 = 一个打开的流程。
支持点击切换、× / 中键关闭、双击重命名、未保存圆点标记；运行期间整体锁定。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QToolButton, QWidget)

from . import icons, theme


class FlowDoc:
    """一个打开的流程标签页：流程数据 + 画布视图状态。

    collapsed/scroll/selected 让切换标签时画布恢复原样（折叠状态、滚动位置、选中步骤）。
    """

    __slots__ = ("flow", "path", "dirty", "collapsed", "scroll", "selected")

    def __init__(self, flow, path=None) -> None:
        self.flow = flow
        self.path = path
        self.dirty = False
        self.collapsed: set = set()
        self.scroll: int = 0
        self.selected = None


class _Tab(QWidget):
    """单个标签：流程图标 + 名称 + 关闭按钮（VS Code 风格平铺条）。

    底色/圆弧全部在 paintEvent 里手写绘制——样式表背景在滚动视口场景下
    表现不稳定（某些启动顺序下完全不绘制），QPainter 直绘一画一个准。
    """

    clicked = Signal()
    close_requested = Signal()
    rename_requested = Signal()

    ARC = 10                          # 上缘圆弧半径（逻辑像素）
    WIDTH = 190                       # 标签固定宽度（逻辑像素）

    def paintEvent(self, e):                            # noqa: N802
        p = QPainter(self)
        r = self.rect()
        # 先整铺条底色：上缘圆弧的缺口、悬停底色都从这里透出来，
        # 也避免标签下方垫着系统默认底色在圆弧处透出异色
        p.fillRect(r, QColor(theme.TABSTRIP))
        if self._active:
            # 深色块只带上缘两角圆弧，下缘平直与画布衔接（VS Code 式按下去的效果）
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.CANVAS_BG))
            a = self.ARC
            x0, y0, x1, y1 = r.left(), r.top(), r.right() + 1, r.bottom() + 1
            path = QPainterPath()
            path.moveTo(x0, y1)
            path.lineTo(x0, y0 + a)
            path.quadTo(x0, y0, x0 + a, y0)
            path.lineTo(x1 - a, y0)
            path.quadTo(x1, y0, x1, y0 + a)
            path.lineTo(x1, y1)
            path.closeSubpath()
            p.drawPath(path)
        elif self._hovered:
            p.fillRect(r, QColor(255, 255, 255, 15))    # ≈ 条底 + 6% 白
        p.end()

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("FlowTab")
        self.setProperty("active", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(self.WIDTH)                  # 标签按钮统一宽度
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)  # 纵向填满整条标签栏
        self.setMinimumHeight(1)
        self._active = False
        self._dirty = False
        self._hovered = False
        self._text_w = self.WIDTH - 60                  # 标题省略宽度（扣图标/按钮/边距）

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 5, 0)
        lay.setSpacing(5)

        self.icon = QLabel()
        self.icon.setObjectName("FlowTabIcon")
        self.icon.setFixedSize(14, 14)
        self._icon_pm = icons.app_icon().pixmap(QSize(14, 14))  # 统一用程序主图标

        self.dot = QLabel("●")
        self.dot.setObjectName("FlowTabDot")
        self.dot.setFixedSize(13, 13)
        self.dot.hide()

        self.title = QLabel(title)
        self.title.setObjectName("FlowTabTitle")

        self.btn_close = QToolButton()
        self.btn_close.setObjectName("FlowTabClose")
        self.btn_close.setIcon(icons.glyph_icon("close", theme.TEXT_SUB, 11))
        self.btn_close.setFixedSize(18, 18)
        self.btn_close.setToolTip("关闭标签（也可用鼠标中键）")
        self.btn_close.clicked.connect(self.close_requested)

        lay.addWidget(self.icon)
        lay.addWidget(self.title)
        lay.addWidget(self.dot)
        lay.addWidget(self.btn_close)
        self._paint_icon()
        self._refresh_close()

    # ------------------------------------------------------------------
    def set_active(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", active)      # 对外状态标记（测试/调试可查）
        # 标题色内联（不依赖动态属性 QSS 的 polish 时机）；底色由 paintEvent 重绘
        self.title.setStyleSheet(
            f"color: {theme.TEXT if active else theme.TEXT_SUB};"
            f" background: transparent; border: none; font-size: 12px;")
        self._paint_icon()
        self._refresh_close()
        self.update()

    def _paint_icon(self) -> None:
        self.icon.setPixmap(self._icon_pm)

    def _refresh_close(self) -> None:
        """未保存圆点 vs 关闭按钮：
        未保存且未悬停且未激活 → 显示圆点；其余情况 × 常显。"""
        if self._dirty and not self._hovered and not self._active:
            self.dot.show()
            self.btn_close.hide()
        else:
            self.dot.hide()
            self.btn_close.show()

    def set_title(self, text: str) -> None:
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.title.font())
        self.title.setText(fm.elidedText(text, Qt.ElideMiddle, self._text_w))

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._refresh_close()

    def set_tip(self, tip: str) -> None:
        self.title.setToolTip(tip)

    # ------------------------------------------------------------------
    def mousePressEvent(self, e):                           # noqa: N802
        if e.button() == Qt.MiddleButton:
            self.close_requested.emit()                     # 中键关闭
            return
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):                     # noqa: N802
        if e.button() == Qt.LeftButton:
            self.rename_requested.emit()                    # 双击重命名
        super().mouseDoubleClickEvent(e)

    def enterEvent(self, e):                                # noqa: N802
        self._hovered = True
        self._refresh_close()                               # 悬停出 ×（圆点暂让位）
        self.update()                                       # 悬停底色由 paintEvent 画
        super().enterEvent(e)

    def leaveEvent(self, e):                                # noqa: N802
        self._hovered = False
        self._refresh_close()
        self.update()
        super().leaveEvent(e)


class FlowTabBar(QScrollArea):
    """横向可滚动的流程标签栏。"""

    tab_clicked = Signal(int)
    tab_close_clicked = Signal(int)
    tab_rename_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FlowTabBar")
        self.setFixedHeight(27)             # 条高 36 → 27（3/4），标签按钮纵向自动填满
        self.setFrameShape(QScrollArea.NoFrame)
        # VS Code 式：滚动条永不显示（点标签/滚轮自动滚动），避免滚动条抢占条高
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._locked = False

        self._box = QWidget()
        self._box.setMinimumHeight(25)      # 至少撑满条高，resizeEvent 里再精确对齐
        self._lay = QHBoxLayout(self._box)
        self._lay.setContentsMargins(6, 0, 6, 0)
        self._lay.setSpacing(0)                 # 标签平铺相邻，VS Code 式连续条
        self.setWidget(self._box)           # 不随视口拉伸，超出宽度出横向滚动条

        # 条底色由 eventFilter 在视口的 Paint 事件里直绘（QSS 背景在滚动视口
        # 场景 + 某些启动顺序下会整片不画，手写绘制保证任何环境都一致）
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, e):                          # noqa: N802
        if obj is self.viewport() and e.type() == QEvent.Paint:
            p = QPainter(self.viewport())
            p.fillRect(self.viewport().rect(), QColor(theme.TABSTRIP))
            p.end()
            return True                                     # 底色已画，跳过默认绘制
        return super().eventFilter(obj, e)

    def resizeEvent(self, e):                           # noqa: N802
        # QScrollArea 默认只把内容widget顶到视口宽度，纵向保持 sizeHint ——
        # 这里强制内容widget纵向填满整条标签栏，标签才能与条同高
        self._box.setMinimumHeight(self.viewport().height())
        super().resizeEvent(e)

    # ------------------------------------------------------------------
    def _tab(self, i: int) -> _Tab:
        return self._lay.itemAt(i).widget()

    def count(self) -> int:                                 # noqa: N802
        return self._lay.count()

    def add_tab(self, title: str) -> int:
        tab = _Tab(title)
        tab.set_title(title)
        idx = self._lay.count()
        self._lay.insertWidget(idx, tab)
        # 索引在信号发出时动态计算：关闭前置标签后不会错位
        tab.clicked.connect(
            lambda: None if self._locked
            else self.tab_clicked.emit(self._lay.indexOf(tab)))
        tab.close_requested.connect(
            lambda: None if self._locked
            else self.tab_close_clicked.emit(self._lay.indexOf(tab)))
        tab.rename_requested.connect(
            lambda: None if self._locked
            else self.tab_rename_requested.emit(self._lay.indexOf(tab)))
        self._sync_box()
        return idx

    def remove_tab(self, i: int) -> None:
        item = self._lay.takeAt(i)
        if item is not None and item.widget() is not None:
            item.widget().deleteLater()
        self._sync_box()

    def _sync_box(self) -> None:
        """按 标签数 × 固定宽 + 边距 精确同步内容 widget 的尺寸。

        不能用 adjustSize()/sizeHint：布局缓存会让新增标签立刻取到旧尺寸，
        内容 widget 宽度不足时 QHBoxLayout 会把标签压到最小宽以下摆放，
        而 setFixedWidth 又把宽度钳回 190 —— 两个标签就会重叠半个。
        """
        m = self._lay.contentsMargins()
        w = self._lay.count() * _Tab.WIDTH + m.left() + m.right()
        self._box.resize(w, self._box.height())

    def set_current(self, i: int) -> None:
        for n in range(self._lay.count()):
            w = self._lay.itemAt(n).widget()
            if isinstance(w, _Tab):
                w.set_active(n == i)
                if n == i:
                    try:
                        self.ensureWidgetVisible(w, 80, 0)
                    except Exception:
                        pass

    def set_title(self, i: int, title: str) -> None:
        self._tab(i).set_title(title)

    def set_dirty(self, i: int, dirty: bool) -> None:
        self._tab(i).set_dirty(dirty)

    def set_tip(self, i: int, tip: str) -> None:
        self._tab(i).set_tip(tip)

    # ------------------------------------------------------------------
    def set_locked(self, locked: bool) -> None:
        """运行期间锁定：禁止切换/关闭/重命名。"""
        self._locked = locked
        self.setCursor(Qt.ArrowCursor if locked else Qt.PointingHandCursor)
