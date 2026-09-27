"""
AutoRPA - 模块注册中心
========================
所有功能积木在这里登记，UI 的左侧"模块库"和执行引擎的调度都从这里取。
新增一个功能模块 = 写一个函数 + 打一个 @module 装饰器，无需改动界面代码。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .spec import ERROR_POLICY_PARAMS, ModuleSpec, Param, VarSlot

# 分类固定顺序与配色（UI 用）
CATEGORIES: List[str] = [
    "图像识别",
    "鼠标操作",
    "键盘操作",
    "窗口系统",
    "流程控制",
    "变量容器",
    "文件操作",
    "外部调用",
    "通用工具",
]

CATEGORY_STYLE: Dict[str, Dict[str, str]] = {
    "图像识别": {"color": "#7C5CFF", "soft": "#F0EDFF", "glyph": "camera"},
    "鼠标操作": {"color": "#2B6CF6", "soft": "#E8F0FE", "glyph": "mouse"},
    "键盘操作": {"color": "#12B76A", "soft": "#E6F7EF", "glyph": "keyboard"},
    "窗口系统": {"color": "#F79009", "soft": "#FFF4E6", "glyph": "window"},
    "变量容器": {"color": "#06AED4", "soft": "#E4F7FB", "glyph": "table"},
    "流程控制": {"color": "#F04438", "soft": "#FDECEA", "glyph": "branch"},
    "通用工具": {"color": "#667085", "soft": "#EFF1F4", "glyph": "settings"},
    "文件操作": {"color": "#2E90FA", "soft": "#EAF3FE", "glyph": "folder"},
    "外部调用": {"color": "#6172F3", "soft": "#EEF0FD", "glyph": "lightning"},
}


class Registry:
    def __init__(self) -> None:
        self._specs: Dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> None:
        if spec.type_id in self._specs:
            raise ValueError(f"模块 type_id 重复: {spec.type_id}")
        if not spec.glyph:
            spec.glyph = CATEGORY_STYLE.get(spec.category, {}).get("glyph", "settings")
        if not spec.badge:
            spec.badge = CATEGORY_STYLE.get(spec.category, {}).get("badge", "•")
        # 为所有模块统一追加"运行控制"参数（异常策略 / 重试 / 超时）
        existing = {p.name for p in spec.params}
        for p in ERROR_POLICY_PARAMS:
            if p.name not in existing:
                spec.params.append(p)
        self._specs[spec.type_id] = spec

    def get(self, type_id: str) -> Optional[ModuleSpec]:
        return self._specs.get(type_id)

    def all(self) -> List[ModuleSpec]:
        return list(self._specs.values())

    def by_category(self) -> Dict[str, List[ModuleSpec]]:
        out: Dict[str, List[ModuleSpec]] = {c: [] for c in CATEGORIES}
        for spec in self._specs.values():
            out.setdefault(spec.category, []).append(spec)
        return out

    def search(self, keyword: str) -> List[ModuleSpec]:
        kw = keyword.strip().lower()
        if not kw:
            return self.all()
        res = []
        for s in self._specs.values():
            if kw in s.name.lower() or kw in s.type_id.lower() or kw in s.desc.lower():
                res.append(s)
        return res


REGISTRY = Registry()


def module(
    type_id: str,
    name: str,
    category: str,
    params: Optional[List[Param]] = None,
    desc: str = "",
    is_block: bool = False,
    block_kind: str = "",
    returns_value: bool = False,
    var_slots: Optional[List[VarSlot]] = None,
    examples: Optional[List[str]] = None,
) -> Callable:
    """把一个执行函数注册成可拖拽模块。

    用法::

        @module("mouse.click", "鼠标点击", "鼠标操作", params=[...])
        def _run(node, ctx):
            ...
    """

    def deco(fn: Callable) -> Callable:
        REGISTRY.register(
            ModuleSpec(
                type_id=type_id,
                name=name,
                category=category,
                runner=fn,
                params=list(params or []),
                desc=desc,
                is_block=is_block,
                block_kind=block_kind,
                returns_value=returns_value,
                var_slots=list(var_slots or []),
                examples=list(examples or []),
            )
        )
        return fn

    return deco
