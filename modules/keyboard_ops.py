"""键盘操作模块组 —— 键盘输入、快捷键、组合键。"""
from __future__ import annotations

import threading
import time

from core.registry import module
from core.spec import (P_BOOL, P_FLOAT, P_KEY, P_NUMBER, P_SELECT, P_TEXT,
                       P_TEXTAREA, Param, VarSlot)
from core import vartypes as vt
from core.platform import IS_MAC

KEYS = [
    "enter", "tab", "esc", "space", "backspace", "delete", "insert",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "ctrl", "alt", "shift", "win", "capslock", "printscreen",
]


@module(
    "key.type", "键盘输入文本", "键盘操作",
    desc="像人一样把文字敲进当前焦点窗口；支持 {{变量}} 和中文（自动走剪贴板）",
    examples=[
        "在搜索框覆盖旧内容并确认：输入内容 关键字、输入前先清空 开启、输入后按回车 开启",
        "往已有段落中间补一句话：输入内容 补充说明、输入前先清空 关闭、字符间隔 0.05",
        "用变量拼问候语：输入内容 你好 {{name}}，今天是 {{date}}、输入后按回车 开启",
    ],
    params=[
        Param("text", "输入内容", P_TEXTAREA, "", multiline=True,
              placeholder="支持 {{变量}}，例如：你好 {{name}}，今天是 {{date}}",
              help="要敲入的文字，支持 {{变量}}；含中文或特殊符号时会自动改走剪贴板粘贴，"
                   "整段内容不会被拆散"),
        Param("clear_first", "输入前先清空", P_BOOL, False,
              help="开启：先 Ctrl+A 全选再输入，等于覆盖原内容；"
                   "关闭：直接在光标处追加，适合往已有内容中间插入"),
        Param("press_enter", "输入后按回车", P_BOOL, False,
              help="开启：输入完自动按回车，适合确认、提交表单或换行；关闭：只输入文本"),
        Param("interval", "字符间隔", P_FLOAT, 0.02, minimum=0.0, maximum=1.0,
              suffix="秒（模拟打字速度）",
              help="相邻两个字符之间的间隔秒数，越小打字越快；0 表示不等待（最快）"),
    ],
    var_slots=[
        VarSlot("in", "输入内容", value_param="text", vtype=vt.VT_STRING,
                desc="要敲入的文本，支持 {{变量}}"),
    ],
)
def _key_type(node, ctx):
    p = node.params
    text = ctx.resolve(p.get("text", ""))
    if p.get("clear_first"):
        ctx.input.select_all()
        ctx.sleep(0.08)
    ctx.input.write(text, interval=float(p.get("interval", 0.02) or 0.02))
    if p.get("press_enter"):
        ctx.sleep(0.05)
        ctx.input.press("enter")
    shown = text if len(text) <= 40 else text[:40] + "…"
    ctx.info(f"⌨ 已输入：{shown}")


@module(
    "key.hotkey", "按下快捷键", "键盘操作",
    desc="发送组合键，如 ctrl+c、ctrl+shift+s、alt+f4、win+d",
    examples=[
        "复制选中内容：快捷键 ctrl+c（macOS 上 ctrl 即 ⌘ Command，等同 command+c）",
        "强制关闭当前窗口：快捷键 alt+f4（Windows）；macOS 填 command+q",
        "连按 3 次快捷键：快捷键 ctrl+v、执行次数 3、间隔 0.2",
    ],
    params=[
        Param("keys", "快捷键", P_KEY, "ctrl+c",
              placeholder="点击输入框后直接按组合键录入",
              help="点击输入框后直接按组合键即可录入（退格/删除清空重录）。"
                   "macOS 上 ctrl 指 ⌘ Command，control 指真实 Control 键"),
        Param("times", "执行次数", P_NUMBER, 1, minimum=1, maximum=50, suffix="次",
              help="重复发送快捷键的次数，如 3 表示连按 3 次 ctrl+c；"
                   "多次执行时相邻两次按「间隔」等待"),
        Param("interval", "间隔", P_FLOAT, 0.15, minimum=0.0, maximum=10.0, suffix="秒",
              help="执行次数大于 1 时，相邻两次按键之间的等待秒数；0 表示不等待"),
        Param("wait_after", "按完等待", P_FLOAT, 0.2, minimum=0.0, maximum=60.0, suffix="秒",
              help="快捷键全部按完后等待的秒数，给软件留出响应时间；0 表示不等待"),
    ],
)
def _key_hotkey(node, ctx):
    p = node.params
    raw = ctx.resolve(p.get("keys", "")) or ""
    parts = [k.strip().lower() for k in raw.replace("＋", "+").split("+") if k.strip()]
    if not parts:
        raise RuntimeError("未填写快捷键")
    for i in range(int(p.get("times", 1) or 1)):
        ctx.check_stop()
        if i:
            ctx.sleep(float(p.get("interval", 0.15) or 0.0))
        ctx.input.hotkey(parts)
    ctx.sleep(float(p.get("wait_after", 0.2) or 0.0))
    ctx.info(f"⌨ 快捷键 {'+'.join(parts)}" + (f" ×{p.get('times')}" if int(p.get('times', 1) or 1) > 1 else ""))


@module(
    "key.press", "按键", "键盘操作",
    desc="按下单个按键多次，例如连续按向下键翻列表",
    examples=[
        "连续向下翻列表：按键 down、次数 10、间隔 0.1",
        "打开选中项：按键 enter、按完等待 0.5",
    ],
    params=[
        Param("key", "按键", P_SELECT, "enter", choices=KEYS,
              help="要按的按键，从列表中选择；如向下键配大次数可连续翻列表、翻页"),
        Param("times", "次数", P_NUMBER, 1, minimum=1, maximum=999, suffix="次",
              help="按键重复次数，如 10 表示连按 10 次；"
                   "连续按下时相邻两次按「间隔」等待，避免软件来不及响应"),
        Param("interval", "间隔", P_FLOAT, 0.1, minimum=0.0, maximum=10.0, suffix="秒",
              help="次数大于 1 时相邻两次按键之间的等待秒数；0 表示不等待"),
        Param("wait_after", "按完等待", P_FLOAT, 0.1, minimum=0.0, maximum=60.0, suffix="秒",
              help="全部按完后等待的秒数，给软件留出响应时间；0 表示不等待"),
    ],
)
def _key_press(node, ctx):
    p = node.params
    key = str(p.get("key", "enter"))
    times = int(p.get("times", 1) or 1)
    interval = float(p.get("interval", 0.1) or 0.0)
    for i in range(times):
        ctx.check_stop()
        ctx.input.press(key)
        if i < times - 1:
            ctx.sleep(interval)
    ctx.sleep(float(p.get("wait_after", 0.1) or 0.0))
    ctx.info(f"⌨ 按键 {key}" + (f" ×{times}" if times > 1 else ""))


@module(
    "key.hold", "按住 / 松开按键", "键盘操作",
    desc="按下不放或抬起某个键，用于配合鼠标做选区、连续拖动",
    examples=[
        "连选多个文件：先 动作 按住、按键 shift，鼠标逐个点击后，再 动作 松开、按键 shift",
        "扩展文本选区：动作 按住、按键 shift，鼠标点选区另一端；选完再 动作 松开",
    ],
    params=[
        Param("key", "按键", P_SELECT, "shift", choices=KEYS,
              help="要操作的按键；按住 shift 点选可做连选，按住 ctrl 拖鼠标可多选区域"),
        Param("action", "动作", P_SELECT, "按住", choices=["按住", "松开"],
              help="按住：把按键按下不放，之后的鼠标操作会带上该键，直到「松开」；"
                   "松开：抬起该键，两个动作需配对使用"),
        Param("wait_after", "之后等待", P_FLOAT, 0.1, minimum=0.0, maximum=60.0, suffix="秒",
              help="动作完成后等待的秒数，给界面留出响应时间；0 表示不等待"),
    ],
)
def _key_hold(node, ctx):
    key = str(node.params.get("key", "shift"))
    if node.params.get("action") == "松开":
        ctx.input.key_up(key)
        ctx.info(f"⌨ 松开 {key}")
    else:
        ctx.input.key_down(key)
        ctx.info(f"⌨ 按住 {key}")
    ctx.sleep(float(node.params.get("wait_after", 0.1) or 0.0))


@module(
    "key.paste_text", "粘贴文本到当前窗口", "键盘操作",
    desc="把长文本放进剪贴板再 Ctrl+V，比逐字输入快得多，适合填长表单",
    examples=[
        "粘贴大段文本覆盖原文：粘贴内容 长文本、粘贴前清空 开启",
        "往已有内容中间插入：粘贴内容 插入片段、粘贴前清空 关闭",
    ],
    params=[
        Param("text", "粘贴内容", P_TEXTAREA, "", multiline=True,
              help="要粘贴的文本，支持 {{变量}}；整段内容先放进剪贴板再 Ctrl+V，"
                   "长文本比逐字输入快得多，适合填长表单"),
        Param("clear_first", "粘贴前清空", P_BOOL, True,
              help="开启：粘贴前 Ctrl+A 全选，整段覆盖原内容；"
                   "关闭：直接粘到光标处，适合往已有内容中间插入"),
        Param("restore_clipboard", "粘贴后还原剪贴板", P_BOOL, True,
              help="开启：粘贴完成后把剪贴板恢复成原来的内容，避免覆盖你手动复制的东西；"
                   "关闭：剪贴板保留刚粘贴的文本"),
    ],
    var_slots=[
        VarSlot("in", "粘贴内容", value_param="text", vtype=vt.VT_STRING,
                desc="要粘贴的文本，支持 {{变量}}"),
    ],
)
def _key_paste(node, ctx):
    p = node.params
    text = ctx.resolve(p.get("text", ""))
    if not text:
        raise RuntimeError("粘贴内容为空")
    old = ctx.input.get_clipboard()
    ctx.input.set_clipboard(text)
    if p.get("clear_first"):
        ctx.input.select_all()
        ctx.sleep(0.08)
    ctx.sleep(0.05)
    ctx.input.paste()
    ctx.sleep(0.1)
    if p.get("restore_clipboard") and old:
        ctx.input.set_clipboard(old)
    ctx.info(f"📋 已粘贴 {len(text)} 个字符")


# ------------------------------------------------------------------ 热键触发输入
# 界面写法（ctrl+alt+q）→ pynput GlobalHotKeys 格式（<ctrl>+<alt>+q）的映射。
# 与发送侧归一化保持一致：macOS 上「ctrl」指 ⌘ Command，真实 Control 写 "control"
_PYNPUT_MODS = {"ctrl": "<ctrl>", "control": "<ctrl>", "alt": "<alt>",
                "shift": "<shift>", "win": "<cmd>", "cmd": "<cmd>", "command": "<cmd>"}
if IS_MAC:
    _PYNPUT_MODS["ctrl"] = "<cmd>"
    _PYNPUT_MODS["control"] = "<ctrl>"
_PYNPUT_SPECIAL = {
    "esc": "esc", "escape": "esc", "space": "space", "tab": "tab",
    "enter": "enter", "return": "enter", "backspace": "backspace",
    "delete": "delete", "insert": "insert",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end",
    "pageup": "page_up", "pagedown": "page_down",
    "printscreen": "print_screen", "capslock": "caps_lock",
}
_PYNPUT_SPECIAL.update({f"f{i}": f"f{i}" for i in range(1, 13)})


def _combo_str(parts) -> str:
    """把 ctrl+alt+q 这样的写法转成 pynput GlobalHotKeys 的格式。"""
    out = []
    for k in parts:
        if k in _PYNPUT_MODS:
            out.append(_PYNPUT_MODS[k])
        elif k in _PYNPUT_SPECIAL:
            out.append(f"<{_PYNPUT_SPECIAL[k]}>")
        elif len(k) == 1:
            out.append(k)
        else:
            raise RuntimeError(f"触发快捷键包含不支持的键：{k}")
    return "+".join(out)


def _wait_hotkey(parts, ctx, timeout: float = 0.0) -> bool:
    """后台监听全局热键：人工按下后返回 True，超时返回 False。
    等待期间随时响应流程的停止/暂停信号。"""
    try:
        from pynput import keyboard as _kb
    except Exception:
        raise RuntimeError("缺少 pynput 库，无法监听全局热键（pip install pynput）")
    fired = threading.Event()
    try:
        listener = _kb.GlobalHotKeys({_combo_str(parts): fired.set})
    except Exception as exc:
        raise RuntimeError(f"触发快捷键格式不正确：{exc}")
    listener.daemon = True
    listener.start()
    try:
        deadline = time.time() + timeout if timeout > 0 else None
        while not fired.is_set():
            ctx.check_stop()
            if deadline is not None and time.time() > deadline:
                return False
            time.sleep(0.08)
        return True
    finally:
        listener.stop()


@module(
    "key.hotkey_type", "热键触发输入", "键盘操作",
    desc="流程执行到这里会等待：人工在任意窗口按下设定快捷键后，自动把内容输入到当前焦点处",
    examples=[
        "客服快捷回复：触发快捷键 ctrl+alt+q、输入内容 您好，已收到您的问题",
        "触发后自动提交表单：触发快捷键 ctrl+alt+q、输入后按回车 开启"
        "（macOS 上 ctrl 即 ⌘ Command）",
    ],
    params=[
        Param("hotkey", "触发快捷键", P_KEY, "ctrl+alt+q",
              placeholder="点击输入框后直接按组合键录入",
              help="运行中人工按下即触发；点击输入框后直接按组合键录入。"
                   "macOS 上 ctrl 指 ⌘ Command"),
        Param("text", "输入内容", P_TEXTAREA, "", multiline=True,
              placeholder="支持 {{变量}}；触发后自动键入到当前光标处",
              help="触发快捷键后要自动键入到当前光标处的文字，支持 {{变量}}；不能为空"),
        Param("press_enter", "输入后按回车", P_BOOL, False,
              help="开启：输入完自动按回车，适合触发后确认或提交表单；关闭：只输入文本"),
        Param("interval", "字符间隔", P_FLOAT, 0.02, minimum=0.0, maximum=1.0,
              suffix="秒（模拟打字速度）",
              help="相邻两个字符之间的间隔秒数，越小打字越快；0 表示不等待（最快）"),
    ],
    var_slots=[
        VarSlot("in", "输入内容", value_param="text", vtype=vt.VT_STRING,
                desc="触发快捷键后要自动输入的文本，支持 {{变量}}"),
    ],
)
def _key_hotkey_type(node, ctx):
    p = node.params
    text = ctx.resolve(p.get("text", ""))
    if not text:
        raise RuntimeError("输入内容为空")
    raw = ctx.resolve(p.get("hotkey", "")) or ""
    parts = [k.strip().lower() for k in raw.replace("＋", "+").split("+") if k.strip()]
    if not parts:
        raise RuntimeError("未填写触发快捷键")
    timeout = float(p.get("timeout", 0.0) or 0.0)
    ctx.info(f"⌨ 等待热键 {'+'.join(parts)}，手动按下后自动输入…")
    if not _wait_hotkey(parts, ctx, timeout):
        raise RuntimeError(f"等待热键 {'+'.join(parts)} 超时（可在「运行控制」里调大超时时间）")
    ctx.input.write(text, interval=float(p.get("interval", 0.02) or 0.02))
    if p.get("press_enter"):
        ctx.sleep(0.05)
        ctx.input.press("enter")
    shown = text if len(text) <= 40 else text[:40] + "…"
    ctx.success(f"⌨ 热键触发，已输入：{shown}")
