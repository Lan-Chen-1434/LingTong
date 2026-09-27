"""
图像识别模块组
================
基于 OpenCV 模板匹配实现"看图操作电脑"，是整套工具的核心能力。
支持：多模板候选、置信度阈值、限定识别区域、等待出现、偏移点击、坐标回写变量。
"""
from __future__ import annotations

import os
import time

from core.registry import module
from core.spec import (P_BOOL, P_FLOAT, P_IMAGE, P_NUMBER, P_REGION, P_SELECT,
                       P_TEXT, Param, VarSlot)
from core import vartypes as vt

from .common import click_at, parse_region, require_image, wait_for_image

_REGION_HELP = "限定搜索范围可大幅提速。格式 x,y,w,h（如 0,0,1920,300）；留空 = 全屏"


def _direction_region(anchor, direction: str, distance: int,
                      margin: int = 24):
    """由锚点矩形向外扩展出某个方向的搜索区域（锚点区域找图用）。"""
    ax, ay, aw, ah = anchor.x, anchor.y, anchor.w, anchor.h
    if direction == "右侧":
        return (ax + aw - 4, ay - margin, distance + 4, ah + 2 * margin)
    if direction == "左侧":
        return (ax - distance, ay - margin, distance + 4, ah + 2 * margin)
    if direction == "下方":
        return (ax - margin, ay + ah - 4, aw + 2 * margin, distance + 4)
    if direction == "上方":
        return (ax - margin, ay - distance, aw + 2 * margin, distance + 4)
    return None


@module(
    "image.click", "图像点击", "图像识别",
    desc="在屏幕上找到模板图片并点击它；支持锚点定位（先找参照物再点目标），类似 UiPath 的 Anchor Base",
    params=[
        Param("image", "模板图片", P_IMAGE, [],
              help="可添加多张，命中任意一张即算成功；支持「抓图取图」直接从屏幕截取"),
        Param("click_type", "操作方式", P_SELECT, "单击",
              choices=["单击", "双击", "三击", "右键单击", "移动到(悬停)", "仅定位不点击"],
              help="对识别到的目标执行的操作：双击适合打开，三击常用于全选整行文本，"
                   "移动到(悬停)只移鼠标不点击，仅定位不点击配合「坐标保存到变量」使用"),
        Param("locate_mode", "定位方式", P_SELECT, "直接点击图像",
              choices=["直接点击图像", "锚点偏移点击", "锚点区域找图"],
              help="锚点模式：先找一个稳定唯一的参照物（如「用户名：」标签），再相对它定位。"
                   "锚点找不到会报错——配合失败策略即可实现「判断锚点是否存在」"),
        Param("anchor", "锚点图片", P_IMAGE, [],
              visible_when={"locate_mode": ["锚点偏移点击", "锚点区域找图"]},
              help="截取稳定且唯一的参照元素，例如输入框左侧的标签文字"),
        Param("direction", "目标在锚点的", P_SELECT, "右侧",
              choices=["右侧", "左侧", "上方", "下方"],
              visible_when={"locate_mode": ["锚点区域找图"]},
              help="目标图在锚点的哪个方向，就在锚点该方向「最大距离」范围内搜索；方向选错会找不到目标"),
        Param("distance", "最大距离", P_NUMBER, 300, minimum=20, maximum=3000, suffix="像素",
              visible_when={"locate_mode": ["锚点区域找图"]},
              help="在锚点该方向多远范围内搜索目标图"),
        Param("confidence", "相似度阈值", P_FLOAT, 0.85, minimum=0.30, maximum=1.00,
              step=0.01, help="推荐 0.80~0.92；界面有缩放/换肤时会降低"),
        Param("wait", "等待出现", P_FLOAT, 5.0, minimum=0.0, maximum=600.0,
              suffix="秒", help="在超时时间内轮询等待图片出现，0 = 只找一次"),
        Param("interval", "轮询间隔", P_FLOAT, 0.5, minimum=0.1, maximum=10.0, suffix="秒",
              help="每次查找失败后的等待时长；页面加载慢时加大间隔可减少无效检测和 CPU 占用"),
        Param("region", "识别区域", P_REGION, "", help=_REGION_HELP),
        Param("offset_x", "偏移 X", P_NUMBER, 0, minimum=-2000, maximum=2000, suffix="像素",
              help="点击位置相对图片中心的偏移；锚点模式下相对锚点中心"),
        Param("offset_y", "偏移 Y", P_NUMBER, 0, minimum=-2000, maximum=2000, suffix="像素",
              help="点击位置相对图片中心的纵向偏移，正数向下、负数向上；锚点模式下相对锚点中心"),
        Param("restore_cursor", "点击后鼠标归位", P_BOOL, False,
              help="开启：点击完成后把鼠标移回原位，不打扰用户手头操作；"
                   "关闭：鼠标停留在点击位置"),
        Param("save_var", "坐标保存到变量", P_TEXT, "",
              placeholder="如 last_point（留空=不保存）",
              help="保存后可用 {{last_point.x}} / {{last_point.y}} 引用"),
    ],
    var_slots=[
        VarSlot("out", "命中坐标", name_param="save_var", vtype=vt.VT_DICT,
                desc="内容为 {x, y, score}；留空变量名 = 不保存"),
    ],
    examples=[
        "点击屏幕上的「登录」按钮：模板图片 截该按钮、操作方式 单击、相似度阈值 0.85、等待出现 5",
        "双击打开桌面图标：模板图片 截该图标、操作方式 双击、识别区域 0,0,1920,300（只搜上半屏，更快）",
        "点输入框但框本身不好截：定位方式 锚点偏移点击、锚点图片 截输入框左侧「用户名：」标签、偏移 X 60",
        "点列表每行的「详情」按钮：定位方式 锚点区域找图、锚点图片 截行首序号、目标在锚点的 右侧、最大距离 400",
    ],
)
def _image_click(node, ctx):
    p = node.params
    conf = float(p.get("confidence", 0.85) or 0.85)
    wait = float(p.get("wait", 5.0) or 0.0)
    region = parse_region(p.get("region", ""), ctx)
    interval = float(p.get("interval", 0.5) or 0.5)
    ox = int(p.get("offset_x", 0) or 0)
    oy = int(p.get("offset_y", 0) or 0)
    way = str(p.get("click_type", "单击"))
    locate = str(p.get("locate_mode", "直接点击图像"))

    origin = ctx.input.position() if p.get("restore_cursor") else None
    match = None

    if locate == "锚点偏移点击":
        # 只找锚点，点击位置 = 锚点中心 + 偏移（目标本身可能无法截图识别）
        anchor_imgs = require_image(node, ctx, "anchor")
        anchor = ctx.find_image(anchor_imgs, conf, region, timeout=wait, interval=interval)
        if anchor is None:
            names = "、".join(os.path.basename(i) for i in anchor_imgs)
            raise RuntimeError(f"等待 {wait:.1f}s 未找到锚点图像：{names}")
        cx, cy = anchor.center_x + ox, anchor.center_y + oy
        ctx.info(f"⚓ 锚点命中 ({anchor.center_x},{anchor.center_y})"
                 f"，按偏移 ({ox},{oy}) 点击 → ({cx},{cy})")
        match = anchor

    elif locate == "锚点区域找图":
        # 先找锚点，再在锚点某方向的限定区域内找目标图
        anchor_imgs = require_image(node, ctx, "anchor")
        anchor = ctx.find_image(anchor_imgs, conf, region, timeout=wait, interval=interval)
        if anchor is None:
            names = "、".join(os.path.basename(i) for i in anchor_imgs)
            raise RuntimeError(f"等待 {wait:.1f}s 未找到锚点图像：{names}")
        direction = str(p.get("direction", "右侧"))
        distance = int(p.get("distance", 300) or 300)
        sub = _direction_region(anchor, direction, distance)
        ctx.debug(f"⚓ 锚点命中 ({anchor.center_x},{anchor.center_y})"
                  f"，向其{direction} {distance}px 内查找目标…")
        imgs = require_image(node, ctx, "image")
        match = ctx.find_image(imgs, conf, sub, timeout=0)
        if match is None:
            raise RuntimeError(f"锚点已找到，但在其{direction} {distance}px 范围内未找到目标图像")
        cx, cy = match.center_x + ox, match.center_y + oy

    else:
        imgs = require_image(node, ctx, "image")
        match = ctx.find_image(imgs, conf, region, timeout=wait, interval=interval)
        if match is None:
            names = "、".join(os.path.basename(i) for i in imgs)
            raise RuntimeError(f"等待 {wait:.1f}s 未在屏幕上找到图像：{names}")
        cx, cy = match.center_x + ox, match.center_y + oy

    if way == "移动到(悬停)":
        ctx.input.move(cx, cy, 0.25)
    elif way == "仅定位不点击":
        pass
    elif way == "双击":
        click_at(ctx, cx, cy, "左键", 2)
    elif way == "三击":
        click_at(ctx, cx, cy, "左键", 3)
    elif way == "右键单击":
        click_at(ctx, cx, cy, "右键", 1)
    else:
        click_at(ctx, cx, cy, "左键", 1)

    var = (p.get("save_var") or "").strip()
    if var:
        ctx.set_var(var, {"x": cx, "y": cy, "score": round(match.score, 4)})
    if origin:
        ctx.input.move(origin[0], origin[1], 0.2)

    ctx.info(f"🖱 图像点击「{os.path.basename(match.template)}」→ ({cx},{cy}) "
             f"相似度 {match.score:.2f}")


@module(
    "image.wait", "等待图像出现", "图像识别",
    desc="阻塞等待某个界面元素出现，常用于等待页面加载完成",
    params=[
        Param("image", "模板图片", P_IMAGE, [],
              help="要等待的界面元素截图，出现即继续执行；可添加多张，任意一张出现就算成功"),
        Param("confidence", "相似度阈值", P_FLOAT, 0.85, minimum=0.30, maximum=1.00, step=0.01,
              help="推荐 0.80~0.92；界面有缩放/换肤时可适当调低"),
        Param("wait", "最长等待", P_FLOAT, 30.0, minimum=0.5, maximum=3600.0, suffix="秒",
              help="最长等待秒数，超时未出现则按失败策略处理；等待期间流程阻塞在本步"),
        Param("interval", "轮询间隔", P_FLOAT, 0.5, minimum=0.1, maximum=10.0, suffix="秒",
              help="每次检测之间的间隔；页面刷新慢时加大间隔可减少无效检测"),
        Param("region", "识别区域", P_REGION, "", help=_REGION_HELP),
        Param("need_disappear", "改为等待图像消失", P_BOOL, False,
              help="打开后：等到该图像从屏幕上消失才算成功"),
        Param("save_var", "坐标保存到变量", P_TEXT, "", placeholder="留空=不保存",
              help="保存命中坐标的变量名，内容为 {x, y, score}，"
                   "后续步骤可用 {{变量名.x}} 引用；留空 = 不保存"),
    ],
    var_slots=[
        VarSlot("out", "命中坐标", name_param="save_var", vtype=vt.VT_DICT,
                desc="内容为 {x, y, score}；留空变量名 = 不保存"),
    ],
    examples=[
        "等网页加载完成：模板图片 截加载后的页面标志（如 logo）、最长等待 30、相似度阈值 0.85",
        "等加载动画/弹窗消失：模板图片 截加载动画、改为等待图像消失 开启、最长等待 15",
        "等提示出现并记下位置：模板图片 截提示文字、坐标保存到变量 tip_pos，后续用 {{tip_pos.x}} 引用",
    ],
)
def _image_wait(node, ctx):
    p = node.params
    imgs = require_image(node, ctx)
    conf = float(p.get("confidence", 0.85) or 0.85)
    wait = float(p.get("wait", 30.0) or 0.0)
    region = parse_region(p.get("region", ""), ctx)
    interval = float(p.get("interval", 0.5) or 0.5)
    disappear = bool(p.get("need_disappear"))

    if disappear:
        ctx.info(f"⏳ 等待图像消失（最长 {wait:.0f}s）…")
        start = time.time()
        while True:
            ctx.check_stop()
            if ctx.screen.find_any(imgs, conf, region, timeout=0) is None:
                ctx.success("✓ 图像已消失")
                return
            if time.time() - start >= wait:
                raise RuntimeError(f"等待 {wait:.1f}s 后图像仍未消失")
            ctx.sleep(interval)

    ctx.info(f"⏳ 等待图像出现（最长 {wait:.0f}s）…")
    match = wait_for_image(node, ctx, "image", wait)
    if match is None:
        raise RuntimeError(f"等待 {wait:.1f}s 后图像未出现")
    var = (p.get("save_var") or "").strip()
    if var:
        ctx.set_var(var, {"x": match.center_x, "y": match.center_y,
                          "score": round(match.score, 4)})
    ctx.success(f"✓ 图像已出现 @ ({match.center_x},{match.center_y})")


@module(
    "image.exists", "判断图像是否存在", "图像识别",
    desc="判断界面上有没有某个元素，结果存入变量，供「条件判断」使用",
    returns_value=True,
    params=[
        Param("image", "模板图片", P_IMAGE, [],
              help="要检测的界面元素截图；可添加多张，存在任意一张即判断为存在"),
        Param("confidence", "相似度阈值", P_FLOAT, 0.85, minimum=0.30, maximum=1.00, step=0.01,
              help="推荐 0.80~0.92；界面有缩放/换肤时可适当调低"),
        Param("region", "识别区域", P_REGION, "", help=_REGION_HELP),
        Param("save_var", "结果存入变量", P_TEXT, "image_found",
              help="变量值：True / False。条件判断里写 {{image_found}} == True"),
        Param("wait", "等待出现", P_FLOAT, 0.0, minimum=0.0, maximum=600.0, suffix="秒",
              help="在超时时间内轮询等待，期间图像出现则提前成功；0 = 只检测一次"),
    ],
    var_slots=[
        VarSlot("out", "判断结果", name_param="save_var", vtype=vt.VT_BOOL,
                desc="图像存在 = True，不存在 = False；条件判断里写 {{image_found}} == True"),
    ],
    examples=[
        "判断有没有「新增」按钮再决定分支：模板图片 截该按钮、结果存入变量 has_btn，"
        "条件判断里写 {{has_btn}} == True",
        "3 秒内图标出现即算成功：模板图片 截图标、等待出现 3、结果存入变量 icon_found",
    ],
)
def _image_exists(node, ctx):
    p = node.params
    match = wait_for_image(node, ctx, "image", 0.0)
    var = (p.get("save_var") or "image_found").strip() or "image_found"
    ctx.set_var(var, match is not None)
    if match:
        ctx.set_var(f"{var}.x", match.center_x)
        ctx.set_var(f"{var}.y", match.center_y)
        ctx.success(f"✓ 图像存在 → {{{{{var}}}}} = True")
    else:
        ctx.warn(f"✗ 图像不存在 → {{{{{var}}}}} = False")


@module(
    "image.find_all", "查找所有匹配并批量点击", "图像识别",
    desc="找出屏幕上所有匹配项（例如列表里的每一行「详情」按钮）并逐个点击",
    params=[
        Param("image", "模板图片", P_IMAGE, [],
              help="目标元素截图，如列表里每行都有的「详情」按钮；会找出屏幕上所有匹配项"),
        Param("confidence", "相似度阈值", P_FLOAT, 0.88, minimum=0.30, maximum=1.00, step=0.01,
              help="推荐 0.85~0.95；太低会把相似元素也当成匹配项，太高可能漏识别"),
        Param("region", "识别区域", P_REGION, "", help=_REGION_HELP),
        Param("action", "对每个匹配项", P_SELECT, "仅记录坐标",
              choices=["仅记录坐标", "依次单击", "依次双击"],
              help="仅记录坐标=只把位置存入变量不点击；依次单击/双击=按从左到右、"
                   "从上到下逐个点击，适合批量处理列表里的每一行"),
        Param("max_count", "最多处理个数", P_NUMBER, 50, minimum=1, maximum=9999, suffix="个",
              help="最多识别并处理的匹配个数，超出的忽略；防止页面上意外出现"
                   "大量相似元素时点击失控"),
        Param("save_var", "坐标列表存入变量", P_TEXT, "matches",
              help="内容为列表，可用「遍历变量」循环处理"),
    ],
    var_slots=[
        VarSlot("out", "匹配项列表", name_param="save_var", vtype=vt.VT_TABLE,
                desc="每行一个匹配项（x / y / score 三列），可用「遍历变量」循环处理"),
    ],
    examples=[
        "批量点开列表每行的「详情」：模板图片 截行内「详情」按钮、对每个匹配项 依次单击、最多处理个数 50",
        "只收集位置不点击：模板图片 截目标、对每个匹配项 仅记录坐标、坐标列表存入变量 matches，"
        "配合「遍历变量」逐行处理",
    ],
)
def _image_find_all(node, ctx):
    p = node.params
    imgs = require_image(node, ctx)
    conf = float(p.get("confidence", 0.88) or 0.88)
    region = parse_region(p.get("region", ""), ctx)
    limit = int(p.get("max_count", 50) or 50)
    action = str(p.get("action", "仅记录坐标"))

    hits = ctx.screen.find_all(imgs, conf, region)[:limit]
    var = (p.get("save_var") or "matches").strip() or "matches"
    ctx.set_var(var, [{"x": m.center_x, "y": m.center_y, "score": round(m.score, 4)}
                      for m in hits])
    if not hits:
        ctx.warn("未找到任何匹配项")
        return
    ctx.info(f"✓ 共找到 {len(hits)} 个匹配项，已存入 {{{{{var}}}}}")
    if action == "依次单击":
        for m in hits:
            ctx.check_stop()
            click_at(ctx, m.center_x, m.center_y, "左键", 1)
            ctx.sleep(0.25)
    elif action == "依次双击":
        for m in hits:
            ctx.check_stop()
            click_at(ctx, m.center_x, m.center_y, "左键", 2)
            ctx.sleep(0.35)


@module(
    "image.pixel", "像素颜色判断", "图像识别",
    desc="读取指定坐标的颜色并与目标色比较，适合判断按钮是否高亮、状态灯颜色",
    returns_value=True,
    params=[
        Param("x", "坐标 X", P_NUMBER, 0, minimum=0, maximum=20000,
              picker="pixel",
              help="取样点横坐标（屏幕像素），可点右侧取色器从屏幕拾取；"
                   "开启「坐标来自变量」后填变量名，如 last_point.x"),
        Param("y", "坐标 Y", P_NUMBER, 0, minimum=0, maximum=20000,
              help="取样点纵坐标（屏幕像素）；开启「坐标来自变量」后填变量名，如 last_point.y"),
        Param("color", "目标颜色", P_TEXT, "#FF0000", placeholder="#RRGGBB",
              help="十六进制颜色如 #FF0000（红色）、#00FF00（绿色）；判断高亮按钮时常用"),
        Param("tolerance", "容差", P_NUMBER, 12, minimum=0, maximum=255,
              help="每个通道允许的偏差，光线变化大可调高"),
        Param("result_type", "结果类型", P_SELECT, "布尔",
              choices=["布尔", "字符串"],
              help="布尔=写入 True / False；字符串=写入 匹配 / 不匹配"),
        Param("save_var", "结果存入变量", P_TEXT, "color_ok",
              help="保存判断结果的变量名；实际颜色会写入 {{变量名.rgb}}（如 255,0,0）"),
        Param("use_var_coord", "坐标来自变量", P_BOOL, False,
              help="打开后 X/Y 填写变量名，如 last_point.x"),
    ],
    var_slots=[
        VarSlot("out", "判断结果", name_param="save_var", type_param="result_type",
                vtype=vt.VT_BOOL, type_choices=["布尔", "字符串"],
                desc="颜色匹配 = True（或 匹配），不匹配 = False（或 不匹配）"),
    ],
    examples=[
        "判断保存按钮是否高亮：坐标 X/Y 点右侧取色器从屏幕拾取、目标颜色 #00A2FF、容差 20、结果存入变量 btn_on",
        "对上一步图像点击的位置验色：坐标来自变量 开启、坐标 X last_point.x、坐标 Y last_point.y、目标颜色 #FF0000",
        "想看实际颜色值：结果存入变量 c 后读 {{c.rgb}}（如 255,0,0）；结果类型 选 字符串 则写入 匹配/不匹配",
    ],
)
def _pixel_check(node, ctx):
    p = node.params
    if p.get("use_var_coord"):
        x = int(ctx.resolve_value("{{" + str(p.get("x", "0")) + "}}") or 0)
        y = int(ctx.resolve_value("{{" + str(p.get("y", "0")) + "}}") or 0)
    else:
        x, y = int(p.get("x", 0)), int(p.get("y", 0))

    target = str(p.get("color", "#FF0000")).strip().lstrip("#")
    try:
        tr, tg, tb = int(target[0:2], 16), int(target[2:4], 16), int(target[4:6], 16)
    except (ValueError, IndexError):
        raise RuntimeError(f"颜色格式不正确：{p.get('color')}（应为 #RRGGBB）")

    r, g, b = ctx.screen.pixel(x, y)
    tol = int(p.get("tolerance", 12) or 12)
    ok = (abs(r - tr) <= tol and abs(g - tg) <= tol and abs(b - tb) <= tol)
    var = (p.get("save_var") or "color_ok").strip() or "color_ok"
    as_str = str(p.get("result_type") or "布尔") == "字符串"
    val = ("匹配" if ok else "不匹配") if as_str else ok
    ctx.set_var(var, val)
    ctx.set_var(f"{var}.rgb", f"{r},{g},{b}")
    ctx.info(f"🎨 ({x},{y}) 实际 RGB({r},{g},{b}) vs 目标({tr},{tg},{tb}) → "
             f"{'匹配' if ok else '不匹配'}，{{{{{var}}}}} = {val}")


@module(
    "image.save_crop", "截取屏幕区域保存", "图像识别",
    desc="把屏幕上的指定区域截图存成图片，可直接当模板图用，也可提取图中的文字/表格",
    params=[
        Param("region", "截取区域", P_REGION, "", allow_empty=False,
              help=_REGION_HELP + "；点「框选区域」可直接在屏幕上拖选（此处不可留空）"),
        Param("path", "保存路径", P_TEXT, "output/image/shot_{{timestamp}}.png",
              help="支持变量；相对路径基于本流程文件夹"),
        Param("wait", "截取前等待", P_FLOAT, 0.0, minimum=0.0, maximum=60.0, suffix="秒",
              help="先等待该秒数再截图，等界面动画/加载完成；0 = 立即截取"),
        Param("extract_mode", "提取方式", P_SELECT, "OCR 识别",
              choices=["OCR 识别", "浏览器源代码"],
              help="OCR 识别=对截图做文字识别（有误差）；"
                   "浏览器源代码=复制网页 DOM 里的真实数据，100% 准确且不受屏幕范围限制"
                   "（表头超宽、行数多都能拿到；但分页/虚拟滚动加载的表格只能拿到当前页）"),
        Param("browser", "浏览器窗口", P_TEXT, "Chrome",
              placeholder="窗口标题包含的关键词",
              visible_when={"extract_mode": ["浏览器源代码"]},
              help="Windows 按窗口标题匹配；macOS 按应用名匹配（Chrome / Safari / Edge 等），"
                   "并需在 系统设置→隐私与安全性→辅助功能 中授权。支持 {{变量}}"),
        Param("select_all", "先全选页面", P_BOOL, True,
              visible_when={"extract_mode": ["浏览器源代码"]},
              help="开启=Ctrl+A 复制整页，再自动过滤出表格；"
                   "关闭=只复制已选中的内容——运行前手动选中表格，"
                   "或在上一步用「鼠标拖拽」模块自动框选表格区域（页面有多个表格时推荐关闭）"),
        Param("path_var", "输出路径变量", P_TEXT, "shot_path",
              placeholder="留空则不输出",
              help="把截图的完整保存路径写入该变量，后续步骤可用 {{变量名}} 引用；留空 = 不输出"),
        Param("content_var", "输出内容变量", P_TEXT, "",
              placeholder="留空则不提取",
              help="把提取到的文字/表格写入该变量，留空 = 不提取；内容形式由「输出内容类型」"
                   "决定（OCR 识别方式需先安装 OCR 组件）"),
        Param("content_type", "输出内容类型", P_SELECT, "字符串",
              choices=["字符串", "表格"],
              help="字符串=提取全部文字；表格=按行/列提取成表格变量。"
                   "浏览器源代码模式下：字符串=整页文字，表格=按截图区域的表头"
                   "在页面数据里自动定位到同一张表再提取（首行为列名）"),
    ],
    var_slots=[
        VarSlot("out", "保存路径", name_param="path_var", vtype=vt.VT_STRING,
                desc="截图成功后的完整文件路径（字符串）"),
        VarSlot("out", "截图内容", name_param="content_var", type_param="content_type",
                vtype=vt.VT_STRING, type_choices=["字符串", "表格"],
                desc="提取图中内容：字符串=全部文字；表格=按行列提取成表格变量。"
                     "变量名留空则不提取"),
    ],
    examples=[
        "截图当模板图用：截取区域 框选目标、保存路径 output/image/btn.png、输出路径变量 shot_path",
        "等 2 秒动画结束再截：截取前等待 2、保存路径 output/image/shot_{{timestamp}}.png（默认即可）",
        "提取网页表格（100% 准确）：提取方式 浏览器源代码、浏览器窗口 Chrome（macOS 可用 Safari，"
        "需在辅助功能授权）、输出内容变量 table、输出内容类型 表格",
        "提取截图里的文字：提取方式 OCR 识别、输出内容变量 text、输出内容类型 字符串（需先安装 OCR 组件）",
    ],
)
def _save_crop(node, ctx):
    region = parse_region(node.params.get("region", ""), ctx)
    if region is None:
        raise RuntimeError("请填写截取区域，格式 x,y,w,h")
    wait = float(node.params.get("wait", 0.0) or 0.0)
    if wait:
        ctx.sleep(wait)
    path = ctx.resolve(node.params.get("path") or "output/image/shot.png")
    if not os.path.isabs(path):
        path = os.path.join(ctx.base_dir, path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not ctx.screen.save_crop(region, path):
        raise RuntimeError("截图保存失败")
    ctx.success(f"📷 已保存截图 → {path}")

    path_var = (node.params.get("path_var") or "").strip()
    if path_var:
        ctx.set_var(path_var, path)
        ctx.info(f"   路径已写入 {{{{{path_var}}}}}")

    content_var = (node.params.get("content_var") or "").strip()
    if not content_var:
        return
    want_table = str(node.params.get("content_type") or "字符串") == "表格"

    if str(node.params.get("extract_mode") or "OCR 识别") == "浏览器源代码":
        _extract_from_browser(node, ctx, content_var, want_table, path, region)
        return

    from core.drivers.ocr import HAS_OCR, image_to_table, image_to_text, install_hint
    if not HAS_OCR:
        raise RuntimeError(install_hint())
    if want_table:
        rows = image_to_table(path)
        ctx.set_var(content_var, rows)
        ctx.success(f"📷 已提取表格 {{{{{content_var}}}}}（{len(rows)} 行）")
    else:
        text = image_to_text(path)
        ctx.set_var(content_var, text)
        ctx.success(f"📷 已提取文字 {len(text)} 字符 → {{{{{content_var}}}}}")


def _header_tokens_from_shot(path: str):
    """OCR 截图顶部区域（表头行），返回表头关键词列表；无 OCR 组件时返回空。"""
    from core.drivers.ocr import HAS_OCR, ocr_regions
    if not HAS_OCR:
        return []
    try:
        from PIL import Image
        img = Image.open(path)
        w, h = img.size
        band = img.crop((0, 0, w, max(24, int(h * 0.15))))     # 顶部约15%即表头带
        tmp = os.path.join(os.path.dirname(os.path.abspath(path)),
                           f"_hdr_{os.getpid()}.png")
        band.save(tmp)
        try:
            regions = ocr_regions(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        text = " ".join(r["text"] for r in regions)
        import re
        return [t for t in re.split(r"[^\w一-鿿]+", text) if t]
    except Exception:
        return []


def _extract_from_browser(node, ctx, content_var: str, want_table: bool,
                          shot_path: str = "", region=None) -> None:
    """浏览器源代码提取：激活浏览器窗口 → Ctrl+A 全选 → Ctrl+C 复制 → 读剪贴板。

    复制到的是页面真实数据（非截图识别），表格在剪贴板里是制表符分隔的文本。
    整页内容按"非表格行"切成若干张表；表格模式下用截图顶部的表头 OCR 结果
    在候选表中匹配，定位到你要的那张表，而不是盲目取第一张。
    """
    kw = ctx.resolve(node.params.get("browser", "")).strip()
    if kw and not ctx.window.activate(kw, wait=0.3):
        raise RuntimeError(f"找不到浏览器窗口：{kw}（可修改「浏览器窗口」关键词）")
    if kw:
        ctx.sleep(0.2)                                   # 等页面就绪（激活本身已有等待）

    ctx.input.set_clipboard("")
    ctx.sleep(0.08)
    if node.params.get("select_all", True):
        # 先在截取区域左上角点一下，确保焦点在页面上，Ctrl+A 才会选中整个文档
        cx, cy = (int(region[0]), int(region[1])) if region else ctx.input.position()
        ctx.input.click(cx, cy, button="左键", clicks=1)
        ctx.sleep(0.12)
        ctx.input.select_all()
        ctx.sleep(0.4)
    ctx.input.copy()
    ctx.sleep(0.45)
    text = ctx.input.get_clipboard()
    if node.params.get("select_all", True):
        # 在截取区域左上角单击，收起全选高亮（Esc/方向键在浏览器里都不起作用）
        cx, cy = (int(region[0]), int(region[1])) if region else ctx.input.position()
        ctx.input.click(cx, cy, button="左键", clicks=1)
    if not text.strip():
        raise RuntimeError("未能从浏览器复制到内容（页面可能没有可选中区域）")

    if want_table:
        # 非表格行是表与表的分界：整页复制内容 → 按段切成若干张候选表
        tables = []
        cur = []
        for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if "\t" in ln:
                cur.append(ln.split("\t"))
            elif cur:
                tables.append(cur)
                cur = []
        if cur:
            tables.append(cur)
        if not tables:
            raise RuntimeError("复制到的内容里没有表格（没有制表符分隔），"
                               "可改用「字符串」类型，或先手动选中页面上的表格")

        # 用截图区域的表头在候选表里定位目标表（仅多张表时才需要 OCR 表头，
        # 单张表直接取之，省一次识别耗时）
        pick = 0
        if len(tables) > 1:
            tokens = _header_tokens_from_shot(shot_path) if shot_path else []
            if tokens:
                best_score = 0
                for i, t in enumerate(tables):
                    head = [c.lower() for c in t[0]]
                    score = sum(1 for tok in tokens
                               if any(tok.lower() in c for c in head))
                    if score > best_score:
                        pick, best_score = i, score
                if best_score == 0:
                    ctx.warn(f"表头 {tokens} 在页面数据中没匹配到，已回退取第一张表")
            elif shot_path:
                ctx.info("未安装 OCR 组件，无法按截图表头定位表格，已取第一张表")

        cells = tables[pick]
        ncol = max(len(c) for c in cells)
        header = [(h.strip() or f"列{i + 1}") for i, h in enumerate(cells[0])]
        header += [f"列{i + 1}" for i in range(len(header), ncol)]
        rows = []
        for r in cells[1:]:
            r = [c.strip() for c in r] + [""] * (ncol - len(r))
            rows.append(dict(zip(header, r)))
        ctx.set_var(content_var, rows)
        ctx.success(f"🌐 已从浏览器提取表格 {{{{{content_var}}}}}（{len(rows)} 行 × {ncol} 列）")
    else:
        ctx.set_var(content_var, text)
        ctx.success(f"🌐 已从浏览器提取文字 {len(text)} 字符 → {{{{{content_var}}}}}")
