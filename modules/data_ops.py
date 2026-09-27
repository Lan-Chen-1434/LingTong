"""变量容器模块组 —— 剪贴板取数、变量运算、数据表攒数据、导出文件。"""
from __future__ import annotations

import csv
import json
import os
import re
from typing import Any, Dict, List

from core.registry import module
from core.spec import (P_BOOL, P_FLOAT, P_NUMBER, P_SELECT, P_TEXT, P_TEXTAREA,
                       Param, VarSlot)
from core import vartypes as vt
from core.vartypes import _tidy


@module(
    "data.set_var", "设置 / 运算变量", "变量容器",
    desc="给变量赋值，或对已有变量做拼接、加减、去空格等运算。变量用 {{名字}} 引用",
    returns_value=True,
    params=[
        Param("name", "变量名", P_TEXT, "my_var", placeholder="英文/数字/下划线",
              help="变量名，后续步骤用 {{变量名}} 引用；只能含英文、数字、下划线，如 my_var"),
        Param("vtype", "变量类型", P_SELECT, "字符串",
              choices=[vt.label_of(t) for t in vt.VT_ORDER],
              help="字符串/数字/布尔直接输入值（数字可写公式，如 {{单价}}*2）；"
                   "列表/字典/表格点「编辑内容」在表格里逐格填写"),
        Param("op", "运算方式", P_SELECT, "赋值",
              choices=["赋值", "追加文本", "数字相加", "数字相减", "转大写",
                       "转小写", "去除首尾空格", "截取(&起始,长度)", "替换文本"],
              help="「赋值」直接写入新值；其余运算基于变量当前值：追加/加减/大小写/去空格无需填值；"
                   "「截取」填 起始,长度（如 2,3，长度留空则取到末尾）；「替换文本」填 原文|查找|替换"),
        Param("value", "值 / 参数", P_TEXTAREA, "", multiline=True,
              placeholder="支持 {{变量}}。替换文本格式：原文|查找|替换",
              help="要赋的值或运算参数，支持 {{变量}} 插值，按所选类型自动转换；"
                   "运算方式非「赋值」时填运算参数（如截取 2,3、替换 原文|查找|替换）"),
        Param("save_prev", "把原值备份为 _prev", P_BOOL, False,
              help="开启：运算前先把变量当前值存入 _prev，可用 {{_prev}} 做新旧对比、"
                   "变化检测；关闭：直接覆盖，不保留旧值"),
    ],
    var_slots=[
        VarSlot("in", "设置变量", name_param="name", value_param="value",
                type_param="vtype", name_is_ref=False,
                desc="变量名称可自定义；值按类型录入——字符串直接写、数字可写公式、"
                     "布尔选 True/False、列表/字典/表格用表格编辑器"),
    ],
    examples=[
        "存文本供后面步骤引用：变量名 my_title、变量类型 字符串、运算方式 赋值、"
        "值 / 参数 订单_{{日期}}",
        "给已有变量累加金额：变量名 total、运算方式 数字相加、值 / 参数 100"
        "（total 当前值需为数字）",
        "去掉抓取文本的首尾空格：变量名 copied、运算方式 去除首尾空格（值 / 参数 留空）",
        "改值前留旧值做对比：运算方式 赋值、值 / 参数 9.9、把原值备份为 _prev 开启",
    ],
)
def _set_var(node, ctx):
    p = node.params
    name = (p.get("name") or "my_var").strip() or "my_var"
    op = str(p.get("op", "赋值"))
    raw = p.get("value", "")
    old = ctx.get_var(name)
    if p.get("save_prev"):
        ctx.set_var("_prev", old)

    if op == "赋值":
        # 按声明的变量类型转换：字符串保留 {{变量}} 引用对象的能力，
        # 数字支持公式，布尔选 True/False，列表/字典/表格逐格插值并自动转型
        ctx.set_var(name, vt.coerce_input(p.get("vtype", "字符串"), raw,
                                          ctx.resolve, ctx.resolve_value))
        ctx.info(f"🔧 变量 {name} = {_brief(ctx.get_var(name))}")
        return

    # 其余运算都基于文本形式进行
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    if op == "追加文本":
        ctx.set_var(name, f"{'' if old is None else old}{ctx.resolve(text)}")
    elif op == "数字相加":
        ctx.set_var(name, _tidy(_num(old) + _num(ctx.resolve(text))))
    elif op == "数字相减":
        ctx.set_var(name, _tidy(_num(old) - _num(ctx.resolve(text))))
    elif op == "转大写":
        ctx.set_var(name, str(old or "").upper())
    elif op == "转小写":
        ctx.set_var(name, str(old or "").lower())
    elif op == "去除首尾空格":
        ctx.set_var(name, str(old or "").strip())
    elif op == "截取(&起始,长度)":
        spec = ctx.resolve(text)
        try:
            start_s, len_s = (spec.split(",") + ["-"])[:2]
            start = int(start_s)
            length = int(len_s) if len_s.strip() not in ("-", "") else None
            s = str(old or "")
            ctx.set_var(name, s[start:] if length is None else s[start:start + length])
        except ValueError:
            raise RuntimeError(f"截取参数格式应为「起始,长度」，当前：{spec}")
    elif op == "替换文本":
        parts = ctx.resolve(text).split("|")
        if len(parts) < 3:
            raise RuntimeError("替换文本格式应为：原文|查找|替换")
        ctx.set_var(name, str(old or "").replace(parts[1], parts[2]))
    ctx.info(f"🔧 变量 {name} = {_brief(ctx.get_var(name))}")


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        try:
            return float(re.sub(r"[^\d.\-]", "", str(v)) or 0)
        except ValueError:
            return 0.0


def _brief(v: Any, n: int = 60) -> str:
    s = str(v)
    return s if len(s) <= n else s[:n] + "…"


@module(
    "data.clipboard_read", "读取剪贴板", "变量容器",
    desc="把剪贴板里的文字读进变量",
    returns_value=True,
    params=[
        Param("save_var", "存入变量", P_TEXT, "clip",
              help="读取到的文本存入该变量，后续步骤用 {{变量名}} 引用"),
        Param("trim", "去除首尾空白", P_BOOL, True,
              help="开启：去掉文本首尾的空格、换行（默认开，避免误带空白）；关闭：原样保存"),
        Param("on_empty", "内容为空时", P_SELECT, "只警告", choices=["只警告", "报错停止"],
              help="剪贴板为空或只有空白时：「只警告」记录后继续执行；「报错停止」中断流程，"
                   "适合必须拿到内容的关键步骤"),
    ],
    var_slots=[
        VarSlot("out", "剪贴板内容", name_param="save_var", vtype=vt.VT_STRING,
                desc="读取到的文本存入该变量"),
    ],
    examples=[
        "把已复制好的内容存进变量：存入变量 order_no、去除首尾空白 开启、内容为空时 只警告",
        "必须拿到内容才继续：存入变量 copied、内容为空时 报错停止（为空会中断流程）",
    ],
)
def _clip_read(node, ctx):
    text = ctx.input.get_clipboard()
    if node.params.get("trim"):
        text = text.strip()
    var = (node.params.get("save_var") or "clip").strip() or "clip"
    ctx.set_var(var, text)
    if not text and node.params.get("on_empty") == "报错停止":
        raise RuntimeError("剪贴板内容为空")
    ctx.info(f"📋 剪贴板读取 {len(text)} 字符 → {{{{{var}}}}}: {_brief(text)}")


@module(
    "data.clipboard_write", "写入剪贴板", "变量容器",
    desc="把文本（可含变量）复制到剪贴板",
    params=[Param("text", "内容", P_TEXTAREA, "", multiline=True,
                  help="要复制到剪贴板的内容，支持 {{变量}} 插值，多行文本原样保留")],
    var_slots=[
        VarSlot("in", "写入内容", value_param="text", vtype=vt.VT_STRING,
                desc="要复制到剪贴板的文本，支持 {{变量}}"),
    ],
    examples=[
        "把拼好的文本复制出去：内容 您好 {{name}}，共 {{count}} 条记录",
        "复制变量值以便粘贴：内容 {{matched}}（配合「键盘」步骤的 Ctrl+V 粘贴）",
    ],
)
def _clip_write(node, ctx):
    text = ctx.resolve(node.params.get("text", ""))
    ctx.input.set_clipboard(text)
    ctx.info(f"📋 已写入剪贴板 {len(text)} 字符")


@module(
    "data.copy_selection", "复制当前选中内容", "变量容器",
    desc="发送 Ctrl+A + Ctrl+C 抓取当前窗口里的全部文字，结果存入变量",
    returns_value=True,
    params=[
        Param("select_all", "先按 Ctrl+A 全选", P_BOOL, True,
              help="开启：先 Ctrl+A 全选当前窗口内容再复制，适合整页抓取；"
                   "关闭：只复制你已手动选中的内容"),
        Param("save_var", "存入变量", P_TEXT, "copied",
              help="抓取到的文本存入该变量，后续步骤用 {{变量名}} 引用"),
        Param("wait", "复制后等待", P_FLOAT, 0.35, minimum=0.05, maximum=10.0, suffix="秒",
              help="复制后等待的秒数，给目标程序留出响应剪贴板的时间；"
                   "太短可能抓到空内容，范围 0.05–10 秒"),
    ],
    var_slots=[
        VarSlot("out", "抓取到的文本", name_param="save_var", vtype=vt.VT_STRING,
                desc="抓取到的文本存入该变量（名称可自定义）"),
    ],
    examples=[
        "抓取当前窗口的全部文字：先按 Ctrl+A 全选 开启、存入变量 page、复制后等待 0.5",
        "只复制已选中的段落：先按 Ctrl+A 全选 关闭、存入变量 copied（先手动选好文本再运行）",
    ],
)
def _copy_selection(node, ctx):
    p = node.params
    ctx.input.set_clipboard("")
    ctx.sleep(0.08)
    if p.get("select_all"):
        ctx.input.select_all()
        ctx.sleep(float(p.get("wait", 0.35) or 0.35))
    ctx.input.copy()
    ctx.sleep(float(p.get("wait", 0.35) or 0.35))
    text = ctx.input.get_clipboard()
    var = (p.get("save_var") or "copied").strip() or "copied"
    ctx.set_var(var, text)
    if not text:
        ctx.warn("未获取到内容（可能没有可复制区域）")
    else:
        ctx.success(f"📋 已抓取 {len(text)} 字符 → {{{{{var}}}}}")


@module(
    "data.from_clipboard", "把剪贴板文本解析成数据", "变量容器",
    desc="把复制来的表格/列表文本按行、制表符解析成数据表，供循环逐条处理",
    returns_value=True,
    params=[
        Param("split", "按什么切分", P_SELECT, "按换行", choices=["按换行", "按换行+制表符(表格)"],
              help="「按换行」每行一项，适合一行一条的清单；「按换行+制表符(表格)」按列拆分，"
                   "适合从 Excel、网页表格复制来的数据"),
        Param("has_header", "首行是表头", P_BOOL, True, visible_when={"split": ["按换行+制表符(表格)"]},
              help="开启：首行作为列名，结果是表格，循环里用 {{item.列名}} 取列；"
                   "关闭：结果是二维列表，用 {{item[0]}} 取列"),
        Param("filter_empty", "过滤空行", P_BOOL, True,
              help="开启：跳过空白行，避免解析出空数据（默认开）；关闭：保留空行"),
        Param("save_var", "存入变量", P_TEXT, "rows",
              help="解析结果存入该变量，类型随切分方式变化：按换行=一维列表、"
                   "表格无表头=二维列表、表格带表头=表格"),
        Param("also_to_table", "同时写入数据表", P_BOOL, False,
              help="开启：除变量外把每条数据追加进「数据表」，可用「遍历数据表」循环处理；"
                   "关闭：只存变量"),
    ],
    var_slots=[
        VarSlot("out", "解析结果", name_param="save_var",
                vtype_fn=lambda p: (vt.VT_LIST1D if p.get("split") == "按换行"
                                    else (vt.VT_TABLE if p.get("has_header") else vt.VT_LIST2D)),
                desc="类型随切分方式：按换行=一维列表；表格+表头=表格；表格无表头=二维列表"),
    ],
    examples=[
        "把从 Excel 复制的表格存成表格：按什么切分 按换行+制表符(表格)、首行是表头 开启、"
        "存入变量 rows（循环里用 {{item.列名}} 取列）",
        "一行一条的清单变列表：按什么切分 按换行、存入变量 names",
        "解析同时攒进数据表供循环：按什么切分 按换行+制表符(表格)、首行是表头 开启、"
        "同时写入数据表 开启",
    ],
)
def _from_clip(node, ctx):
    p = node.params
    text = ctx.input.get_clipboard()
    if not text.strip():
        raise RuntimeError("剪贴板没有内容，请先复制数据")
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    if p.get("filter_empty"):
        lines = [ln for ln in lines if ln.strip()]
    rows: List[Any]
    if p.get("split") == "按换行+制表符(表格)":
        cells = [ln.split("\t") for ln in lines]
        if p.get("has_header") and cells:
            header = [h.strip() for h in cells[0]]
            rows = [dict(zip(header, [c.strip() for c in r])) for r in cells[1:]]
        else:
            rows = [[c.strip() for c in r] for r in cells]
    else:
        rows = [ln.strip() for ln in lines]
    var = (p.get("save_var") or "rows").strip() or "rows"
    ctx.set_var(var, rows)
    if p.get("also_to_table"):
        for r in rows:
            ctx.add_data(r if isinstance(r, dict) else {"内容": r})
    ctx.success(f"📊 解析出 {len(rows)} 条数据 → {{{{{var}}}}}")


@module(
    "data.regex", "正则提取文本", "变量容器",
    desc="从一段文本里按规则提取需要的内容，例如从整页文字里抠出价格、手机号",
    returns_value=True,
    params=[
        Param("source", "源文本", P_TEXTAREA, "{{copied}}", multiline=True,
              help="要从中提取内容的文本，支持 {{变量}} 插值，如 {{copied}} 表示刚抓取的内容"),
        Param("pattern", "正则表达式", P_TEXT, r"(\d+\.\d{2})",
              help="用括号包住要提取的部分。示例：价格 (\\d+\\.\\d{2})、手机号 (1\\d{10})"),
        Param("mode", "取结果", P_SELECT, "第一个", choices=["第一个", "全部(列表)", "拼接成一行"],
              help="「第一个」只取首个匹配，无匹配则为空字符串；「全部(列表)」所有匹配存成一维列表，"
                   "适合逐条循环；「拼接成一行」用空格连成一段文本"),
        Param("save_var", "存入变量", P_TEXT, "matched",
              help="提取结果存入该变量，后续步骤用 {{变量名}} 引用；"
                   "「全部(列表)」时变量是一维列表，其余为字符串"),
    ],
    var_slots=[
        VarSlot("in", "源文本", value_param="source", vtype=vt.VT_STRING,
                desc="要从中提取内容的文本，支持 {{变量}}"),
        VarSlot("out", "提取结果", name_param="save_var",
                vtype_fn=lambda p: (vt.VT_LIST1D if p.get("mode") == "全部(列表)" else vt.VT_STRING),
                desc="「全部(列表)」时为一维列表，其余为字符串"),
    ],
    examples=[
        "从抓取文本里抠出价格：源文本 {{copied}}、正则表达式 (\\d+\\.\\d{2})、"
        "取结果 第一个、存入变量 price",
        "收集全部手机号逐条循环：正则表达式 (1\\d{10})、取结果 全部(列表)、存入变量 phones",
        "把多个匹配拼成一段文字：正则表达式 ([A-Za-z]+)、取结果 拼接成一行、存入变量 words",
    ],
)
def _regex(node, ctx):
    p = node.params
    src = ctx.resolve(p.get("source", ""))
    pattern = str(p.get("pattern", ""))
    if not pattern:
        raise RuntimeError("未填写正则表达式")
    try:
        found = re.findall(pattern, src)
    except re.error as exc:
        raise RuntimeError(f"正则表达式有误：{exc}") from exc
    if found and isinstance(found[0], tuple):
        found = [f[0] for f in found]
    mode = str(p.get("mode", "第一个"))
    if mode == "第一个":
        value: Any = found[0] if found else ""
    elif mode == "全部(列表)":
        value = found
    else:
        value = " ".join(str(f) for f in found)
    var = (p.get("save_var") or "matched").strip() or "matched"
    ctx.set_var(var, value)
    ctx.info(f"🔍 正则匹配到 {len(found)} 项 → {{{{{var}}}}} = {_brief(value)}")


@module(
    "data.export_var", "导出所有变量到文件", "变量容器",
    desc="调试用：把当前全部变量快照写入文件，排查取值问题",
    params=[Param("path", "保存路径", P_TEXT, "output/txt/vars_{{timestamp}}.json", browse_mode="save",
                  help="变量快照（JSON）保存路径：相对路径基于流程所在目录，可用 {{timestamp}} 避免覆盖；"
                       "留空则用 output/txt/vars.json")],
    examples=[
        "排查各变量当前取值：保存路径 留空（默认存到 output/txt/vars.json）",
        "每次运行留一份快照不覆盖旧文件：保存路径 vars_{{timestamp}}.json；绝对路径 "
        "Windows 用 C:/...、macOS 用 /Users/...",
    ],
)
def _export_vars(node, ctx):
    path = ctx.resolve(node.params.get("path") or "output/txt/vars.json")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    safe = {k: (v if isinstance(v, (str, int, float, bool, list, dict, type(None))) else str(v))
            for k, v in ctx.vars.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2, default=str)
    ctx.success(f"🧾 变量快照已导出 → {path}")
