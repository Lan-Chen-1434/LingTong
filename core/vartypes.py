"""
AutoRPA - 变量类型系统
========================
变量在界面上有明确类型：字符串 / 数字 / 布尔 / 一维列表 / 二维列表 / 字典 / 表格。

* 字符串、数字、布尔：值直接在参数面板上输入（数字支持运算公式）。
* 一维列表、二维列表、字典、表格：值通过「编辑内容」表格对话框录入，
  在 node.params 里以真正的 list / dict 对象存储（JSON 序列化天然兼容）。

运行时通过 coerce_input() 把界面录入的值转成实际变量对象：
  - 每个单元格的文本都会先做 {{变量}} 插值；
  - 长得像数字的单元格自动转成 int / float，"True"/"False" 转成 bool；
  - 老流程文件里的纯文本（逐行 / "k = v" / JSON）也能被正确解析。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List

# ---------------------------------------------------------------- 类型常量
VT_STRING = "string"      # 字符串
VT_NUMBER = "number"      # 数字（值或运算公式）
VT_BOOL = "bool"          # 布尔（True / False）
VT_LIST1D = "list1d"      # 一维列表
VT_LIST2D = "list2d"      # 二维列表
VT_DICT = "dict"          # 字典
VT_TABLE = "table"        # 表格（list[dict]，与数据表同构）

VT_LABELS: Dict[str, str] = {
    VT_STRING: "字符串",
    VT_NUMBER: "数字",
    VT_BOOL: "布尔",
    VT_LIST1D: "一维列表",
    VT_LIST2D: "二维列表",
    VT_DICT: "字典",
    VT_TABLE: "表格",
}
_LABEL_TO_VT: Dict[str, str] = {v: k for k, v in VT_LABELS.items()}

#: 可供用户选择的类型顺序（下拉框）
VT_ORDER: List[str] = [VT_STRING, VT_NUMBER, VT_BOOL,
                       VT_LIST1D, VT_LIST2D, VT_DICT, VT_TABLE]

#: 需要用「编辑内容」表格对话框录入的类型；其余类型直接内联输入
STRUCTURED_TYPES = (VT_LIST1D, VT_LIST2D, VT_DICT, VT_TABLE)


def label_of(vtype: str) -> str:
    """类型常量 → 中文名；传入中文名时原样返回。"""
    return VT_LABELS.get(vtype, vtype if vtype in _LABEL_TO_VT else VT_LABELS[VT_STRING])


def vtype_of(text: Any) -> str:
    """中文名 / 常量 → 类型常量；无法识别时按字符串处理。"""
    s = str(text or "").strip()
    if s in VT_LABELS:
        return s
    return _LABEL_TO_VT.get(s, VT_STRING)


def default_value(vtype: str) -> Any:
    """各类型的初始值。"""
    return {
        VT_STRING: "",
        VT_NUMBER: "",
        VT_BOOL: True,
        VT_LIST1D: [],
        VT_LIST2D: [[]],
        VT_DICT: {},
        VT_TABLE: [],
    }.get(vtype_of(vtype), "")


# ---------------------------------------------------------------- 文本解析（兼容老流程文件）
def _split_lines(text: str) -> List[str]:
    return [ln.strip() for ln in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if ln.strip()]


def _split_cells(line: str) -> List[str]:
    sep = "\t" if "\t" in line else ","
    return [c.strip() for c in line.split(sep)]


def normalize_value(vtype: str, raw: Any) -> Any:
    """把任意存储形式规整成对应类型的 Python 对象（不做变量插值）。

    编辑器用它读取 node.params；老流程里的纯文本值也能被解析进来。
    """
    vt = vtype_of(vtype)
    if vt == VT_BOOL:
        return coerce_bool(raw)
    if vt in (VT_STRING, VT_NUMBER):
        return "" if raw is None else str(raw)

    # ---- 结构化类型 ----
    if isinstance(raw, str):
        parsed = _parse_structured_text(vt, raw)
        if parsed is not None:
            raw = parsed
        else:
            raw = default_value(vt)

    if vt == VT_LIST1D:
        if isinstance(raw, (list, tuple)):
            return list(raw)
        return [] if raw in (None, "") else [raw]

    if vt == VT_LIST2D:
        if isinstance(raw, (list, tuple)):
            rows = []
            for r in raw:
                rows.append(list(r) if isinstance(r, (list, tuple)) else [r])
            return rows
        return [[]]

    if vt == VT_DICT:
        if isinstance(raw, dict):
            return dict(raw)
        return {}

    if vt == VT_TABLE:
        if isinstance(raw, (list, tuple)):
            out = []
            for r in raw:
                if isinstance(r, dict):
                    out.append(dict(r))
                elif isinstance(r, (list, tuple)):
                    out.append({f"列{i + 1}": c for i, c in enumerate(r)})
                else:
                    out.append({"列1": r})
            return out
        return []

    return raw


def _parse_structured_text(vt: str, text: str) -> Any:
    """把文本解析成结构化对象；解析不了返回 None。

    依次尝试：JSON → 逐行 / 逗号·制表符分隔 / "k = v" 行格式。
    """
    s = str(text or "").strip()
    if not s:
        return default_value(vt)
    try:
        obj = json.loads(s)
        return normalize_value(vt, obj)
    except (ValueError, TypeError):
        pass

    if vt == VT_LIST1D:
        return _split_lines(s)
    if vt == VT_LIST2D:
        return [_split_cells(ln) for ln in _split_lines(s)]
    if vt == VT_DICT:
        d: Dict[str, Any] = {}
        for ln in _split_lines(s):
            if "=" in ln:
                k, v = ln.split("=", 1)
            elif "：" in ln:
                k, v = ln.split("：", 1)
            elif ":" in ln:
                k, v = ln.split(":", 1)
            else:
                continue
            if k.strip():
                d[k.strip()] = v.strip()
        return d
    if vt == VT_TABLE:
        lines = _split_lines(s)
        if not lines:
            return []
        header = _split_cells(lines[0])
        return [dict(zip(header, _split_cells(ln))) for ln in lines[1:]]
    return None


# ---------------------------------------------------------------- 运行时求值
_TRUE_WORDS = {"1", "true", "yes", "on", "是", "真"}
_FALSE_WORDS = {"0", "false", "no", "off", "否", "假", ""}


def coerce_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    s = str(raw or "").strip().lower()
    if s in _TRUE_WORDS:
        return True
    if s in _FALSE_WORDS:
        return False
    return bool(s)


_NUM_EXPR_SAFE = re.compile(r"^[\d\s+\-*/%().]*$")
_INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def _tidy(v: float) -> Any:
    return int(v) if float(v).is_integer() else v


def coerce_number(raw: Any, resolve: Callable[[Any], str]) -> Any:
    """数字：支持直接数值与运算公式（如 {{count}} + 1、(3+2)*4）。"""
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, (int, float)):
        return _tidy(float(raw))
    text = resolve(str(raw or "")).strip()
    if not text:
        return 0
    if _NUM_EXPR_SAFE.match(text):
        try:
            return _tidy(float(eval(text, {"__builtins__": {}}, {})))  # noqa: S307
        except Exception:
            pass
    try:
        return _tidy(float(text.replace(",", "")))
    except ValueError:
        raise RuntimeError(f"数字格式不正确：「{raw}」（可填数值或运算公式）")


def _auto_scalar(text: str) -> Any:
    """单元格文本 → 自动类型：整数 / 小数 / 布尔 / 原样字符串。"""
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    if text == "True":
        return True
    if text == "False":
        return False
    return text


def _deep_resolve(obj: Any, resolve: Callable[[Any], str]) -> Any:
    """结构化值递归处理：字符串做 {{变量}} 插值 + 自动类型转换。"""
    if isinstance(obj, str):
        return _auto_scalar(resolve(obj))
    if isinstance(obj, list):
        return [_deep_resolve(v, resolve) for v in obj]
    if isinstance(obj, tuple):
        return [_deep_resolve(v, resolve) for v in obj]
    if isinstance(obj, dict):
        return {str(resolve(k)): _deep_resolve(v, resolve) for k, v in obj.items()}
    return obj


def coerce_input(vtype: str, raw: Any, resolve: Callable[[Any], str],
                 resolve_value: Callable[[Any], Any] = None) -> Any:
    """把界面录入的值转换为运行时变量对象。

    resolve       = ctx.resolve（文本插值）
    resolve_value = ctx.resolve_value（整串单变量引用时保留原始类型），仅字符串类型用。
    """
    vt = vtype_of(vtype)
    if vt == VT_STRING:
        if resolve_value is not None and isinstance(raw, str):
            return resolve_value(raw)
        return raw if not isinstance(raw, str) else resolve(raw)
    if vt == VT_NUMBER:
        return coerce_number(raw, resolve)
    if vt == VT_BOOL:
        if isinstance(raw, str):
            raw = resolve(raw)
        return coerce_bool(raw)
    # 结构化：先规整（兼容老文本），再逐格插值与自动转型
    return _deep_resolve(normalize_value(vt, raw), resolve)


# ---------------------------------------------------------------- 展示辅助
def brief(vtype: str, value: Any) -> str:
    """「编辑内容」按钮旁的摘要，如 "3 行 × 2 列" / "共 4 项"。"""
    vt = vtype_of(vtype)
    try:
        if vt == VT_LIST1D:
            return f"共 {len(value or [])} 项"
        if vt == VT_LIST2D:
            rows = value or []
            cols = max((len(r) for r in rows), default=0)
            return f"{len(rows)} 行 × {cols} 列"
        if vt == VT_DICT:
            return f"共 {len(value or {})} 个键"
        if vt == VT_TABLE:
            rows = value or []
            cols = max((len(r) for r in rows), default=0)
            return f"{len(rows)} 行 × {cols} 列"
    except TypeError:
        pass
    s = str(value)
    return s if len(s) <= 18 else s[:18] + "…"
