"""流程控制模块组 —— 循环、条件、异常捕获、子流程、流程跳转。"""
from __future__ import annotations

import os
import re

from core.exceptions import BreakLoop, ContinueLoop, RunAborted
from core.registry import module
from core.spec import (P_BOOL, P_FLOAT, P_NUMBER, P_SELECT, P_TEXT, P_TEXTAREA,
                       Param, VarSlot)
from core import vartypes as vt


def _iter_all_nodes(nodes):
    """深度优先遍历全部节点（不依赖 Flow.walk，兼容任意嵌套）。"""
    for n in nodes:
        if n is None:
            continue
        yield n
        kids = getattr(n, "children", None)
        if kids:
            yield from _iter_all_nodes(kids)


def _flow_var_types(flow) -> dict:
    """收集流程里所有「设置 / 运算变量」节点声明的变量类型（变量名 → 类型标签）。"""
    out: dict = {}
    if flow is None:
        return out
    try:
        nodes = list(_iter_all_nodes(getattr(flow, "nodes", []) or []))
    except (TypeError, AttributeError):
        return out
    for n in nodes:
        if getattr(n, "type_id", "") == "data.set_var":
            name = str((getattr(n, "params", None) or {}).get("name") or "").strip()
            if name:
                out.setdefault(name, str((n.params or {}).get("vtype") or "字符串"))
    return out


#: 循环「数据来源」的显式类型选项（「自动」= 跟随流程里声明的变量类型）
_SOURCE_TYPE_CHOICES = ["自动", "字符串", "数字", "布尔",
                        "一维列表", "二维列表", "字典", "表格"]
_AUTO_SENTINEL = "自动"


def _resolved_source_label(params: dict, flow) -> str:
    """来源变量的类型标签：显式选择 > 流程里声明的类型 > 空(未知)。

    「遍历变量」模式下用户可在输入变量里直接选类型（含「自动」）；
    选了具体类型就以此为准，选「自动」才去扫描流程里「设置/运算变量」的声明。
    """
    pick = str(params.get("src_type") or "").strip()
    if pick and not pick.startswith(_AUTO_SENTINEL):
        return pick
    src = str(params.get("dataset") or "").strip()
    m = re.fullmatch(r"\{\{\s*([^{}]+?)\s*\}\}", src)
    if not m:
        return ""
    return _flow_var_types(flow).get(m.group(1).strip(), "")


def _source_item_vtype(params: dict, flow) -> str:
    """根据「数据来源」变量的类型推导循环「当前项」的类型。

    标量类型原样对应：字符串→字符串、数字→数字、布尔→布尔；
    一维列表 → 字符串；二维列表 → 一维列表；
    字典 → 字典（键值对，用 {{item.key}} / {{item.value}} 取值）；
    表格 → 字典；其他/未知 → 字典（数据表行）。
    """
    src_type = _resolved_source_label(params, flow)
    return {
        "字符串": vt.VT_STRING,
        "数字": vt.VT_NUMBER,
        "布尔": vt.VT_BOOL,
        "一维列表": vt.VT_STRING,
        "二维列表": vt.VT_LIST1D,
        "字典": vt.VT_DICT,
        "表格": vt.VT_DICT,
    }.get(src_type, vt.VT_DICT)


def _source_vtype(params: dict, flow) -> str:
    """推导「数据来源」本身的类型：显式选择 > 流程声明 > 默认表格。"""
    label = _resolved_source_label(params, flow)
    known = label in vt.VT_LABELS or label in vt.VT_LABELS.values()
    return vt.vtype_of(label) if known else vt.VT_TABLE


_ITEM_TYPE_TIP = ("输出类型随数据来源自动推导：字符串→字符串、数字→数字、布尔→布尔、"
                  "一维列表→字符串、二维列表→一维列表、"
                  "字典→键值对字典(用 {{item.key}} / {{item.value}} 取值)、表格→字典")


@module(
    "flow.loop", "循环", "流程控制",
    desc="把里面的步骤重复执行：固定次数、遍历变量、按条件循环",
    is_block=True, block_kind="loop",
    params=[
        Param("mode", "循环方式", P_SELECT, "固定次数",
              choices=["固定次数", "遍历变量", "条件循环", "无限循环"],
              help="固定次数=执行指定轮数后自动结束；遍历变量=逐条处理表格、列表、字典"
                   "（如逐行填表单）；条件循环=每轮开始前判断条件，需配合最大次数保护；"
                   "无限循环=一直执行直到遇到「跳出循环」节点"),
        Param("times", "循环次数", P_NUMBER, 3, minimum=1, maximum=100000, suffix="次",
              visible_when={"mode": ["固定次数"]},
              help="循环执行的总轮数，范围 1~100000 次；中途遇到「跳出循环」节点会提前结束"),
        Param("loop_index_name", "序号变量名", P_TEXT, "loop_index",
              help="每轮自动写入当前序号（从1开始），用 {{变量名}} 引用。"
                   "多层嵌套时建议分别设为 i、j、外层序号，避免冲突"),
        Param("dataset", "数据来源", P_TEXT, "{{rows}}",
              visible_when={"mode": ["遍历变量"]},
              help="填变量名（如 {{rows}}）。支持遍历：表格(List[Dict])、字典(遍历Key)、一维列表、二维列表。留空则遍历已抓取的数据表"),
        Param("src_type", "变量类型", P_SELECT, "自动",
              choices=_SOURCE_TYPE_CHOICES,
              visible_when={"mode": ["遍历变量"]},
              help="要遍历的变量类型；「自动」会根据流程里声明的变量类型推导；"
                   "选错类型会取不到值，不确定时保持「自动」即可"),
        Param("item_var", "每项变量名", P_TEXT, "item",
              visible_when={"mode": ["遍历变量"]},
              help="每轮把当前项写入该变量。表格用 {{item.列名}}；"
                   "字典用 {{item.key}} / {{item.value}}；一维列表直接用 {{item}}；"
                   "按Key取值 {{来源[item]}}；按序号取值 {{列表[0]}}"),
        Param("condition", "继续条件", P_TEXT, "{{count}} < 10",
              visible_when={"mode": ["条件循环"]},
              help="每轮开始前判断一次，结果为真才继续循环，如：{{count}} < 10；"
                   "建议同时设置「最大次数保护」避免条件写错造成死循环"),
        Param("max_times", "最大次数保护", P_NUMBER, 200, minimum=1, maximum=100000,
              suffix="次", visible_when={"mode": ["条件循环"]},
              help="循环轮数达到该上限后强制退出，防止条件写错造成死循环；"
                   "确需更多轮时再增大，范围 1~100000 次"),
    ],
    var_slots=[
        VarSlot("in", "数据来源", name_param="dataset", type_param="src_type",
                vtype=vt.VT_TABLE, vtype_ctx_fn=_source_vtype,
                visible_when={"mode": ["遍历变量"]},
                desc="要被遍历的数据。类型可选（自动=跟随流程里声明的变量类型）；"
                     "支持表格、字典、一维列表、二维列表；留空则遍历已抓取的数据表"),
        VarSlot("out", "循环序号", name_param="loop_index_name", vtype=vt.VT_NUMBER,
                desc="每轮自动写入当前序号（从1开始），用 {{变量名}} 引用。"
                     "多层嵌套时建议分别设为 i、j、外层序号，避免冲突"),
        VarSlot("out", "当前项", name_param="item_var", vtype=vt.VT_DICT,
                vtype_ctx_fn=_source_item_vtype,
                visible_when={"mode": ["遍历变量"]},
                desc=_ITEM_TYPE_TIP + "；取值：表格 {{item.列名}}、字典 {{item.key}}/{{item.value}}、"
                     "列表 {{列表[序号]}}、一维列表 {{item}}"),
    ],
    examples=[
        "固定重试 5 次：循环方式 固定次数、循环次数 5、序号变量名 i（用 {{i}} 拿当前轮数）",
        "逐行处理表格：循环方式 遍历变量、数据来源 {{rows}}、变量类型 自动、每项变量名 item，"
        "循环里用 {{item.列名}} 取当前行",
        "条件循环防死循环：循环方式 条件循环、继续条件 {{count}} < 10、最大次数保护 200",
        "一直试直到成功：循环方式 无限循环，循环里「图像识别」成功后用「跳出循环」节点结束",
    ],
)
def _loop(node, ctx):
    """循环体由引擎调度，这里不会被执行到。"""
    raise RuntimeError("循环节点应由引擎处理")


@module(
    "flow.if", "条件判断", "流程控制",
    desc="满足条件才执行里面的步骤；添加时会自动附带「否则」分支",
    is_block=True, block_kind="if",
    params=[
        Param("condition", "条件", P_TEXTAREA, "{{image_found}} == True", multiline=True,
              help="支持 and / or / 并且 / 或者；比较符 > < >= <= == !=；"
                   "也可写 包含 / 不包含。示例：{{price}} < 100 and {{存在}} == True"),
    ],
    examples=[
        "找到图片才执行：条件 {{image_found}} == True",
        "价格区间判断：条件 {{price}} >= 100 and {{price}} <= 500（也支持中文 并且 / 或者）",
    ],
)
def _if(node, ctx):
    raise RuntimeError("条件节点应由引擎处理")


@module(
    "flow.try", "异常捕获", "流程控制",
    desc="里面的步骤出错时不中断流程，而是执行「异常处理」分支里的步骤",
    is_block=True, block_kind="try",
    params=[
        Param("log_error", "捕获时打印错误", P_BOOL, True,
              help="开启：捕获到异常时在运行日志里打印错误原因，便于排查问题；"
                   "关闭：静默吞掉错误，日志里看不到出错信息"),
    ],
    examples=[
        "易错步骤不中断：把「点击、输入」等易错步骤放进本节点，「异常处理」分支里写兜底步骤",
        "静默容错：捕获时打印错误 关闭，出错只跳过、运行日志里不显示错误",
    ],
)
def _try(node, ctx):
    raise RuntimeError("异常捕获节点应由引擎处理")


@module(
    "flow.group", "分组", "流程控制",
    desc="仅用于归类整理，不影响执行顺序；可以折叠起来让流程更清晰",
    is_block=True, block_kind="group",
    params=[
        Param("title", "分组名称", P_TEXT, "步骤组",
              help="分组的显示名称，仅用于界面归类整理，不影响执行顺序；如：公共登录、数据抓取"),
        Param("collapse", "默认折叠", P_BOOL, False,
              help="开启：打开流程时该分组默认折叠收起，只显示标题栏，适合步骤较多的分组；"
                   "关闭：默认展开，显示全部分组内步骤"),
    ],
    examples=[
        "整理长流程：分组名称 数据抓取、默认折叠 开启，打开流程只看标题",
        "仅归类不影响执行：把登录相关步骤拖进本节点，执行顺序完全不变",
    ],
)
def _group(node, ctx):
    """纯分组节点：引擎会直接执行其 children。"""


@module(
    "flow.break", "跳出循环", "流程控制",
    desc="立刻结束当前所在的循环",
    params=[],
    examples=[
        "找到目标就停：循环里「图像识别」成功后接本节点，立即结束当前循环",
        "配合无限循环：循环方式 无限循环，满足条件时用本节点跳出",
    ],
)
def _break(node, ctx):
    ctx.info("⤴ 跳出循环")
    raise BreakLoop()


@module(
    "flow.continue", "继续下一次循环", "流程控制",
    desc="跳过本次循环里剩余的步骤，直接进入下一轮",
    params=[
        Param("condition", "条件(可空)", P_TEXT, "",
              help="留空 = 无条件跳过本次剩余步骤，直接进入下一轮；"
                   "填写后仅在条件成立时才跳过，如：{{index}} >= 5"),
    ],
    examples=[
        "跳过空行：条件(可空) {{item.姓名}} == \"\"（留空则每轮都跳过剩余步骤）",
        "前 5 条不处理：条件(可空) {{loop_index}} <= 5（配合循环的序号变量名）",
    ],
)
def _continue(node, ctx):
    cond = str(node.params.get("condition") or "").strip()
    if cond and not ctx.eval_condition(cond):
        ctx.debug(f"继续条件不成立，不跳过：{cond}")
        return
    ctx.info("⏭ 继续下一次循环")
    raise ContinueLoop()


@module(
    "flow.stop", "结束流程", "流程控制",
    desc="立即终止整个流程（可设置状态消息）",
    params=[
        Param("message", "结束原因", P_TEXT, "流程按要求结束",
              help="结束流程时记录的原因提示，会写入运行日志并显示在流程结果里；"
                   "支持 {{变量}} 插值"),
        Param("as_error", "标记为失败", P_BOOL, False,
              help="开启：以失败状态终止整个流程（状态里带「结束原因」），"
                   "适合校验不通过时中止；关闭：以成功状态正常结束"),
    ],
    examples=[
        "校验失败中止：结束原因 校验未通过：{{msg}}、标记为失败 开启",
        "正常提前收尾：结束原因 全部处理完成、标记为失败 关闭，以成功状态结束",
        "满足条件才结束：在「条件判断」分支里放本节点，不成立则继续后续步骤",
    ],
)
def _stop(node, ctx):
    msg = ctx.resolve(node.params.get("message") or "流程已结束")
    if node.params.get("as_error"):
        raise RunAborted(f"主动终止：{msg}")
    ctx.success(f"⏹ {msg}")
    raise RunAborted(msg)


@module(
    "flow.call", "调用子流程", "流程控制",
    desc="运行另一个流程文件（公共登录、公共清理逻辑可拆出去复用）",
    params=[
        Param("path", "流程文件", P_TEXT, "flows/sub.arpa", placeholder="*.arpa",
              help="要调用的子流程文件：支持相对路径（相对当前流程文件所在目录）"
                   "或绝对路径，如：flows/login.arpa；支持 {{变量}} 插值拼接"),
        Param("share_vars", "共享变量与数据", P_BOOL, True,
              help="开启：子流程与主流程共用同一套变量和数据表，子流程里改的值会带回主流程"
                   "（当前版本始终共用，此开关暂为预留）"),
        Param("fail_fast", "子流程失败则中断", P_BOOL, False,
              help="开启：子流程出错时立即中断主流程并抛出错误；"
                   "关闭：忽略子流程的错误，记录警告后继续执行后续步骤"),
    ],
    examples=[
        "复用登录流程：流程文件 flows/login.arpa；绝对路径 Windows 用 C:/flows/login.arpa、"
        "macOS 用 /Users/你/flows/login.arpa",
        "失败不影响主流程：子流程失败则中断 关闭，出错只记警告继续",
        "按环境拼路径：流程文件 flows/{{env}}/job.arpa（{{env}} 由前面步骤赋值）",
    ],
)
def _call(node, ctx):
    from core.engine import execute_subflow
    from core.models import Flow

    path = ctx.resolve(node.params.get("path") or "")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    if not os.path.isfile(path):
        raise RuntimeError(f"子流程文件不存在：{path}")
    sub = Flow.load(path)
    ctx.info(f"↳ 调用子流程「{sub.name}」（{path}）")
    try:
        execute_subflow(sub, ctx)
        ctx.success(f"✓ 子流程「{sub.name}」执行完成")
    except Exception as exc:                            # noqa: BLE001
        if node.params.get("fail_fast"):
            raise
        ctx.warn(f"子流程「{sub.name}」执行出错：{exc}")


@module(
    "_else", "否则", "流程控制",
    desc="「条件判断」的不成立分支，把步骤拖进它下面",
    is_block=True, block_kind="group",
    params=[],
    examples=[
        "不成立时执行备用步骤：把兜底步骤拖到本节点下（如：没找到图片就刷新重试）",
        "二选一：「条件判断」里放正常步骤，本节点里放异常处理步骤",
    ],
)
def _else(node, ctx):
    """分支分隔节点，由引擎按分支切分。"""


@module(
    "_catch", "异常处理", "流程控制",
    desc="「异常捕获」出错后要执行的步骤，拖到它下面",
    is_block=True, block_kind="group",
    params=[],
    examples=[
        "出错后兜底：把出错后的补救步骤拖到本节点下（如：失败时截图留证）",
        "出错发通知：本节点里放「运行脚本」发消息，Shell 脚本仅 macOS/Linux、"
        "PowerShell 脚本仅 Windows 可用",
    ],
)
def _catch(node, ctx):
    """分支分隔节点，由引擎按分支切分。"""
