"""
流程树的纯数据操作
====================
这些函数只操作 Flow/FlowNode 数据结构，不碰任何 Qt 对象，
因此可以脱离界面单独写单元测试。
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from core.models import Flow, FlowNode


def find_location(flow: Flow, uid: str) -> Optional[Tuple[List[FlowNode], int, Optional[FlowNode]]]:
    """按 uid 找出节点所在位置，返回 (所属列表, 索引, 父节点)。"""
    def rec(nodes: List[FlowNode], parent: Optional[FlowNode]):
        for i, n in enumerate(nodes):
            if n.uid == uid:
                return nodes, i, parent
            got = rec(n.children, n)
            if got:
                return got
        return None
    return rec(flow.nodes, None)


def is_descendant(ancestor: FlowNode, uid: str) -> bool:
    """uid 对应的节点是否位于 ancestor 的子树内（含自身）。"""
    return any(c.uid == uid for c in ancestor.walk())


def detach(flow: Flow, uid: str) -> Optional[FlowNode]:
    """把节点从树里摘除并返回该节点。"""
    loc = find_location(flow, uid)
    if not loc:
        return None
    lst, idx, _ = loc
    return lst.pop(idx)


def insert(flow: Flow, node: FlowNode, parent: Optional[FlowNode], index: int = -1) -> None:
    """把节点插入到 parent（None=根）的 children 的 index 处（-1=末尾）。"""
    target = parent.children if parent is not None else flow.nodes
    if index < 0 or index > len(target):
        target.append(node)
    else:
        target.insert(index, node)


def clone_with_new_uids(node: FlowNode) -> FlowNode:
    """深复制一棵子树，并为所有节点重新生成 uid（避免粘贴后 uid 冲突）。"""
    clone = node.clone()
    for n in clone.walk():
        n.uid = FlowNode.create(n.type_id).uid
    return clone


def count_nodes(flow: Flow) -> int:
    return sum(len(list(n.walk())) for n in flow.nodes)


def max_depth(nodes: List[FlowNode], d: int = 0) -> int:
    m = d
    for n in nodes:
        if n.children:
            m = max(m, max_depth(n.children, d + 1))
    return m


def flatten(flow: Flow, collapsed: set) -> List[Tuple[FlowNode, int, Optional[FlowNode], int]]:
    """把树按可见性扁平化为 (node, depth, parent, index) 序列。"""
    out: List[Tuple[FlowNode, int, Optional[FlowNode], int]] = []

    def rec(nodes: List[FlowNode], depth: int, parent: Optional[FlowNode]) -> None:
        for i, n in enumerate(nodes):
            out.append((n, depth, parent, i))
            if n.children and n.uid not in collapsed:
                rec(n.children, depth + 1, n)

    rec(flow.nodes, 0, None)
    return out
