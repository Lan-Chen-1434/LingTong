"""
执行引擎
==========
流程 = 节点树。引擎在后台线程按深度优先遍历执行：

* 普通节点  → 调用 ModuleSpec.runner(node, ctx)
* 容器节点  → 由 BlockHandlers 负责调度其 children

每个节点都受"运行控制"参数约束（失败策略 / 重试次数 / 超时）。
执行中通过回调把日志与"当前执行到哪一步"推给界面。
"""
from __future__ import annotations

import os
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from .. import paths
from ..context import RunContext
from ..exceptions import (BreakLoop, ContinueLoop, NodeFailed, RunAborted)
from ..models import Flow, FlowNode
from ..registry import REGISTRY
from .blocks import BlockHandlers

_MARK = {"info": "·", "ok": "✔", "warn": "▲", "error": "✖", "debug": "·"}


class _RunFileLog:
    """把本次运行的日志同步写入 <流程文件夹>/log/run_<时间戳>.txt。"""

    def __init__(self, base_dir: str, flow_name: str) -> None:
        self._lock = threading.Lock()
        self._fp = None
        try:
            log_dir = os.path.join(base_dir, "log")
            os.makedirs(log_dir, exist_ok=True)
            fp = os.path.join(log_dir, time.strftime("run_%Y%m%d_%H%M%S.txt"))
            self._fp = open(fp, "a", encoding="utf-8")
            self._fp.write(f"===== 「{flow_name}」 {time.strftime('%Y-%m-%d %H:%M:%S')} 开始运行 =====\n")
            self._fp.flush()
        except OSError:
            self._fp = None

    def __call__(self, level: str, msg: str) -> None:
        if self._fp is None:
            return
        try:
            with self._lock:
                self._fp.write(f"{time.strftime('%H:%M:%S')} {_MARK.get(level, '·')} {msg}\n")
                self._fp.flush()
        except OSError:
            pass

    def close(self, ok: bool, msg: str) -> None:
        if self._fp is None:
            return
        try:
            with self._lock:
                state = "成功" if ok else "失败/中断"
                self._fp.write(f"===== 运行结束（{state}：{msg}） =====\n")
                self._fp.close()
        except OSError:
            pass
        self._fp = None


class FlowRunner(BlockHandlers):
    """在独立线程中执行流程。"""

    def __init__(self, flow: Flow,
                 logger: Optional[Callable[[str, str], None]] = None,
                 progress: Optional[Callable[[Optional[FlowNode], str], None]] = None,
                 finished: Optional[Callable[[bool, str], None]] = None,
                 base_dir: Optional[str] = None) -> None:
        self.flow = flow
        # 每次运行的日志同时写入流程文件夹 log/ 下的运行日志文件
        self._file_log = _RunFileLog(base_dir, flow.name) if base_dir else None
        if self._file_log is not None:
            prev = logger
            if prev is not None:
                logger = lambda level, msg: (prev(level, msg), self._file_log(level, msg))
            else:
                logger = self._file_log
        self.ctx = RunContext(flow, logger=logger, progress=progress, base_dir=base_dir)
        self.progress = progress or (lambda node, status: None)
        self.finished = finished or (lambda ok, msg: None)
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------ 线程控制
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._main, name="LingTong-Runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.ctx.stop_event.set()
        self.ctx.pause_event.set()

    def toggle_pause(self) -> bool:
        """返回 True 表示当前处于暂停状态。"""
        if self.ctx.pause_event.is_set():
            self.ctx.pause_event.clear()
            return True
        self.ctx.pause_event.set()
        return False

    @property
    def paused(self) -> bool:
        return not self.ctx.pause_event.is_set()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------ 主流程
    def _main(self) -> None:
        ok, msg = False, ""
        started = time.time()
        try:
            delay = float(self.flow.start_delay or 0.0)
            if delay > 0:
                self.ctx.info(f"流程将在 {delay:.1f} 秒后开始执行…")
                self.ctx.sleep(delay)
            self.ctx.success(f"▶ 开始执行「{self.flow.name}」")
            self._run_block(self.flow.nodes, self.ctx)
            cost = time.time() - started
            self.ctx.success(f"流程执行完成，耗时 {cost:.2f} 秒")
            ok, msg = True, f"完成 · {cost:.2f}s"
        except RunAborted as exc:
            self.ctx.warn(f"{exc}")
            ok, msg = False, str(exc)
        except NodeFailed as exc:
            self.ctx.error(f"{exc}")
            ok, msg = False, str(exc)
        except Exception as exc:                       # noqa: BLE001
            self.ctx.error(f"引擎内部异常: {exc}")
            self.ctx.debug(traceback.format_exc())
            ok, msg = False, str(exc)
        finally:
            self._running = False
            if self._file_log is not None:
                self._file_log.close(ok, msg)
            self.progress(None, "done")
            self.finished(ok, msg)

    def _run_block(self, nodes: List[FlowNode], ctx: RunContext,
                   loop_vars: Optional[Dict[str, Any]] = None) -> None:
        """顺序执行一组节点。BreakLoop / ContinueLoop 会向上抛出由循环节点接住。"""
        if loop_vars:
            ctx.vars.update(loop_vars)
        for node in nodes:
            ctx.check_stop()
            if not node.enabled:
                continue
            try:
                self._run_node(node, ctx)
            except (BreakLoop, ContinueLoop):
                raise

    # ------------------------------------------------------------ 单节点
    def _run_node(self, node: FlowNode, ctx: RunContext) -> None:
        spec = REGISTRY.get(node.type_id)
        if spec is None:
            raise NodeFailed(f"未知模块: {node.type_id}")

        # 窗口作用域钩子：位于「窗口内运行」容器内时，执行前先确认目标窗口仍在前台
        if ctx.win_scopes:
            ctx.win_scopes[-1].ensure(ctx)

        self.progress(node, "running")
        t0 = time.time()
        retry_limit = self._retry_limit(node)
        attempt = 0
        while True:
            attempt += 1
            try:
                if spec.is_block:
                    self._run_container(node, spec, ctx)
                else:
                    if spec.runner is None:
                        raise NodeFailed(f"模块 {spec.name} 未实现执行逻辑")
                    spec.runner(node, ctx)
                self.progress(node, "ok")
                return
            except RunAborted:
                self.progress(node, "skip")
                raise
            except (BreakLoop, ContinueLoop):
                self.progress(node, "skip")
                raise
            except Exception as exc:                    # noqa: BLE001
                self.ctx.screen.invalidate()
                if attempt <= retry_limit:
                    interval = float(node.params.get("retry_interval", 1.0) or 0.0)
                    ctx.warn(f"↻「{node.display_name}」第 {attempt} 次失败：{exc}"
                             f"，{interval:.1f}s 后重试")
                    ctx.sleep(interval)
                    continue
                cost = time.time() - t0
                policy = str(node.params.get("on_error", "停止流程"))
                detail = f"「{node.display_name}」执行失败（{cost:.2f}s）：{exc}"
                if policy in ("跳过此步", "重试后跳过"):
                    ctx.warn(f"{detail} → 已跳过")
                    self.progress(node, "skip")
                    return
                self.progress(node, "fail")
                raise NodeFailed(detail) from exc

    @staticmethod
    def _retry_limit(node: FlowNode) -> int:
        policy = str(node.params.get("on_error", "停止流程"))
        if policy in ("重试", "重试后跳过"):
            try:
                return max(0, int(node.params.get("retry", 3)))
            except (TypeError, ValueError):
                return 3
        return 0


# ================================================================ 便捷入口
def execute_subflow(flow: Flow, ctx: RunContext) -> None:
    """在当前上下文中执行另一个流程（供「调用子流程」模块使用）。"""
    runner = FlowRunner(flow, base_dir=ctx.base_dir)
    runner.ctx = ctx
    runner.progress = ctx.progress
    runner._run_block(flow.nodes, ctx)                  # noqa: SLF001


def run_flow_sync(flow: Flow, logger=None, progress=None, base_dir=None) -> bool:
    """同步执行（供命令行 / 调试 / 单元测试使用）。

    base_dir 缺省 = 该流程的工作区文件夹（flows/<流程名>/）。
    """
    if base_dir is None:
        base_dir = paths.workspace_for(flow)
    done = {"ok": False}

    def _fin(ok, msg):
        done["ok"] = ok

    r = FlowRunner(flow, logger=logger, progress=progress, finished=_fin, base_dir=base_dir)
    r.start()
    r.join()
    return done["ok"]
