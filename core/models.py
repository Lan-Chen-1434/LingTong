"""
AutoRPA - 流程数据模型
========================
一个流程(Flow)是一棵节点树；节点(Node)携带参数。
循环/条件这类容器节点拥有 children，形成嵌套结构。
序列化后就是一份干净的 JSON，方便保存、分享、版本管理。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from .registry import REGISTRY

FLOW_VERSION = "1.0"


@dataclass
class FlowNode:
    type_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    children: List["FlowNode"] = field(default_factory=list)
    enabled: bool = True
    note: str = ""
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    # ------------------------------------------------------------------ 构造
    @classmethod
    def create(cls, type_id: str) -> "FlowNode":
        spec = REGISTRY.get(type_id)
        params = spec.defaults() if spec else {}
        return cls(type_id=type_id, params=params)

    @property
    def spec(self):
        return REGISTRY.get(self.type_id)

    @property
    def display_name(self) -> str:
        spec = self.spec
        return spec.name if spec else f"未知模块({self.type_id})"

    # ------------------------------------------------------------------ 序列化
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type_id": self.type_id,
            "params": self.params,
            "enabled": self.enabled,
            "note": self.note,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FlowNode":
        node = cls(type_id=data.get("type_id", ""), params=dict(data.get("params") or {}))
        node.enabled = bool(data.get("enabled", True))
        node.note = data.get("note", "")
        node.children = [cls.from_dict(c) for c in data.get("children") or []]
        # 老流程兼容迁移（在补齐默认值之前）
        if node.type_id == "flow.loop":
            old_index = node.params.get("index_var")
            if old_index and "loop_index_name" not in node.params:
                node.params["loop_index_name"] = old_index
        # 补齐新增参数（老流程文件兼容）
        spec = REGISTRY.get(node.type_id)
        if spec:
            for p in spec.params:
                node.params.setdefault(p.name, p.default)
        # 老流程兼容：「遍历数据表」已更名为「遍历变量」
        if node.type_id == "flow.loop" and \
                str(node.params.get("mode", "")) == "遍历数据表":
            node.params["mode"] = "遍历变量"
        return node

    def clone(self) -> "FlowNode":
        return FlowNode.from_dict(self.to_dict())

    def walk(self) -> Iterator["FlowNode"]:
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Flow:
    name: str = "未命名流程"
    nodes: List[FlowNode] = field(default_factory=list)
    description: str = ""
    hotkey_run: str = "f9"
    hotkey_stop: str = "f12"
    start_delay: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": FLOW_VERSION,
            "name": self.name,
            "description": self.description,
            "hotkey_run": self.hotkey_run,
            "hotkey_stop": self.hotkey_stop,
            "start_delay": self.start_delay,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Flow":
        flow = cls(
            name=data.get("name", "未命名流程"),
            description=data.get("description", ""),
            hotkey_run=data.get("hotkey_run", "f9"),
            hotkey_stop=data.get("hotkey_stop", "f12"),
            start_delay=float(data.get("start_delay", 1.0)),
        )
        flow.nodes = [FlowNode.from_dict(n) for n in data.get("nodes") or []]
        return flow

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "Flow":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
