"""
AutoRPA 异常体系
==================
全部自定义异常集中在这里，避免引擎、上下文、模块三方互相 import 造成循环依赖。

异常语义
--------
RunAborted     用户主动停止 → 直接结束整个流程，不算失败
NodeFailed     节点执行失败 → 按该节点的"失败时"策略处理（停止/跳过/重试）
BreakLoop      跳出循环 → 只结束当前循环，流程继续
ContinueLoop   跳过本次循环 → 进入下一轮
"""
from __future__ import annotations


class RunAborted(Exception):
    """用户主动停止流程（含「结束流程」模块）。"""


class NodeFailed(Exception):
    """节点执行失败。"""


class VarLookupError(Exception):
    """变量或路径取值失败（如 KeyError、IndexError、变量不存在）。"""


class BreakLoop(Exception):
    """跳出当前循环。"""


class ContinueLoop(Exception):
    """跳过本次循环剩余步骤，进入下一次。"""
