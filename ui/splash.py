"""
「灵瞳」启动屏
================
纯黑贾维斯风 Splash：0/1 数字雨、旋转科技眼、粒子轨道、
呼吸辉光、扫描线、底部进度条 + 真实分阶段初始化（不是假进度）。

用法::

    splash = SplashScreen()
    splash.show()
    splash.start_boot([
        ("初始化渲染环境", fn1),
        ("加载功能模块", fn2),
        ("构建主界面", fn3),
    ], on_done=fn_finish)
"""
from __future__ import annotations

import math
import os
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QApplication, QWidget

from core import paths as _paths

from . import icons, theme

W, H = 760, 440

_SFX_DIR = os.path.join(_paths.ROOT, "assets", "sfx")


def _play_loop(name: str) -> None:
    """循环播放背景音效（数字雨滴答声），关闭时需调用 _stop_sfx。

    非 Windows / 无声卡 / 文件缺失时静默跳过。
    """
    try:
        if os.name != "nt":
            return
        import winsound
        path = os.path.join(_SFX_DIR, name)
        if os.path.exists(path):
            winsound.PlaySound(path, winsound.SND_FILENAME
                               | winsound.SND_ASYNC | winsound.SND_LOOP)
    except Exception:
        pass


def _stop_sfx() -> None:
    try:
        if os.name != "nt":
            return
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


class SplashScreen(QWidget):
    """无边框透明底启动屏，60fps 自绘动画。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(W, H)
        self._center_on_screen()

        self._phase = 0.0                       # 动画相位 0~1
        self._elapsed = 0
        self._progress = 0.0                    # 0~1
        self._progress_target = 0.0
        self._step_text = "正在启动…"
        self._steps: List[Tuple[str, Callable]] = []
        self._step_idx = 0
        self._on_done: Optional[Callable] = None
        self._closing = False
        self._opacity = 0.0

        self._particles = self._make_particles()
        self._rain = self._make_rain()

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(16)                    # ~60fps

        self._fade_in = QTimer(self)
        self._fade_in.setSingleShot(False)
        self._fade_in.timeout.connect(self._fade_in_step)
        self._fade_in.start(16)

        QTimer.singleShot(350, lambda: _play_loop("rain.wav"))

    # ================================================================ 定位
    def _center_on_screen(self) -> None:
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - W // 2, scr.center().y() - H // 2)

    # ================================================================ 分阶段启动
    def start_boot(self, steps: List[Tuple[str, Callable]], on_done: Callable) -> None:
        self._steps = list(steps)
        self._on_done = on_done
        self._step_idx = 0
        self._progress_target = 0.06
        QTimer.singleShot(450, self._run_next_step)

    def _run_next_step(self) -> None:
        if self._step_idx < len(self._steps):
            text, fn = self._steps[self._step_idx]
            self._step_text = text
            try:
                fn()
            except Exception:                   # 初始化单步失败不阻塞启动
                pass
            self._step_idx += 1
            self._progress_target = self._step_idx / len(self._steps)
            QTimer.singleShot(430, self._run_next_step)
        else:
            self._step_text = "启动完成"
            self._progress_target = 1.0
            QTimer.singleShot(520, self._finish)

    def _finish(self) -> None:
        if self._on_done:
            self._on_done()
        self.fade_out_close()

    def fade_out_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        _stop_sfx()                              # 兜底：任何路径关闭都停声
        self._fade_out = QTimer(self)
        self._fade_out.timeout.connect(self._fade_out_step)
        self._fade_out.start(16)

    # ================================================================ 动画驱动
    def _tick(self) -> None:
        self._elapsed += 16
        self._phase = (self._phase + 0.006) % 1.0
        # 进度条平滑趋近目标（缓动）
        self._progress += (self._progress_target - self._progress) * 0.08
        self.update()

    def _fade_in_step(self) -> None:
        self._opacity = min(1.0, self._opacity + 0.055)
        self.setWindowOpacity(self._opacity)
        if self._opacity >= 1.0:
            self._fade_in.stop()

    def _fade_out_step(self) -> None:
        self._opacity = max(0.0, self._opacity - 0.06)
        self.setWindowOpacity(self._opacity)
        if self._opacity <= 0.0:
            self._fade_out.stop()
            self._anim.stop()
            self.close()

    @staticmethod
    def _make_particles() -> List[dict]:
        import random
        rng = random.Random(2026)
        pts = []
        for _ in range(22):
            pts.append({
                "r": rng.uniform(0.30, 0.46),      # 半径（相对标志尺寸）
                "a": rng.uniform(0, 2 * math.pi),  # 初始角
                "v": rng.uniform(0.15, 0.45),      # 角速度
                "s": rng.uniform(0.9, 1.9),        # 大小
                "c": rng.choice(["#00E5FF", "#22D3EE", "#5EEAD4"]),
            })
        return pts

    @staticmethod
    def _make_rain() -> List[dict]:
        """0/1 数字雨：每列一串预生成的 01 字符，按各自速度下落。"""
        import random
        rng = random.Random(97)
        cols = []
        x = 26.0
        while x < W - 26:
            cols.append({
                "x": x,
                "speed": rng.uniform(0.018, 0.075),  # 行/帧
                "offset": rng.uniform(0, 60),
                "trail": rng.randint(11, 20),
                "s": "".join(rng.choice("01") for _ in range(64)),
                "bright": rng.uniform(0.45, 1.0),
            })
            x += rng.uniform(10, 15)
        return cols

    # ================================================================ 绘制
    def paintEvent(self, e) -> None:                      # noqa: N802
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            self._draw(p)
        finally:
            p.end()

    def _draw(self, p: QPainter) -> None:
        # ---- 底板（圆角 + 纯黑渐变 + 边框 + 投影）----
        body = QRectF(14, 14, W - 28, H - 28)
        shadow = QRectF(16, 20, W - 28, H - 28)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 170)))
        p.drawRoundedRect(shadow, 22, 22)

        g = QLinearGradient(body.topLeft(), body.bottomRight())
        g.setColorAt(0.0, QColor("#05070B"))
        g.setColorAt(0.55, QColor("#090C12"))
        g.setColorAt(1.0, QColor("#030508"))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(body, 20, 20)
        p.setPen(QPen(QColor("#16414F"), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), 20, 20)

        # ---- 网格 ----
        p.setPen(QPen(QColor(0, 229, 255, 10), 1))
        gx = 36
        for x in range(int(body.left()) + gx, int(body.right()), gx):
            p.drawLine(int(x), int(body.top() + 6), int(x), int(body.bottom() - 6))
        for y in range(int(body.top()) + gx, int(body.bottom()), gx):
            p.drawLine(int(body.left() + 6), int(y), int(body.right() - 6), int(y))

        # ---- 0/1 数字雨（黑客矩阵感，仅在底板内）----
        p.save()
        p.setClipRect(body)
        f_bin = QFont("Consolas", 10)
        p.setFont(f_bin)
        cell_h = 13
        rows = int(body.height()) // cell_h + 1
        for col in self._rain:
            head = (self._elapsed * col["speed"] + col["offset"]) % (rows + col["trail"])
            hi = int(head)
            for i in range(col["trail"]):
                row = hi - i
                if row < 0 or row >= rows:
                    continue
                ch = col["s"][(row * 3 + i + int(col["offset"])) % len(col["s"])]
                if i == 0:
                    c = QColor(170, 248, 255, int(215 * col["bright"]))
                else:
                    c = QColor(0, 229, 255, int(95 * (1 - i / col["trail"]) ** 1.5 * col["bright"]))
                p.setPen(c)
                p.drawText(QPointF(col["x"], body.top() + 12 + row * cell_h), ch)
        p.restore()

        # ---- 扫描线 ----
        scan_y = body.top() + ((self._elapsed * 0.06) % (body.height() + 60)) - 30
        sg = QLinearGradient(QPointF(0, scan_y - 16), QPointF(0, scan_y + 16))
        sg.setColorAt(0.0, QColor(0, 229, 255, 0))
        sg.setColorAt(0.5, QColor(0, 229, 255, 26))
        sg.setColorAt(1.0, QColor(0, 229, 255, 0))
        p.fillRect(QRectF(body.left(), scan_y - 16, body.width(), 32), QBrush(sg))

        # ---- 四角取景括号 ----
        m, ln = body.left() + 16, 26
        p.setPen(QPen(QColor("#22D3EE"), 2.2, Qt.SolidLine, Qt.RoundCap))
        for (ox, oy, sx, sy) in ((body.left() + 16, body.top() + 16, 1, 1),
                                 (body.right() - 16, body.top() + 16, -1, 1),
                                 (body.left() + 16, body.bottom() - 16, 1, -1),
                                 (body.right() - 16, body.bottom() - 16, -1, -1)):
            path = QPainterPath(QPointF(ox + sx * ln, oy))
            path.lineTo(QPointF(ox, oy))
            path.lineTo(QPointF(ox, oy + sy * ln))
            p.drawPath(path)

        # ---- 品牌标志（旋转动画，纯黑底不需要自带底色块）----
        logo_size = 148
        logo_r = QRectF(W / 2 - logo_size / 2, 66, logo_size, logo_size)
        icons.draw_eye_mark(p, logo_r, self._phase, False)

        # ---- 粒子轨道 ----
        ccx, ccy = W / 2, 66 + logo_size / 2
        for pt in self._particles:
            ang = pt["a"] + self._elapsed * 0.001 * pt["v"]
            rad = pt["r"] * logo_size
            x = ccx + rad * math.cos(ang)
            y = ccy + rad * math.sin(ang)
            c = QColor(pt["c"])
            tw = 0.5 + 0.5 * math.sin(self._elapsed * 0.004 + pt["a"])
            c.setAlpha(int(60 + 130 * tw))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            s = pt["s"] * 2.1
            p.drawEllipse(QRectF(x - s / 2, y - s / 2, s, s))

        # ---- 名称与标语 ----
        f_name = theme.font(30)
        f_name.setBold(True)
        p.setFont(f_name)
        name_c = QColor("#EAF2FF")
        p.setPen(QPen(name_c))
        p.drawText(QRectF(0, 226, W, 46), Qt.AlignCenter, "灵 瞳")

        f_en = theme.font(9)
        f_en.setLetterSpacing(QFont.PercentageSpacing, 240)
        p.setFont(f_en)
        p.setPen(QPen(QColor("#4E8FA8")))
        p.drawText(QRectF(0, 272, W, 20), Qt.AlignCenter, "LINGTONG VISION")

        f_tag = theme.font(10)
        p.setFont(f_tag)
        p.setPen(QPen(QColor("#6E93A8")))
        p.drawText(QRectF(0, 296, W, 20), Qt.AlignCenter, "看得懂屏幕的自动化助手")

        # ---- 进度条 ----
        bar_w, bar_h = 460, 5
        bx, by = (W - bar_w) / 2, H - 86
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#0E1620")))
        p.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), bar_h / 2, bar_h / 2)

        fill_w = max(bar_h, bar_w * self._progress)
        pg = QLinearGradient(QPointF(bx, 0), QPointF(bx + fill_w, 0))
        pg.setColorAt(0.0, QColor("#0077B6"))
        pg.setColorAt(1.0, QColor("#00E5FF"))
        p.setBrush(QBrush(pg))
        p.drawRoundedRect(QRectF(bx, by, fill_w, bar_h), bar_h / 2, bar_h / 2)
        # 进度头光点
        head_x = bx + fill_w
        hc = QColor("#00E5FF")
        hc.setAlpha(170)
        p.setBrush(QBrush(hc))
        p.drawEllipse(QRectF(head_x - 7, by + bar_h / 2 - 7, 14, 14))
        hc.setAlpha(255)
        p.setBrush(QBrush(hc))
        p.drawEllipse(QRectF(head_x - 3, by + bar_h / 2 - 3, 6, 6))

        # ---- 步骤文本 + 百分比 ----
        f_step = theme.font(10)
        p.setFont(f_step)
        p.setPen(QPen(QColor("#7FD8E8")))
        p.drawText(QRectF(bx, by + 18, bar_w * 0.7, 20),
                   Qt.AlignLeft | Qt.AlignVCenter, "▸ " + self._step_text)
        p.setPen(QPen(QColor("#4E8FA8")))
        p.drawText(QRectF(bx + bar_w * 0.7, by + 18, bar_w * 0.3, 20),
                   Qt.AlignRight | Qt.AlignVCenter, f"{int(self._progress * 100)}%")

        # ---- 底部小字 ----
        f_ver = theme.font(8)
        p.setFont(f_ver)
        p.setPen(QPen(QColor(110, 155, 175, 130)))
        p.drawText(QRectF(0, H - 40, W, 16), Qt.AlignCenter,
                   "图像识别 · 键鼠模拟 · 全局热键 · 数据抓取")
