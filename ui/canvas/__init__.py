"""
流程画布
==========
自绘的流程编辑器（不是 QTreeWidget 封装）：
卡片式节点 + 嵌套容器 + 拖拽落点预览 + 运行状态高亮。

分层
----
row.py        数据行与几何常量
ops.py        流程树的纯数据操作（可单测）
painter.py    全部绘制逻辑
__init__.py   交互：选择 / 拖拽 / 拖放 / 右键菜单 / 键盘
"""
from __future__ import annotations

import time
from typing import List, Optional

from PySide6.QtCore import QMimeData, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QPainter
from PySide6.QtWidgets import QMenu, QScrollArea, QToolTip, QWidget

from core.models import Flow, FlowNode
from core.registry import REGISTRY

from .. import icons, theme
from ..widgets import MODULE_MIME, NODE_MIME, wrap_tooltip
from . import ops, painter
from .row import (CHEVRON_ZONE, GAP, INDENT, PAD_LEFT, PAD_TOP, ROW_H, STEP,
                  Row)


class _Surface(QWidget):
    """画布的实际绘制与交互表面（所有事件转发给 FlowCanvas）。"""

    def __init__(self, canvas: "FlowCanvas") -> None:
        super().__init__(canvas)
        self.canvas = canvas
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(320)

    def sizeHint(self) -> QSize:                          # noqa: N802
        return QSize(760, max(400, self.canvas.content_height()))

    def resizeEvent(self, e) -> None:                     # noqa: N802
        self.setMinimumHeight(self.canvas.content_height())

    # ---- 绘制 ----
    def paintEvent(self, e) -> None:                      # noqa: N802
        p = QPainter(self)
        try:
            self.canvas.paint(p)
        finally:
            p.end()

    # ---- 鼠标 / 键盘 ----
    def mousePressEvent(self, e) -> None:                 # noqa: N802
        self.canvas.handle_press(e)

    def mouseMoveEvent(self, e) -> None:                  # noqa: N802
        self.canvas.handle_move(e)

    def leaveEvent(self, e) -> None:                      # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e) -> None:               # noqa: N802
        self.canvas.handle_release(e)

    def mouseDoubleClickEvent(self, e) -> None:           # noqa: N802
        self.canvas.handle_double_click(e)

    def contextMenuEvent(self, e) -> None:                # noqa: N802
        self.canvas.handle_context_menu(e)

    def keyPressEvent(self, e) -> None:                   # noqa: N802
        self.canvas.handle_key(e)

    # ---- 拖放 ----
    def dragEnterEvent(self, e) -> None:                  # noqa: N802
        if e.mimeData().hasFormat(MODULE_MIME) or e.mimeData().hasFormat(NODE_MIME):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:                   # noqa: N802
        self.canvas.update_drop_preview(e.position().toPoint(), e.mimeData())
        e.acceptProposedAction()

    def dragLeaveEvent(self, e) -> None:                  # noqa: N802
        self.canvas.clear_drop_preview()

    def dropEvent(self, e) -> None:                       # noqa: N802
        pos = e.position().toPoint()
        md = e.mimeData()
        handled = False
        if md.hasFormat(MODULE_MIME):
            type_id = bytes(md.data(MODULE_MIME)).decode("utf-8")
            handled = self.canvas.drop_new_module(type_id, pos)
        elif md.hasFormat(NODE_MIME):
            uid = bytes(md.data(NODE_MIME)).decode("utf-8")
            handled = self.canvas.drop_move_node(uid, pos)
        self.canvas.clear_drop_preview()
        if handled:
            e.acceptProposedAction()
            self.canvas.flow_changed.emit()
        else:
            e.ignore()
        self.update()


class FlowCanvas(QScrollArea):
    """流程画布（带滚动的容器）。"""

    node_selected = Signal(object)
    flow_changed = Signal()
    status_message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 纵向滚动条常显：占位宽度固定，避免内容多少变化时卡片宽度抖动
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setStyleSheet(f"QScrollArea {{ background: {theme.CANVAS_BG}; }}")

        self.flow: Flow = Flow()
        self.rows: List[Row] = []
        self.selected: Optional[FlowNode] = None
        self.collapsed: set = set()
        self.runtime: dict = {}                  # uid -> status
        self.running_uid: Optional[str] = None
        self.error_uid: Optional[str] = None
        self._drop: Optional[tuple] = None
        self._press_pos: Optional[QPoint] = None
        self._press_row: Optional[Row] = None
        self._hover_uid: Optional[str] = None

        # ---- 渲染节流：把高频 update() 合并到 16ms 一帧 ----
        self._repaint_pending = False
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.timeout.connect(self._do_repaint)

        # ---- 运行脉冲动画：仅在有节点运行时启动 ----
        self._pulse = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)

        # ---- 运行高亮最小停留：切换太快时排进队列，每个目标至少展示 MIN_RUNNING_MS ----
        self._running_since = 0.0
        self._pending_running: List[Optional[FlowNode]] = []   # 待展示的高亮目标队列
        self._dwell_timer = QTimer(self)
        self._dwell_timer.setSingleShot(True)
        self._dwell_timer.timeout.connect(self._apply_pending_running)

        self.surface = _Surface(self)
        self.setWidget(self.surface)

    # ================================================================ 渲染调度
    def request_repaint(self) -> None:
        """请求重绘。同一帧内的多次请求自动合并，避免重复绘制。"""
        if self._repaint_pending:
            return
        self._repaint_pending = True
        self._repaint_timer.start(16)

    def _do_repaint(self) -> None:
        self._repaint_pending = False
        self.surface.update()

    def _pulse_tick(self) -> None:
        self._pulse = (self._pulse + 0.055) % 1.0
        self.request_repaint()

    # ================================================================ 数据
    def set_flow(self, flow: Flow, keep_selection: bool = False) -> None:
        self.flow = flow
        self.collapsed.clear()
        self.runtime.clear()
        self.running_uid = None
        self.error_uid = None
        self._dwell_timer.stop()
        self._pending_running.clear()
        if not keep_selection:
            self.selected = None
        self.refresh(emit=False)

    def refresh(self, emit: bool = True) -> None:
        self._rebuild_rows()
        self.surface.setMinimumHeight(self.content_height())
        self.request_repaint()
        if emit:
            self.flow_changed.emit()

    def resizeEvent(self, event) -> None:                 # noqa: N802
        """窗口尺寸变化（含启动最大化）时重建行几何，保证卡片宽度始终贴齐。"""
        super().resizeEvent(event)
        if self.flow.nodes:
            self._rebuild_rows()
            self.request_repaint()

    def content_height(self) -> int:
        return int(PAD_TOP * 2 + len(self.rows) * STEP + 30)

    def count_nodes(self) -> int:
        return ops.count_nodes(self.flow)

    def _rebuild_rows(self) -> None:
        """扁平化树 + 预计算几何 + 容器子树范围。"""
        flat = ops.flatten(self.flow, self.collapsed)
        rows = [Row(n, d, p, i) for n, d, p, i in flat]
        for idx, r in enumerate(rows):
            r.y = PAD_TOP + idx * STEP
            cx = PAD_LEFT + r.depth * INDENT + CHEVRON_ZONE
            cw = max(220.0, self.surface.width() - cx - PAD_LEFT)
            r.card = QRectF(cx, r.y, cw, ROW_H)
            if r.node.children:
                r.chevron = QRectF(PAD_LEFT + r.depth * INDENT + 4,
                                   r.y + ROW_H / 2 - 8, 16, 16)
            if r.node.children and r.node.uid not in self.collapsed:
                last = idx
                for j in range(idx + 1, len(rows)):
                    if rows[j].depth > r.depth:
                        last = j
                    else:
                        break
                r.subtree_end = last
        self.rows = rows

    # ================================================================ 定位
    def _row_at(self, y: float) -> Optional[Row]:
        for r in self.rows:
            if r.y <= y <= r.y + ROW_H:
                return r
        return None

    def _nearest_index(self, y: float) -> int:
        for i, r in enumerate(self.rows):
            if y < r.y + ROW_H / 2:
                return i
        return len(self.rows)

    # ================================================================ 增删改
    def add_module(self, type_id: str, parent: Optional[FlowNode] = None,
                   index: int = -1, select: bool = True) -> Optional[FlowNode]:
        spec = REGISTRY.get(type_id)
        if spec is None:
            return None
        node = FlowNode.create(type_id)
        if spec.block_kind == "if":
            node.children = [FlowNode.create("_else")]
        elif spec.block_kind == "try":
            node.children = [FlowNode.create("_catch")]
        ops.insert(self.flow, node, parent, index)
        if parent is not None:
            self.collapsed.discard(parent.uid)
        if select:
            self.selected = node
            self.node_selected.emit(node)
        self.refresh()
        self.status_message.emit(f"已添加「{spec.name}」")
        return node

    def delete_node(self, node: Optional[FlowNode] = None) -> None:
        node = node or self.selected
        if node is None:
            return
        name = node.display_name
        ops.detach(self.flow, node.uid)
        if self.selected is node:
            self.selected = None
            self.node_selected.emit(None)
        self.refresh()
        self.status_message.emit(f"已删除「{name}」")

    def delete_node_by_uid(self, uid: str) -> None:
        """画布节点被拖回模块库时调用：按 uid 定位并删除。"""
        loc = ops.find_location(self.flow, uid)
        if not loc:
            return
        lst, idx, _ = loc
        node = lst[idx]
        self.delete_node(node)

    def duplicate_node(self, node: Optional[FlowNode] = None) -> None:
        node = node or self.selected
        if node is None:
            return
        loc = ops.find_location(self.flow, node.uid)
        if not loc:
            return
        lst, idx, _ = loc
        clone = ops.clone_with_new_uids(node)
        lst.insert(idx + 1, clone)
        self.selected = clone
        self.node_selected.emit(clone)
        self.refresh()
        self.status_message.emit(f"已复制「{node.display_name}」")

    def move_node(self, node: FlowNode, delta: int) -> None:
        loc = ops.find_location(self.flow, node.uid)
        if not loc:
            return
        lst, idx, _ = loc
        new_idx = idx + delta
        if not (0 <= new_idx < len(lst)):
            return
        lst.insert(new_idx, lst.pop(idx))
        self.refresh()

    def wrap_in(self, node: FlowNode, type_id: str) -> None:
        """把选中步骤包进循环/分组等容器。"""
        loc = ops.find_location(self.flow, node.uid)
        if not loc:
            return
        lst, idx, _ = loc
        wrapper = FlowNode.create(type_id)
        if wrapper.spec and wrapper.spec.block_kind == "if":
            wrapper.children.append(FlowNode.create("_else"))
        lst[idx] = wrapper
        wrapper.children.insert(0, node)
        self.selected = wrapper
        self.node_selected.emit(wrapper)
        self.refresh()
        self.status_message.emit(f"已用「{wrapper.display_name}」包裹该步骤")

    def toggle_enabled(self, node: Optional[FlowNode] = None) -> None:
        node = node or self.selected
        if node is None:
            return
        node.enabled = not node.enabled
        self.refresh()

    def toggle_collapse(self, node: FlowNode) -> None:
        if node.uid in self.collapsed:
            self.collapsed.discard(node.uid)
        else:
            self.collapsed.add(node.uid)
        self.refresh(emit=False)

    def clear_all(self) -> None:
        self.flow.nodes.clear()
        self.selected = None
        self.node_selected.emit(None)
        self.refresh()

    # ================================================================ 运行态
    MIN_RUNNING_MS = 100      # 运行高亮最小停留时间，避免快步骤一闪而过
    MAX_PENDING_RUNNING = 20  # 队列上限：防止超长流程/大循环把待展示积压成几分钟

    def set_running(self, node: Optional[FlowNode]) -> None:
        """切换运行高亮（带最小停留）。

        快步骤连续完成时，running/ok 事件会挤在同一帧到达——
        只把高亮"记住最后一个"会导致中间节点全部看不见（只闪第一下）。
        这里改成 FIFO 队列：每个目标至少展示 MIN_RUNNING_MS，
        高亮就会一格一格跑过去；新目标入队时吞掉队尾的 clear，避免蓝光闪烁。
        """
        uid = node.uid if node else None
        if uid == self.running_uid and not self._pending_running:
            return
        if self.running_uid is not None and uid != self.running_uid:
            remain = self.MIN_RUNNING_MS - (time.monotonic() - self._running_since) * 1000
            if remain > 0:
                # 当前高亮还没停够：入队等待，到点后按顺序逐个展示
                while self._pending_running and self._pending_running[-1] is None:
                    self._pending_running.pop()
                self._pending_running.append(node)
                if len(self._pending_running) > self.MAX_PENDING_RUNNING:
                    self._pending_running.pop(0)
                if not self._dwell_timer.isActive():
                    self._dwell_timer.start(int(remain) + 1)
                return
        self._dwell_timer.stop()
        self._pending_running.clear()
        self._apply_running(node)

    def _apply_pending_running(self) -> None:
        """停留时间到：展示队列里的下一个目标。"""
        if not self._pending_running:
            return
        node = self._pending_running.pop(0)
        self._apply_running(node)
        if self._pending_running:
            self._dwell_timer.start(self.MIN_RUNNING_MS)

    def _apply_running(self, node: Optional[FlowNode]) -> None:
        self.running_uid = node.uid if node else None
        if node:
            self._running_since = time.monotonic()
            loc = ops.find_location(self.flow, node.uid)
            if loc and loc[2]:
                # 自动展开父级让运行位置可见
                for n in self.flow.nodes:
                    for sub in n.walk():
                        if sub is loc[2]:
                            self.collapsed.discard(sub.uid)
            self._scroll_to(node)
            if not self._pulse_timer.isActive():
                self._pulse = 0.0
                self._pulse_timer.start(50)
        else:
            if self._pulse_timer.isActive():
                self._pulse_timer.stop()
        self.request_repaint()

    def set_status(self, node: Optional[FlowNode], status: str) -> None:
        if node is None:
            return
        if status == "running":
            self.runtime.pop(node.uid, None)
        else:
            self.runtime[node.uid] = status
        self.request_repaint()

    def set_error(self, node: Optional[FlowNode]) -> None:
        """标记报错节点：红色高亮框停留，停掉 running 动画。"""
        self._dwell_timer.stop()
        self._pending_running.clear()
        self.running_uid = None
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()
        self.error_uid = node.uid if node else None
        if node:
            loc = ops.find_location(self.flow, node.uid)
            if loc and loc[2]:
                for n in self.flow.nodes:
                    for sub in n.walk():
                        if sub is loc[2]:
                            self.collapsed.discard(sub.uid)
            self._scroll_to(node)
        self.request_repaint()

    def clear_error(self) -> None:
        self.error_uid = None
        self.request_repaint()

    def clear_runtime(self) -> None:
        self.runtime.clear()
        self._dwell_timer.stop()
        self._pending_running.clear()
        self.running_uid = None
        self.error_uid = None
        self.request_repaint()

    def _scroll_to(self, node: FlowNode) -> None:
        for r in self.rows:
            if r.node is node:
                target = max(0.0, r.y - 120)
                self.verticalScrollBar().setValue(int(target))
                return

    # ================================================================ 拖放
    def update_drop_preview(self, pos: QPoint, mime: QMimeData) -> None:
        move_uid = None
        if mime.hasFormat(NODE_MIME):
            move_uid = bytes(mime.data(NODE_MIME)).decode("utf-8")
        self._drop = self._compute_target(pos.y(), move_uid)
        self.request_repaint()

    def _compute_target(self, y: float, move_uid: Optional[str]):
        if not self.rows:
            return (None, 0, "append")
        row = self._row_at(y)
        if row is None:
            idx = self._nearest_index(y)
            if idx <= 0:
                return (None, 0, "insert")
            return (None, len(self.flow.nodes), "insert")
        spec = row.node.spec
        if spec is not None and spec.is_block and row.node.type_id not in ("_else", "_catch"):
            mid = row.card.top() + ROW_H / 2
            if abs(y - mid) < ROW_H * 0.30:
                return (row.node, len(row.node.children), "into")
        above = y < row.card.top() + ROW_H / 2
        return (row.parent, row.index + (0 if above else 1), "insert")

    def clear_drop_preview(self) -> None:
        self._drop = None
        self.request_repaint()

    def drop_new_module(self, type_id: str, pos: QPoint) -> bool:
        parent, index, _mode = self._compute_target(pos.y(), None)
        self.add_module(type_id, parent, index)
        return True

    def drop_move_node(self, uid: str, pos: QPoint) -> bool:
        loc = ops.find_location(self.flow, uid)
        if not loc:
            return False
        src_list, src_idx, _ = loc
        node = src_list[src_idx]
        parent, index, mode = self._compute_target(pos.y(), uid)

        if parent is not None and ops.is_descendant(node, parent.uid):
            self.status_message.emit("不能把容器拖进它自己里面")
            return False

        src_list.pop(src_idx)
        dst = self.flow.nodes if parent is None else parent.children
        if parent is not None:
            self.collapsed.discard(parent.uid)
            if mode == "into":
                index = len(dst)
        index = max(0, min(index, len(dst)))
        dst.insert(index, node)
        self.selected = node
        self.node_selected.emit(node)
        self.refresh()
        return True

    # ================================================================ 事件
    def handle_press(self, e) -> None:
        pos = e.position().toPoint()
        self.surface.setFocus()
        if e.button() == Qt.RightButton:
            row = self._row_at(pos.y())
            if row:
                self.selected = row.node
                self.node_selected.emit(row.node)
                self.refresh(emit=False)
            return
        if e.button() != Qt.LeftButton:
            return
        for r in self.rows:
            if r.chevron and r.chevron.contains(pos.x(), pos.y()):
                self.toggle_collapse(r.node)
                return
        row = self._row_at(pos.y())
        self._press_pos = pos
        self._press_row = row
        self.selected = row.node if row else None
        self.node_selected.emit(self.selected)
        self.request_repaint()

    def handle_move(self, e) -> None:
        pos = e.position().toPoint()
        row = self._row_at(pos.y())
        uid = row.node.uid if row else None
        if uid != self._hover_uid:
            self._hover_uid = uid
            self.request_repaint()
            # 悬停步骤卡片时显示说明气泡（模块用途 + 当前参数摘要）
            if row is not None and not row.node.type_id.startswith("_"):
                QToolTip.showText(e.globalPosition().toPoint(),
                                  self._node_tooltip(row.node), self.surface)
            else:
                QToolTip.hideText()

        if self._press_pos is None or not (e.buttons() & Qt.LeftButton):
            return
        if self._press_row is None:
            return
        if (pos - self._press_pos).manhattanLength() < 10:
            return
        node = self._press_row.node
        QToolTip.hideText()
        self._press_pos = None
        self._press_row = None
        drag = QDrag(self.surface)
        mime = QMimeData()
        mime.setData(NODE_MIME, node.uid.encode("utf-8"))
        drag.setMimeData(mime)
        drag.setPixmap(self._node_drag_pixmap(node))
        drag.setHotSpot(QPoint(24, 24))
        drag.exec(Qt.MoveAction)
        self._drop = None
        self.request_repaint()

    def _node_tooltip(self, node: FlowNode) -> str:
        """步骤卡片的悬停说明：模块名 + 用途 + 当前参数摘要 + 备注。"""
        spec = REGISTRY.get(node.type_id)
        if spec is None:
            return ""
        parts = [f"【{spec.name}】"]
        if spec.desc:
            parts.append(spec.desc)
        text = " ".join(parts)
        try:
            summary = spec.summary(node.params)
        except Exception:
            summary = ""
        if summary:
            text += f"\n当前参数：{summary}"
        if node.note:
            text += f"\n📝 备注：{node.note}"
        return wrap_tooltip(text)

    def _node_drag_pixmap(self, node: FlowNode):
        """拖动节点时的幽灵卡片：画一个与画布卡片外观一致的半透明预览。"""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QBrush, QFont, QFontMetrics, QPixmap, QPen
        spec = node.spec
        cat = spec.category if spec else "通用工具"
        color = theme.cat_color(cat)
        w, h = 250, 56
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # 半透明深色卡片 + 分类色边框
        p.setBrush(QBrush(QColor(17, 23, 34, 235)))
        p.setPen(QPen(QColor(color), 2))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 10, 10)
        # 左侧分类色条
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawRoundedRect(QRectF(12, 10, 3.5, h - 20), 2, 2)
        # 图标
        if spec and spec.glyph:
            pm_icon = icons.ICON_CACHE.icon(spec.glyph, color, theme.cat_soft(cat), 30)
        else:
            pm_icon = icons.BADGE_CACHE.badge(spec.badge if spec else "•", color,
                                              theme.cat_soft(cat), 30)
        p.drawPixmap(24, (h - 30) // 2, pm_icon)
        # 标题文字
        p.setPen(QColor(theme.TEXT))
        f = theme.font(10)
        f.setBold(True)
        p.setFont(f)
        title = node.display_name
        fm = QFontMetrics(f)
        title = fm.elidedText(title, Qt.ElideRight, w - 100)
        p.drawText(QRectF(64, 0, w - 74, h), int(Qt.AlignVCenter) | int(Qt.AlignLeft), title)
        p.end()
        return pm

    def handle_release(self, e) -> None:
        self._press_pos = None
        self._press_row = None

    def handle_double_click(self, e) -> None:
        row = self._row_at(e.position().y())
        if row and row.node.children:
            self.toggle_collapse(row.node)

    def handle_key(self, e) -> None:
        k = e.key()
        mods = e.modifiers()
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_node()
        elif k == Qt.Key_D and (mods & Qt.ControlModifier):
            self.duplicate_node()
        elif k == Qt.Key_Space:
            self.toggle_enabled()
        elif k == Qt.Key_Up and (mods & Qt.AltModifier) and self.selected:
            self.move_node(self.selected, -1)
        elif k == Qt.Key_Down and (mods & Qt.AltModifier) and self.selected:
            self.move_node(self.selected, 1)
        elif k == Qt.Key_Up:
            self._select_relative(-1)
        elif k == Qt.Key_Down:
            self._select_relative(1)
        else:
            super().keyPressEvent(e)
            return
        e.accept()

    def _select_relative(self, delta: int) -> None:
        if not self.rows:
            return
        if self.selected is None:
            self.selected = self.rows[0].node
            self.node_selected.emit(self.selected)
            self.request_repaint()
            return
        for i, r in enumerate(self.rows):
            if r.node is self.selected:
                j = max(0, min(len(self.rows) - 1, i + delta))
                self.selected = self.rows[j].node
                self.node_selected.emit(self.selected)
                self._scroll_to(self.selected)
                self.request_repaint()
                return

    def handle_context_menu(self, e) -> None:
        row = self._row_at(e.position().y())
        menu = QMenu(self.surface)
        if row:
            node = row.node
            a_dup = menu.addAction("复制此步骤")
            a_up = menu.addAction("上移")
            a_down = menu.addAction("下移")
            menu.addSeparator()
            a_loop = menu.addAction("用循环包裹")
            a_grp = menu.addAction("用分组包裹")
            menu.addSeparator()
            a_tog = menu.addAction("禁用此步骤" if node.enabled else "启用此步骤")
            a_col = menu.addAction("展开/折叠") if node.children else None
            menu.addSeparator()
            a_del = menu.addAction("删除")
            act = menu.exec(e.globalPos())
            if act is None:
                return
            if act == a_dup:
                self.duplicate_node(node)
            elif act == a_up:
                self.move_node(node, -1)
            elif act == a_down:
                self.move_node(node, 1)
            elif act == a_loop:
                self.wrap_in(node, "flow.loop")
            elif act == a_grp:
                self.wrap_in(node, "flow.group")
            elif act == a_tog:
                self.toggle_enabled(node)
            elif a_col is not None and act == a_col:
                self.toggle_collapse(node)
            elif act == a_del:
                self.delete_node(node)
        else:
            menu.addAction("清空画布", self.clear_all)
            menu.addAction("全部展开", lambda: (self.collapsed.clear(), self.refresh(emit=False)))
            menu.exec(e.globalPos())

    # ================================================================ 绘制
    def paint(self, p: QPainter) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.fillRect(self.surface.rect(), QColor(theme.CANVAS_BG))

        if not self.rows:
            painter.draw_empty(p, self.surface.width())
            return

        state = painter.CanvasState(
            selected_uid=self.selected.uid if self.selected else None,
            hover_uid=self._hover_uid,
            running_uid=self.running_uid,
            error_uid=self.error_uid,
            runtime=dict(self.runtime),
            drop=self._drop,
            collapsed=set(self.collapsed),
            pulse=self._pulse,
        )
        painter.draw_all(p, self.surface.width(), self.rows, state)


__all__ = ["FlowCanvas"]
