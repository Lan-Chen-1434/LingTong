"""进程/程序调用模块组 —— 调用外部程序、脚本、命令行工具。"""
from __future__ import annotations

import os
import re
import shlex
from typing import Any, Dict, List

from core.platform import IS_WIN, normalize_path, run_command
from core.registry import module
from core.spec import P_BOOL, P_FLOAT, P_NUMBER, P_SELECT, P_TEXT, P_TEXTAREA, Param, VarSlot
from core import vartypes as vt


def _split_args(text: str) -> List[str]:
    """把命令行参数字符串拆成列表；空串返回 []。"""
    text = text.strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return [p.strip() for p in text.split() if p.strip()]


def _coerce_output(vtype: str, text: str) -> Any:
    """按所选变量类型把程序输出文本转成变量对象。

    列表/字典/表格优先按 JSON 解析，失败回退逐行 / CSV / "k = v" 文本格式
    （因此 pandas 的 df.to_json(orient='records') 与 df.to_csv() 都能转成表格）；
    回退文本格式解析出的单元格会像界面录入一样自动转成数字 / 布尔。
    """
    t = vt.vtype_of(vtype)
    if t == vt.VT_STRING:
        return text
    if t == vt.VT_BOOL:
        return vt.coerce_bool(text)
    if t == vt.VT_NUMBER:
        s = text.strip().replace(",", "")
        try:
            n = float(s)
        except ValueError:
            raise RuntimeError(
                f"程序输出不是数字：「{text[:40]}」，可在「输出变量」类型改选「字符串」")
        return int(n) if n.is_integer() else n
    return _deep_autotype(vt.normalize_value(t, text))


_INT_CELL = re.compile(r"^-?(0|[1-9]\d*)$")
_FLOAT_CELL = re.compile(r"^-?\d+\.\d+$")


def _deep_autotype(obj: Any) -> Any:
    """把文本解析出的字符串单元格自动转成数字 / 布尔（与界面录入规则一致）。"""
    if isinstance(obj, str):
        s = obj.strip()
        if _INT_CELL.match(s):
            return int(s)
        if _FLOAT_CELL.match(s):
            return float(s)
        if s == "True":
            return True
        if s == "False":
            return False
        return obj
    if isinstance(obj, list):
        return [_deep_autotype(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _deep_autotype(v) for k, v in obj.items()}
    return obj


@module(
    "process.run", "调用程序", "外部调用",
    desc="调用外部可执行程序、批处理脚本或命令行工具，支持等待完成、超时、捕获输出",
    params=[
        Param("program", "程序路径", P_TEXT, "",
              placeholder="可执行文件路径，如 python、notepad、C:/app/run.exe",
              help="要运行的程序：可写系统命令名（python、notepad 等，需能在命令行直接运行），"
                   "也可点右侧「…」选择 .exe / .bat / .ps1 等可执行文件；支持 {{变量}} 拼接路径",
              browse_mode="file"),
        Param("work_dir", "工作目录", P_TEXT, "",
              placeholder="留空使用流程所在目录",
              help="程序启动后所在的文件夹：程序里用相对路径读写文件（如 ./data.txt）都相对于这里；"
                   "留空则使用流程文件（.arpa）所在目录",
              browse_mode="folder"),
        Param("arguments", "命令行参数", P_TEXTAREA, "", multiline=True,
              placeholder="每行一个参数，或用空格分隔",
              help="传给程序的参数，每行一个或用空格分隔；含空格的参数请加引号，如 --name \"张三\"；"
                   "支持 {{变量}} 插值"),
        Param("wait_finish", "等待程序结束", P_BOOL, True,
              help="开启：等程序退出后才执行下一步，能拿到退出码和输出，适合脚本、批处理；"
                   "关闭：程序一启动就继续执行下一步，适合打开记事本、浏览器等不需要结果的程序"),
        Param("timeout", "超时时间", P_NUMBER, 0, minimum=0, maximum=9999, suffix="秒（0=不限）",
              help="等待程序结束的最长时间，超过则报错停止；0 表示不限。仅在「等待程序结束」开启时生效"),
        Param("capture_output", "捕获输出", P_BOOL, False,
              help="开启后程序打印到屏幕的内容存入输出变量；运行出错时的信息在 {{变量名_stderr}}，"
                   "退出码在 {{变量名_code}}"),
        Param("save_var", "输出变量", P_TEXT, "proc_result",
              visible_when={"capture_output": [True]},
              help="存程序输出的变量名，后续步骤用 {{变量名}} 引用；"
                   "另有 {{变量名_code}} 退出码、{{变量名_stderr}} 错误输出"),
        Param("save_type", "输出类型", P_SELECT, "字符串",
              choices=[vt.label_of(t) for t in vt.VT_ORDER],
              visible_when={"capture_output": [True]},
              help="程序输出按该类型解析：选「字符串」为原样文本；选列表/字典/表格时建议程序输出 JSON，"
                   "表格也可输出 CSV 文本（首行表头），如 pandas 的 "
                   "df.to_json(orient='records') 或 df.to_csv(index=False)"),
        Param("hidden", "隐藏窗口", P_BOOL, False,
              visible_when={"wait_finish": [False]},
              help="Windows 下启动时不弹出黑色控制台窗口，在后台静默运行；仅在「等待程序结束」关闭时生效"),
    ],
    var_slots=[
        VarSlot("out", "程序输出", name_param="save_var", type_param="save_type",
                visible_when={"capture_output": [True]},
                vtype=vt.VT_STRING,
                desc="程序的标准输出按所选类型转换后存入该变量"
                     "（需开启「捕获输出」；退出码与错误输出在同名 _code / _stderr 变量）"),
    ],
    examples=[
        "打开记事本并等它关闭再继续：程序路径 notepad、等待程序结束 开启（Windows）；"
        "macOS 填 /System/Applications/TextEdit.app/Contents/MacOS/TextEdit",
        "运行脚本拿表格数据：程序路径 python、命令行参数 script.py、捕获输出 开启、输出类型 表格",
        "后台静默运行不弹窗：程序路径 C:/tools/run.exe、等待程序结束 关闭、隐藏窗口 开启（Windows）",
    ],
)
def _run_process(node, ctx):
    p = node.params
    program = ctx.resolve(p.get("program") or "").strip()
    if not program:
        raise RuntimeError("未指定程序路径")

    work_dir_raw = p.get("work_dir", "")
    work_dir = normalize_path(ctx.resolve(work_dir_raw)) if work_dir_raw else ctx.base_dir

    args_text = ctx.resolve(p.get("arguments", ""))
    args = _split_args(args_text)
    cmd = [program] + args

    wait = bool(p.get("wait_finish", True))
    timeout = float(p.get("timeout", 0) or 0)
    capture = bool(p.get("capture_output", False))
    hidden = bool(p.get("hidden", False))

    ctx.info(f"▶ 调用程序：{program} {' '.join(args)}")

    env = None
    kwargs: Dict[str, Any] = {
        "cwd": work_dir,
        "capture_output": capture,
        "timeout": timeout if timeout > 0 else None,
    }

    if hidden and IS_WIN and not wait:
        # Windows 后台隐藏窗口
        try:
            import subprocess
            si = subprocess.STARTUPINFO()                       # type: ignore[attr-defined]
            si.dwFlags = subprocess.STARTF_USESHOWWINDOW        # type: ignore[attr-defined]
            si.wShowWindow = 0
            kwargs["startupinfo"] = si
        except Exception:
            pass

    result = run_command(cmd, **kwargs)

    if result["timeout"]:
        raise RuntimeError(f"程序运行超时（>{timeout}s）：{program}")

    rc = result["returncode"]
    if capture:
        var = (p.get("save_var") or "proc_result").strip() or "proc_result"
        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        out_type = vt.vtype_of(p.get("save_type") or "")
        ctx.set_var(var, _coerce_output(out_type, stdout))
        if stderr:
            ctx.set_var(f"{var}_stderr", stderr)
        ctx.set_var(f"{var}_code", rc)
        ctx.success(f"📟 {program} 退出码 {rc}，输出 {len(stdout)} 字符"
                    f"（{vt.label_of(out_type)}）→ {{{{{var}}}}}")
    else:
        ctx.success(f"📟 {program} 已启动（不等待结束）")


@module(
    "process.run_script", "运行脚本", "外部调用",
    desc="直接执行一段 Python / Shell / Batch 脚本，适合临时数据转换或系统操作",
    params=[
        Param("script_type", "脚本类型", P_SELECT, "Python",
              choices=["Python", "Shell (Bash/Zsh)", "Windows CMD", "PowerShell"],
              help="Python 用运行本软件的解释器执行（已装的第三方库如 pandas 都能用）；"
                   "Windows CMD 相当于双击 .bat；PowerShell 适合系统管理命令；"
                   "Shell (Bash/Zsh) 需要系统装有 sh（Windows 默认没有，会执行失败）"),
        Param("script", "脚本内容", P_TEXTAREA, "", multiline=True,
              placeholder="print('Hello from script')",
              help="直接写脚本正文，不需要文件路径；支持 {{变量}} 插值，"
                   "脚本的标准输出存入输出变量，如：\n"
                   "import json\n"
                   "print(json.dumps([[1, 2], [3, 4]]))  # 输出类型选「二维列表」可得到列表变量"),
        Param("work_dir", "工作目录", P_TEXT, "",
              placeholder="留空使用流程所在目录",
              help="脚本临时文件写入并在该文件夹下运行，脚本里的相对路径"
                   "（open('./data.txt')、pd.read_csv('x.csv')）都相对于这里；"
                   "留空则使用流程文件（.arpa）所在目录",
              browse_mode="folder"),
        Param("timeout", "超时时间", P_NUMBER, 30, minimum=0, maximum=3600, suffix="秒",
              help="脚本最长运行时间，超时将强制终止并报错停止；0 表示不限"),
        Param("save_var", "输出变量", P_TEXT, "script_output",
              help="存脚本输出的变量名，后续步骤用 {{变量名}} 引用；"
                   "另有 {{变量名_code}} 退出码、{{变量名_stderr}} 错误输出"),
        Param("save_type", "输出类型", P_SELECT, "字符串",
              choices=[vt.label_of(t) for t in vt.VT_ORDER],
              help="脚本输出按该类型解析：选「字符串」为原样文本；选列表/字典/表格时建议脚本输出 JSON，"
                   "表格也可输出 CSV 文本（首行表头），如 pandas 的 "
                   "df.to_json(orient='records') 或 df.to_csv(index=False)"),
    ],
    var_slots=[
        VarSlot("out", "脚本输出", name_param="save_var", type_param="save_type",
                vtype=vt.VT_STRING,
                desc="脚本的标准输出按所选类型转换后存入该变量"
                     "（退出码与错误输出在同名 _code / _stderr 变量）"),
    ],
    examples=[
        "CSV 转表格变量：脚本类型 Python、"
        "脚本内容 print(pd.read_csv('data.csv').to_json(orient='records'))、输出类型 表格",
        "macOS 压缩备份：脚本类型 Shell (Bash/Zsh)、"
        "脚本内容 zip -r /Users/me/backup.zip /Users/me/Documents",
        "Windows 查本机 IP：脚本类型 Windows CMD、脚本内容 ipconfig、输出类型 字符串",
        "取系统日期做文件名：脚本类型 PowerShell、脚本内容 Get-Date -Format yyyyMMdd（Windows）",
    ],
)
def _run_script(node, ctx):
    p = node.params
    script_type = str(p.get("script_type", "Python"))
    script = ctx.resolve(p.get("script", ""))
    if not script.strip():
        raise RuntimeError("脚本内容为空")

    work_dir_raw = p.get("work_dir", "")
    work_dir = normalize_path(ctx.resolve(work_dir_raw)) if work_dir_raw else ctx.base_dir
    timeout = float(p.get("timeout", 30) or 30)

    import tempfile
    if script_type == "Python":
        suffix = ".py"
        if IS_WIN:
            cmd = ["python", "__tmp_script__.py"]
        else:
            cmd = ["python3", "__tmp_script__.py"]
    elif script_type == "Shell (Bash/Zsh)":
        suffix = ".sh"
        cmd = ["sh", "__tmp_script__.sh"]
    elif script_type == "Windows CMD":
        suffix = ".bat"
        cmd = ["cmd", "/c", "__tmp_script__.bat"]
    else:  # PowerShell
        suffix = ".ps1"
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", "__tmp_script__.ps1"]

    tmp_path = os.path.join(work_dir, f"__tmp_script__{suffix}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(script)

        result = run_command(cmd, cwd=work_dir, capture_output=True, timeout=timeout)
        if result["timeout"]:
            raise RuntimeError(f"脚本执行超时（>{timeout}s）")

        rc = result["returncode"]
        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        var = (p.get("save_var") or "script_output").strip() or "script_output"
        out_type = vt.vtype_of(p.get("save_type") or "")
        ctx.set_var(var, _coerce_output(out_type, stdout))
        if stderr:
            ctx.set_var(f"{var}_stderr", stderr)
        ctx.set_var(f"{var}_code", rc)

        if rc != 0:
            ctx.warn(f"脚本退出码 {rc}，stderr：{stderr[:200]}")
        ctx.success(f"📝 {script_type} 脚本执行完成，输出 {len(stdout)} 字符"
                    f"（{vt.label_of(out_type)}）→ {{{{{var}}}}}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
