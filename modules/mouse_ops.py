"""鼠标操作模块组 —— 直接按坐标操作鼠标。"""
from __future__ import annotations

from core.registry import module
from core.spec import P_BOOL, P_FLOAT, P_NUMBER, P_SELECT, P_TEXT, Param, VarSlot
from core import vartypes as vt

from .common import click_at

_BTN = ["左键", "右键", "中键"]


@module(
    "mouse.click", "鼠标点击(坐标)", "鼠标操作",
    desc="在指定屏幕坐标点击鼠标；坐标可用变量，例如配合图像识别结果做二次点击",
    params=[
        Param("x", "坐标 X", P_NUMBER, 0, minimum=0, maximum=20000,
              help="目标点的屏幕水平坐标（像素，左上角为 0）；配合「坐标来自变量」时填变量名，如 last_point.x"),
        Param("y", "坐标 Y", P_NUMBER, 0, minimum=0, maximum=20000,
              help="目标点的屏幕垂直坐标（像素，左上角为 0）；配合「坐标来自变量」时填变量名，如 last_point.y"),
        Param("button", "鼠标键", P_SELECT, "左键", choices=_BTN,
              help="左键：普通点击、双击打开；右键：弹出上下文菜单；中键：浏览器里常用于关闭标签页"),
        Param("clicks", "点击次数", P_NUMBER, 1, minimum=1, maximum=10, suffix="次",
              help="1 次为单击；2 次为双击，用于打开文件/文件夹；游戏连击场景可用 3 次以上"),
        Param("use_var", "坐标来自变量", P_BOOL, False,
              help="开启：X、Y 填变量名（不带大括号），坐标从变量读取，如图像识别结果的 last_point.x、last_point.y；"
                   "关闭：X、Y 直接填数字坐标"),
        Param("duration", "移动耗时", P_FLOAT, 0.15, minimum=0.0, maximum=5.0, suffix="秒",
              help="鼠标移动到目标点的耗时：数值越小移动越快，0 表示瞬间跳过去；部分程序对过快的移动无响应，"
                   "点不中时可调大到 0.3~0.5 秒模拟人工轨迹"),
    ],
    examples=[
        "单击某个按钮：坐标 X 520、坐标 Y 360、鼠标键 左键、点击次数 1；点不中可调大移动耗时到 0.3",
        "双击打开文件或文件夹：坐标 X 800、坐标 Y 600、鼠标键 左键、点击次数 2",
        "右键弹出上下文菜单：坐标 X 400、坐标 Y 300、鼠标键 右键",
        "点击图像识别到的目标：坐标来自变量 开启、坐标 X last_point.x、坐标 Y last_point.y",
    ],
)
def _mouse_click(node, ctx):
    p = node.params
    if p.get("use_var"):
        x = int(float(ctx.resolve_value("{{" + str(p.get("x", "0")) + "}}") or 0))
        y = int(float(ctx.resolve_value("{{" + str(p.get("y", "0")) + "}}") or 0))
    else:
        x, y = int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)
    clicks = int(p.get("clicks", 1) or 1)
    dur = float(p.get("duration", 0.15) or 0.0)
    if x == 0 and y == 0 and not p.get("use_var"):
        ctx.warn("坐标为 (0,0)，请确认是否已填写")
    ctx.input.move(x, y, dur)
    click_at(ctx, x, y, str(p.get("button", "左键")), clicks)


@module(
    "mouse.move", "鼠标移动到", "鼠标操作",
    desc="把鼠标移动到指定坐标（不点击），常用于悬停触发菜单",
    params=[
        Param("x", "坐标 X", P_NUMBER, 0, minimum=0, maximum=20000,
              help="目标水平坐标（像素，左上角为 0）；选「相对当前位置」时表示相对当前鼠标的横向偏移量"),
        Param("y", "坐标 Y", P_NUMBER, 0, minimum=0, maximum=20000,
              help="目标垂直坐标（像素，左上角为 0）；选「相对当前位置」时表示相对当前鼠标的纵向偏移量"),
        Param("mode", "移动方式", P_SELECT, "绝对坐标", choices=["绝对坐标", "相对当前位置"],
              help="绝对坐标：以屏幕左上角为原点移动到 (X,Y)，适合跳到固定位置；"
                   "相对当前位置：在当前鼠标位置基础上偏移 (X,Y)，适合先移到大区域再微调"),
        Param("duration", "移动耗时", P_FLOAT, 0.25, minimum=0.0, maximum=5.0, suffix="秒",
              help="移动到目标点的耗时：数值越小越快，0 表示瞬间跳过去；悬停触发菜单等场景可用较大值让轨迹更自然"),
    ],
    examples=[
        "悬停弹出下拉菜单：坐标 X 600、坐标 Y 200、移动方式 绝对坐标、移动耗时 0.5（轨迹更自然）",
        "从当前位置向右下微调：移动方式 相对当前位置、坐标 X 20、坐标 Y 20",
        "瞬间跳到屏幕角落：坐标 X 10、坐标 Y 10、移动耗时 0",
    ],
)
def _mouse_move(node, ctx):
    p = node.params
    x, y = int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)
    dur = float(p.get("duration", 0.25) or 0.0)
    if p.get("mode") == "相对当前位置":
        ctx.input.move_rel(x, y, dur)
        ctx.debug(f"鼠标相对移动 ({x},{y})")
    else:
        ctx.input.move(x, y, dur)
        ctx.debug(f"鼠标移动到 ({x},{y})")


@module(
    "mouse.drag", "鼠标拖拽", "鼠标操作",
    desc="从一个点按住拖到另一个点，用于拖动滑块、选中文本、拖拽文件",
    params=[
        Param("x1", "起点 X", P_NUMBER, 0, minimum=0, maximum=20000,
              help="按下鼠标的起点水平坐标（像素）；想从当前位置开始可先用「鼠标移动到」"),
        Param("y1", "起点 Y", P_NUMBER, 0, minimum=0, maximum=20000,
              help="按下鼠标的起点垂直坐标（像素）；想从当前位置开始可先用「鼠标移动到」"),
        Param("x2", "终点 X", P_NUMBER, 0, minimum=0, maximum=20000,
              help="松开鼠标的终点水平坐标（像素），即拖到的目标位置"),
        Param("y2", "终点 Y", P_NUMBER, 0, minimum=0, maximum=20000,
              help="松开鼠标的终点垂直坐标（像素），即拖到的目标位置"),
        Param("button", "鼠标键", P_SELECT, "左键", choices=_BTN,
              help="左键：大多数拖拽场景（滑块、文件、选中文本）；右键拖拽仅个别程序支持，一般用不到"),
        Param("duration", "拖拽耗时", P_FLOAT, 0.6, minimum=0.1, maximum=10.0, suffix="秒",
              help="从起点拖到终点的过程耗时：数值小拖得快、大则缓慢；拖滑块验证码时建议 0.5~1 秒更像人工"),
        Param("hold", "按住停留", P_FLOAT, 0.15, minimum=0.0, maximum=3.0, suffix="秒",
              help="按下后在起点停留的时长，部分控件需要短暂停留才识别为拖动；0 表示不停留、按下即拖"),
    ],
    examples=[
        "拖滑块验证码：起点 X 300、起点 Y 500、终点 X 650、终点 Y 500、拖拽耗时 0.8（更像人工）",
        "把文件拖进文件夹：起点 X 200、起点 Y 150、终点 X 500、终点 Y 400、拖拽耗时 0.6",
        "选中一段文本：起点 X 100、起点 Y 300、终点 X 600、终点 Y 300、按住停留 0.2",
    ],
)
def _mouse_drag(node, ctx):
    p = node.params
    ctx.input.drag(int(p.get("x1", 0) or 0), int(p.get("y1", 0) or 0),
                   int(p.get("x2", 0) or 0), int(p.get("y2", 0) or 0),
                   duration=float(p.get("duration", 0.6) or 0.6),
                   button=str(p.get("button", "左键")),
                   hold=float(p.get("hold", 0.15) or 0.0))
    ctx.debug("鼠标拖拽完成")


@module(
    "mouse.scroll", "鼠标滚轮", "鼠标操作",
    desc="滚动页面；正数向下滚，负数向上滚",
    params=[
        Param("amount", "滚动格数", P_NUMBER, 3, minimum=-100, maximum=100,
              suffix="格（正=向下）",
              help="每次滚动的格数：正数向下滚（网页翻页），负数向上滚，如 -3 表示向上滚 3 格；"
                   "绝对值越大滚动越快"),
        Param("x", "滚轮位置 X", P_NUMBER, -1, minimum=-1, maximum=20000,
              help="滚动事件发送到的屏幕水平坐标：-1 表示不移动鼠标、在当前位置滚动；"
                   "要滚动指定窗口时填窗口内的坐标，需与 Y 同时填写"),
        Param("y", "滚轮位置 Y", P_NUMBER, -1, minimum=-1, maximum=20000,
              help="滚动事件发送到的屏幕垂直坐标：-1 表示在当前位置滚动；与 X 配合指定具体滚动位置"),
        Param("repeat", "重复次数", P_NUMBER, 1, minimum=1, maximum=100, suffix="次",
              help="连续滚动次数：1 表示只滚一次；滚动长页面时可设较大值配合「每次间隔」匀速滚动"),
        Param("gap", "每次间隔", P_FLOAT, 0.1, minimum=0.0, maximum=10.0, suffix="秒",
              help="相邻两次滚动之间的间隔；仅在重复次数大于 1 时生效，0 表示不间断连续滚动"),
    ],
    examples=[
        "匀速向下翻长网页：滚动格数 3、重复次数 5、每次间隔 0.2",
        "快速回滚到页面顶部：滚动格数 -10、重复次数 3",
        "滚动指定窗口（先把鼠标移到窗口内）：滚轮位置 X 640、滚轮位置 Y 400、滚动格数 5",
    ],
)
def _mouse_scroll(node, ctx):
    p = node.params
    x, y = int(p.get("x", -1)), int(p.get("y", -1))
    cx, cy = (None, None) if (x < 0 or y < 0) else (x, y)
    for i in range(int(p.get("repeat", 1) or 1)):
        ctx.check_stop()
        ctx.input.scroll(int(p.get("amount", 3) or 0), cx, cy)
        if i:
            ctx.sleep(float(p.get("gap", 0.1) or 0.0))
    ctx.debug(f"滚轮 {p.get('amount')} 格 ×{p.get('repeat')}")


@module(
    "mouse.get_position", "获取鼠标当前位置", "鼠标操作",
    desc="把当前鼠标坐标存入变量，供后续步骤使用",
    returns_value=True,
    params=[
        Param("save_var", "存入变量", P_TEXT, "mouse_pos",
              help="存坐标的变量名，后续步骤用 {{变量名.x}} 与 {{变量名.y}} 引用，如 {{mouse_pos.x}}"),
        Param("delay", "先等待", P_FLOAT, 0.0, minimum=0.0, maximum=60.0, suffix="秒",
              help="先等待若干秒再读取位置，给你时间把鼠标移到目标处；0 表示立即读取当前位置"),
    ],
    var_slots=[
        VarSlot("out", "鼠标坐标", name_param="save_var", vtype=vt.VT_DICT,
                desc="内容为 {x, y}，用 {{mouse_pos.x}} / {{mouse_pos.y}} 引用"),
    ],
    examples=[
        "记录当前鼠标位置：存入变量 mouse_pos，后续步骤用 {{mouse_pos.x}} / {{mouse_pos.y}} 引用坐标",
        "先移好鼠标再记录：先等待 3、存入变量 mouse_pos，倒计时内把鼠标移到目标处再读取",
    ],
)
def _mouse_get_pos(node, ctx):
    wait = float(node.params.get("delay", 0.0) or 0.0)
    if wait:
        ctx.info(f"请把鼠标移到目标位置，{wait:.0f} 秒后读取…")
        ctx.sleep(wait)
    x, y = ctx.input.position()
    var = (node.params.get("save_var") or "mouse_pos").strip() or "mouse_pos"
    ctx.set_var(var, {"x": x, "y": y})
    ctx.set_var(f"{var}.x", x)
    ctx.set_var(f"{var}.y", y)
    ctx.success(f"📍 鼠标位置 ({x},{y}) 已存入 {{{{{var}}}}}")
