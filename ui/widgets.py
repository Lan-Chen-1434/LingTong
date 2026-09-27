"""可复用界面组件：卡片面板、可拖拽模块项、标题栏等。"""
from __future__ import annotations

import re
from typing import Callable, List, Optional

from PySide6.QtCore import QMimeData, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QSizePolicy, QSpinBox, QVBoxLayout,
                               QWidget)

from . import icons, theme

MODULE_MIME = "application/x-lingtong-module"
NODE_MIME = "application/x-lingtong-node"


# ------------------------------------------------------------------ 提示气泡折行
def _disp_w(s: str) -> int:
    """字符串的显示宽度：中文/全角占 2，ASCII 占 1。"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


#: 提示文本分词：CJK/全角字符单独成 token，ASCII 按词（不含空格）、空白按段成 token
_TOOLTIP_TOKEN_RE = re.compile(r"[\u2E80-\uFFEF]|[^\s\u2E80-\uFFEF]+?(?=[\s\u2E80-\uFFEF]|$)|\s+")


def wrap_tooltip(text: str, max_w: int = 72) -> str:
    """按显示宽度给提示文本折行，防止 tooltip 过宽（Qt 不会自动折行）。

    折到约 360px 宽，优先在空格处断行、不拆开英文单词，超长代码片段才硬拆；
    高度由气泡随内容自适应。
    """
    out: List[str] = []
    for raw in str(text).split("\n"):
        tokens = _TOOLTIP_TOKEN_RE.findall(raw)
        cur, w = "", 0
        for tok in tokens:
            if tok.isspace():
                # 空格只填充行内，行尾/行首的空格直接跳过
                if cur and w + len(tok) <= max_w:
                    cur += tok
                    w += len(tok)
                continue
            tw = _disp_w(tok)
            if w + tw > max_w and cur:
                out.append(cur.rstrip())
                cur, w = tok, tw
                # 超长 ASCII 词（如代码片段）硬拆，不让它单独撑宽气泡
                while w > max_w:
                    cut = max_w
                    while _disp_w(tok[:cut]) > max_w:
                        cut -= 1
                    out.append(tok[:cut])
                    tok = tok[cut:]
                    cur, w = tok, _disp_w(tok)
            else:
                cur += tok
                w += tw
        out.append(cur.rstrip())
    return "\n".join(out)


# ------------------------------------------------------------------ 防误触滚轮控件
class NoWheelComboBox(QComboBox):
    """滚轮事件直接透传给父级滚动区——在参数面板上滚动时不会误改选项。"""

    def wheelEvent(self, e) -> None:                       # noqa: N802
        e.ignore()


class NoWheelSpinBox(QSpinBox):
    """滚轮事件透传：滚动面板时不会误改数值。"""

    def wheelEvent(self, e) -> None:                       # noqa: N802
        e.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """滚轮事件透传：滚动面板时不会误改数值。"""

    def wheelEvent(self, e) -> None:                       # noqa: N802
        e.ignore()


class Card(QFrame):
    """带标题的白色圆角面板。"""

    def __init__(self, title: str = "", hint: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        self.head = QWidget()
        self.head.setFixedHeight(40)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(14, 0, 10, 0)
        hl.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PanelTitle")
        hl.addWidget(self.title_label)
        hl.addStretch(1)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("PanelHint")
        hl.addWidget(self.hint_label)
        self.head_extra = hl
        self._outer.addWidget(self.head)

        line = QFrame()
        line.setObjectName("Divider")
        line.setFixedHeight(1)
        self._outer.addWidget(line)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(10, 8, 10, 10)
        self.body_layout.setSpacing(8)
        self._outer.addWidget(self.body, 1)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)

    def set_hint(self, text: str) -> None:
        self.hint_label.setText(text)


class ModuleChip(QWidget):
    """模块库中的一项：可拖拽到画布，也可双击直接追加。"""

    activated = Signal(str)          # 双击 → 追加到流程末尾
    drag_started = Signal()

    def __init__(self, type_id: str, name: str, desc: str, badge: str,
                 color: str, soft: str, glyph: str = "", parent=None) -> None:
        super().__init__(parent)
        self.type_id = type_id
        self.setFixedHeight(30)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(f"<b>{name}</b><br>{desc}<br><br>拖拽到右侧画布，或双击快速添加")
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._press: Optional[QPoint] = None
        self._badge = badge
        self._color = color
        self._soft = soft
        self._name = name

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(9)
        self.icon_label = QLabel()
        if glyph:
            self.icon_label.setPixmap(icons.ICON_CACHE.icon(glyph, color, soft, 20))
        else:
            self.icon_label.setPixmap(icons.BADGE_CACHE.badge(badge, color, soft, 20))
        self.icon_label.setFixedSize(20, 20)
        lay.addWidget(self.icon_label)
        self.text_label = QLabel(name)
        self.text_label.setStyleSheet(f"font-size: 12.5px; color: {theme.TEXT};")
        lay.addWidget(self.text_label, 1)

    # -------- 绘制 --------
    def enterEvent(self, e) -> None:                      # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:                      # noqa: N802
        self._hover = False
        self.update()

    def paintEvent(self, e) -> None:                      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._hover:
            p.setBrush(QBrush(QColor(theme.PRIMARY_SOFT)))
            p.setPen(QPen(QColor(theme.PRIMARY), 1))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 7, 7)
        p.end()

    # -------- 交互 --------
    def mousePressEvent(self, e) -> None:                 # noqa: N802
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()

    def mouseMoveEvent(self, e) -> None:                  # noqa: N802
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() < 8:
            return
        self._press = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MODULE_MIME, self.type_id.encode("utf-8"))
        mime.setText(f"LingTong:{self.type_id}")
        drag.setMimeData(mime)
        # 半透明幽灵卡片：截取自身并降低透明度
        pm = self.grab()
        ghost = QPixmap(pm.size())
        ghost.fill(Qt.transparent)
        gp = QPainter(ghost)
        gp.setOpacity(0.72)
        gp.drawPixmap(0, 0, pm)
        gp.end()
        drag.setPixmap(ghost)
        drag.setHotSpot(QPoint(int(ghost.width() / 2), 10))
        self.drag_started.emit()
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, e) -> None:               # noqa: N802
        self._press = None

    def mouseDoubleClickEvent(self, e) -> None:           # noqa: N802
        self.activated.emit(self.type_id)


class SearchBox(QWidget):
    """带图标与清除按钮的搜索框。"""

    changed = Signal(str)

    def __init__(self, placeholder: str = "搜索…", parent=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QLineEdit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(self.changed.emit)
        lay.addWidget(self.edit)

    def text(self) -> str:
        return self.edit.text()


class StatPill(QWidget):
    """状态小胶囊：图标 + 文字 + 颜色。"""

    def __init__(self, text: str, color: str, soft: str, glyph: str = "", parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 4, 11, 4)
        lay.setSpacing(5)
        if glyph:
            ic = QLabel()
            ic.setPixmap(icons.glyph_pixmap(glyph, color, 13, 1.7))
            lay.addWidget(ic)
        self.label = QLabel(text)
        self.label.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")
        lay.addWidget(self.label)
        self.setStyleSheet(
            f"background:{soft}; border-radius: 999px; border: 1px solid {color}22;")

    def set_text(self, text: str) -> None:
        self.label.setText(text)


class EmptyHint(QWidget):
    """空状态提示。"""

    def __init__(self, title: str, sub: str = "", parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 40, 20, 40)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:14px; font-weight:600;")
        lay.addWidget(t)
        if sub:
            s = QLabel(sub)
            s.setAlignment(Qt.AlignCenter)
            s.setWordWrap(True)
            s.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:12px;")
            lay.addWidget(s)
