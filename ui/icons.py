"""
AutoRPA 图标绘制
=================
所有界面图标都用 QPainter 现场绘制矢量图形，不依赖任何图片资源，
天然适配高分屏、可随时换色、打包体积最小。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QPainter, QPainterPath,
                           QPen, QPixmap, QPolygonF)

from . import theme


def _c(color) -> QColor:
    return color if isinstance(color, QColor) else QColor(color)


def draw_glyph(p: QPainter, name: str, r: QRectF, color, weight: float = 1.8) -> None:
    """在矩形 r 内绘制名为 name 的矢量图标。"""
    col = _c(color)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(col, weight, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)

    s = min(r.width(), r.height())
    cx, cy = r.center().x(), r.center().y()
    u = s / 24.0                                  # 以 24×24 为设计基准
    L = lambda v: r.left() + v * u               # noqa: E731
    T = lambda v: r.top() + v * u                # noqa: E731
    Rc = QRectF(r.left(), r.top(), s, s)

    if name == "play":
        p.setBrush(QBrush(col))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(L(8), T(5)), QPointF(L(19), T(12)), QPointF(L(8), T(19))]))
    elif name == "stop":
        p.setBrush(QBrush(col))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(L(7), T(7), 10 * u, 10 * u), 2 * u, 2 * u)
    elif name == "pause":
        p.setBrush(QBrush(col))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(L(8), T(6), 3.4 * u, 12 * u), 1.4 * u, 1.4 * u)
        p.drawRoundedRect(QRectF(L(13), T(6), 3.4 * u, 12 * u), 1.4 * u, 1.4 * u)
    elif name == "step":
        p.setBrush(QBrush(col))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(L(6), T(7)), QPointF(L(15), T(12)), QPointF(L(6), T(17))]))
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(L(16.5), T(6), 2.6 * u, 12 * u), 1.2 * u, 1.2 * u)
    elif name == "new":
        p.drawRoundedRect(QRectF(L(5), T(3.5), 14 * u, 17 * u), 2 * u, 2 * u)
        p.drawLine(QPointF(L(12), T(9)), QPointF(L(12), T(15)))
        p.drawLine(QPointF(L(9), T(12)), QPointF(L(15), T(12)))
    elif name == "open":
        p.drawPolyline(QPolygonF([QPointF(L(3), T(19)), QPointF(L(3), T(6)),
                                  QPointF(L(9.5), T(6)), QPointF(L(11.5), T(9)),
                                  QPointF(L(21), T(9))]))
        p.drawPolyline(QPolygonF([QPointF(L(3), T(19)), QPointF(L(5.5), T(11.5)),
                                  QPointF(L(22), T(11.5)), QPointF(L(19.5), T(19)),
                                  QPointF(L(3), T(19))]))
    elif name == "save":
        p.drawRoundedRect(QRectF(L(4), T(4), 16 * u, 16 * u), 2 * u, 2 * u)
        p.drawRect(QRectF(L(8), T(4), 8 * u, 6 * u))
        p.drawRoundedRect(QRectF(L(7.5), T(13), 9 * u, 7 * u), 1.2 * u, 1.2 * u)
    elif name == "saveas":
        p.drawRoundedRect(QRectF(L(3), T(3), 14 * u, 14 * u), 2 * u, 2 * u)
        p.drawRect(QRectF(L(6.5), T(3), 7 * u, 5 * u))
        p.drawRoundedRect(QRectF(L(6), T(11.5), 8 * u, 5.5 * u), 1.2 * u, 1.2 * u)
        # 斜向铅笔 = 另存
        p.drawLine(QPointF(L(13.5), T(15.5)), QPointF(L(20), T(9)))
        p.drawLine(QPointF(L(15.5), T(17.5)), QPointF(L(22), T(11)))
        p.drawLine(QPointF(L(13.5), T(15.5)), QPointF(L(15.5), T(17.5)))
        p.drawLine(QPointF(L(20), T(9)), QPointF(L(22), T(11)))
    elif name == "folder":
        p.drawPolyline(QPolygonF([QPointF(L(3), T(19.5)), QPointF(L(3), T(5)),
                                  QPointF(L(10), T(5)), QPointF(L(12), T(8.5)),
                                  QPointF(L(21), T(8.5)), QPointF(L(21), T(19.5)),
                                  QPointF(L(3), T(19.5))]))
    elif name == "camera":
        p.drawRoundedRect(QRectF(L(3), T(7), 18 * u, 13 * u), 2 * u, 2 * u)
        p.drawPolyline(QPolygonF([QPointF(L(8.5), T(7)), QPointF(L(10), T(4)),
                                  QPointF(L(14), T(4)), QPointF(L(15.5), T(7))]))
        p.drawEllipse(QPointF(L(12), T(13.5)), 3.6 * u, 3.6 * u)
    elif name == "crosshair":
        p.drawEllipse(QPointF(cx, cy), 7.5 * u, 7.5 * u)
        p.drawEllipse(QPointF(cx, cy), 2.2 * u, 2.2 * u)
        for a, b in ((12, 1.5), (12, 22.5), (1.5, 12), (22.5, 12)):
            if a == 12:
                p.drawLine(QPointF(L(12), T(b if b < 12 else b - 0.0001)),
                           QPointF(L(12), T(b)))
            else:
                p.drawLine(QPointF(L(a), T(12)), QPointF(L(b), T(12)))
        p.drawLine(QPointF(L(12), T(2)), QPointF(L(12), T(5.4)))
        p.drawLine(QPointF(L(12), T(18.6)), QPointF(L(12), T(22)))
        p.drawLine(QPointF(L(2), T(12)), QPointF(L(5.4), T(12)))
        p.drawLine(QPointF(L(18.6), T(12)), QPointF(L(22), T(12)))
    elif name == "trash":
        p.drawLine(QPointF(L(4), T(6.5)), QPointF(L(20), T(6.5)))
        p.drawPolyline(QPolygonF([QPointF(L(7), T(6.5)), QPointF(L(8), T(20)),
                                  QPointF(L(16), T(20)), QPointF(L(17), T(6.5))]))
        p.drawPolyline(QPolygonF([QPointF(L(9.5), T(6.5)), QPointF(L(9.8), T(3.5)),
                                  QPointF(L(14.2), T(3.5)), QPointF(L(14.5), T(6.5))]))
    elif name == "copy":
        p.drawRoundedRect(QRectF(L(8), T(8), 12 * u, 12 * u), 2 * u, 2 * u)
        p.drawPolyline(QPolygonF([QPointF(L(16), T(5)), QPointF(L(4), T(5)),
                                  QPointF(L(4), T(17))]))
    elif name == "up":
        p.drawPolyline(QPolygonF([QPointF(L(12), T(19)), QPointF(L(12), T(5))]))
        p.drawPolyline(QPolygonF([QPointF(L(5.5), T(11.5)), QPointF(L(12), T(5)),
                                  QPointF(L(18.5), T(11.5))]))
    elif name == "down":
        p.drawPolyline(QPolygonF([QPointF(L(12), T(5)), QPointF(L(12), T(19))]))
        p.drawPolyline(QPolygonF([QPointF(L(5.5), T(12.5)), QPointF(L(12), T(19)),
                                  QPointF(L(18.5), T(12.5))]))
    elif name == "chevron_down":
        p.drawPolyline(QPolygonF([QPointF(L(6), T(9.5)), QPointF(L(12), T(15.5)),
                                  QPointF(L(18), T(9.5))]))
    elif name == "chevron_right":
        p.drawPolyline(QPolygonF([QPointF(L(9.5), T(6)), QPointF(L(15.5), T(12)),
                                  QPointF(L(9.5), T(18))]))
    elif name == "search":
        p.drawEllipse(QPointF(L(10.5), T(10.5)), 6.2 * u, 6.2 * u)
        p.drawLine(QPointF(L(15.2), T(15.2)), QPointF(L(20.5), T(20.5)))
    elif name == "wand":
        p.drawLine(QPointF(L(5), T(19)), QPointF(L(15), T(9)))
        p.drawLine(QPointF(L(13), T(7)), QPointF(L(17), T(11)))
        for dx, dy in ((-1.5, 0), (18.5, 4), (4, -1.5)):
            pass
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(L(18), T(3)), QPointF(L(19.4), T(5.6)),
                                 QPointF(L(22), T(7)), QPointF(L(19.4), T(8.4)),
                                 QPointF(L(18), T(11)), QPointF(L(16.6), T(8.4)),
                                 QPointF(L(14), T(7)), QPointF(L(16.6), T(5.6))]))
    elif name == "clock":
        p.drawEllipse(QPointF(cx, cy), 8.2 * u, 8.2 * u)
        p.drawPolyline(QPolygonF([QPointF(L(12), T(7.2)), QPointF(L(12), T(12)),
                                  QPointF(L(15.6), T(14))]))
    elif name == "branch":
        p.drawEllipse(QPointF(L(6.5), T(6)), 2.2 * u, 2.2 * u)
        p.drawEllipse(QPointF(L(6.5), T(18)), 2.2 * u, 2.2 * u)
        p.drawEllipse(QPointF(L(17.5), T(12)), 2.2 * u, 2.2 * u)
        p.drawPolyline(QPolygonF([QPointF(L(8.7), T(6)), QPointF(L(13), T(6)),
                                  QPointF(L(15.3), T(9.8))]))
        p.drawPolyline(QPolygonF([QPointF(L(8.7), T(18)), QPointF(L(13), T(18)),
                                  QPointF(L(15.3), T(14.2))]))
    elif name == "repeat":
        p.drawPolyline(QPolygonF([QPointF(L(4), T(9)), QPointF(L(4), T(7)),
                                  QPointF(L(6), T(5)), QPointF(L(18), T(5)),
                                  QPointF(L(20), T(7)), QPointF(L(20), T(11))]))
        p.drawPolyline(QPolygonF([QPointF(L(20), T(15)), QPointF(L(20), T(17)),
                                  QPointF(L(18), T(19)), QPointF(L(6), T(19)),
                                  QPointF(L(4), T(17)), QPointF(L(4), T(13))]))
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(L(2), T(11)), QPointF(L(6.6), T(11)), QPointF(L(4.3), T(14.4))]))
        p.drawPolygon(QPolygonF([QPointF(L(22), T(13)), QPointF(L(17.4), T(13)), QPointF(L(19.7), T(9.6))]))
    elif name == "shield":
        p.drawPolyline(QPolygonF([QPointF(L(12), T(3)), QPointF(L(20), T(6.5)),
                                  QPointF(L(20), T(12)), QPointF(L(12), T(21)),
                                  QPointF(L(4), T(12)), QPointF(L(4), T(6.5)),
                                  QPointF(L(12), T(3))]))
        p.drawPolyline(QPolygonF([QPointF(L(8.5), T(12)), QPointF(L(11), T(14.6)),
                                  QPointF(L(15.6), T(9.4))]))
    elif name == "keyboard":
        p.drawRoundedRect(QRectF(L(2.5), T(6), 19 * u, 12 * u), 2 * u, 2 * u)
        p.setPen(QPen(col, max(1.2, weight * 0.8), Qt.SolidLine, Qt.RoundCap))
        for i in range(4):
            p.drawLine(QPointF(L(5.5 + i * 3.6), T(10)), QPointF(L(6.6 + i * 3.6), T(10)))
        for i in range(3):
            p.drawLine(QPointF(L(7.3 + i * 3.6), T(14)), QPointF(L(8.4 + i * 3.6), T(14)))
        p.drawLine(QPointF(L(15.5), T(14)), QPointF(L(18.5), T(14)))
    elif name == "mouse":
        p.drawRoundedRect(QRectF(L(7), T(3), 10 * u, 18 * u), 5 * u, 5 * u)
        p.setPen(QPen(col, max(1.2, weight * 0.85), Qt.SolidLine))
        p.drawLine(QPointF(L(12), T(4.5)), QPointF(L(12), T(9.5)))
    elif name == "table":
        p.drawRoundedRect(QRectF(L(3.5), T(5), 17 * u, 14 * u), 1.6 * u, 1.6 * u)
        p.setPen(QPen(col, max(1.1, weight * 0.8)))
        p.drawLine(QPointF(L(3.5), T(9.6)), QPointF(L(20.5), T(9.6)))
        p.drawLine(QPointF(L(9.5), T(9.6)), QPointF(L(9.5), T(19)))
        p.drawLine(QPointF(L(15), T(9.6)), QPointF(L(15), T(19)))
    elif name == "window":
        p.drawRoundedRect(QRectF(L(3), T(4.5), 18 * u, 15 * u), 2 * u, 2 * u)
        p.drawLine(QPointF(L(3), T(9)), QPointF(L(21), T(9)))
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(L(6.4), T(6.8)), 0.9 * u, 0.9 * u)
        p.drawEllipse(QPointF(L(9.4), T(6.8)), 0.9 * u, 0.9 * u)
    elif name == "cube":
        p.drawPolyline(QPolygonF([QPointF(L(12), T(3)), QPointF(L(20), T(7.5)),
                                  QPointF(L(20), T(16.5)), QPointF(L(12), T(21)),
                                  QPointF(L(4), T(16.5)), QPointF(L(4), T(7.5)),
                                  QPointF(L(12), T(3))]))
        p.drawPolyline(QPolygonF([QPointF(L(4), T(7.5)), QPointF(L(12), T(12)),
                                  QPointF(L(20), T(7.5))]))
        p.drawLine(QPointF(L(12), T(12)), QPointF(L(12), T(21)))
    elif name == "check":
        p.drawPolyline(QPolygonF([QPointF(L(5), T(12.5)), QPointF(L(10), T(17.5)),
                                  QPointF(L(19), T(6.5))]))
    elif name == "close":
        p.drawLine(QPointF(L(6.5), T(6.5)), QPointF(L(17.5), T(17.5)))
        p.drawLine(QPointF(L(17.5), T(6.5)), QPointF(L(6.5), T(17.5)))
    elif name == "info":
        p.drawEllipse(QPointF(cx, cy), 8.4 * u, 8.4 * u)
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(L(12), T(8.2)), 1.15 * u, 1.15 * u)
        p.setPen(QPen(col, weight, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(L(12), T(11)), QPointF(L(12), T(16.6)))
    elif name == "warning":
        p.drawPolyline(QPolygonF([QPointF(L(12), T(3.4)), QPointF(L(21.4), T(19.6)),
                                  QPointF(L(2.6), T(19.6)), QPointF(L(12), T(3.4))]))
        p.drawLine(QPointF(L(12), T(9.4)), QPointF(L(12), T(14)))
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(L(12), T(16.7)), 1.05 * u, 1.05 * u)
    elif name == "lightning":
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(L(13.6), T(2.5)), QPointF(L(5.5), T(13.4)),
                                 QPointF(L(11), T(13.4)), QPointF(L(10.4), T(21.5)),
                                 QPointF(L(18.5), T(10.6)), QPointF(L(13), T(10.6))]))
    elif name == "list":
        p.setPen(QPen(col, weight, Qt.SolidLine, Qt.RoundCap))
        for i in range(3):
            y = 6.5 + i * 5.5
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(L(5), T(y)), 1.15 * u, 1.15 * u)
            p.drawLine(QPointF(L(9), T(y)), QPointF(L(19.5), T(y)))
    elif name == "settings":
        p.drawEllipse(QPointF(cx, cy), 3.2 * u, 3.2 * u)
        for i in range(8):
            import math
            a = i * math.pi / 4
            x1, y1 = cx + math.cos(a) * 5.6 * u, cy + math.sin(a) * 5.6 * u
            x2, y2 = cx + math.cos(a) * 9.2 * u, cy + math.sin(a) * 9.2 * u
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    else:
        p.drawEllipse(QRectF(L(6), T(6), 12 * u, 12 * u))

    p.restore()


def glyph_pixmap(name: str, color, size: int = 18, weight: float = 1.8) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_glyph(p, name, QRectF(0, 0, size, size), color, weight)
    p.end()
    return pm


def glyph_icon(name: str, color, size: int = 18, weight: float = 1.8) -> QIcon:
    return QIcon(glyph_pixmap(name, color, size, weight))


def app_icon_path() -> str:
    from core import paths
    name = "app.ico" if os.name == "nt" else "app.icns"
    return os.path.join(paths.ROOT, "assets", "icons", name)


def app_icon() -> QIcon:
    path = app_icon_path()
    if os.path.isfile(path):
        return QIcon(path)
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_eye_mark(p, QRectF(0, 0, 64, 64), 0.0, True)
    p.end()
    return QIcon(pm)


def draw_eye_mark(p: QPainter, r: QRectF, phase: float = 0.0,
                  with_bg: bool = True) -> None:
    """绘制「灵瞳」品牌标志：六边形取景框 + 渐变虹膜 + 发光瞳孔 + 电路走线。

    phase 为 0~1 的动画相位（旋转轨道 / 呼吸辉光），静态绘制传 0。
    """
    import math

    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)

    cx, cy = r.center().x(), r.center().y()
    u = min(r.width(), r.height())

    CYAN = QColor("#22D3EE")
    VIOLET = QColor("#8B5CF6")
    CORE = QColor("#5EEAD4")
    WHITE = QColor("#F5FAFF")

    if with_bg:
        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, QColor("#18244C"))
        g.setColorAt(1.0, QColor("#070B14"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, u * 0.235, u * 0.235)

    # ---- 呼吸辉光 ----
    glow = 0.55 + 0.45 * math.sin(phase * 2 * math.pi)
    halo = QColor(CYAN)
    halo.setAlpha(int(60 + 50 * glow))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(halo))
    p.drawEllipse(QRectF(cx - u * 0.17, cy - u * 0.17, u * 0.34, u * 0.34))

    def poly_points(n, radius, rot_deg):
        pts = []
        for i in range(n):
            a = math.radians(rot_deg + i * 360 / n)
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        return pts

    # ---- 六边形（青→紫分段描边）----
    r_hex = u * 0.335
    hex_pts = poly_points(6, r_hex, -90)
    for i in range(6):
        c = QColor()
        t = i / 5
        c.setRgbF(CYAN.redF() + (VIOLET.redF() - CYAN.redF()) * t,
                  CYAN.greenF() + (VIOLET.greenF() - CYAN.greenF()) * t,
                  CYAN.blueF() + (VIOLET.blueF() - CYAN.blueF()) * t)
        p.setPen(QPen(c, u * 0.022, Qt.SolidLine, Qt.RoundCap))
        x1, y1 = hex_pts[i]
        x2, y2 = hex_pts[(i + 1) % 6]
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # ---- 电路走线（四向）----
    p.setPen(QPen(CYAN, u * 0.014, Qt.SolidLine, Qt.RoundCap))
    for ang in (0, 90, 180, 270):
        a = math.radians(ang)
        x1 = cx + (r_hex + u * 0.008) * math.cos(a)
        y1 = cy + (r_hex + u * 0.008) * math.sin(a)
        x2 = cx + (r_hex + u * 0.062) * math.cos(a)
        y2 = cy + (r_hex + u * 0.062) * math.sin(a)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(CORE))
        p.drawEllipse(QRectF(x2 - u * 0.013, y2 - u * 0.013, u * 0.026, u * 0.026))
        p.setPen(QPen(CYAN, u * 0.014, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)

    # ---- 虹膜渐变环 ----
    r_iris = u * 0.235
    seg = 36
    for i in range(seg):
        c = QColor()
        t = i / (seg - 1)
        c.setRgbF(CYAN.redF() + (VIOLET.redF() - CYAN.redF()) * t,
                  CYAN.greenF() + (VIOLET.greenF() - CYAN.greenF()) * t,
                  CYAN.blueF() + (VIOLET.blueF() - CYAN.blueF()) * t)
        c.setAlpha(235)
        p.setPen(QPen(c, u * 0.011, Qt.SolidLine, Qt.FlatCap))
        a1 = (i / seg) * 2 * math.pi
        a2 = ((i + 0.75) / seg) * 2 * math.pi
        x1 = cx + r_iris * math.cos(a1)
        y1 = cy + r_iris * math.sin(a1)
        x2 = cx + r_iris * math.cos(a2)
        y2 = cy + r_iris * math.sin(a2)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # ---- 旋转轨道刻度 ----
    r_orb = u * 0.295
    base = phase * 2 * math.pi
    for i in range(24):
        a = base + i * (2 * math.pi / 24)
        major = (i % 4 == 0)
        c = QColor(CYAN)
        c.setAlpha(200 if major else 80)
        p.setPen(QPen(c, u * (0.010 if major else 0.006), Qt.SolidLine, Qt.FlatCap))
        x1 = cx + r_orb * math.cos(a)
        y1 = cy + r_orb * math.sin(a)
        x2 = cx + (r_orb + u * (0.014 if major else 0.008)) * math.cos(a)
        y2 = cy + (r_orb + u * (0.014 if major else 0.008)) * math.sin(a)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # ---- 瞳孔 ----
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(CORE))
    p.drawEllipse(QRectF(cx - u * 0.105, cy - u * 0.105, u * 0.21, u * 0.21))
    p.setBrush(QBrush(WHITE))
    p.drawEllipse(QRectF(cx - u * 0.058, cy - u * 0.058, u * 0.116, u * 0.116))
    hi = QColor(255, 255, 255, 235)
    p.setBrush(QBrush(hi))
    p.drawEllipse(QRectF(cx - u * 0.045, cy - u * 0.048, u * 0.024, u * 0.024))

    p.restore()


def logo_pixmap(size: int = 30) -> QPixmap:
    """品牌小标识（顶栏用）—— 深空底科技眼。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_eye_mark(p, QRectF(0, 0, size, size), 0.0, True)
    p.end()
    return pm


def badge_pixmap(text: str, color: str, soft: str, size: int = 30, radius: float = 9.0) -> QPixmap:
    """分类徽章：圆角底色 + 分类汉字，用作树/卡片上的模块图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(soft)))
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setPen(QPen(QColor(color)))
    f = QFont()
    f.setFamily(theme.UI_FONT)
    f.setPixelSize(int(size * 0.5))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, text)
    p.end()
    return pm


def icon_pixmap(glyph: str, color: str, soft: str, size: int = 30, radius: float = 9.0) -> QPixmap:
    """分类图标：圆角底色 + 矢量 glyph 图标，替代原来的单字 badge。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(soft)))
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    # glyph 绘制在中心，留 18% 边距
    margin = size * 0.18
    draw_glyph(p, glyph, QRectF(margin, margin, size - margin * 2, size - margin * 2),
               color, weight=1.6)
    p.end()
    return pm


class _GlyphCache:
    _cache: dict = {}

    @classmethod
    def badge(cls, text: str, color: str, soft: str, size: int = 30) -> QPixmap:
        key = (text, color, soft, size)
        if key not in cls._cache:
            cls._cache[key] = badge_pixmap(text, color, soft, size)
        return cls._cache[key]


class _IconCache:
    _cache: dict = {}

    @classmethod
    def icon(cls, glyph: str, color: str, soft: str, size: int = 30) -> QPixmap:
        key = (glyph, color, soft, size)
        if key not in cls._cache:
            cls._cache[key] = icon_pixmap(glyph, color, soft, size)
        return cls._cache[key]


BADGE_CACHE = _GlyphCache
ICON_CACHE = _IconCache
