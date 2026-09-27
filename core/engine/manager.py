"""
运行生命周期管理
==================
把 FlowRunner 的创建、暂停、停止、销毁收敛到一个状态机里，
保证：同一时刻只有一个流程在跑、停止可被等待、关闭时线程安全退出。

UI 线程永远不直接操作线程，只通过这里下达指令；
引擎到 UI 的数据只走信号（跨线程自动队列化）。
"""
from __future__ import annotations

import enum
from typing import Callable, Optional

from ..context import RunContext
from ..models import Flow
from .runner import FlowRunner


class RunState(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


class RunManager:
    """流程运行的唯一入口与状态机。"""

    def __init__(self) -> None:
        self._runner: Optional[FlowRunner] = None
        self._state = RunState.IDLE

    # ------------------------------------------------------------ 状态
    @property
    def state(self) -> RunState:
        if self._runner is None:
            return RunState.IDLE
        if self._runner.running:
            return RunState.PAUSED if self._runner.paused else RunState.RUNNING
        return self._state

    @property
    def running(self) -> bool:
        return self.state in (RunState.RUNNING, RunState.PAUSED, RunState.STOPPING)

    @property
    def runner(self) -> Optional[FlowRunner]:
        return self._runner

    @property
    def ctx(self) -> Optional[RunContext]:
        return self._runner.ctx if self._runner else None

    # ------------------------------------------------------------ 指令
    def start(self, flow: Flow, logger: Callable, progress: Callable,
              finished: Callable, base_dir: Optional[str] = None) -> bool:
        """启动流程。已有流程在跑时直接拒绝。"""
        if self.running:
            return False
        self._runner = FlowRunner(
            flow,
            logger=lambda lv, msg: logger(lv, msg),
            progress=lambda n, s: self._on_progress(progress, n, s),
            finished=lambda ok, msg: self._on_finished(finished, ok, msg),
            base_dir=base_dir,
        )
        self._state = RunState.RUNNING
        self._runner.start()
        return True

    def _on_progress(self, cb: Callable, node, status: str) -> None:
        cb(node, status)

    def _on_finished(self, cb: Callable, ok: bool, msg: str) -> None:
        self._state = RunState.IDLE
        cb(ok, msg)

    def toggle_pause(self) -> bool:
        """返回 True 表示切换后处于暂停。"""
        if not (self._runner and self._runner.running):
            return False
        return self._runner.toggle_pause()

    def stop(self) -> None:
        """请求停止（非阻塞）。真正的线程回收由 finished 回调完成。"""
        if self._runner and self._runner.running:
            self._state = RunState.STOPPING
            self._runner.stop()

    def shutdown(self, timeout: float = 2.5) -> str:
        """关闭程序时调用：停止并最多等待 timeout 秒回收线程。"""
        if not self._runner:
            return "无运行任务"
        if self._runner.running:
            self._runner.stop()
        self._runner.join(timeout)
        alive = self._runner.running
        if alive:
            return "运行线程未在限定时间内退出，已随进程强制结束"
        return "已安全停止"
