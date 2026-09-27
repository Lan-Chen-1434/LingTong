"""
AutoRPA - 跨平台兼容层
========================
封装 Windows / macOS / Linux 的平台差异，上层代码无需关心具体系统。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional

SYSTEM = platform.system().lower()          # 'windows', 'darwin', 'linux'
IS_WIN = SYSTEM == "windows"
IS_MAC = SYSTEM == "darwin"
IS_LINUX = SYSTEM == "linux"


def open_path(path: str) -> None:
    """用系统默认方式打开文件或文件夹。"""
    path = os.path.normpath(path)
    if IS_WIN:
        os.startfile(path)                      # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.call(["open", path])         # noqa: S603,S607
    else:
        subprocess.call(["xdg-open", path])     # noqa: S603,S607


def reveal_in_finder(path: str) -> None:
    """在文件管理器中定位并高亮指定文件/文件夹（仅 macOS/Windows 有意义）。"""
    path = os.path.normpath(path)
    if IS_MAC:
        subprocess.call(["open", "-R", path])   # noqa: S603,S607
    elif IS_WIN:
        subprocess.call(["explorer", "/select,", path])  # noqa: S603,S607
    else:
        open_path(os.path.dirname(path) if os.path.isfile(path) else path)


def run_command(cmd: List[str], cwd: Optional[str] = None,
                timeout: Optional[float] = None,
                capture_output: bool = False,
                shell: bool = False,
                env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """跨平台运行外部命令，返回统一结果字典。

    Returns:
        {"returncode": int, "stdout": str, "stderr": str, "timeout": bool}
    """
    kwargs: Dict[str, Any] = {"cwd": cwd, "shell": shell, "env": env}
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["encoding"] = "utf-8"
        kwargs["errors"] = "replace"
    if timeout and timeout > 0:
        kwargs["timeout"] = timeout

    try:
        result = subprocess.run(cmd, **kwargs)      # noqa: S603
        return {
            "returncode": result.returncode,
            "stdout": result.stdout if capture_output else "",
            "stderr": result.stderr if capture_output else "",
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -1,
            "stdout": exc.stdout if capture_output and exc.stdout else "",
            "stderr": exc.stderr if capture_output and exc.stderr else "",
            "timeout": True,
        }
    except FileNotFoundError as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"找不到命令：{exc}",
            "timeout": False,
        }
    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "timeout": False,
        }


def normalize_path(path: str) -> str:
    """统一路径格式：展开用户目录 ~，转成绝对路径，规范化分隔符。"""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    return os.path.normpath(path)


def list_window_titles() -> List[str]:
    """跨平台获取窗口标题列表。"""
    if IS_WIN:
        try:
            import pygetwindow as gw
            return [t for t in gw.getAllTitles() if t and t.strip()]
        except Exception:
            pass
        # fallback: Win32 EnumWindows
        try:
            import ctypes
            from ctypes import wintypes

            titles: List[str] = []

            def _enum_cb(hwnd, _):
                if ctypes.windll.user32.IsWindowVisible(hwnd):      # type: ignore[attr-defined]
                    buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)  # type: ignore[attr-defined]
                    if buf.value:
                        titles.append(buf.value)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(_enum_cb), 0)  # type: ignore[attr-defined]
            return titles
        except Exception:
            pass
    elif IS_MAC:
        try:
            result = run_command(
                ["osascript", "-e", 'tell application "System Events" to get name of every window of (get processes whose background only is false)'],
                capture_output=True)
            if result["returncode"] == 0:
                text = result["stdout"].strip()
                if text:
                    # AppleScript 返回逗号分隔的列表字符串
                    return [t.strip().strip('"') for t in text.split(",") if t.strip()]
        except Exception:
            pass
    return []


def activate_window(title_keyword: str, exact: bool = False, wait: float = 0.4) -> bool:
    """跨平台激活窗口。"""
    if IS_WIN:
        try:
            import pygetwindow as gw
            wins = gw.getWindowsWithTitle(title_keyword)
            if not wins:
                return False
            w = wins[0]
            if exact:
                for cand in wins:
                    if cand.title == title_keyword:
                        w = cand
                        break
            if w.isMinimized:
                w.restore()
            w.activate()
            import time
            time.sleep(wait)
            return True
        except Exception:
            pass
        # fallback Win32
        try:
            import ctypes
            from ctypes import wintypes

            target = None

            def _enum_cb(hwnd, _):
                nonlocal target
                if ctypes.windll.user32.IsWindowVisible(hwnd):      # type: ignore[attr-defined]
                    buf = ctypes.create_unicode_buffer(256)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)  # type: ignore[attr-defined]
                    t = buf.value
                    if exact and t == title_keyword:
                        target = hwnd
                        return False
                    if not exact and title_keyword in t:
                        target = hwnd
                        return False
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(_enum_cb), 0)  # type: ignore[attr-defined]
            if target:
                ctypes.windll.user32.SetForegroundWindow(target)    # type: ignore[attr-defined]
                import time
                time.sleep(wait)
                return True
        except Exception:
            pass
    elif IS_MAC:
        try:
            script = f'''
tell application "System Events"
    set procList to every process whose name contains "{title_keyword.replace('"', '\\"')}"
    if (count of procList) > 0 then
        set frontmost of first item of procList to true
    end if
end tell
'''
            result = run_command(["osascript", "-e", script], capture_output=True)
            if result["returncode"] == 0:
                import time
                time.sleep(wait)
                return True
        except Exception:
            pass
    return False


def active_window_title() -> str:
    """跨平台获取当前活动窗口标题。"""
    if IS_WIN:
        try:
            import pygetwindow as gw
            return gw.getActiveWindowTitle() or ""
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()       # type: ignore[attr-defined]
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)     # type: ignore[attr-defined]
            return buf.value or ""
        except Exception:
            pass
    elif IS_MAC:
        try:
            result = run_command(
                ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True)
            if result["returncode"] == 0:
                return result["stdout"].strip().strip('"')
        except Exception:
            pass
    return ""
