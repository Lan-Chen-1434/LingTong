"""
AutoRPA - 模块规格定义
========================
每个"功能积木"都由一个 ModuleSpec 描述：它叫什么、属于哪个分类、需要哪些参数。
UI 侧根据 Param 列表自动渲染出参数表单，无需为每个模块手写界面。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------- 参数类型常量
P_TEXT = "text"          # 单行文本
P_TEXTAREA = "textarea"  # 多行文本
P_NUMBER = "number"      # 整数
P_FLOAT = "float"        # 小数
P_BOOL = "bool"          # 开关
P_SELECT = "select"      # 下拉选择
P_IMAGE = "image"        # 模板图片（可多张，支持"截图取图"）
P_KEY = "key"            # 快捷键录制
P_FILE = "file"          # 文件路径
P_FOLDER = "folder"      # 目录路径
P_COLOR = "color"        # 颜色（十六进制）
P_CODE = "code"          # 表达式 / 变量
P_REGION = "region"      # 屏幕区域（X/Y/宽/高 四栏 + 框选按钮）


@dataclass
class Param:
    """一个模块参数的描述。"""

    name: str
    label: str
    ptype: str = P_TEXT
    default: Any = ""
    choices: Optional[List[str]] = None
    minimum: float = -1.0e9
    maximum: float = 1.0e9
    step: float = 1.0
    help: str = ""
    placeholder: str = ""
    suffix: str = ""                       # 单位后缀，如 "秒" "像素"
    visible_when: Optional[Dict[str, List[str]]] = None   # {"mode": ["图像"]} 条件显示
    multiline: bool = False
    allow_empty: bool = True               # P_REGION：是否允许留空（空 = 全屏）
    browse_mode: str = ""                  # "file" / "folder" / "save" —— P_TEXT 也可带浏览按钮
    picker: str = ""                       # "pixel" = 参数行带「拾取坐标和颜色」按钮（拾取后回填兄弟参数）

    def coerce(self, value: Any) -> Any:
        """把界面上的原始输入转换成运行时需要的类型。"""
        try:
            if self.ptype == P_NUMBER:
                return int(float(value))
            if self.ptype == P_FLOAT:
                return float(value)
            if self.ptype == P_BOOL:
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on", "是")
                return bool(value)
            if self.ptype == P_IMAGE:
                if isinstance(value, (list, tuple)):
                    return [str(v) for v in value if str(v).strip()]
                if value in (None, ""):
                    return []
                return [str(value)]
        except (TypeError, ValueError):
            return self.default
        return value


@dataclass
class VarSlot:
    """模块的输入 / 输出变量声明。

    界面（步骤参数面板）按此渲染「输入变量 / 输出变量」分区：
      - 输入变量：变量名称 + 变量类型 + 值（值编辑器随类型变化）；
      - 输出变量：变量名称 + 变量类型（无值，类型通常为模块固有、不可改）。
    底层数据仍存放在普通 params 里，保存 / 加载 / 老流程文件完全兼容。

    direction   "in" | "out"
    label       变量位的显示名，如 "内容"、"判断结果"
    name_param  存放变量名的参数名（如 save_var）；空 = 不显示变量名称行
    value_param 存放值的参数名（仅输入变量）
    type_param  存放用户所选类型的参数名（类型可编辑时，如设置变量）
    vtype       固定变量类型（core.vartypes 常量），type_param 为空时生效
    vtype_fn    动态类型：fn(node.params) -> vtype，用于结果类型随参数变化的模块
    type_choices 限定类型下拉的选项（中文标签列表）；输出变量想允许自选类型时配合
                type_param 使用（如截图提取内容可选 字符串/表格）
    desc        悬浮说明
    visible_when 条件显示（与 Param.visible_when 同规则）
    """

    direction: str
    label: str
    name_param: str = ""
    value_param: str = ""
    type_param: str = ""
    vtype: str = "string"
    vtype_fn: Optional[Callable[[Dict[str, Any]], str]] = None
    vtype_ctx_fn: Optional[Callable[[Dict[str, Any], Any], str]] = None   # fn(params, flow)
    type_choices: Optional[List[str]] = None    # 限制可选项的中文标签（输出变量类型可选时用）
    desc: str = ""
    visible_when: Optional[Dict[str, List[str]]] = None
    name_is_ref: bool = True

    def param_names(self) -> List[str]:
        """该变量位占用的底层参数（不再出现在「参数设置」分区）。"""
        return [n for n in (self.name_param, self.value_param, self.type_param) if n]

    def current_vtype(self, values: Dict[str, Any], flow: Any = None) -> str:
        """按当前参数（及可选的流程上下文）算出应显示的变量类型。

        type_param 显式选了具体类型 → 以它为准；
        选了「自动…」（或未设置）→ 回退到 vtype_ctx_fn / vtype_fn 动态推导。
        """
        from .vartypes import vtype_of
        if self.type_param:
            raw = str(values.get(self.type_param, "") or "").strip()
            if raw and not raw.startswith("自动"):
                return vtype_of(raw)
        if self.vtype_ctx_fn is not None and flow is not None:
            try:
                return self.vtype_ctx_fn(values, flow)
            except Exception:
                return self.vtype
        if self.vtype_fn is not None:
            try:
                return self.vtype_fn(values)
            except Exception:
                return self.vtype
        if self.type_param:
            raw = str(values.get(self.type_param, "") or "").strip()
            if raw:
                return vtype_of(raw)
        return self.vtype


@dataclass
class ModuleSpec:
    """一个可拖拽功能模块的完整定义。"""

    type_id: str                                  # 唯一标识，如 "image.click"
    name: str                                     # 显示名，如 "图像点击"
    category: str                                 # 分类，如 "图像识别"
    runner: Optional[Callable] = None             # 执行函数 runner(node, ctx)
    params: List[Param] = field(default_factory=list)
    desc: str = ""                                # 一句话说明（悬浮提示）
    badge: str = ""                               # 卡片上显示的 1 个字（兼容老代码）
    glyph: str = ""                               # 矢量图标名（替代 badge，更专业）
    is_block: bool = False                        # 是否为容器节点（循环/条件）
    block_kind: str = ""                          # "loop" | "if" | "try" | "group"
    returns_value: bool = False                   # 是否产出变量给后续步骤用
    var_slots: List[VarSlot] = field(default_factory=list)   # 输入/输出变量声明
    examples: List[str] = field(default_factory=list)        # 使用示例（参数面板展示，可照抄参数值）

    # ---- 便捷方法 ----
    def param(self, name: str) -> Optional[Param]:
        for p in self.params:
            if p.name == name:
                return p
        return None

    def input_slots(self) -> List[VarSlot]:
        return [s for s in self.var_slots if s.direction == "in"]

    def output_slots(self) -> List[VarSlot]:
        return [s for s in self.var_slots if s.direction == "out"]

    def var_param_names(self) -> set:
        """被变量位占用的参数名集合（这些参数不在「参数设置」里重复渲染）。"""
        out: set = set()
        for s in self.var_slots:
            out.update(s.param_names())
        return out

    def defaults(self) -> Dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def visible_params(self, values: Dict[str, Any]) -> List[Param]:
        """按 visible_when 规则过滤出当前应该显示的参数。"""
        out: List[Param] = []
        for p in self.params:
            if not p.visible_when:
                out.append(p)
                continue
            ok = True
            for dep_name, allowed in p.visible_when.items():
                if str(values.get(dep_name, "")) not in [str(a) for a in allowed]:
                    ok = False
                    break
            if ok:
                out.append(p)
        return out

    @property
    def has_error_policy(self) -> bool:
        return any(p.name == "on_error" for p in self.params)

    def summary(self, values: Dict[str, Any]) -> str:
        """生成卡片上显示的一行参数摘要（不含运行控制参数，避免无标签的值引起误读）。"""
        bits: List[str] = []
        for p in self.params:
            if p.name in ("on_error", "retry", "retry_interval"):
                continue
            if p.ptype in (P_IMAGE, P_FILE, P_FOLDER):
                v = values.get(p.name)
                if isinstance(v, list) and v:
                    bits.append(f"{p.label}: {v[0].split('/')[-1].split(chr(92))[-1]}")
                elif v:
                    bits.append(f"{p.label}: {str(v).split('/')[-1].split(chr(92))[-1]}")
            elif p.ptype == P_BOOL:
                continue
            else:
                v = values.get(p.name)
                if v not in (None, "", 0, 0.0):
                    s = str(v)
                    if len(s) > 22:
                        s = s[:22] + "…"
                    bits.append(s)
            if len(bits) >= 3:
                break
        return "  ·  ".join(bits)


# --------------------------------------------------------------- 通用运行控制参数
ERROR_POLICY_PARAMS: List[Param] = [
    Param("on_error", "失败时", P_SELECT, "停止流程",
          choices=["停止流程", "跳过此步", "重试", "重试后跳过"],
          help="该步骤执行失败时的处理：停止流程=立即中断整个流程；跳过此步=忽略错误继续下一步；"
               "重试=按下方次数与间隔重试，仍失败则停止；重试后跳过=重试仍失败则跳过"),
    Param("retry", "重试次数", P_NUMBER, 3, minimum=1, maximum=99,
          suffix="次", visible_when={"on_error": ["重试", "重试后跳过"]},
          help="失败后重试的最大次数"),
    Param("retry_interval", "重试间隔", P_FLOAT, 1.0, minimum=0.0, maximum=600.0,
          suffix="秒", visible_when={"on_error": ["重试", "重试后跳过"]},
          help="两次重试之间等待的秒数，给目标程序留出响应时间；如页面加载慢可设为 2~3"),
    Param("timeout", "超时时间", P_FLOAT, 0.0, minimum=0.0, maximum=9999.0,
          suffix="秒（0=不限）", help="找图等待或操作超时保护"),
]
