"""通用工具与文件操作模块组 —— 日志、随机延时、系统信息、文件读写。"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import time
from typing import Any, Dict, List

from core.platform import open_path
from core.registry import module
from core.spec import (P_BOOL, P_FLOAT, P_NUMBER, P_SELECT, P_TEXT, P_TEXTAREA,
                       Param, VarSlot)
from core import vartypes as vt


# ==================================================================== 辅助函数

def _cell_to_rc(cell: str):
    """Excel 单元格如 A1 → (col=1, row=1)；B2 → (2,2)；AA10 → (27,10)。"""
    m = re.match(r"^([A-Za-z]+)(\d+)$", str(cell or "").strip())
    if not m:
        return 1, 1
    col_s, row_s = m.groups()
    col = 0
    for c in col_s.upper():
        col = col * 26 + (ord(c) - ord("A") + 1)
    return col, int(row_s)


def _unwrap_braces(text: str) -> str:
    """把 {{name}} 解包成 name。"""
    m = re.match(r"^\{\{\s*([A-Za-z_]\w*)\s*\}\}$", str(text or "").strip())
    return m.group(1) if m else str(text or "").strip()


def _resolve_by_selector(ctx, var_name: str, selector: Any) -> Any:
    """按选择器从变量池取值；selector 为空时返回整个变量。"""
    name = _unwrap_braces(var_name).strip()
    if not name:
        return None
    sel = str(selector or "").strip()
    if not sel:
        return ctx.get_var(name)
    if sel.isdigit():
        expr = f"{{{{{name}[{sel}]}}}}"
    elif sel.startswith((".", "[")):
        expr = f"{{{{{name}{sel}}}}}"
    else:
        expr = f"{{{{{name}.{sel}}}}}"
    return ctx.resolve_value(expr)


def _value_to_text(value: Any, fmt: str = "txt") -> str:
    """把任意变量值格式化为 txt 文本。"""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return "\n".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (list, tuple, dict)):
            # 二维列表 / 表格 → 类似 CSV 的文本
            lines: List[str] = []
            for row in value:
                if isinstance(row, dict):
                    lines.append("\t".join(str(v) for v in row.values()))
                else:
                    lines.append("\t".join(str(c) for c in row))
            return "\n".join(lines)
        return " ".join(str(v) for v in value)
    return str(value)


def _write_excel(path: str, value: Any, fmt: str, start_cell: str,
                 list_direction: str) -> None:
    """把数据写入 Excel（xlsx / xls / csv）。"""
    col0, row0 = _cell_to_rc(start_cell)
    is_csv = fmt == "csv"

    # ---- CSV：直接用 csv 模块 ----
    if is_csv:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            _write_to_sheet(writer, value, list_direction)
        return

    # ---- xlsx / xls ----
    is_xls = fmt == "xls"
    if is_xls:
        try:
            import xlwt
        except ImportError:
            raise RuntimeError(
                "写入 .xls 需要安装 xlwt：pip install xlwt\n"
                "或者改用 .xlsx 格式（推荐）") from None
        book = xlwt.Workbook()
        sheet = book.add_sheet("Sheet1")
        _write_to_xlwt(sheet, value, row0, col0, list_direction)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        book.save(path)
        return

    # xlsx
    try:
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise RuntimeError("写入 .xlsx 需要安装 openpyxl：pip install openpyxl") from None

    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    _write_to_openpyxl(ws, value, row0, col0, list_direction)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    wb.save(path)


def _write_to_sheet(writer, value: Any, list_direction: str) -> None:
    """CSV writer 专用写入。"""
    if isinstance(value, (list, tuple)):
        if not value:
            return
        if isinstance(value[0], dict):
            # 表格
            keys = list(value[0].keys())
            writer.writerow(keys)
            for row in value:
                writer.writerow([row.get(k, "") for k in keys])
        elif isinstance(value[0], (list, tuple)):
            # 二维列表
            for row in value:
                writer.writerow(list(row))
        else:
            # 一维列表
            if list_direction == "横向":
                writer.writerow(list(value))
            else:
                for v in value:
                    writer.writerow([v])
    elif isinstance(value, dict):
        for k, v in value.items():
            writer.writerow([k, v])
    else:
        writer.writerow([value])


def _write_to_openpyxl(ws, value: Any, row0: int, col0: int, list_direction: str) -> None:
    """向 openpyxl worksheet 写入数据。"""
    if isinstance(value, (list, tuple)):
        if not value:
            return
        if isinstance(value[0], dict):
            keys = list(value[0].keys())
            for j, k in enumerate(keys):
                ws.cell(row=row0, column=col0 + j, value=k)
            for i, row in enumerate(value):
                for j, k in enumerate(keys):
                    ws.cell(row=row0 + 1 + i, column=col0 + j, value=row.get(k, ""))
        elif isinstance(value[0], (list, tuple)):
            for i, row in enumerate(value):
                for j, v in enumerate(row):
                    ws.cell(row=row0 + i, column=col0 + j, value=v)
        else:
            if list_direction == "横向":
                for j, v in enumerate(value):
                    ws.cell(row=row0, column=col0 + j, value=v)
            else:
                for i, v in enumerate(value):
                    ws.cell(row=row0 + i, column=col0, value=v)
    elif isinstance(value, dict):
        ws.cell(row=row0, column=col0, value=str(value))
    else:
        ws.cell(row=row0, column=col0, value=value)


def _write_to_xlwt(sheet, value: Any, row0: int, col0: int, list_direction: str) -> None:
    """向 xlwt worksheet 写入数据。"""
    if isinstance(value, (list, tuple)):
        if not value:
            return
        if isinstance(value[0], dict):
            keys = list(value[0].keys())
            for j, k in enumerate(keys):
                sheet.write(row0 - 1, col0 - 1 + j, k)
            for i, row in enumerate(value):
                for j, k in enumerate(keys):
                    sheet.write(row0 + i, col0 - 1 + j, row.get(k, ""))
        elif isinstance(value[0], (list, tuple)):
            for i, row in enumerate(value):
                for j, v in enumerate(row):
                    sheet.write(row0 - 1 + i, col0 - 1 + j, v)
        else:
            if list_direction == "横向":
                for j, v in enumerate(value):
                    sheet.write(row0 - 1, col0 - 1 + j, v)
            else:
                for i, v in enumerate(value):
                    sheet.write(row0 - 1 + i, col0 - 1, v)
    elif isinstance(value, dict):
        sheet.write(row0 - 1, col0 - 1, str(value))
    else:
        sheet.write(row0 - 1, col0 - 1, value)


def _read_excel(path: str, fmt: str):
    """读取 Excel，返回 (data, is_single_row_or_col)。"""
    if fmt == "xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise RuntimeError("读取 .xlsx 需要 openpyxl：pip install openpyxl") from None
        wb = load_workbook(path, data_only=True)
        ws = wb.active
        if ws is None:
            return [], True
        rows: List[List[Any]] = []
        for r in ws.iter_rows(values_only=True):
            rows.append(list(r))
        return _excel_rows_to_data(rows)

    if fmt == "xls":
        try:
            import xlrd
        except ImportError:
            raise RuntimeError("读取 .xls 需要 xlrd：pip install xlrd") from None
        book = xlrd.open_workbook(path)
        sheet = book.sheet_by_index(0)
        rows: List[List[Any]] = []
        for i in range(sheet.nrows):
            rows.append([sheet.cell_value(i, j) for j in range(sheet.ncols)])
        return _excel_rows_to_data(rows)

    if fmt == "csv":
        rows: List[List[Any]] = []
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for r in reader:
                rows.append(r)
        return _excel_rows_to_data(rows)

    return [], True


def _excel_rows_to_data(rows: List[List[Any]]):
    """把原始行列表转成智能结构：多行+多列 → table；单行/单列 → list1d。"""
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        return [], True
    # 只有一行 → 一维列表
    if len(rows) == 1:
        return rows[0], True
    # 只有一列 → 一维列表
    if all(len(r) == 1 for r in rows):
        return [r[0] for r in rows], True
    # 多行多列：尝试把第一行当表头 → table（list[dict]）
    header = [str(c).strip() for c in rows[0]]
    out = []
    for r in rows[1:]:
        d = {}
        for i, h in enumerate(header):
            d[h] = r[i] if i < len(r) else ""
        out.append(d)
    return out, False


def _detect_format(path: str) -> str:
    """按扩展名自动检测文件格式。"""
    ext = os.path.splitext(path)[1].lower()
    mapping = {
        ".txt": "txt", ".json": "json",
        ".csv": "csv", ".xlsx": "xlsx", ".xls": "xls",
    }
    return mapping.get(ext, "txt")


def _derive_read_vtype(params: Dict[str, Any], flow=None) -> str:
    """根据读取格式推导输出变量类型。"""
    fmt = str(params.get("format", "自动检测")).lower()
    if fmt == "自动检测":
        fmt = _detect_format(str(params.get("path", "")))
    if fmt in ("xlsx", "xls", "csv"):
        # Excel 格式在运行时才知是单行还是多行，默认先标 table
        return vt.VT_TABLE
    if fmt == "json":
        return vt.VT_DICT
    return vt.VT_STRING


# ==================================================================== 模块定义

@module(
    "util.log", "输出日志", "通用工具",
    desc="在运行日志里打印一条自定义信息，方便观察流程走到哪、变量取值对不对",
    params=[
        Param("level", "级别", P_SELECT, "信息", choices=["信息", "成功", "警告", "错误"],
              help="日志在面板里的颜色与筛选级别：信息=普通记录；成功=标绿，用于关键完成节点；"
                   "警告=标黄，提示有异常但未中断；错误=标红表示出错（流程仍会继续）"),
        Param("message", "内容", P_TEXTAREA, "", multiline=True,
              help="要打印的内容，支持 {{变量}} 插值与取值语法，如 {{表格[0]['名称']}}；"
                   "常用于标记流程节点、核对变量取值",
              placeholder="支持 {{变量}} 与取值语法：\n"
                          "列表第 N 项 → {{列表[0]}}（从 0 开始）\n"
                          "字典某 Key → {{字典['名称']}} 或 {{字典.名称}}\n"
                          "循环当前项 → {{item}} / {{item.列名}} / {{来源[item]}}"),
    ],
    var_slots=[
        VarSlot("in", "日志内容", value_param="message", vtype=vt.VT_STRING,
                desc="要打印的文本。取值语法（同 Python）：列表 {{列表[0]}} 按序号（从 0 开始）；"
                     "字典 {{字典['Key']}} 或 {{字典.Key}}；嵌套可组合如 {{表格[2]['价格']}}"),
    ],
    examples=[
        "标记流程节点：级别 信息、内容 「开始处理订单」",
        "核对变量取值：级别 成功、内容 「共读取 {{rows}} 行数据」",
        "出错时标红但不中断流程：级别 错误、内容 「登录失败：{{err_msg}}」",
    ],
)
def _log(node, ctx):
    msg = ctx.resolve(node.params.get("message", ""))
    level = str(node.params.get("level", "信息"))
    {"信息": ctx.info, "成功": ctx.success,
     "警告": ctx.warn, "错误": ctx.error}.get(level, ctx.info)(f"📝 {msg}")


@module(
    "util.random_delay", "随机延时", "通用工具",
    desc="在区间内取一个随机等待时间，让自动化节奏更接近真人操作",
    params=[
        Param("min_s", "最短", P_FLOAT, 0.5, minimum=0.0, maximum=3600.0, suffix="秒",
              help="随机等待区间的下限，单位秒，最小 0（表示不额外等待）；"
                   "若与「最长」填反（最短>最长）会自动交换两者"),
        Param("max_s", "最长", P_FLOAT, 2.0, minimum=0.0, maximum=3600.0, suffix="秒",
              help="随机等待区间的上限，单位秒，最大 3600；实际等待时间在「最短」与「最长」之间"
                   "均匀随机取值，让节奏更像真人操作"),
    ],
    examples=[
        "模拟真人点击节奏：最短 0.5、最长 2.0（每次随机等 0.5~2 秒）",
        "需要约 2 秒的等待：最短 1.8、最长 2.2；"
        "最短和最长填反了也会自动交换，不会报错",
    ],
)
def _random_delay(node, ctx):
    lo = float(node.params.get("min_s", 0.5) or 0.0)
    hi = float(node.params.get("max_s", 2.0) or 0.0)
    if hi < lo:
        lo, hi = hi, lo
    t = random.uniform(lo, hi)
    ctx.sleep(t)
    ctx.debug(f"⏱ 随机等待 {t:.2f} 秒")


@module(
    "util.read_file", "读取文件", "文件操作",
    desc="读取本地文件内容，自动按格式解析成变量（Excel→表格/列表，JSON→字典，TXT→字符串）",
    returns_value=True,
    params=[
        Param("path", "文件路径", P_TEXT, "", browse_mode="file",
              help="要读取的文件路径，支持 {{变量}}；相对路径基于本流程文件夹，"
                   "建议点右侧 … 浏览选择，避免手写出错",
              placeholder="点击右侧 … 选择文件"),
        Param("format", "文件格式", P_SELECT, "自动检测",
              choices=["自动检测", "txt", "csv", "xlsx", "xls", "json"],
              help="自动检测按扩展名判断（.txt/.json/.csv/.xlsx/.xls）也可手动指定；"
                   "解析结果不同：txt→字符串，json→字典，Excel/csv→表格（多行）或一维列表（单行/单列）"),
        Param("encoding", "编码", P_SELECT, "utf-8", choices=["utf-8", "gbk", "utf-8-sig"],
              help="文本文件编码：utf-8 最常用；gbk 适合老款中文软件导出的文件；"
                   "utf-8-sig 适合带 BOM 的 UTF-8（如 Excel 另存生成的 csv）"),
        Param("save_var", "存入变量", P_TEXT, "file_content",
              help="读取结果存入的变量名，后续用 {{变量名}} 引用，如 {{file_content}}；"
                   "Excel 表格数据可按 {{变量名[0]['列名']}} 取值"),
    ],
    var_slots=[
        VarSlot("out", "文件内容", name_param="save_var",
                vtype_ctx_fn=_derive_read_vtype,
                desc="txt=字符串；json=字典；Excel/csv=多行字典列表，单行一维列表"),
    ],
    examples=[
        "读取 Excel 表格：文件路径 C:/数据/名单.xlsx（Windows）、"
        "/Users/你/名单.xlsx（macOS）、存入变量 rows",
        "读取 JSON 配置：文件路径 config.json、文件格式 json、存入变量 cfg，"
        "用 {{cfg['url']}} 取值",
        "读取老款中文软件导出的表格：文件格式 csv、编码 gbk，"
        "存入变量 rows",
    ],
)
def _read_file(node, ctx):
    p = node.params
    path = ctx.resolve(p.get("path") or "").strip()
    if not path:
        raise RuntimeError("未指定文件路径")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    if not os.path.isfile(path):
        raise RuntimeError(f"文件不存在：{path}")

    fmt = str(p.get("format", "自动检测")).lower()
    if fmt == "自动检测":
        fmt = _detect_format(path)

    var = (p.get("save_var") or "file_content").strip() or "file_content"
    encoding = str(p.get("encoding", "utf-8"))

    if fmt == "txt":
        with open(path, "r", encoding=encoding, errors="replace") as f:
            text = f.read()
        ctx.set_var(var, text)
        ctx.success(f"📄 已读取文本 {path}（{len(text)} 字符）→ {{{{{var}}}}}")
        return

    if fmt == "json":
        with open(path, "r", encoding=encoding, errors="replace") as f:
            data = json.load(f)
        ctx.set_var(var, data)
        ctx.success(f"📄 已读取 JSON {path} → {{{{{var}}}}}")
        return

    # csv / xlsx / xls
    data, is_single = _read_excel(path, fmt)
    ctx.set_var(var, data)
    type_label = "一维列表" if is_single else "表格"
    ctx.success(f"📄 已读取 {fmt.upper()} {path}（{type_label} {len(data)} 行/项）→ {{{{{var}}}}}")


@module(
    "util.write_file", "写入文件", "文件操作",
    desc="把变量写入文件，支持 txt / csv / xlsx / xls / json 多种格式",
    params=[
        Param("path", "文件路径", P_TEXT, "output/excel/result.xlsx", browse_mode="save",
              help="保存路径，支持 {{变量}}；相对路径基于本流程文件夹，"
                   "不存在的目录会自动创建，已存在的文件会被覆盖",
              placeholder="支持 {{变量}}，点击右侧 … 选择保存位置"),
        Param("format", "输出格式", P_SELECT, "xlsx",
              choices=["txt", "csv", "xlsx", "xls", "json"],
              help="txt=纯文本；csv=逗号分隔；xlsx/xls=Excel；json=JSON（仅支持字典）"),
        Param("start_cell", "起始单元格", P_TEXT, "A1",
              visible_when={"format": ["csv", "xlsx", "xls"]},
              placeholder="如 A1、B2",
              help="数据从该单元格开始填充，一维列表默认横向扩展"),
        Param("list_direction", "一维列表填充方向", P_SELECT, "横向",
              choices=["横向", "纵向"],
              visible_when={"format": ["csv", "xlsx", "xls"]},
              help="一维列表的填充方向：横向=每个元素占一格往右排，适合写表头行；"
                   "纵向=每个元素独占一行，适合写序号列；二维列表与表格不受此选项影响"),
        Param("input_var", "写入变量", P_TEXT, "rows",
              help="要写入的变量名，如 rows（配合下方「写入内容」变量槽）"),
        Param("input_selector", "取值路径", P_TEXT, "",
              help="从变量里取一部分写入：留空输出整个变量；填 key 名取字典某键，"
                   "如 名称；填序号取列表某项，如 [0]（序号从 0 开始）",
              placeholder="可留空（输出整个变量）或填 key 名、[0] 取局部值"),
        Param("input_vtype", "变量类型", P_SELECT, "自动",
              choices=["自动", "字符串", "数字", "布尔", "一维列表", "二维列表",
                       "字典", "表格"],
              help="要写入的变量类型；「自动」按流程里声明的变量类型处理"),
    ],
    var_slots=[
        VarSlot("in", "写入内容",
                name_param="input_var",
                value_param="input_selector",
                type_param="input_vtype",
                desc="变量名称：要输出的变量；"
                     "值：可留空（输出整个变量）或填路径如 key 名、序号 [0] 取局部值"),
    ],
    examples=[
        "把表格存成 Excel：写入变量 rows、输出格式 xlsx、"
        "文件路径 output/结果.xlsx（Windows）、/Users/你/结果.xlsx（macOS）",
        "存 JSON 字典：写入变量 info、输出格式 json、文件路径 output/info.json",
        "一维列表写成表头行：写入变量 names、输出格式 xlsx、起始单元格 A1、"
        "一维列表填充方向 横向（想逐行写就选 纵向）",
    ],
)
def _write_file(node, ctx):
    p = node.params
    path = ctx.resolve(p.get("path") or "").strip()
    if not path:
        raise RuntimeError("未指定文件路径")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    fmt = str(p.get("format", "txt")).lower()
    var_name = _unwrap_braces(p.get("input_var", "")).strip()
    if not var_name:
        raise RuntimeError("未指定输入变量")
    selector = p.get("input_selector", "")
    value = _resolve_by_selector(ctx, var_name, selector)
    if value is None:
        raise RuntimeError(f"变量「{var_name}」未定义或选择器「{selector}」取不到值")

    if fmt == "json":
        if not isinstance(value, dict):
            raise RuntimeError(f"JSON 格式仅支持字典变量，当前类型：{type(value).__name__}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        ctx.success(f"📝 已写入 JSON {path}")
        return

    if fmt == "txt":
        text = _value_to_text(value)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        ctx.success(f"📝 已写入文本 {path}（{len(text)} 字符）")
        return

    # csv / xlsx / xls
    start_cell = str(p.get("start_cell", "A1") or "A1").strip()
    list_direction = str(p.get("list_direction", "横向"))
    _write_excel(path, value, fmt, start_cell, list_direction)
    ctx.success(f"📝 已写入 {fmt.upper()} {path}")


@module(
    "util.open_folder", "打开文件夹", "文件操作",
    desc="在系统文件管理器中打开目录，例如流程结束后打开输出目录查看结果",
    params=[
        Param("path", "目录", P_TEXT, "output", browse_mode="folder",
              help="相对路径基于本流程文件夹；默认 output 为流程的输出目录"),
    ],
    examples=[
        "流程结束打开结果目录：目录 output（相对本流程文件夹，会自动创建）",
        "打开系统里的指定目录（Windows）：目录 C:/报告/2026；"
        "macOS：目录 /Users/你/Documents",
    ],
)
def _open_folder(node, ctx):
    path = ctx.resolve(node.params.get("path") or "output")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    os.makedirs(path, exist_ok=True)
    open_path(path)
    ctx.info(f"📂 已打开文件夹 {path}")


@module(
    "util.system_info", "获取系统信息", "通用工具",
    desc="读取屏幕分辨率、鼠标位置、活动窗口等环境信息存入变量",
    returns_value=True,
    params=[Param("save_var", "存入变量", P_TEXT, "sys_info",
                  help="存入的字典变量名，后续用 {{变量名.键}} 引用，"
                       "如 {{sys_info.screen_width}}；留空则默认为 sys_info")],
    var_slots=[
        VarSlot("out", "系统信息", name_param="save_var", vtype=vt.VT_DICT,
                desc="含 screen_width / mouse_x / active_window / time 等键"),
    ],
    examples=[
        "取屏幕分辨率做坐标换算：存入变量 sys_info，"
        "用 {{sys_info.screen_width}}、{{sys_info.screen_height}} 引用",
        "记录当前活动窗口标题：存入变量 sys_info，用 {{sys_info.active_window}}",
    ],
)
def _system_info(node, ctx):
    w, h = ctx.screen.screen_size()
    mx, my = ctx.input.position()
    info = {"screen_width": w, "screen_height": h,
            "mouse_x": mx, "mouse_y": my,
            "active_window": ctx.window.active_title(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    var = (node.params.get("save_var") or "sys_info").strip() or "sys_info"
    ctx.set_var(var, info)
    for k, v in info.items():
        ctx.set_var(f"{var}.{k}", v)
    ctx.info(f"🖥 分辨率 {w}×{h}，鼠标 ({mx},{my})，窗口「{info['active_window']}」")


@module(
    "util.wait_user", "等待用户继续", "通用工具",
    desc="弹窗等待人工确认后继续，用于验证码、扫码等需要人介入的环节",
    params=[
        Param("message", "提示文字", P_TEXT, "请完成人工操作后点击确定",
              help="弹窗里显示的提示文字，支持 {{变量}} 插值；"
                   "用于扫码、验证码、人工确认等需要人介入的环节"),
    ],
    examples=[
        "扫码登录环节：提示文字 「请用手机扫码登录后再点确定」",
        "人工核对后再继续：提示文字 「请核对第 {{num}} 条数据，无误后点确定」",
    ],
)
def _wait_user(node, ctx):
    msg = ctx.resolve(node.params.get("message", ""))
    try:
        import pyautogui
        pyautogui.confirm(text=msg, title="灵瞳 等待中", buttons=["继续"])
    except Exception:
        ctx.sleep(2.0)
    ctx.info("👤 用户已确认，继续执行")


_TIME_FORMATS = {
    "日期（2026-09-26）": "%Y-%m-%d",
    "时间（17:31:50）": "%H:%M:%S",
    "日期时间（2026-09-26 17:31:50）": "%Y-%m-%d %H:%M:%S",
    "紧凑日期（20260926）": "%Y%m%d",
    "紧凑时间（173150）": "%H%M%S",
    "中文日期（2026年09月26日）": "%Y年%m月%d日",
    "时间戳（整数秒）": "__timestamp__",
}


@module(
    "util.current_time", "获取当前时间", "通用工具",
    desc="按选好的格式把当前日期/时间写入变量，常用于拼文件名、记录运行时间",
    returns_value=True,
    params=[
        Param("fmt", "时间格式", P_SELECT, "日期时间（2026-09-26 17:31:50）",
              choices=list(_TIME_FORMATS.keys()),
              help="直接选一种常用格式即可，不用手写格式代码"),
        Param("save_var", "存入变量", P_TEXT, "now_time",
              help="写入的变量名，值为按所选格式生成的日期/时间文本，"
                   "常用于拼文件名，如 report_{{now_time}}.xlsx"),
    ],
    var_slots=[
        VarSlot("out", "当前时间", name_param="save_var", vtype=vt.VT_STRING,
                desc="按所选格式写入的日期/时间文本"),
    ],
    examples=[
        "拼不重复的文件名：时间格式 紧凑日期（20260926）、存入变量 now_time，"
        "写入文件路径填 report_{{now_time}}.xlsx",
        "记录运行时刻：时间格式 日期时间（2026-09-26 17:31:50）、存入变量 run_time",
    ],
)
def _current_time(node, ctx):
    fmt = str(node.params.get("fmt", ""))
    code = _TIME_FORMATS.get(fmt, "%Y-%m-%d %H:%M:%S")
    value = str(int(time.time())) if code == "__timestamp__" else time.strftime(code)
    var = (node.params.get("save_var") or "now_time").strip() or "now_time"
    ctx.set_var(var, value)
    ctx.info(f"🕒 当前时间 {value} → {{{{{var}}}}}")
