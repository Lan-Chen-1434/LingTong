"""
.arpa 流程文件关联
======================
在注册表 HKCU（当前用户，无需管理员）登记：

* ``.arpa`` 扩展名 → ProgID ``LingTong.Flow``
* ProgID 的 DefaultIcon → assets/icons/app.ico（资源管理器里显示的图标）
* ``shell\\open\\command`` → 用本程序打开该流程文件

已关联且内容未变时直接跳过；有变化才刷新资源管理器图标缓存。
非 Windows 平台或注册表写入失败时静默跳过，不影响启动。
"""
from __future__ import annotations

import os
import sys

from core import paths

ROOT = paths.ROOT
PROGID = "LingTong.Flow"
EXT = ".arpa"


def _pythonw() -> str:
    """双击打开时用 pythonw，避免控制台窗口闪一下。"""
    exe = sys.executable
    w = exe.replace("python.exe", "pythonw.exe")
    return w if os.path.isfile(w) else exe


def register() -> bool:
    """登记 .arpa 关联。返回 True 表示关联内容有更新（需要刷新图标缓存）。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False

    icon_path = os.path.join(ROOT, "assets", "icons", "app.ico")
    if getattr(sys, "frozen", False):
        # 打包版：直接用可执行文件打开
        main_py, open_cmd = None, f'"{sys.executable}" "%1"'
    else:
        # 源码版：用 pythonw 跑 main.py
        main_py = os.path.join(ROOT, "main.py")
        open_cmd = f'"{_pythonw()}" "{main_py}" "%1"'
    if not os.path.isfile(icon_path) or (main_py and not os.path.isfile(main_py)):
        return False
    icon_val = f"{icon_path},0"

    def _read(key_path: str, name=None) -> str:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                v, _ = winreg.QueryValueEx(k, name)
                return str(v)
        except OSError:
            return ""

    # 已按我们的设定关联过 → 不动
    if (_read(r"Software\Classes\.arpa") == PROGID
            and _read(rf"Software\Classes\{PROGID}\DefaultIcon") == icon_val
            and _read(rf"Software\Classes\{PROGID}\shell\open\command") == open_cmd):
        return False

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              r"Software\Classes\.arpa") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, PROGID)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              rf"Software\Classes\{PROGID}") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "灵瞳流程")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              rf"Software\Classes\{PROGID}\DefaultIcon") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, icon_val)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              rf"Software\Classes\{PROGID}\shell\open\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, open_cmd)
    except OSError:
        return False

    _notify_icon_cache()
    return True


def _notify_icon_cache() -> None:
    """通知资源管理器刷新图标缓存，新图标立即生效。"""
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST,
                                             None, None)
    except Exception:
        pass
