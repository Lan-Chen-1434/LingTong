"""
应用引导
==========
桌面应用启动前的全部准备工作：DPI 感知、QApplication、字体、主题、图标。
把它从 main.py 拆出来，入口就能只做"解析参数 → 分发任务"。
"""
from __future__ import annotations

import sys
from typing import Optional


def enable_dpi_awareness() -> None:
    """让进程感知 DPI 缩放——否则 125%/150% 缩放下找图与坐标会错位。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE_V2
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def create_app(argv: list):
    """创建并配置好 QApplication。"""
    import modules  # noqa: F401  导入即注册全部功能积木

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QStyleFactory

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    from ui import theme
    app = QApplication(argv)
    app.setApplicationName("LingTong")
    app.setOrganizationName("LingTong")
    app.setFont(theme.font(9))
    # Fusion 风格 + 深色调色板：保证深色主题在所有控件上表现一致
    # （原生 windows 风格会忽略部分 QSS，且交替行底色来自调色板）
    app.setStyle(QStyleFactory.create("Fusion"))
    from PySide6.QtGui import QColor, QPalette
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(theme.BG))
    pal.setColor(QPalette.WindowText, QColor(theme.TEXT))
    pal.setColor(QPalette.Base, QColor(theme.PANEL_SOFT))
    pal.setColor(QPalette.AlternateBase, QColor(theme.PANEL))
    pal.setColor(QPalette.Text, QColor(theme.TEXT))
    pal.setColor(QPalette.ToolTipBase, QColor("#10161F"))
    pal.setColor(QPalette.ToolTipText, QColor(theme.TEXT))
    pal.setColor(QPalette.Button, QColor(theme.PANEL))
    pal.setColor(QPalette.ButtonText, QColor(theme.TEXT))
    pal.setColor(QPalette.Highlight, QColor(theme.PRIMARY))
    pal.setColor(QPalette.HighlightedText, QColor("#04222B"))
    app.setPalette(pal)

    from ui import icons
    from ui.theme import QSS
    app.setStyleSheet(QSS)
    app.setWindowIcon(icons.app_icon())
    return app


def enable_dark_titlebar(win) -> None:
    """原生标题栏贴合主题：沉浸式深色 + Win11 标题栏底色/文字色设为令牌色。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ui import theme

        hwnd = int(win.winId())
        dwmapi = ctypes.windll.dwmapi

        def _set(attr: int, value: int) -> None:
            buf = ctypes.c_int(value)
            dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(buf),
                                         ctypes.sizeof(buf))

        _set(20, 1)                                  # DWMWA_USE_IMMERSIVE_DARK_MODE
        # Win11 专属：标题栏底色/文字色（COLORREF = 0x00BBGGRR），老系统静默失败
        bg = theme.BG.lstrip("#")
        _set(35, int(bg[4:6] + bg[2:4] + bg[0:2], 16))   # DWMWA_CAPTION_COLOR
        fg = theme.TEXT.lstrip("#")
        _set(36, int(fg[4:6] + fg[2:4] + fg[0:2], 16))   # DWMWA_TEXT_COLOR
    except Exception:
        pass


def run_gui(argv: list, open_flow: Optional[str] = None) -> int:
    enable_dpi_awareness()
    app = create_app(argv)

    from app import assoc
    assoc.register()                        # .arpa 文件图标 + 双击打开（失败不阻塞启动）

    from core.registry import REGISTRY
    from ui.main_window import MainWindow
    from ui.splash import SplashScreen

    state = {"win": None}

    def build_window() -> None:
        state["win"] = MainWindow()

    def done() -> None:
        win = state["win"]
        win.showMaximized()
        enable_dark_titlebar(win)
        win.start_fade_in()
        if open_flow:
            win.open_flow_path(open_flow)

    splash = SplashScreen()
    splash.show()
    splash.start_boot([
        ("初始化渲染环境", lambda: None),
        (f"加载 {len(REGISTRY.all())} 个功能模块", lambda: None),
        ("检测系统驱动", lambda: None),
        ("构建主界面", build_window),
        ("扫描示例流程", lambda: None),
    ], done)
    return app.exec()
