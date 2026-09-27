"""
AutoRPA 变量池
================
负责 {{变量}} 插值 与 条件表达式求值。
设计上不依赖任何驱动——剪贴板、鼠标位置这类"运行时值"由 RunContext 用
`register_special()` 注入，使本类可以脱离桌面环境单独测试。
"""
from __future__ import annotations

import datetime as _dt
import random
import re
from typing import Any, Callable, Dict, List, Optional

from .exceptions import VarLookupError

VAR_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
SAFE_CHARS = re.compile(r"^[\w\s\+\-\*/%<>=!&|().,'\"\[\]:_]*$")

ALLOWED_BUILTINS = {
    "len": len, "int": int, "float": float, "str": str, "bool": bool,
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "True": True, "False": False, "None": None,
}


class VarStore:
    """变量池：字典 + 特殊值钩子 + 插值/求值。"""

    def __init__(self, warn: Optional[Callable[[str], None]] = None) -> None:
        self.vars: Dict[str, Any] = {}
        self.special: Dict[str, Callable[[], Any]] = {}
        self._warn = warn or (lambda msg: None)
        self._seed_builtins()

    # ------------------------------------------------------------ 初始化
    def _seed_builtins(self) -> None:
        now = _dt.datetime.now()
        self.vars.update({
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": int(now.timestamp()),
            "year": now.year, "month": now.month, "day": now.day,
            "hour": now.hour, "minute": now.minute, "second": now.second,
            "weekday": now.weekday() + 1,
        })
        self.register_special("random", lambda: random.randint(1000, 9999))
        self.register_special("now", lambda: _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def register_special(self, name: str, fn: Callable[[], Any]) -> None:
        """注册一个取值时动态计算的占位符，如 clipboard、mouse_x。"""
        self.special[name.lower()] = fn

    # ------------------------------------------------------------ 读写
    def set(self, name: str, value: Any) -> None:
        self.vars[str(name)] = value

    def get(self, name: str, default: Any = None) -> Any:
        return self.vars.get(str(name), default)

    def lookup(self, expr: str) -> Any:
        """解析 {{...}} 内部的名字：支持 name、name.key、name[0]、name['key'] 链式访问。

        顶层变量不存在 → 返回 None（由 resolve 按场景处理）。
        路径访问失败（KeyError / IndexError / 属性缺失）→ 抛 VarLookupError。
        """
        key = expr.strip()
        fn = self.special.get(key.lower())
        if fn is not None:
            try:
                return fn()
            except Exception:
                return None

        tokens = self._tokenize_path(key)
        if not tokens:
            return self.vars.get(key, "")

        root = tokens[0]
        if root not in self.vars:
            return self.vars.get(key, "")

        cur = self.vars[root]
        for token in tokens[1:]:
            if token.startswith("."):
                name = token[1:]
                if isinstance(cur, dict):
                    if name not in cur:
                        raise VarLookupError(
                            f"字典「{root}」中不存在键「{name}」（当前可用键：{list(cur.keys())}）")
                    cur = cur[name]
                elif isinstance(cur, (list, tuple)):
                    try:
                        cur = cur[int(name)]
                    except (ValueError, IndexError) as exc:
                        raise VarLookupError(
                            f"列表「{root}」索引「{name}」越界（长度 {len(cur)}）") from exc
                else:
                    cur = getattr(cur, name, None)
                    if cur is None:
                        raise VarLookupError(
                            f"对象「{root}」没有属性「{name}」")
            elif token.startswith("[") and token.endswith("]"):
                inner = token[1:-1].strip()
                if inner.startswith(("'", '"')) and inner.endswith(("'", '"')):
                    idx = inner[1:-1]
                else:
                    # 方括号里是变量名（如 {{dict[item]}}）→ 先解析变量
                    if inner in self.vars:
                        idx = self.vars[inner]
                    else:
                        try:
                            idx = int(inner)
                        except ValueError:
                            idx = inner
                if isinstance(cur, (list, tuple)):
                    try:
                        cur = cur[idx]
                    except (IndexError, TypeError) as exc:
                        raise VarLookupError(
                            f"列表「{root}」索引「{idx}」越界（长度 {len(cur)}）") from exc
                elif isinstance(cur, dict):
                    if idx not in cur:
                        raise VarLookupError(
                            f"字典「{root}」中不存在键「{idx}」（当前可用键：{list(cur.keys())}）")
                    cur = cur[idx]
                else:
                    raise VarLookupError(
                        f"无法对「{root}」使用索引「{idx}」：当前值不是列表或字典（类型 {type(cur).__name__}）")
            else:
                raise VarLookupError(f"未知的路径片段「{token}」")
            if cur is None:
                return None
        return cur

    @staticmethod
    def _tokenize_path(s: str) -> List[str]:
        """把路径字符串切分成 token 列表：'a.b[0]' → ['a', '.b', '[0]']。"""
        tokens: List[str] = []
        i = 0
        while i < len(s):
            if s[i] == ".":
                j = i + 1
                while j < len(s) and s[j] not in ".[":
                    j += 1
                tokens.append(s[i:j])
                i = j
            elif s[i] == "[":
                j = i + 1
                depth = 1
                while j < len(s) and depth > 0:
                    if s[j] == "[":
                        depth += 1
                    elif s[j] == "]":
                        depth -= 1
                    j += 1
                tokens.append(s[i:j])
                i = j
            else:
                j = i + 1
                while j < len(s) and s[j] not in ".[":
                    j += 1
                tokens.append(s[i:j])
                i = j
        return tokens

    # ------------------------------------------------------------ 插值
    def resolve(self, text: Any, default: str = "") -> str:
        """把字符串里的 {{变量}} 替换成实际值。

        整串就是单个 {{...}} 且 lookup 失败时，直接抛出 VarLookupError，
        让引擎把错误停在具体节点；混合文本中找不到的变量仍替换为空字符串。
        """
        if text is None:
            return default
        if not isinstance(text, str):
            return str(text)
        if "{{" not in text:
            return text

        # 整串为单个 {{...}} 时做严格检查
        single = VAR_PATTERN.fullmatch(text.strip())
        if single:
            val = self.lookup(single.group(1))
            return "" if val is None else str(val)

        def _sub(m: "re.Match[str]") -> str:
            val = self.lookup(m.group(1))
            return "" if val is None else str(val)

        return VAR_PATTERN.sub(_sub, text)

    def resolve_value(self, text: Any) -> Any:
        """整串就是单个 {{变量}} 时，返回原始类型（数字/列表/字典）。

        lookup 失败时抛出 VarLookupError。
        """
        if isinstance(text, str):
            m = VAR_PATTERN.fullmatch(text.strip())
            if m:
                return self.lookup(m.group(1))
        return self.resolve(text)

    # ------------------------------------------------------------ 条件求值
    def eval_condition(self, expr: str, fallback: bool = False) -> bool:
        """求值条件表达式。先做变量插值，再做受限 eval。

        支持中英混写::

            {{count}} > 5
            {{存在}} == True
            {{名称}} 包含 "订单"  并且  {{count}} >= 3
            价格 不等于 0 或者 价格 大于 100
        """
        if expr is None:
            return fallback
        raw = str(expr).strip()
        if not raw:
            return fallback

        low = raw.lower()
        if low in ("true", "1", "真", "yes", "是"):
            return True
        if low in ("false", "0", "假", "no", "否"):
            return False

        cooked = (raw.replace("并且", " and ").replace("或者", " or ")
                     .replace("不包含", " not in ").replace("包含", " in ")
                     .replace("不等于", " != ").replace("等于", " == ")
                     .replace("大于等于", " >= ").replace("小于等于", " <= ")
                     .replace("大于", " > ").replace("小于", " < ")
                     .replace("非", " not "))

        text = self.resolve(cooked)
        text = text.replace("真", "True").replace("假", "False")
        # 允许裸变量名（不带 {{}}）直接引用数值
        for k, v in sorted(self.vars.items(), key=lambda kv: -len(kv[0])):
            if isinstance(v, (int, float)) and re.search(rf"\b{re.escape(k)}\b", text):
                text = re.sub(rf"\b{re.escape(k)}\b", repr(v), text)

        if not SAFE_CHARS.match(text):
            self._warn(f"条件表达式含非法字符，已按 False 处理: {raw}")
            return fallback
        try:
            return bool(eval(text, {"__builtins__": ALLOWED_BUILTINS}, {}))  # noqa: S307
        except Exception as exc:
            self._warn(f"条件求值失败 [{raw}] → {exc}，按 False 处理")
            return fallback
