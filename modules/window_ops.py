"""窗口 / 系统操作模块组。"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from core.platform import IS_WIN, open_path, run_command
from core.registry import module
from core.spec import (P_BOOL, P_FLOAT, P_NUMBER, P_REGION, P_SELECT, P_TEXT,
                       P_TEXTAREA, Param, VarSlot)
from core import vartypes as vt


@module(
    "win.activate", "激活窗口", "窗口系统",
    desc="根据标题关键字把某个程序窗口切到最前，自动化开始前几乎必备的一步",
    params=[
        Param("title", "窗口标题关键字", P_TEXT, "", placeholder="如 记事本 / Chrome / Excel",
              help="用标题里的部分关键字匹配即可，如「Excel」能匹配「月度报表 - Excel」；"
                   "支持 {{变量}} 插值，未找到时错误信息会列出当前窗口标题"),
        Param("exact", "标题完全匹配", P_BOOL, False,
              help="开启：标题必须完全一致才激活，适合有多个同类窗口时精确定位；"
                   "关闭（默认）：包含关键字即匹配，取第一个找到的窗口"),
        Param("wait", "切换后等待", P_FLOAT, 0.5, minimum=0.0, maximum=30.0, suffix="秒",
              help="激活后等待的秒数，给窗口留出绘制和加载时间；0 表示不等待，窗口较重时建议 0.5~2 秒"),
    ],
    examples=[
        "自动化开始前把窗口切到前台：窗口标题关键字 Excel、切换后等待 1；"
        "有多个同类窗口时把 标题完全匹配 开启精确定位",
        "激活浏览器窗口再操作网页：窗口标题关键字 Chrome、切换后等待 0.5（Windows）；"
        "macOS 可填 Safari",
        "窗口标题来自变量：窗口标题关键字 {{window_title}}、切换后等待 0.5",
    ],
)
def _win_activate(node, ctx):
    title = ctx.resolve(node.params.get("title", ""))
    if not title:
        raise RuntimeError("未填写窗口标题关键字")
    ok = ctx.window.activate(title, bool(node.params.get("exact")),
                             float(node.params.get("wait", 0.5) or 0.5))
    if not ok:
        titles = ctx.window.list_titles()[:8]
        raise RuntimeError(f"未找到窗口「{title}」。当前窗口示例：{titles}")
    ctx.success(f"🪟 已激活窗口「{title}」")


@module(
    "win.scope", "窗口内运行", "窗口系统",
    desc="容器：把步骤拖进来，运行期间始终保持目标窗口在前台——掉前台自动抢回；"
         "可始终保持最大化；激活重试到上限仍失败则流程失败",
    is_block=True, block_kind="win",
    params=[
        Param("title", "窗口标题关键字", P_TEXT, "", placeholder="如 记事本 / Chrome / Excel",
              help="容器内所有步骤都针对这个窗口执行，填标题部分关键字即可；"
                   "如「Chrome」能匹配「百度 - Google Chrome」，支持 {{变量}} 插值"),
        Param("exact", "标题完全匹配", P_BOOL, False,
              help="开启：标题必须完全一致才激活；关闭（默认）：包含关键字即匹配"),
        Param("maximize", "保持窗口最大化", P_BOOL, True,
              help="勾选后激活时会确保窗口最大化；取消则不改窗口大小"),
        Param("wait", "切换后等待", P_FLOAT, 0.5, minimum=0.0, maximum=30.0, suffix="秒",
              help="每次激活窗口后等待的秒数，给窗口留出绘制时间；0 表示不等待"),
        Param("retries", "激活尝试次数", P_NUMBER, 3, minimum=1, maximum=50, suffix="次",
              help="进入容器和运行中重新激活时，最多尝试的次数；超过仍未激活则流程失败"),
        Param("retry_interval", "尝试间隔", P_FLOAT, 1.0, minimum=0.1, maximum=60.0, suffix="秒",
              help="每次激活尝试之间的等待秒数；窗口响应慢时适当调大，如 2~3 秒"),
    ],
    examples=[
        "让后续步骤始终钉在某个窗口内：窗口标题关键字 Chrome、保持窗口最大化 开启、"
        "把要操作的步骤拖进这个容器里",
        "窗口响应慢时调大等待：切换后等待 2、尝试间隔 3、激活尝试次数 5",
        "不改窗口大小运行：保持窗口最大化 关闭、窗口标题关键字 记事本（Windows）；"
        "macOS 可填 文本编辑",
    ],
)
def _win_scope(node, ctx):
    """容器节点：执行逻辑在引擎 BlockHandlers._run_win_scope。"""
    raise RuntimeError("窗口内运行节点应由引擎处理")


@module(
    "win.state", "窗口最大化/最小化/关闭", "窗口系统",
    desc="改变指定窗口的显示状态",
    params=[
        Param("title", "窗口标题关键字", P_TEXT, "",
              help="填标题部分关键字即可，支持 {{变量}} 插值；未找到窗口会报错"),
        Param("action", "操作", P_SELECT, "最大化", choices=["最大化", "最小化", "关闭"],
              help="最大化：铺满屏幕，便于取图和点击；最小化：暂时收起不占屏幕；关闭：直接关掉窗口"),
        Param("wait", "操作后等待", P_FLOAT, 0.4, minimum=0.0, maximum=30.0, suffix="秒",
              help="操作后等待的秒数，等窗口完成状态切换再执行下一步；0 表示不等待"),
    ],
    examples=[
        "截图取图前铺满屏幕：窗口标题关键字 记事本、操作 最大化、操作后等待 0.5（Windows）；"
        "macOS 可填 TextEdit",
        "关掉卡住的弹窗：窗口标题关键字 提示、操作 关闭",
        "暂时收起不占屏幕：窗口标题关键字 Excel、操作 最小化",
    ],
)
def _win_state(node, ctx):
    p = node.params
    title = ctx.resolve(p.get("title", ""))
    if not title:
        raise RuntimeError("未填写窗口标题关键字")
    action = str(p.get("action", "最大化"))
    fn = {"最大化": ctx.window.maximize, "最小化": ctx.window.minimize,
          "关闭": ctx.window.close}[action]
    if not fn(title):
        raise RuntimeError(f"{action}窗口「{title}」失败：未找到该窗口")
    ctx.sleep(float(p.get("wait", 0.4) or 0.0))
    ctx.success(f"🪟 已{action}窗口「{title}」")


@module(
    "win.list", "获取窗口列表", "窗口系统",
    desc="列出当前所有窗口标题，存入变量做后续判断或日志留证",
    returns_value=True,
    params=[Param("save_var", "存入变量", P_TEXT, "windows",
                  help="保存窗口标题列表的变量名，可配合「遍历列表」逐个激活窗口；如 windows")],
    examples=[
        "列出所有窗口再逐个检查：存入变量 windows，配合「列表取值」和「遍历列表」使用",
        "找不到目标窗口时排查：存入变量 windows，把列表写入日志查看当前窗口标题",
    ],
    var_slots=[
        VarSlot("out", "窗口标题列表", name_param="save_var", vtype=vt.VT_LIST1D,
                desc="文本列表，一行一个窗口标题，可用「列表取值」按序号取出"),
    ],
)
def _win_list(node, ctx):
    titles = ctx.window.list_titles()
    var = (node.params.get("save_var") or "windows").strip() or "windows"
    ctx.set_var(var, titles)
    ctx.info(f"🪟 共 {len(titles)} 个窗口，已存入 {{{{{var}}}}}")
    for t in titles[:10]:
        ctx.debug(f"   · {t}")


@module(
    "sys.run", "运行程序 / 打开文件", "窗口系统",
    desc="启动 exe、打开文档、访问网址",
    params=[
        Param("path", "程序或文件路径", P_TEXT, "", placeholder="C:/Windows/notepad.exe 或 https://...",
              help="启动程序、打开文档或访问网址：填 .exe / .bat 等程序路径，支持 {{变量}} 插值；"
                   "以 http://、https:// 开头的网址会用默认浏览器打开"),
        Param("args", "启动参数", P_TEXT, "", placeholder="多个参数用空格分隔",
              help="传给程序的命令行参数，多个用空格分隔，支持 {{变量}} 插值；仅启动程序时生效，打开网址用不到"),
        Param("wait", "启动后等待", P_FLOAT, 1.0, minimum=0.0, maximum=120.0, suffix="秒",
              help="启动后等待的秒数，给程序留出加载时间；0 表示启动完立即继续"),
    ],
    examples=[
        "打开记事本：程序或文件路径 C:/Windows/notepad.exe、启动后等待 1（Windows）",
        "macOS 打开文本编辑：程序或文件路径 "
        "/System/Applications/TextEdit.app/Contents/MacOS/TextEdit、启动后等待 1",
        "macOS 用系统方式打开应用：程序或文件路径 /usr/bin/open、启动参数 -a TextEdit",
        "打开网页：程序或文件路径 https://www.example.com，自动用默认浏览器打开",
        "带参数启动并等它加载：程序或文件路径 C:/app/report.exe、启动参数 daily 2026、启动后等待 5",
    ],
)
def _sys_run(node, ctx):
    p = node.params
    path = ctx.resolve(p.get("path", "")).strip()
    if not path:
        raise RuntimeError("未填写要运行的程序路径")
    args = ctx.resolve(p.get("args", "")).strip()
    cmd = [path] + (args.split() if args else [])
    try:
        if path.lower().startswith(("http://", "https://")):
            open_path(path)
        else:
            subprocess.Popen(cmd, close_fds=True)   # noqa: S603
    except Exception as exc:
        raise RuntimeError(f"启动失败：{exc}") from exc
    ctx.sleep(float(p.get("wait", 1.0) or 0.0))
    ctx.success(f"🚀 已启动 {path}")


@module(
    "sys.kill", "结束进程", "窗口系统",
    desc="按进程名结束程序，例如 taskkill 掉卡住的弹窗进程",
    params=[
        Param("name", "进程名", P_TEXT, "", placeholder="如 notepad.exe（不含路径）",
              help="要结束的进程名，不含路径，如「notepad」或「notepad.exe」，支持 {{变量}} 插值；"
                   "Windows 下会自动补全 .exe 后缀"),
        Param("force", "强制结束", P_BOOL, True,
              help="开启：强制结束（相当于 taskkill /F），卡死的程序也能杀掉，但可能丢失未保存数据；"
                   "关闭：先正常请求退出，更温和但可能被程序拒绝"),
    ],
    examples=[
        "杀掉卡死的记事本：进程名 notepad.exe、强制结束 开启（Windows）；"
        "macOS 填 TextEdit（进程名不要带 .exe）",
        "温和结束进程：进程名 chrome、强制结束 关闭，先请求正常退出，避免丢失未保存数据",
    ],
)
def _sys_kill(node, ctx):
    name = ctx.resolve(node.params.get("name", "")).strip()
    if not name:
        raise RuntimeError("未填写进程名")
    force = bool(node.params.get("force"))
    if IS_WIN:
        if not name.lower().endswith(".exe"):
            name += ".exe"
        cmd = ["taskkill", "/IM", name] + (["/F"] if force else [])
    else:
        # macOS / Linux: kill / pkill
        cmd = ["pkill", "-f", name] + (["-9"] if force else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)  # noqa: S603
    except Exception as exc:
        raise RuntimeError(f"结束进程失败：{exc}") from exc
    if r.returncode != 0:
        raise RuntimeError(f"未找到进程 {name}")
    ctx.success(f"✓ 已结束进程 {name}")


@module(
    "sys.wait", "等待延时", "窗口系统",
    desc="固定等待若干秒，给界面留出加载时间",
    params=[
        Param("seconds", "等待时长", P_FLOAT, 1.0, minimum=0.01, maximum=3600.0, suffix="秒",
              help="固定等待的秒数，如 0.5、2；用于等界面加载、等动画播完，最小 0.01 秒、最大 1 小时"),
        Param("random_extra", "附加随机抖动", P_FLOAT, 0.0, minimum=0.0, maximum=60.0,
              suffix="秒", help="在等待时长上再加 0~N 秒随机值，让操作节奏更像真人"),
    ],
    examples=[
        "等页面加载完再继续：等待时长 2",
        "等动画并模拟真人节奏：等待时长 0.5、附加随机抖动 1（实际等 0.5~1.5 秒）",
    ],
)
def _sys_wait(node, ctx):
    import random
    sec = float(node.params.get("seconds", 1.0) or 0.0)
    extra = float(node.params.get("random_extra", 0.0) or 0.0)
    total = sec + (random.uniform(0, extra) if extra > 0 else 0)
    ctx.sleep(total)
    ctx.info(f"⏱ 等待 {total:.2f} 秒")


@module(
    "sys.message", "弹出提示框", "窗口系统",
    desc="弹出提示/确认框。确认框可用于「人工确认后继续」这类半自动场景",
    params=[
        Param("message", "提示内容", P_TEXTAREA, "", multiline=True,
              help="弹出框里显示的文字，支持多行和 {{变量}} 插值；留空则显示默认提示"),
        Param("mode", "类型", P_SELECT, "提示(自动继续)", choices=["提示(自动继续)", "确认框(等待点击)"],
              help="提示：只显示消息，点确定或直接继续；确认框：等待人点「确定/取消」并把结果存入变量，"
                   "适合需人工判断后再继续的半自动场景"),
        Param("save_var", "确认结果存入变量", P_TEXT, "user_confirm", visible_when={"mode": ["确认框(等待点击)"]},
              help="存放确认结果的变量名：点「确定」为 True，点「取消」或关闭窗口为 False；如 user_confirm"),
    ],
    var_slots=[
        VarSlot("out", "确认结果", name_param="save_var", vtype=vt.VT_BOOL,
                visible_when={"mode": ["确认框(等待点击)"]},
                desc="点「确定」= True，否则 = False"),
    ],
    examples=[
        "弹个提示自动继续：提示内容 处理完成，共 {{count}} 条、类型 提示(自动继续)",
        "人工确认后再继续：类型 确认框(等待点击)、确认结果存入变量 user_confirm，"
        "再用「条件判断」按 user_confirm 是否为 True 走分支",
    ],
)
def _sys_message(node, ctx):
    p = node.params
    msg = ctx.resolve(p.get("message", "")) or "灵瞳 提示"
    if p.get("mode") == "确认框(等待点击)":
        try:
            import pyautogui
            r = pyautogui.confirm(text=msg, title="灵瞳 确认")
            ok = (r == "OK")
        except Exception:
            ok = True
        var = (p.get("save_var") or "user_confirm").strip() or "user_confirm"
        ctx.set_var(var, ok)
        ctx.info(f"💬 用户确认结果：{ok}")
    else:
        try:
            import pyautogui
            pyautogui.alert(text=msg, title="灵瞳")
        except Exception:
            pass
        ctx.info(f"💬 {msg}")


@module(
    "sys.screenshot", "截取屏幕", "窗口系统",
    desc="全屏或区域截图保存，作为运行证据或素材",
    params=[
        Param("mode", "范围", P_SELECT, "全屏", choices=["全屏", "自定义区域"],
              help="全屏：截取整个屏幕；自定义区域：只截框选的局部区域，适合固定位置的状态留证"),
        Param("region", "区域", P_REGION, "", allow_empty=False,
              visible_when={"mode": ["自定义区域"]},
              help="点「框选区域」直接在屏幕上拖选，自动填入 X/Y/宽/高"),
        Param("path", "保存路径", P_TEXT, "output/image/screen_{{timestamp}}.png", browse_mode="save",
              help="截图保存位置：相对路径基于流程所在目录，{{timestamp}} 自动替换为当前时间避免覆盖；"
                   "留空则用默认路径 output/image/screen.png"),
    ],
    examples=[
        "运行留证（Windows）：范围 全屏、保存路径 C:/shots/run_{{timestamp}}.png",
        "运行留证（macOS）：范围 全屏、保存路径 /Users/你的名字/shots/run_{{timestamp}}.png",
        "只截固定区域：范围 自定义区域，点「框选区域」在屏幕上拖选后自动填入",
        "用默认路径即可：保存路径留空，存到流程目录的 output/image/screen.png",
    ],
)
def _sys_screenshot(node, ctx):
    p = node.params
    path = ctx.resolve(p.get("path") or "output/image/screen.png")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    region = None
    if p.get("mode") == "自定义区域":
        from .common import parse_region
        region = parse_region(p.get("region", ""), ctx)
        if region is None:
            raise RuntimeError("区域格式应为 x,y,w,h")
    if region is None:
        size = ctx.screen.screen_size()
        region = (0, 0, size[0], size[1])
    if ctx.screen.save_crop(region, path):
        ctx.success(f"📷 截图已保存 → {path}")
    else:
        raise RuntimeError("截图失败")


@module(
    "sys.pause_resume", "暂停等待人工处理", "窗口系统",
    desc="流程挂起，等人处理完（如输验证码）后按快捷键继续",
    params=[
        Param("message", "提示文字", P_TEXT, "请人工处理完成后，在控制台点击「继续」",
              help="暂停时显示在日志/控制台里的提示，告诉操作的人该做什么；支持 {{变量}} 插值"),
        Param("auto_seconds", "自动继续等待", P_FLOAT, 0.0, minimum=0.0, maximum=3600.0,
              suffix="秒（0=只能手动继续）",
              help="到达秒数后自动继续执行，无需人工点「继续」，如限定输验证码 30 秒；0 表示一直等人工继续"),
    ],
    examples=[
        "输验证码场景：提示文字 请输完验证码后点「继续」、自动继续等待 0（只能手动继续）",
        "限时处理超时自动继续：提示文字 请在 30 秒内完成、自动继续等待 30",
    ],
)
def _sys_pause(node, ctx):
    import time as _t
    msg = ctx.resolve(node.params.get("message", ""))
    auto = float(node.params.get("auto_seconds", 0.0) or 0.0)
    ctx.warn(f"⏸ 已暂停：{msg}")
    ctx.pause_event.clear()
    start = _t.time()
    while not ctx.pause_event.is_set():
        if ctx.stop_event.is_set():
            ctx.pause_event.set()
            return
        if auto and _t.time() - start >= auto:
            ctx.pause_event.set()
            break
        _t.sleep(0.15)
    ctx.success("▶ 已继续执行")
