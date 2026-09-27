"""
容器节点调度
==============
循环 / 条件 / 容错 / 分组 这四类"积木套积木"的执行逻辑。
以 mixin 形式注入 FlowRunner，与节点执行/重试策略解耦。
"""
from __future__ import annotations

from typing import Any, List

from ..context import RunContext
from ..exceptions import BreakLoop, ContinueLoop, RunAborted
from ..models import FlowNode
from .winscope import WinScope

MAX_LOOP_GUARD = 1_000_000


class BlockHandlers:
    """容器节点处理逻辑（配合 FlowRunner 使用）。"""

    # ================================================================ 入口
    def _run_container(self, node: FlowNode, spec, ctx: RunContext) -> None:
        kind = spec.block_kind
        if kind == "loop":
            self._run_loop(node, ctx)
        elif kind == "if":
            self._run_if(node, ctx)
        elif kind == "try":
            self._run_try(node, ctx)
        elif kind == "win":
            self._run_win_scope(node, ctx)
        else:                                            # group / 其它
            self._run_block(node.children, ctx)

    # ================================================================ 窗口作用域
    def _run_win_scope(self, node: FlowNode, ctx: RunContext) -> None:
        """「窗口内运行」容器：进入时激活窗口（超次失败），
        运行期间由 _run_node 的步骤前钩子持续校验激活状态。"""
        p = node.params
        title = str(ctx.resolve(p.get("title", "")) or "").strip()
        if not title:
            raise RuntimeError("未填写窗口标题关键字")
        scope = WinScope(
            title=title,
            exact=bool(p.get("exact")),
            maximize=bool(p.get("maximize", True)),
            wait=float(p.get("wait", 0.5) or 0.0),
            retries=int(p.get("retries", 3) or 3),
            retry_interval=float(p.get("retry_interval", 1.0) or 0.0),
        )
        scope.ensure(ctx)                     # 首次激活：找不到 / 抢不回 → 流程失败
        ctx.win_scopes.append(scope)
        try:
            self._run_block(node.children, ctx)
        finally:
            ctx.win_scopes.pop()

    # ================================================================ 分支切分
    @staticmethod
    def _split_branches(children: List[FlowNode]):
        """按分支容器（否则 / 异常处理）切分子节点。

        「否则」「异常处理」本身是容器节点，它们 **各自的 children** 就是分支内容。
        """
        main: List[FlowNode] = []
        else_b: List[FlowNode] = []
        catch_b: List[FlowNode] = []
        for c in children:
            if c.type_id == "_else":
                else_b.extend(c.children)
            elif c.type_id == "_catch":
                catch_b.extend(c.children)
            else:
                main.append(c)
        return main, else_b, catch_b

    # ================================================================ 循环
    def _run_body(self, body: List[FlowNode], ctx: RunContext) -> bool:
        """执行一轮循环体。返回 False 表示收到"跳出循环"。"""
        try:
            self._run_block(body, ctx)
        except BreakLoop:
            self.ctx.info("⤴ 跳出循环")
            return False
        except ContinueLoop:
            return True
        return True

    def _run_loop(self, node: FlowNode, ctx: RunContext) -> None:
        p = node.params
        mode = str(p.get("mode", "固定次数"))
        body = node.children

        if mode == "固定次数":
            try:
                total = int(p.get("times", 1))
            except (TypeError, ValueError):
                total = 1
            self.ctx.info(f"⟳ 循环 {total} 次" + (f" · {node.note}" if node.note else ""))
            for i in range(max(0, total)):
                ctx.check_stop()
                ctx.set_var(p.get("loop_index_name", "loop_index") or "loop_index", i + 1)
                ctx.set_var("loop_total", total)
                if not self._run_body(body, ctx):
                    break

        elif mode in ("遍历变量", "遍历数据表"):   # 「遍历数据表」为更名前的老写法
            rows = self._resolve_dataset(p.get("dataset", ""), ctx)
            item_var = p.get("item_var", "item") or "item"
            self.ctx.info(f"⟳ 遍历变量 {len(rows)} 条")
            for i, row in enumerate(rows):
                ctx.check_stop()
                ctx.set_var(item_var, row)
                # 自动展开子变量：字典 → item.key；列表 → item[0]、item[1]…
                if isinstance(row, dict):
                    for k, v in row.items():
                        ctx.set_var(f"{item_var}.{k}", v)
                elif isinstance(row, (list, tuple)):
                    for j, v in enumerate(row):
                        ctx.set_var(f"{item_var}[{j}]", v)
                ctx.set_var("loop_total", len(rows))
                ctx.set_var(p.get("loop_index_name", "loop_index") or "loop_index", i + 1)
                if not self._run_body(body, ctx):
                    break

        elif mode == "条件循环":
            try:
                limit = int(float(p.get("max_times", 100) or 100))
            except (TypeError, ValueError):
                limit = 100
            cond = p.get("condition", "")
            self.ctx.info(f"⟳ 条件循环（最多 {limit} 次）：{cond}")
            i = 0
            while i < min(limit, MAX_LOOP_GUARD):
                ctx.check_stop()
                if not ctx.eval_condition(cond):
                    break
                i += 1
                ctx.set_var(p.get("loop_index_name", "loop_index") or "loop_index", i)
                ctx.set_var("loop_total", limit)
                if not self._run_body(body, ctx):
                    break

        else:  # 无限循环（靠"跳出循环"或停止信号结束）
            self.ctx.info("⟳ 无限循环开始（用「跳出循环」结束）")
            i = 0
            while i < MAX_LOOP_GUARD:
                ctx.check_stop()
                i += 1
                ctx.set_var("loop_index", i)
                if not self._run_body(body, ctx):
                    break

    def _resolve_dataset(self, expr: str, ctx: RunContext) -> List[Any]:
        """把数据来源统一解析成列表。

        支持：列表变量、字典（取 values）、多行文本、逗号分隔的单行文本；
        数字/布尔按单条数据遍历（当前项就是该值本身）；
        留空则用已抓取的数据表。
        """
        val = ctx.resolve_value(expr)
        if isinstance(val, list):
            return val
        if isinstance(val, tuple):
            return list(val)
        if isinstance(val, dict):
            return [{"key": k, "value": v} for k, v in val.items()]
        if isinstance(val, str) and val.strip():
            rows = [r.strip() for r in val.replace("\r\n", "\n").split("\n") if r.strip()]
            if len(rows) == 1:
                parts = [p.strip() for p in
                         rows[0].replace("，", ",").split(",") if p.strip()]
                if len(parts) > 1:
                    rows = parts
            return rows
        if isinstance(val, bool) or isinstance(val, (int, float)):
            return [val]
        if ctx.data:
            return list(ctx.data)
        return []

    # ================================================================ 条件
    def _run_if(self, node: FlowNode, ctx: RunContext) -> None:
        cond = str(node.params.get("condition", ""))
        result = ctx.eval_condition(cond)
        main, else_b, _ = self._split_branches(node.children)
        self.ctx.info(f"◆ 条件判断 [{cond}] → {'成立' if result else '不成立'}")
        self._run_block(main if result else else_b, ctx)

    # ================================================================ 容错
    def _run_try(self, node: FlowNode, ctx: RunContext) -> None:
        main, _, catch_b = self._split_branches(node.children)
        try:
            self._run_block(main, ctx)
        except RunAborted:
            raise
        except Exception as exc:                        # noqa: BLE001
            ctx.warn(f"捕获到异常：{exc}")
            ctx.set_var("error_message", str(exc))
            if catch_b:
                self._run_block(catch_b, ctx)
            elif str(node.params.get("on_error", "停止流程")) == "停止流程":
                raise
