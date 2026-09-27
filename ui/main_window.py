"""
主窗口
========
负责：组装四块面板 + 信号接线 + 多标签流程管理 + 运行控制 + 全局热键。
界面细节（顶栏/画布/面板）都在各自组件里，这里只做"把它们连起来"。

多标签：每个打开的流程是一个 FlowDoc（ui/flowtabs.py），
self.flow / self.flow_path / self.dirty 以 property 形式代理到当前标签，
其余代码无需关心当前在哪个标签页。
"""
from __future__ import annotations

import os
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMessageBox, QPushButton,
                               QSplitter, QStatusBar, QVBoxLayout, QWidget)

from core import APP_TITLE, __version__
from core import paths, samples
from core.drivers import INPUT, check_dependencies
from core.engine import RunManager, RunState
from core.models import Flow
from ui.canvas.ops import max_depth

from . import icons, theme
from .bottom import BottomPanel
from .canvas import FlowCanvas
from .dialogs import CountdownOverlay, PointPickOverlay
from .flowtabs import FlowDoc, FlowTabBar
from .inspector import Inspector
from .palette import ModulePalette
from .topbar import TopBar

ROOT = paths.ROOT


class MainWindow(QMainWindow):
    sig_log = Signal(str, str)
    sig_progress = Signal(object, str)
    sig_finished = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE}  v{__version__}")
        self.setWindowIcon(icons.app_icon())
        self.resize(1460, 900)
        self.setMinimumSize(1120, 700)

        # ---- 多标签：每个打开的流程一个 FlowDoc；初始一个空白标签 ----
        self.docs: list[FlowDoc] = [FlowDoc(Flow(name="未命名流程"), None)]
        self.cur: int = 0
        self.run_manager = RunManager()
        self._hotkey_listener = None
        self._pick_mode = False
        # 清理门槛状态：本次运行是否出现过"跳过"、哪些文档运行整体成功
        # （整体成功 = 运行结束 ok 且全程无跳过；只有这类流程在用户下次保存时才清理）
        self._run_had_skip = False
        self._cleanable: set[int] = set()

        # ---- 自动保存：任何改动后 1.2s 写入自动保存槽，关闭时再写一次 ----
        # 恢复槽放在应用数据目录（AppData），不占 flows/ 的「一流程一文件夹」结构
        from PySide6.QtCore import QStandardPaths
        auto_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(auto_dir, exist_ok=True)
        self._autosave_path = os.path.join(auto_dir, "自动保存.arpa")
        self._migrate_autosave()
        # flows/ 是用户流程工作区：发布包不带它，启动时自动创建
        os.makedirs(paths.FLOWS_DIR, exist_ok=True)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._do_autosave)

        self._build()
        self._wire()
        self._install_shortcuts()
        self._start_hotkeys()

        self.tabs.add_tab(self.docs[0].flow.name)
        self.tabs.set_tip(0, self._doc_tip(self.docs[0]))
        self.tabs.set_current(0)            # 启动即激活首个标签（按下去的效果）
        self._restore_or_template()
        self._append_log("ok", f"{APP_TITLE} 已就绪。左侧拖模块到中间画布即可搭建流程。")
        self._check_deps()

    # ================================================================== 当前标签代理
    # self.flow / self.flow_path / self.dirty 全部代理到当前 FlowDoc，
    # 运行引擎、画布、检查器等存量代码不需要知道标签页的存在。
    @property
    def flow(self) -> Flow:
        return self.docs[self.cur].flow

    @flow.setter
    def flow(self, f: Flow) -> None:
        self.docs[self.cur].flow = f

    @property
    def flow_path(self) -> Optional[str]:
        return self.docs[self.cur].path

    @flow_path.setter
    def flow_path(self, p: Optional[str]) -> None:
        self.docs[self.cur].path = p

    @property
    def dirty(self) -> bool:
        return self.docs[self.cur].dirty

    @dirty.setter
    def dirty(self, v: bool) -> None:
        self.docs[self.cur].dirty = v

    @staticmethod
    def _doc_tip(doc: FlowDoc) -> str:
        """标签悬停提示：流程名称（+ 文件路径）。"""
        if doc.path:
            return f"{doc.flow.name}\n📄 {doc.path}"
        return f"{doc.flow.name}（未保存 · 双击标签可重命名）"

    # ================================================================== 界面
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.topbar = TopBar()
        outer.addWidget(self.topbar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 8)
        body_layout.setSpacing(10)

        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.setChildrenCollapsible(False)
        self.vsplit.setHandleWidth(1)

        self.hsplit = QSplitter(Qt.Horizontal)
        self.hsplit.setChildrenCollapsible(False)
        self.hsplit.setHandleWidth(1)

        self.palette = ModulePalette()
        self.center = self._build_center()
        self.inspector = Inspector(ROOT)
        self.hsplit.addWidget(self.palette)
        self.hsplit.addWidget(self.center)
        self.hsplit.addWidget(self.inspector)
        self.hsplit.setStretchFactor(0, 0)
        self.hsplit.setStretchFactor(1, 1)
        self.hsplit.setStretchFactor(2, 0)
        self.hsplit.setSizes([250, 860, 330])

        self.bottom = BottomPanel()
        self.vsplit.addWidget(self.hsplit)
        self.vsplit.addWidget(self.bottom)
        self.vsplit.setStretchFactor(0, 1)
        self.vsplit.setStretchFactor(1, 0)
        self.vsplit.setSizes([620, 220])
        body_layout.addWidget(self.vsplit, 1)
        outer.addWidget(body, 1)

        self._build_statusbar()

    def _build_center(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("Panel")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QWidget()
        head.setFixedHeight(40)
        h = QHBoxLayout(head)
        h.setContentsMargins(14, 0, 10, 0)
        h.setSpacing(8)
        t = QLabel("流程设计")
        t.setObjectName("PanelTitle")
        h.addWidget(t)
        self.canvas_hint = QLabel("从左侧拖入模块 · 拖到「循环」卡片中间可放进去 · Del 删除")
        self.canvas_hint.setObjectName("PanelHint")
        h.addWidget(self.canvas_hint)
        h.addStretch(1)

        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("Ghost")
        self.btn_clear.setStyleSheet(f"font-size:11.5px; color:{theme.TEXT_SUB};")
        self.btn_clear.clicked.connect(self._clear_canvas)
        h.addWidget(self.btn_clear)

        self.btn_zoom = QPushButton("全部展开")
        self.btn_zoom.setObjectName("Ghost")
        self.btn_zoom.setStyleSheet(f"font-size:11.5px; color:{theme.TEXT_SUB};")
        self.btn_zoom.clicked.connect(self._expand_all)
        h.addWidget(self.btn_zoom)

        v.addWidget(head)

        # ---- 流程标签页：一个标签 = 一个打开的流程（激活标签与画布连成一体） ----
        self.tabs = FlowTabBar()
        v.addWidget(self.tabs)

        self.canvas = FlowCanvas()
        v.addWidget(self.canvas, 1)
        return wrap

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_deps = QLabel("")
        self.lbl_stats = QLabel("")
        self.lbl_mouse = QLabel("")
        self.lbl_mouse.setStyleSheet(f"color:{theme.TEXT_SUB};")
        sb.addWidget(self.lbl_deps)
        sb.addPermanentWidget(self.lbl_stats)
        sb.addPermanentWidget(self.lbl_mouse)

        self._mouse_timer = QTimer(self)
        self._mouse_timer.timeout.connect(self._tick_mouse)
        self._mouse_timer.start(260)
        self._refresh_stats()

    # ================================================================== 接线
    def _wire(self) -> None:
        tb = self.topbar
        tb.new_clicked.connect(self.new_flow)
        tb.open_clicked.connect(self.open_flow)
        tb.save_clicked.connect(self.save_flow)
        tb.save_as_clicked.connect(lambda: self.save_flow(save_as=True))
        tb.sample_selected.connect(self.load_template)
        tb.run_clicked.connect(self.run_flow)
        tb.pause_clicked.connect(self.toggle_pause)
        tb.stop_clicked.connect(self.stop_flow)
        tb.pick_clicked.connect(self.pick_coordinate)

        self.tabs.tab_clicked.connect(self._switch_to)
        self.tabs.tab_close_clicked.connect(self._close_doc)
        self.tabs.tab_rename_requested.connect(self._rename_current)

        self.palette.module_added.connect(self._quick_add)
        self.palette.node_dropped.connect(self.canvas.delete_node_by_uid)
        self.palette.drag_began.connect(
            lambda: self.canvas_hint.setText("松开鼠标即可放置 · 拖到「循环」卡片中间可嵌套"))
        self.canvas.node_selected.connect(self.inspector.show_node)
        self.canvas.flow_changed.connect(self._on_flow_changed)
        self.canvas.status_message.connect(self._toast)
        self.inspector.params_changed.connect(self._on_params_changed)

        self.sig_log.connect(self._append_log, Qt.QueuedConnection)
        self.sig_progress.connect(self._on_progress, Qt.QueuedConnection)
        self.sig_finished.connect(self._on_finished, Qt.QueuedConnection)

    def _install_shortcuts(self) -> None:
        for seq, slot in (("F9", self.run_flow), ("F10", self.toggle_pause),
                          ("F12", self.stop_flow),
                          ("Ctrl+S", self.save_flow), ("Ctrl+O", self.open_flow),
                          ("Ctrl+N", self.new_flow)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(slot)

    def _start_hotkeys(self) -> None:
        """用 pynput 注册系统级热键，程序不在前台也能控制。"""
        try:
            from pynput import keyboard as kb
            self._hotkey_listener = kb.GlobalHotKeys({
                "<f9>": lambda: (self.sig_log.emit("info", "⌨ 全局热键 F9 → 触发运行"), self.run_flow()),
                "<f12>": lambda: (self.sig_log.emit("warn", "⌨ 全局热键 F12 → 紧急停止"), self.stop_flow()),
                "<f10>": self.toggle_pause,
            })
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
        except Exception as exc:                        # noqa: BLE001
            self._append_log("warn", f"全局热键注册失败（仍可用窗口内快捷键）：{exc}")

    # ================================================================== 自动保存
    def _restore_or_template(self) -> None:
        """启动时：优先恢复上次的自动保存；没有则载入第一个示例流程（都进第一个标签）。"""
        if os.path.isfile(self._autosave_path):
            try:
                flow = Flow.load(self._autosave_path)
                self._set_flow(flow, path=self._autosave_path)
                self._append_log("info",
                                 f"已恢复上次的编辑内容（自动保存于 "
                                 f"{time.strftime('%H:%M', time.localtime(os.path.getmtime(self._autosave_path)))}）")
                return
            except Exception:
                pass
        first = samples.list_examples()
        if first:
            try:
                self._set_flow(samples.load_example(first[0][0]), None)
                return
            except Exception:
                pass
        self._set_flow(Flow(name="未命名流程"), None)

    def _migrate_autosave(self) -> None:
        """旧版本把恢复槽放在 flows/自动保存.arpa，迁移到应用数据目录并清掉旧文件。"""
        old = os.path.join(ROOT, "flows", "自动保存.arpa")
        if not os.path.isfile(old):
            return
        import shutil
        try:
            if not os.path.isfile(self._autosave_path):
                shutil.move(old, self._autosave_path)
            elif os.path.getmtime(old) > os.path.getmtime(self._autosave_path):
                shutil.move(old, self._autosave_path)
            else:
                os.remove(old)
        except OSError:
            pass

    def _schedule_autosave(self) -> None:
        """改动发生后延迟落盘，连续输入时合并写入。"""
        self._autosave_timer.start(1200)

    def _do_autosave(self) -> None:
        """落盘策略（针对当前标签）：
        1) 总是写入「自动保存.arpa」恢复槽（崩溃/忘存也不丢当前流程）；
        2) 具名流程（且非示例）同步回写该文件（真·自动保存）；
        3) 未命名流程保持 dirty：关闭时提醒另存，避免静默丢失。
        """
        try:
            doc = self.docs[self.cur]
            os.makedirs(os.path.dirname(self._autosave_path), exist_ok=True)
            doc.flow.save(self._autosave_path)
            if doc.path and doc.path != self._autosave_path \
                    and not self._is_example_path(doc.path):
                doc.flow.save(doc.path)
                doc.dirty = False
                self.tabs.set_dirty(self.cur, False)
            elif doc.path is not None:
                # 恢复槽里的流程：内容持续进恢复槽，视为已保存
                doc.dirty = False
                self.tabs.set_dirty(self.cur, False)
            self.statusBar().showMessage(
                f"✓ 已自动保存 {time.strftime('%H:%M:%S')}", 1800)
        except Exception:
            pass

    # ================================================================== 多标签管理
    def _untitled_name(self) -> str:
        """不与现有标签重名的「未命名流程」。"""
        names = {d.flow.name for d in self.docs}
        if "未命名流程" not in names:
            return "未命名流程"
        n = 2
        while f"未命名流程 {n}" in names:
            n += 1
        return f"未命名流程 {n}"

    def _push_doc(self, flow: Flow, path: Optional[str]) -> None:
        """新开一个标签页并切换过去。"""
        if self.run_manager.running:
            self._toast("运行中不可切换流程")
            return
        doc = FlowDoc(flow, path)
        self.docs.append(doc)
        i = self.tabs.add_tab(flow.name)
        self.tabs.set_tip(i, self._doc_tip(doc))
        self._switch_to(len(self.docs) - 1)

    def _flush_view(self) -> None:
        """切换/关闭前：把当前画布的视图状态记回文档，并触发一次自动保存。"""
        doc = self.docs[self.cur]
        doc.collapsed = set(self.canvas.collapsed)
        doc.scroll = self.canvas.verticalScrollBar().value()
        doc.selected = self.canvas.selected
        self._do_autosave()

    def _show_current(self) -> None:
        """把当前文档加载进画布/检查器/标签高亮（不做自动保存）。"""
        doc = self.docs[self.cur]
        self.canvas.set_flow(doc.flow)
        self.canvas.collapsed = set(doc.collapsed)
        self.canvas.selected = doc.selected
        self.canvas.refresh(emit=False)
        self.canvas.verticalScrollBar().setValue(doc.scroll)
        self.inspector.flow = doc.flow
        self.inspector.base_dir = self._workspace(create=False)   # 参数面板的文件对话框默认进流程文件夹
        self.inspector.show_node(doc.selected)
        self.tabs.set_current(self.cur)
        self.bottom.var_table.set_vars({})
        self._refresh_stats()
        self._update_title()
        # 切换流程后把模块库滚回顶部并强制重绘——避免切换/系统弹窗后
        # 面板停留在底部空白区或残留未重绘的假象"空白"
        self.palette.scroll.verticalScrollBar().setValue(0)
        self.palette.scroll.viewport().update()
        self.palette.update()

    def _switch_to(self, i: int) -> None:
        """点击标签切换流程。"""
        if not (0 <= i < len(self.docs)) or i == self.cur:
            return
        if self.run_manager.running:
            self._toast("运行中不可切换流程")
            return
        self._flush_view()                       # 旧文档：自动保存 + 记下视图状态
        self.cur = i
        self._show_current()

    def _close_doc(self, i: int) -> None:
        """关闭标签页；最后一个也关了会自动补一个空白流程。"""
        if self.run_manager.running:
            self._toast("运行中不可关闭流程")
            return
        if not (0 <= i < len(self.docs)):
            return
        doc = self.docs[i]
        if doc.dirty:
            r = QMessageBox.question(
                self, "关闭标签", f"流程「{doc.flow.name}」还没保存，关闭前是否保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save and not self._save_doc(doc):
                return                                # 用户在保存对话框里取消了
        closing_current = (i == self.cur)
        self._cleanable.discard(id(doc))
        self.docs.pop(i)
        self.tabs.remove_tab(i)
        if not self.docs:
            self.docs.append(FlowDoc(Flow(name="未命名流程"), None))
            self.tabs.add_tab("未命名流程")
            self.tabs.set_tip(0, self._doc_tip(self.docs[0]))
        if i < self.cur:
            self.cur -= 1                        # 前面的标签被抽走，当前索引左移
        else:
            self.cur = min(self.cur, len(self.docs) - 1)
        if closing_current:
            self._show_current()                 # 显示相邻文档（cur 已指向它）
        else:
            self.tabs.set_current(self.cur)      # 只刷新高亮
        self._refresh_stats()
        self._update_title()

    def _rename_current(self, i: int) -> None:
        """双击标签重命名流程。"""
        if not (0 <= i < len(self.docs)):
            return
        doc = self.docs[i]
        name, ok = QInputDialog.getText(self, "重命名流程", "流程名称：",
                                        text=doc.flow.name)
        name = name.strip()
        if not ok or not name or name == doc.flow.name:
            return
        doc.flow.name = name
        doc.dirty = True
        self.tabs.set_title(i, name)
        self.tabs.set_tip(i, self._doc_tip(doc))
        self.tabs.set_dirty(i, True)
        if i == self.cur:
            self.inspector.base_dir = self._workspace(create=False)
            self._update_title()
        self._schedule_autosave()

    def _update_title(self) -> None:
        doc = self.docs[self.cur]
        if doc.path and doc.path != self._autosave_path:
            self.setWindowTitle(
                f"{APP_TITLE}  v{__version__}  —  {os.path.basename(doc.path)}")
        else:
            self.setWindowTitle(f"{APP_TITLE}  v{__version__}")

    # ================================================================== 流程操作
    def new_flow(self) -> None:
        self._push_doc(Flow(name=self._untitled_name()), None)
        self._append_log("info", "已新建空白流程（新标签）")

    def load_template(self, key: str) -> None:
        """示例流程在新标签页打开（key 为示例文件路径；samples.BLANK = 空白流程）。"""
        if key == samples.BLANK:
            self.new_flow()
            return
        try:
            flow = samples.load_example(key)
        except Exception as exc:                        # noqa: BLE001
            QMessageBox.critical(self, "载入失败", f"无法读取示例流程：\n{exc}")
            return
        same = self._find_open_by_name(flow.name)
        if same is not None:
            self._switch_to(same)
            self._toast(f"示例「{flow.name}」已在标签页中打开")
            return
        self._push_doc(flow, None)
        self.bottom.var_table.set_vars({})
        self._append_log("ok", f"已在新标签载入示例流程「{flow.name}」（只读示例：保存时会另存）")
        if flow.description:
            self._append_log("info", f"说明：{flow.description}")

    def _workspace(self, create: bool = True) -> str:
        """当前流程的工作区文件夹（flows/<流程名>/）。

        create=False 只取路径不建目录（避免逐个建文件夹）。
        """
        if create:
            return paths.ensure_flow_dirs(self.flow.name)
        return paths.flow_dir(self.flow.name)

    def open_flow(self) -> None:
        # 默认打开本工具相对路径下的 flows/ 文件夹（一流程一文件夹的结构）
        os.makedirs(paths.FLOWS_DIR, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "打开流程", paths.FLOWS_DIR,
            "灵瞳 流程 (*.arpa *.json);;所有文件 (*)")
        if not path:
            return
        self.open_flow_path(path)

    def _find_open_by_name(self, name: str):
        """按流程名找已打开的标签索引；未保存过的空白标签不算（不挡打开）。"""
        for i, d in enumerate(self.docs):
            if d.flow.name != name:
                continue
            if d.path is None and not d.flow.nodes and not d.dirty:
                continue
            return i
        return None

    def open_flow_path(self, path: str) -> None:
        """打开指定流程文件（供「打开」菜单与双击 .arpa 文件共用）。

        同一文件 / 同名流程已打开时直接切到对应标签，不重复开。
        内置示例只读：可以打开看和改，但保存时强制另存到 flows/，防止覆盖示例。
        """
        ap = os.path.normcase(os.path.abspath(path))
        for i, d in enumerate(self.docs):
            if d.path and os.path.normcase(os.path.abspath(d.path)) == ap:
                self._switch_to(i)
                self._toast("该流程已在标签页中打开")
                return
        try:
            flow = Flow.load(path)
        except Exception as exc:                        # noqa: BLE001
            QMessageBox.critical(self, "打开失败", f"无法读取该流程文件：\n{exc}")
            return
        same = self._find_open_by_name(flow.name)
        if same is not None:
            self._switch_to(same)
            self._toast(f"流程「{flow.name}」已在标签页中打开，不能重复打开")
            return
        is_example = self._is_example_path(path)
        self._push_doc(flow, None if is_example else path)
        self._append_log("ok", f"已在新标签打开流程：{path}")
        if is_example:
            self._append_log("info", "这是内置示例（只读）：修改后请用「保存」另存为你自己的流程")

    def _set_flow(self, flow: Flow, path: Optional[str]) -> None:
        """把流程装进当前标签（启动恢复/初始模板用；用户打开一律走新标签）。"""
        doc = self.docs[self.cur]
        doc.flow = flow
        doc.path = path
        doc.dirty = False
        doc.collapsed = set()
        doc.scroll = 0
        doc.selected = None
        self.canvas.set_flow(flow)
        self.inspector.flow = flow
        self.inspector.base_dir = self._workspace(create=False)
        self.inspector.show_node(None)
        self.tabs.set_title(self.cur, flow.name)
        self.tabs.set_tip(self.cur, self._doc_tip(doc))
        self.tabs.set_dirty(self.cur, False)
        self.bottom.var_table.set_vars({})
        self._refresh_stats()
        self._update_title()
        self.palette.scroll.verticalScrollBar().setValue(0)
        self.palette.scroll.viewport().update()
        self.palette.update()

    def save_flow(self, save_as: bool = False) -> None:
        self._save_doc(self.docs[self.cur], save_as)

    def _save_doc(self, doc: FlowDoc, save_as: bool = False) -> bool:
        """保存指定文档；返回是否已保存（用户在对话框取消则 False）。"""
        path = doc.path
        # 从未保存过 / 另存 / 目标还是自动保存恢复槽 / 目标是内置示例（只读）→ 走另存为
        if save_as or not path or path == self._autosave_path or self._is_example_path(path):
            # 对话框直接打开在 flows/ 根目录：默认文件名 = 当前流程名，
            # 用户能看到已有的流程文件夹，新建的流程名落在结构里
            os.makedirs(paths.FLOWS_DIR, exist_ok=True)
            start = os.path.join(paths.FLOWS_DIR,
                                 f"{paths.sanitize_name(doc.flow.name)}.arpa")
            path, _ = QFileDialog.getSaveFileName(
                self, "保存流程", start, "灵瞳 流程 (*.arpa);;JSON (*.json)")
            if not path:
                return False
            # 直接散存在 flows/ 根目录 → 归位成 flows/<名>/<名>.arpa（一流程一文件夹）
            if os.path.normcase(os.path.dirname(os.path.abspath(path))) == \
                    os.path.normcase(os.path.abspath(paths.FLOWS_DIR)):
                stem = os.path.splitext(os.path.basename(path))[0]
                path = os.path.join(paths.FLOWS_DIR, stem, os.path.basename(path))
            # 对话框里改了文件名 → 流程名跟随文件，标签按钮同步刷新
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem and stem != doc.flow.name:
                doc.flow.name = stem
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)      # 用户在对话框里改名也能落盘
        try:
            doc.flow.save(path)
        except Exception as exc:                        # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return False
        doc.path = path
        doc.dirty = False
        # 保存在 flows/ 里的流程补齐工作区结构（input/output/... 子目录，
        # 以 .arpa 所在文件夹为准）。清理（未引用图片 + 过期日志）有严格门槛：
        # 本次运行须 整体成功且无跳过，之后用户再点保存时才执行一次；
        # 运行失败/中断/有跳过 一律不清理
        try:
            fdir = os.path.normcase(os.path.abspath(paths.FLOWS_DIR))
            if os.path.normcase(os.path.abspath(path)).startswith(fdir + os.sep):
                work = paths.ensure_workspace(os.path.dirname(path))
                if id(doc) in self._cleanable:
                    self._cleanable.discard(id(doc))
                    rm_img = paths.cleanup_unreferenced_images(work, doc.flow)
                    rm_log = paths.cleanup_old_logs(work)
                    if rm_img or rm_log:
                        self._append_log("info", f"清理：未引用图片 {rm_img} 张、过期日志 {rm_log} 个")
        except OSError:
            pass
        i = self.docs.index(doc)
        self.tabs.set_title(i, doc.flow.name)
        self.tabs.set_dirty(i, False)
        self.tabs.set_tip(i, self._doc_tip(doc))
        if i == self.cur:
            self.inspector.base_dir = self._workspace(create=False)
            self._update_title()
        self._append_log("ok", f"已保存到 {path}")
        return True

    @staticmethod
    def _is_example_path(path) -> bool:
        """路径是否在内置示例文件夹里（示例只读，不允许覆盖保存）。"""
        if not path:
            return False
        try:
            ap = os.path.normcase(os.path.abspath(path))
            ex = os.path.normcase(os.path.abspath(paths.EXAMPLES_DIR))
            return ap.startswith(ex + os.sep)
        except Exception:
            return False

    def _confirm_discard(self) -> bool:
        """即将丢弃当前未保存修改时的确认（新建/打开已改为新标签，目前仅兜底使用）。"""
        if not self.dirty or not self.flow.nodes:
            return True
        r = QMessageBox.question(
            self, "尚未保存", "当前流程还没有保存，是否放弃修改？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return r == QMessageBox.Yes

    def _quick_add(self, type_id: str) -> None:
        node = self.canvas.add_module(type_id)
        if node:
            self.inspector.show_node(node)

    def _clear_canvas(self) -> None:
        if not self.flow.nodes:
            return
        r = QMessageBox.question(self, "清空画布", "确定要清空全部步骤吗？",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self.canvas.clear_all()
            self.inspector.show_node(None)

    def _expand_all(self) -> None:
        self.canvas.collapsed.clear()
        self.canvas.refresh(emit=False)

    def _on_flow_changed(self) -> None:
        self.dirty = True
        self.tabs.set_dirty(self.cur, True)
        self._refresh_stats()
        self._schedule_autosave()

    def _on_params_changed(self) -> None:
        self.dirty = True
        self.tabs.set_dirty(self.cur, True)
        self.canvas.refresh(emit=False)
        self._schedule_autosave()

    # ================================================================== 运行
    def run_flow(self) -> None:
        if self.run_manager.running:
            self._toast("流程正在运行中")
            return
        if not self.flow.nodes:
            QMessageBox.information(self, "空流程", "画布上还没有任何步骤，先拖几个模块进来吧。")
            return
        self.bottom.console.clear()
        self.canvas.clear_runtime()
        self.canvas.refresh(emit=False)
        self._set_running_ui(True)
        self.bottom.setCurrentIndex(0)
        # 收走键盘焦点——否则模拟按键会打进我们自己的输入框
        # （比如「键盘输入文本」把文字敲进了左侧搜索框，还会触发过滤）
        fw = QGuiApplication.focusObject()
        if fw is not None and hasattr(fw, "clearFocus"):
            fw.clearFocus()
        self._run_had_skip = False                    # 记录本次运行是否有步骤被跳过

        ok = self.run_manager.start(
            self.flow,
            logger=lambda level, msg: self.sig_log.emit(level, msg),
            progress=lambda node, status: self.sig_progress.emit(node, status),
            finished=lambda ok_, msg: self.sig_finished.emit(ok_, msg),
            base_dir=self._workspace(),     # 相对路径都基于该流程的文件夹解析
        )
        if not ok:
            self._set_running_ui(False)
            return
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._refresh_live)
        self._poll.start(500)

    def _refresh_live(self) -> None:
        ctx = self.run_manager.ctx
        if ctx is None:
            return
        self.bottom.var_table.set_vars(ctx.vars)

    def toggle_pause(self) -> None:
        if not self.run_manager.running:
            return
        paused = self.run_manager.toggle_pause()
        self.topbar.set_paused(paused)
        self._append_log("warn" if paused else "info",
                         "⏸ 已暂停，点「继续」恢复" if paused else "▶ 已恢复执行")

    def stop_flow(self) -> None:
        if self.run_manager.running:
            self.run_manager.stop()
            self._append_log("warn", "正在停止…")

    def _set_running_ui(self, running: bool) -> None:
        self.topbar.set_running(running)
        self.tabs.set_locked(running)         # 运行期间锁定标签切换/关闭
        if not running:
            self.topbar.set_paused(False)
        self.canvas_hint.setText(
            "运行中… F10 暂停 · F12 紧急停止" if running else
            "从左侧拖入模块 · 拖到「循环」卡片中间可放进去 · Del 删除")

    def _on_progress(self, node, status: str) -> None:
        if node is None:
            return
        if status == "skip":
            self._run_had_skip = True
        if status == "running":
            self.canvas.set_running(node)
        elif status == "fail":
            self.canvas.set_error(node)
        else:
            self.canvas.set_running(None)
            self.canvas.set_status(node, status)

    def _restore_window(self) -> None:
        """将主窗口恢复到前台——只在流程结束后调用，运行中绝不打扰目标窗口。
        保持原窗口尺寸（最大化/普通都不变），只处理最小化的还原。"""
        if self.isMinimized():
            # 只清除最小化位：最大化/普通尺寸都保持原状
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        if not self.isActiveWindow():
            self.raise_()
            self.activateWindow()

    def _on_finished(self, ok: bool, msg: str) -> None:
        self._restore_window()
        self._set_running_ui(False)
        if hasattr(self, "_poll"):
            self._poll.stop()
        self._refresh_live()
        self.bottom.console.flush_now()
        # 清理门槛：整体成功（ok 且全程无跳过）的流程，下次保存时才允许清理
        doc = self.docs[self.cur]
        if ok and not self._run_had_skip:
            self._cleanable.add(id(doc))
        else:
            self._cleanable.discard(id(doc))
        self._toast(f"✔ 运行完成 · {msg}" if ok else f"运行结束：{msg}")
        if not ok:
            self.bottom.setCurrentIndex(0)

    # ================================================================== 启动动画衔接
    def start_fade_in(self, duration: int = 420) -> None:
        """主窗口淡入，与启动屏淡出衔接。"""
        from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._fade_anim = anim

    # ================================================================== 状态与工具
    def _append_log(self, level: str, message: str) -> None:
        self.bottom.console.append(level, message)

    def _toast(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 2500)

    def _tick_mouse(self) -> None:
        if self._pick_mode:
            return
        try:
            x, y = INPUT.position()
            self.lbl_mouse.setText(f"鼠标 {x}, {y}      ")
        except Exception:
            self.lbl_mouse.setText("")

    def _refresh_stats(self) -> None:
        n = self.canvas.count_nodes()
        depth = max_depth(self.flow.nodes)
        self.lbl_stats.setText(f"共 {n} 个步骤 · {depth} 层嵌套      ")

    def _check_deps(self) -> None:
        deps = check_dependencies()
        missing = [k for k, ok in deps.items() if not ok]
        if missing:
            self.lbl_deps.setText(f"⚠ 缺少组件：{'、'.join(missing)}")
            self.lbl_deps.setStyleSheet(f"color:{theme.WARN};")
        else:
            self.lbl_deps.setText("✓ 运行环境就绪（图像识别 + 键鼠模拟 + 截图 + 剪贴板）")
            self.lbl_deps.setStyleSheet(f"color:{theme.OK};")

    def pick_coordinate(self) -> None:
        """倒计时（可切到目标页面）→ 全屏单击取点 → 坐标复制到剪贴板。"""
        if self._pick_mode:
            return
        self._pick_mode = True
        self.topbar.btn_pick.setEnabled(False)
        self._countdown = CountdownOverlay(3)
        self._countdown.finished.connect(self._do_pick_point)
        self._countdown.cancelled.connect(self._finish_pick)
        self._countdown.start()

    def _do_pick_point(self) -> None:
        # 先最小化主窗口，避免取点遮罩抓到自己的界面
        self.showMinimized()
        QTimer.singleShot(320, self._open_point_overlay)

    def _open_point_overlay(self) -> None:
        self._overlay = PointPickOverlay()
        bg, scale = PointPickOverlay.grab_virtual_screen()
        self._overlay.set_background(bg, scale)
        self._overlay.picked.connect(self._on_point_picked)
        self._overlay.cancelled.connect(self._finish_pick)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def _on_point_picked(self, pt) -> None:
        s = self._overlay._scale if self._overlay is not None else 1.0
        o = self._overlay._origin if self._overlay is not None else None
        ox, oy = (o.x(), o.y()) if o is not None else (0, 0)
        x = int((pt.x() + ox) * s)
        y = int((pt.y() + oy) * s)
        QGuiApplication.clipboard().setText(f"{x},{y}")
        self._finish_pick()
        self.lbl_mouse.setText(f"✔ 已复制坐标 {x},{y}    ")
        self._append_log("ok", f"📍 坐标 {x},{y} 已复制到剪贴板，可直接粘贴到参数里")

    def _finish_pick(self) -> None:
        self._pick_mode = False
        self.topbar.btn_pick.setEnabled(True)
        if self.isMinimized():
            # 只清除最小化位：最大化/普通尺寸都保持原状
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()

    # ================================================================== 关闭
    def closeEvent(self, e) -> None:                        # noqa: N802
        if self.run_manager.running:
            result = self.run_manager.shutdown(timeout=2.5)
            if "未在" not in result:
                self._append_log("info", result)
        # 关闭前落盘：当前流程进恢复槽，其余具名流程各回各的文件
        try:
            os.makedirs(os.path.dirname(self._autosave_path), exist_ok=True)
            self.docs[self.cur].flow.save(self._autosave_path)
        except Exception:
            pass
        for d in self.docs:
            if d.path and d.path != self._autosave_path \
                    and not self._is_example_path(d.path):
                try:
                    d.flow.save(d.path)
                    d.dirty = False
                except Exception:
                    pass
        # 仍未保存（未命名）的流程：确认后再退出
        if any(d.dirty for d in self.docs):
            names = "、".join(f"「{d.flow.name}」" for d in self.docs if d.dirty)
            r = QMessageBox.question(
                self, "尚未保存", f"流程{names}还没有保存，退出会丢失这些修改，确定退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
        try:
            if self._hotkey_listener:
                self._hotkey_listener.stop()
        except Exception:
            pass
        e.accept()
