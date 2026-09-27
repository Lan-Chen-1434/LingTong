"""功能模块公共辅助函数。"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple


def parse_region(text: Any, ctx=None) -> Optional[Tuple[int, int, int, int]]:
    """把 "x,y,w,h" 文本解析成区域元组；空或全屏 → None。"""
    if ctx is not None:
        text = ctx.resolve(text)
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in ("全屏", "0", "-"):
        return None
    s = s.replace("，", ",").replace(" ", "")
    parts = s.split(",")
    if len(parts) != 4:
        return None
    try:
        x, y, w, h = (int(float(p)) for p in parts)
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def click_at(ctx, x: int, y: int, button: str = "左键",
             clicks: int = 1, offset_x: int = 0, offset_y: int = 0) -> None:
    ctx.input.click(int(x) + int(offset_x), int(y) + int(offset_y),
                    button=button, clicks=clicks)
    ctx.debug(f"点击 ({int(x) + int(offset_x)}, {int(y) + int(offset_y)}) {button}×{clicks}")


def require_image(node, ctx, param: str = "image") -> List[str]:
    """取模板图列表；缺失时抛错。相对路径基于流程文件夹解析。"""
    raw = node.params.get(param) or []
    imgs = [p for p in (raw if isinstance(raw, list) else [raw]) if p]
    imgs = [ctx.resolve(p) for p in imgs]
    imgs = [ctx.resolve_asset(p) for p in imgs]
    imgs = [p for p in imgs if p and os.path.isfile(p)]
    if not imgs:
        raise RuntimeError(f"未设置模板图片或图片文件不存在（路径：{raw}）")
    return imgs


def wait_for_image(node, ctx, param: str = "image", default_wait: float = 0.0):
    """按节点参数等待并定位图片，返回 MatchResult。找不到返回 None。"""
    imgs = require_image(node, ctx, param)
    conf = float(node.params.get("confidence", 0.85) or 0.85)
    wait = float(node.params.get("wait", default_wait) or 0.0)
    region = parse_region(node.params.get("region", ""), ctx)
    interval = float(node.params.get("interval", 0.5) or 0.5)
    match = ctx.find_image(imgs, confidence=conf, region=region,
                           timeout=wait, interval=interval)
    if match:
        ctx.debug(f"✓ 找到图像 {os.path.basename(match.template)} "
                  f"@ ({match.center_x},{match.center_y}) 相似度 {match.score:.2f}")
    return match


def ensure_dir(path: str) -> str:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    return path
