"""
示例流程弹出面板
==================
替代原生 QMenu 的长列表：按分类分组 + 顶部搜索过滤 + 固定尺寸滚动，
悬停每条示例显示说明（description），点击载入。

分组规则：名字里第一个 "-" 之前是分类（如「鼠标操作-鼠标点击」）；
"01-" 开头的归为「入门示例」（显示时去掉数字前缀）。
"""
from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QVBoxLayout, QWidget)

from core import samples
from core.registry import CATEGORY_STYLE

from . import icons, theme

Item = Tuple[str, str, str]          # (文件路径, 名称, 描述)


def _split_group(name: str) -> Tuple[str, str]:
    """示例名 → (分组, 显示名)。"""
    if name[:2].isdigit() and len(name) > 3 and name[2] == "-":
        return "入门示例", name[3:]
    if "-" in name:
        g, _, rest = name.partition("-")
        return g, rest
    return "其他", name


def _group_style(group: str) -> Tuple[str, str, str]:
    """分组名 → (主色, 浅色底, 图标名)，与左侧模块面板用的分类配色一致。

    「入门示例」没有对应分类，单独用主题主色（贾维斯青）+ 播放图标。
    """
    if group == "入门示例":
        return theme.PRIMARY, "#0A2A33", "play"
    return (theme.cat_color(group), theme.cat_soft(group),
            CATEGORY_STYLE.get(group, {}).get("glyph", "list"))


class _ItemRow(QFrame):
    """一条示例：分类图标 + 分类色的名称，说明走悬停提示，悬停高亮，点击选中。"""

    clicked = Signal(str)

    def __init__(self, path: str, text: str, desc: str,
                 color: str, soft: str, glyph: str, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame {{ background:transparent; border-radius:5px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 10, 4)
        lay.setSpacing(8)

        icon = QLabel()
        icon.setPixmap(icons.app_icon().pixmap(QSize(16, 16)))   # 统一用程序主图标
        icon.setFixedSize(16, 16)
        lay.addWidget(icon)

        name = QLabel(text)
        name.setStyleSheet(f"color:{theme.TEXT}; font-size:12.5px;")
        lay.addWidget(name, 1)
        if desc:
            self.setToolTip(desc)

    def enterEvent(self, e) -> None:                        # noqa: N802
        self.setStyleSheet(
            f"QFrame {{ background:{theme.PANEL_HOVER}; border-radius:5px; }}")
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:                        # noqa: N802
        self.setStyleSheet(
            f"QFrame {{ background:transparent; border-radius:5px; }}")
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:                   # noqa: N802
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.path)
        super().mousePressEvent(e)


class SamplesPopup(QWidget):
    """示例流程选择面板（Qt.Popup：点外部自动关闭）。"""

    selected = Signal(str)               # 示例文件路径；samples.BLANK = 空白流程

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget {{ background:{theme.PANEL}; border:1px solid {theme.BORDER_STRONG};"
            f" border-radius:10px; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索示例…（如：循环、剪贴板、图像）")
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(
            f"QLineEdit {{ background:{theme.PANEL_SOFT}; border:1px solid {theme.BORDER};"
            f" border-radius:6px; padding:6px 9px; color:{theme.TEXT}; font-size:12.5px; }}")
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background:transparent; }")
        self.body = QWidget()
        self.body.setStyleSheet("background:transparent;")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 2, 6, 2)
        self.body_layout.setSpacing(2)
        self.body_layout.addStretch(1)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)

        self.setFixedSize(440, 400)
        self._rows: List[Tuple[_ItemRow, str, str, str]] = []   # (row, group, text, desc)
        self._groups: List[Tuple[QLabel, QWidget, QVBoxLayout]] = []

    # ------------------------------------------------------------------
    def reload(self) -> None:
        """每次打开前刷新：重新扫描 examples/ 并重建列表。"""
        for row, *_ in self._rows:
            row.setParent(None)
            row.deleteLater()
        for title, box, _ in self._groups:
            title.setParent(None)
            title.deleteLater()
            box.setParent(None)
            box.deleteLater()
        self._rows.clear()
        self._groups.clear()

        items = samples.list_examples()
        groups: dict = {}
        for path, name, desc in items:
            group, text = _split_group(name)
            if group not in groups:
                groups[group] = []
            groups[group].append((path, text, desc))

        for group in groups:
            color, soft, glyph = _group_style(group)
            title = QLabel(group)
            title.setStyleSheet(
                f"color:{theme.TEXT}; font-size:13px; font-weight:700;"
                f"padding:9px 4px 2px 4px;")
            box = QWidget()
            box.setStyleSheet("background:transparent;")
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(1)
            # 插入到 stretch 之前
            self.body_layout.insertWidget(self.body_layout.count() - 1, title)
            self.body_layout.insertWidget(self.body_layout.count() - 1, box)
            self._groups.append((title, box, lay))
            for path, text, desc in groups[group]:
                row = _ItemRow(path, text, desc, color, soft, glyph)
                row.clicked.connect(self._pick)
                lay.addWidget(row)
                self._rows.append((row, group, text, desc))

        # 空白流程固定垫底（中性灰）
        b_color, b_soft, b_glyph = _group_style("")
        blank = _ItemRow(samples.BLANK, "空白流程", "从零开始搭自己的流程",
                         b_color, b_soft, b_glyph)
        blank.clicked.connect(self._pick)
        self.body_layout.insertWidget(self.body_layout.count() - 1, blank)
        self._rows.append((blank, "", "空白流程", ""))

        self.search.clear()
        self._apply_filter("")

    # ------------------------------------------------------------------
    def _pick(self, path: str) -> None:
        self.selected.emit(path)
        self.close()

    def _apply_filter(self, text: str) -> None:
        kw = text.strip().lower()
        visible_groups = set()
        for row, group, name, desc in self._rows:
            hit = (not kw or kw in name.lower() or kw in desc.lower()
                   or kw in group.lower())
            row.setVisible(hit)
            if hit:
                visible_groups.add(group)
        for title, box, _ in self._groups:
            show = title.text() in visible_groups
            title.setVisible(show)
            box.setVisible(show)

    def show_at(self, anchor: QWidget) -> None:
        """在 anchor 按钮下方弹出并聚焦搜索框。"""
        self.reload()
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        # 防止超出屏幕右/下边缘
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        rect = screen.availableGeometry()
        x = min(pos.x(), rect.right() - self.width() - 8)
        y = min(pos.y() + 4, rect.bottom() - self.height() - 8)
        self.move(max(rect.left() + 8, x), max(rect.top() + 8, y))
        self.show()
        self.search.setFocus()
