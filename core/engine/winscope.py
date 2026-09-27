"""
窗口作用域
==========
「窗口内运行」容器运行期间的激活状态保障。

容器进入时先激活目标窗口（按「激活尝试次数 × 尝试间隔」重试，超过上限
抛异常 → 流程失败）；运行期间引擎在每个步骤执行前调用 ensure()——
当前窗口不是目标窗口时自动重新激活，同样受次数/间隔约束。
勾选「保持窗口最大化」时，激活后会确保窗口处于最大化状态。
"""
from __future__ import annotations


class WinScope:
    """一个「窗口内运行」容器的运行时状态。"""

    def __init__(self, title: str, exact: bool = False, maximize: bool = True,
                 wait: float = 0.5, retries: int = 3,
                 retry_interval: float = 1.0) -> None:
        self.title = title
        self.exact = exact
        self.maximize = maximize
        self.wait = max(0.0, float(wait))
        self.retries = max(1, int(retries))
        self.retry_interval = max(0.0, float(retry_interval))

    # ------------------------------------------------------------------
    def matches(self, ctx) -> bool:
        """当前前台窗口是否是目标窗口。"""
        t = (ctx.window.active_title() or "").strip()
        if not t:
            return False
        return t == self.title if self.exact else self.title in t

    def ensure(self, ctx) -> None:
        """确保目标窗口在前台：不在则重新激活，超次抛异常（流程失败）。"""
        ctx.check_stop()
        if self.matches(ctx):
            self._ensure_maximized(ctx)
            return
        for attempt in range(1, self.retries + 1):
            ctx.check_stop()
            ctx.warn(f"🪟 当前窗口不是「{self.title}」，第 {attempt}/{self.retries} 次重新激活…")
            ok = ctx.window.activate(self.title, self.exact, self.wait)
            if ok and self.matches(ctx):
                self._ensure_maximized(ctx)
                ctx.info(f"🪟 已重新激活窗口「{self.title}」")
                return
            if attempt < self.retries:
                ctx.sleep(self.retry_interval)
        titles = ctx.window.list_titles()[:8]
        raise RuntimeError(
            f"窗口「{self.title}」激活失败：已尝试 {self.retries} 次仍未激活。"
            f"当前窗口示例：{titles}")

    # ------------------------------------------------------------------
    def _ensure_maximized(self, ctx) -> None:
        if not self.maximize:
            return
        try:
            w = ctx.window.find(self.title, self.exact)
        except Exception:
            w = None
        if w is None:
            return
        try:
            if hasattr(w, "isMaximized") and not w.isMaximized:
                w.maximize()
                ctx.sleep(0.2)
        except Exception:
            pass
