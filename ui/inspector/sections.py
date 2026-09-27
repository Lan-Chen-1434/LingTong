"""可折叠分组容器。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget

from .. import icons, theme


class CollapsibleSection(QWidget):
    """带折叠箭头的参数分组，如「参数设置」「运行控制」。"""

    def __init__(self, title: str, expanded: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.expanded = expanded
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.btn = QToolButton()
        self.btn.setCheckable(True)
        self.btn.setChecked(expanded)
        self.btn.setText("  " + title)
        self.btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn.setIcon(icons.glyph_icon("chevron_down", theme.TEXT_SUB, 13, 2.0))
        self.btn.setAutoRaise(True)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet(
            f"QToolButton {{ color:{theme.TEXT}; font-size:12.5px; font-weight:700;"
            f"padding:4px 2px; border:none; background:transparent; }}")
        self.btn.clicked.connect(self._toggle)
        lay.addWidget(self.btn)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 0, 2, 0)
        self.content_layout.setSpacing(10)
        self.content.setVisible(expanded)
        lay.addWidget(self.content)

    def _toggle(self) -> None:
        self.expanded = self.btn.isChecked()
        self.content.setVisible(self.expanded)
        self.btn.setIcon(icons.glyph_icon(
            "chevron_down" if self.expanded else "chevron_right",
            theme.TEXT_SUB, 13, 2.0))
