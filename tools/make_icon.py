"""
生成「灵瞳」程序图标
======================
设计语言：深空蓝紫 + 科技眼（六边形取景框 + 虹膜 + 发光瞳孔）+ 电路走线。
暗色底象征"屏幕深处"，发光瞳孔象征"图像识别的眼睛"。

输出 assets/icons/app.ico（16/24/32/48/64/128/256 七尺寸）、app.icns（macOS，
内含 16~1024 各档 PNG）、app.png、app_1024.png。
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "icons")
S = 1024

CYAN = (34, 211, 238)
VIOLET = (139, 92, 246)
CORE = (94, 234, 212)
WHITE = (245, 250, 255)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def hexagon(cx, cy, r, rot=-90):
    return [(cx + r * math.cos(math.radians(rot + i * 60)),
             cy + r * math.sin(math.radians(rot + i * 60))) for i in range(6)]


def make_base() -> Image.Image:
    """深空圆角底板：径向渐变 + 点阵。"""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    center_c = (24, 34, 76)       # 中心亮一些的藏蓝
    edge_c = (6, 9, 20)           # 边缘近黑
    cx = cy = S / 2
    maxd = math.hypot(cx, cy)
    px = img.load()
    for y in range(S):
        for x in range(0, S, 2):
            d = math.hypot(x - cx, y - cy) / maxd
            d = min(1.0, max(0.0, (d - 0.08) * 1.25))
            c = lerp(center_c, edge_c, d)
            for dx in range(2):
                if x + dx < S:
                    px[x + dx, y] = (*c, 255)

    # 点阵网格（很淡）
    d = ImageDraw.Draw(img)
    step = S // 16
    for gy in range(step, S, step):
        for gx in range(step, S, step):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=(90, 130, 220, 26))

    # 圆角遮罩
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=int(S * 0.235), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def make_glow() -> Image.Image:
    """辉光层：高亮元素画在这里，统一模糊后再叠加。"""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = S / 2, S / 2

    # 瞳孔大辉光
    r_core = S * 0.105
    d.ellipse([cx - r_core * 1.7, cy - r_core * 1.7, cx + r_core * 1.7, cy + r_core * 1.7],
              fill=(*CYAN, 110))
    # 六边形边缘辉光
    d.line(hexagon(cx, cy, S * 0.335), fill=(*CYAN, 90), width=int(S * 0.02), joint="curve")
    d.polygon(hexagon(cx, cy, S * 0.335), outline=(*CYAN, 90))
    return layer.filter(ImageFilter.GaussianBlur(S * 0.035))


def draw_motif(img: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = S / 2, S / 2

    # ---- 电路走线（上下左右，从六边形外圈伸出）----
    r_hex = S * 0.335
    arm = int(S * 0.018)
    trace = [
        (cx, cy - r_hex - S * 0.005, cx, cy - r_hex - S * 0.085),
        (cx, cy + r_hex + S * 0.005, cx, cy + r_hex + S * 0.085),
        (cx - r_hex - S * 0.005, cy, cx - r_hex - S * 0.085, cy),
        (cx + r_hex + S * 0.005, cy, cx + r_hex + S * 0.085, cy),
    ]
    for (x1, y1, x2, y2) in trace:
        d.line([x1, y1, x2, y2], fill=(*CYAN, 210), width=arm)
        d.ellipse([x2 - arm * 1.4, y2 - arm * 1.4, x2 + arm * 1.4, y2 + arm * 1.4],
                  fill=(*CORE, 235))

    # 斜向两条短走线（右上、左下），增加电路感
    for ang, rr in ((30, 1.06), (210, 1.06)):
        x1 = cx + r_hex * rr * math.cos(math.radians(ang))
        y1 = cy + r_hex * rr * math.sin(math.radians(ang))
        x2 = cx + r_hex * (rr + 0.055) * math.cos(math.radians(ang))
        y2 = cy + r_hex * (rr + 0.055) * math.sin(math.radians(ang))
        d.line([x1, y1, x2, y2], fill=(*VIOLET, 190), width=int(arm * 0.8))
        d.ellipse([x2 - arm, y2 - arm, x2 + arm, y2 + arm], fill=(*VIOLET, 220))

    # ---- 六边形取景框（双色拼接，模拟渐变描边）----
    pts = hexagon(cx, cy, r_hex)
    for i in range(6):
        c = lerp(CYAN, VIOLET, i / 5)
        d.line([pts[i], pts[(i + 1) % 6]], fill=(*c, 255),
               width=int(S * 0.022), joint="curve")
    # 六边形四角小圆点（取景框角标感）
    for i in range(0, 6, 2):
        px_, py_ = pts[i]
        r_dot = S * 0.014
        d.ellipse([px_ - r_dot, py_ - r_dot, px_ + r_dot, py_ + r_dot],
                  fill=(*CORE, 255))

    # ---- 虹膜：两圈同心圆 ----
    r1, r2 = S * 0.235, S * 0.185
    for i in range(48):                       # 用多段弧模拟渐变环
        a1 = i * (360 / 48)
        a2 = a1 + 8
        c = lerp(CYAN, VIOLET, i / 47)
        d.arc([cx - r1, cy - r1, cx + r1, cy + r1], a1, a2, fill=(*c, 235), width=int(S * 0.014))
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
              outline=(*CORE, 160), width=int(S * 0.008))

    # ---- 轨道刻度环（虚线）----
    r_orbit = S * 0.295
    for i in range(24):
        a = i * 15
        ar = math.radians(a)
        x1 = cx + r_orbit * math.cos(ar)
        y1 = cy + r_orbit * math.sin(ar)
        x2 = cx + (r_orbit + S * 0.012) * math.cos(ar)
        y2 = cy + (r_orbit + S * 0.012) * math.sin(ar)
        alpha = 200 if i % 4 == 0 else 90
        d.line([x1, y1, x2, y2], fill=(*CYAN, alpha), width=int(S * 0.007))

    # ---- 瞳孔 ----
    r_core = S * 0.105
    d.ellipse([cx - r_core, cy - r_core, cx + r_core, cy + r_core], fill=(*CORE, 255))
    r_in = S * 0.058
    d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=(*WHITE, 255))
    # 瞳孔高光
    hr = S * 0.018
    d.ellipse([cx - r_in * 0.45 - hr, cy - r_in * 0.5 - hr,
               cx - r_in * 0.45 + hr, cy - r_in * 0.5 + hr], fill=(255, 255, 255, 240))

    # ---- 取景括号（四角）----
    m, ln, w = S * 0.075, S * 0.11, int(S * 0.018)
    for (ox, oy, sx, sy) in ((m, m, 1, 1), (S - m, m, -1, 1),
                             (m, S - m, 1, -1), (S - m, S - m, -1, -1)):
        d.line([ox, oy + sy * ln, ox, oy, ox + sx * ln, oy],
               fill=(*CYAN, 200), width=w)

    return Image.alpha_composite(img, layer)


def _png_bytes(img: Image.Image, size: int) -> bytes:
    import io
    buf = io.BytesIO()
    img.resize((size, size), Image.LANCZOS).save(buf, format="PNG")
    return buf.getvalue()


def write_icns(img: Image.Image, path: str) -> None:
    """手写 .icns 容器（icns = 8 字节头 + 若干「类型 + 长度 + PNG」条目）。

    不依赖 macOS 的 iconutil，任何平台都能生成；
    16x16~64x64 用 icp4/5/6，128 及以上用 ic07~ic10。
    """
    entries = [("icp4", 16), ("icp5", 32), ("icp6", 64),
               ("ic07", 128), ("ic08", 256), ("ic09", 512), ("ic10", 1024)]
    body = b""
    for typ, size in entries:
        data = _png_bytes(img, size)
        body += typ.encode("ascii") + (8 + len(data)).to_bytes(4, "big") + data
    blob = b"icns" + (8 + len(body)).to_bytes(4, "big") + body
    with open(path, "wb") as f:
        f.write(blob)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    base = make_base()
    base = Image.alpha_composite(base, make_glow())
    img = draw_motif(base)

    png_path = os.path.join(OUT_DIR, "app.png")
    img.resize((512, 512), Image.LANCZOS).save(png_path)

    ico_path = os.path.join(OUT_DIR, "app.ico")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    img.save(ico_path, format="ICO", sizes=sizes)

    icns_path = os.path.join(OUT_DIR, "app.icns")
    write_icns(img, icns_path)

    img.resize((1024, 1024), Image.LANCZOS).save(os.path.join(OUT_DIR, "app_1024.png"))

    print("图标已生成：")
    for f in ("app.ico", "app.icns", "app.png", "app_1024.png"):
        p = os.path.join(OUT_DIR, f)
        print(f"  {p}  ({os.path.getsize(p)} bytes)")


if __name__ == "__main__":
    main()
