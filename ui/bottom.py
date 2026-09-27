"""
底部信息面板
==============
三个标签页：运行日志（带级别配色）、抓取到的数据表、运行期变量快照。
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from . import icons, theme

LEVEL_STYLE = {
    "info": ("#8B98A9", "·"),
    "ok": (theme.OK, "✔"),
    "warn": (theme.WARN, "▲"),
    "error": (theme.ERR, "✖"),
    "debug": ("#5C6B7E", "·"),
}

# 消息文本里自带的装饰性 emoji（🪟📋⏱🎨⌨⚠✔…）：
# 行首已有级别标记 + 配色，再叠 emoji 会显得一行多个图标，渲染时剥掉行首的
_EMOJI_HEAD = re.compile(
    "[\U0001F000-\U0001FAFF"      # 表情与杂项符号
    "\U00002600-\U000027BF"       # 杂项符号 + Dingbats（⚠✔✖⟳…）
    "\U00002500-\U000025FF"       # 几何图形（▶◆●…）
    "\U000027C0-\U000027FF"       # 补充箭头 A（⟳…）
    "\U00002900-\U000029FF"       # 补充箭头 B（⤳…）
    "\U00002300-\U000023FF"       # 杂项技术符号（⌨⏱⏳…）
    "\U00002190-\U000021FF"       # 箭头（↻）
    "\U00002B00-\U00002BFF"       # 箭头扩展（⤴）
    "\U0000FE0F]"                 # 变体选择符
)


def _strip_emoji(text: str) -> str:
    """去掉行首连续的装饰性 emoji 及其后的空白，只留正文。"""
    while True:
        text = text.lstrip()
        m = _EMOJI_HEAD.match(text)
        if not m:
            return text
        text = text[m.end():]


class Console(QWidget):
    """运行日志控制台。

    高频日志先进入队列，由 80ms 定时器批量写入——
    循环上千步时界面也不会因为逐行刷新而卡顿。
    """

    FLUSH_MS = 80
    MAX_PER_FLUSH = 240

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet(f"background:{theme.PANEL}; border-bottom:1px solid {theme.BORDER};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 0, 8, 0)
        h.setSpacing(6)
        self.stat = QLabel("就绪")
        self.stat.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11.5px;")
        h.addWidget(self.stat)
        h.addStretch(1)
        for text, slot in (("清空", self.clear),):
            b = QPushButton(text)
            b.setObjectName("Ghost")
            b.setStyleSheet(f"font-size:11.5px; color:{theme.TEXT_SUB}; padding:3px 8px;")
            b.clicked.connect(slot)
            h.addWidget(b)
        lay.addWidget(bar)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setObjectName("Console")
        self.view.setFont(QFont("Cascadia Mono", 9))
        self.view.document().setMaximumBlockCount(1500)
        self.view.setStyleSheet(
            f"QTextEdit#Console {{ background:#0B0F16; border:none; padding:6px 4px; }}")
        lay.addWidget(self.view, 1)

        self._count = 0
        self._queue: list = []
        from PySide6.QtCore import QTimer
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush)

    # ------------------------------------------------------------ 写入
    def append(self, level: str, message: str) -> None:
        """入队（线程安全由信号队列保证），随后批量刷新。"""
        self._queue.append((level, message))
        if not self._flush_timer.isActive():
            self._flush_timer.start(self.FLUSH_MS)

    def _flush(self) -> None:
        if not self._queue:
            self._flush_timer.stop()
            return
        batch, self._queue = self._queue[: self.MAX_PER_FLUSH], self._queue[self.MAX_PER_FLUSH:]
        self._write_lines(batch)
        if not self._queue:
            self._flush_timer.stop()

    def flush_now(self) -> None:
        """立刻把队列里的日志全部写出来（流程结束时调用）。"""
        self._flush_timer.stop()
        while self._queue:
            batch, self._queue = self._queue[: self.MAX_PER_FLUSH], self._queue[self.MAX_PER_FLUSH:]
            self._write_lines(batch)

    def _write_lines(self, batch) -> None:
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt_time = QTextCharFormat()
        fmt_time.setForeground(QColor("#5C6B7E"))
        for level, message in batch:
            color, mark = LEVEL_STYLE.get(level, LEVEL_STYLE["info"])
            cursor.insertText(f"{time.strftime('%H:%M:%S')}  ", fmt_time)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if level in ("ok", "error"):
                fmt.setFontWeight(QFont.DemiBold)
            cursor.insertText(f"{mark} {_strip_emoji(str(message))}\n", fmt)
            self._count += 1
        self.view.setTextCursor(cursor)
        self.view.ensureCursorVisible()
        self.stat.setText(f"共 {self._count} 条")

    def clear(self) -> None:
        self._queue.clear()
        self.view.clear()
        self._count = 0
        self.stat.setText("就绪")


class DataTable(QWidget):
    """抓取到的数据表预览。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet(f"background:{theme.PANEL}; border-bottom:1px solid {theme.BORDER};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 0, 8, 0)
        self.stat = QLabel("暂无数据")
        self.stat.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11.5px;")
        h.addWidget(self.stat)
        h.addStretch(1)
        lay.addWidget(bar)

        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setStyleSheet(f"""
            QTableWidget {{ background:{theme.PANEL}; border:none; gridline-color:{theme.BORDER};
                            font-size:12px; }}
            QTableWidget::item {{ padding: 3px 7px; }}
            QTableWidget::item:selected {{ background:{theme.PRIMARY_SOFT}; color:{theme.TEXT}; }}
            QHeaderView::section {{ background:{theme.PANEL_SOFT}; border:none;
                                    border-bottom:1px solid {theme.BORDER};
                                    border-right:1px solid {theme.BORDER};
                                    padding:5px 8px; font-size:11.5px;
                                    color:{theme.TEXT_SUB}; font-weight:600; }}
        """)
        lay.addWidget(self.table, 1)

    def set_rows(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.stat.setText("暂无数据")
            return
        cols: List[str] = []
        for r in rows:
            for k in r.keys():
                if k not in cols:
                    cols.append(k)
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows[:2000]):
            for j, c in enumerate(cols):
                item = QTableWidgetItem(str(r.get(c, "")))
                item.setToolTip(str(r.get(c, "")))
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.stat.setText(f"共 {len(rows)} 行 × {len(cols)} 列")


class VarTable(QWidget):
    """运行期变量快照。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet(f"background:{theme.PANEL}; border-bottom:1px solid {theme.BORDER};")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 0, 8, 0)
        self.stat = QLabel("运行时可查看变量取值")
        self.stat.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11.5px;")
        h.addWidget(self.stat)
        h.addStretch(1)
        lay.addWidget(bar)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["变量", "值"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(f"""
            QTableWidget {{ background:{theme.PANEL}; border:none; font-size:12px;
                            gridline-color:{theme.BORDER}; }}
            QTableWidget::item {{ padding:3px 7px; }}
            QHeaderView::section {{ background:{theme.PANEL_SOFT}; border:none;
                                    border-bottom:1px solid {theme.BORDER};
                                    padding:5px 8px; font-size:11.5px;
                                    color:{theme.TEXT_SUB}; font-weight:600; }}
        """)
        lay.addWidget(self.table, 1)

    def set_vars(self, variables: Dict[str, Any]) -> None:
        items = [(k, v) for k, v in variables.items() if not k.startswith("_")]
        self.table.setRowCount(len(items))
        for i, (k, v) in enumerate(items):
            k_item = QTableWidgetItem(str(k))
            k_item.setForeground(QColor(theme.PRIMARY))
            s = str(v)
            if len(s) > 300:
                s = s[:300] + "…"
            v_item = QTableWidgetItem(s)
            v_item.setToolTip(str(v))
            self.table.setItem(i, 0, k_item)
            self.table.setItem(i, 1, v_item)
        self.stat.setText(f"共 {len(items)} 个变量")


class BottomPanel(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.console = Console()
        self.var_table = VarTable()
        self.addTab(self.console, "  运行日志  ")
        self.addTab(self.var_table, "  变量  ")
        # 注意：不要开 documentMode——真机 Windows 上它会在页签栏顶部
        # 画一条贯穿面板的白色底线（样式表也去不掉），视觉上像一根白线
