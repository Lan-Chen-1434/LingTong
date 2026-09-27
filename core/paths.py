"""
流程工作区路径管理
======================
每个流程独占一个文件夹（flows/<流程名>/），结构::

    flows/<流程名>/
    ├── <流程名>.arpa          流程文件
    ├── input/                 流程的输入资源
    │   ├── image/             模板图等图片
    │   ├── excel/
    │   └── txt/
    ├── python_scripts/        Python 脚本
    ├── vba_scripts/           VBA 脚本
    ├── log/                   每次运行的日志文件
    └── output/                流程的运行产出（按需创建：写入时才建子目录）

约定：
* 流程参数里写相对路径 = 相对本流程文件夹（如 input/image/a.png）；
* 绝对路径照旧使用；
* output/ 不在预建清单里：各产出模块写入前会自建目录，空的 output 不占地方；
* 每次保存流程时清理一次：input/image 里未被流程引用的图片、
  log 里超过一个月的日志（仅当流程上次整体运行成功且无跳过，见 ui/main_window）。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from typing import Optional


def _detect_root() -> str:
    """程序根目录（flows/examples/assets 所在的那一级）。

    源码模式 = 仓库根；打包模式（PyInstaller onedir）= 从可执行文件向上找
    第一个包含资产文件夹的目录。发布包结构::

        LingTong-vX/                ← 根
        ├── LingTong.exe            （Windows）
        ├── LingTong.app/           （macOS，可执行文件在 Contents/MacOS/ 下）
        └── flows/  examples/  assets/
    """
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.dirname(os.path.abspath(sys.executable))
    for _ in range(5):
        if (os.path.isdir(os.path.join(d, "examples"))
                or os.path.isdir(os.path.join(d, "assets"))):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.dirname(os.path.abspath(sys.executable))


ROOT = _detect_root()
FLOWS_DIR = os.path.join(ROOT, "flows")
EXAMPLES_DIR = os.path.join(ROOT, "examples")

# 流程文件夹下要预建的全部子目录
# （output/ 不在其列：运行产出模块写入时才按需创建，不留空目录树）
SUBDIRS = (
    os.path.join("input", "image"),
    os.path.join("input", "excel"),
    os.path.join("input", "txt"),
    "python_scripts",
    "vba_scripts",
    "log",
)

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff")
_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')

# 日志保留天数（"只保留最近一个月"）
LOG_KEEP_DAYS = 31


def sanitize_name(name: str) -> str:
    """文件夹名不允许的字符替换为下划线；空白折叠。"""
    s = _ILLEGAL.sub("_", str(name or "")).strip(" .")
    return s or "未命名流程"


def flow_dir(name: str) -> str:
    return os.path.join(FLOWS_DIR, sanitize_name(name))


def flow_file(name: str) -> str:
    """流程文件的标准位置：flows/<流程名>/<流程名>.arpa"""
    d = flow_dir(name)
    return os.path.join(d, f"{sanitize_name(name)}.arpa")


def ensure_flow_dirs(name: str) -> str:
    """创建流程文件夹及全部子目录，返回文件夹路径。"""
    return ensure_workspace(flow_dir(name))


def ensure_workspace(d: str) -> str:
    """在任意文件夹内补齐工作区子目录（input/output/... 结构），返回该文件夹。"""
    os.makedirs(d, exist_ok=True)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


# ---------------------------------------------------------------- 示例流程
def example_dir(name: str) -> str:
    return os.path.join(EXAMPLES_DIR, sanitize_name(name))


def example_file(name: str) -> str:
    """示例流程的标准位置：examples/<示例名>/<示例名>.arpa"""
    d = example_dir(name)
    return os.path.join(d, f"{sanitize_name(name)}.arpa")


def ensure_example_dirs(name: str) -> str:
    """创建示例流程文件夹及全部子目录（结构与 flows/<流程名>/ 一致），返回路径。"""
    d = example_dir(name)
    os.makedirs(d, exist_ok=True)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


def workspace_for(flow) -> str:
    """flow 对象 → 工作区文件夹（自动建目录）。flow 为 None 时退回程序根目录。"""
    if flow is None:
        return ROOT
    return ensure_flow_dirs(getattr(flow, "name", ""))


# ---------------------------------------------------------------- 路径解析
def resolve(base: str, path: str) -> str:
    """相对路径 → 流程文件夹内解析。

    绝对路径原样返回；相对路径优先按 base/path 找，找不到再尝试
    base/input/image/path（兼容只写了文件名的旧数据）。
    """
    if not path:
        return path
    if os.path.isabs(path):
        return path
    cand = os.path.join(base, path)
    if os.path.isfile(cand) or os.path.isdir(cand):
        return cand
    alt = os.path.join(base, "input", "image", path)
    if os.path.isfile(alt):
        return alt
    return cand


def rel_or_abs(base: str, path: str) -> str:
    """存储用：path 在 base 内 → 存相对路径（流程文件夹整体搬走也不失效）。

    统一用正斜杠，和参数默认值（output/image/...）风格一致。
    """
    ap, ab = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    if ap.startswith(ab + os.sep):
        return os.path.relpath(ap, ab).replace(os.sep, "/")
    return path


def ingest_image(base: str, src: str) -> str:
    """把用户选择的图片收进 base/input/image，返回可存入参数的相对路径。

    已在流程文件夹内的图片只登记相对路径；外部的复制进来（重名自动加序号）。
    """
    img_dir = os.path.join(base, "input", "image")
    os.makedirs(img_dir, exist_ok=True)
    ap = os.path.normcase(os.path.abspath(src))
    ab = os.path.normcase(os.path.abspath(base))
    if ap.startswith(ab + os.sep):
        return os.path.relpath(ap, base).replace(os.sep, "/")
    name = os.path.basename(src)
    stem, ext = os.path.splitext(name)
    dst = os.path.join(img_dir, name)
    i = 2
    while os.path.exists(dst):
        dst = os.path.join(img_dir, f"{stem}_{i}{ext}")
        i += 1
    shutil.copy2(src, dst)
    return os.path.relpath(dst, base).replace(os.sep, "/")


# ---------------------------------------------------------------- 保存时清理
def _walk_nodes(nodes):
    for n in nodes or []:
        yield n
        yield from _walk_nodes(getattr(n, "children", None))


def referenced_images(flow) -> set:
    """流程引用的全部图片：登记路径 + 文件名两种形式都收集。"""
    refs = set()
    for node in _walk_nodes(getattr(flow, "nodes", None)):
        params = getattr(node, "params", {}) or {}
        for key, val in params.items():
            if key not in ("image", "anchor"):
                continue
            items = val if isinstance(val, list) else [val]
            for it in items:
                if not isinstance(it, str) or not it.lower().endswith(_IMG_EXTS):
                    continue
                refs.add(it.replace("\\", "/"))
                refs.add(os.path.basename(it.replace("\\", "/")))
    return refs


def cleanup_unreferenced_images(work: str, flow) -> int:
    """删除 input/image 下未被流程引用的图片，返回删除数。"""
    img_dir = os.path.join(work, "input", "image")
    if not os.path.isdir(img_dir):
        return 0
    refs = referenced_images(flow)
    removed = 0
    for f in os.listdir(img_dir):
        fp = os.path.join(img_dir, f)
        if not os.path.isfile(fp) or not f.lower().endswith(_IMG_EXTS):
            continue
        rel = f"input/image/{f}"
        if f in refs or rel in refs:
            continue
        try:
            os.remove(fp)
            removed += 1
        except OSError:
            pass
    return removed


def cleanup_old_logs(work: str, keep_days: int = LOG_KEEP_DAYS) -> int:
    """删除 log/ 下超过保留期的日志文件，返回删除数。"""
    log_dir = os.path.join(work, "log")
    if not os.path.isdir(log_dir):
        return 0
    cutoff = time.time() - keep_days * 86400
    removed = 0
    for f in os.listdir(log_dir):
        fp = os.path.join(log_dir, f)
        if not os.path.isfile(fp):
            continue
        try:
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
                removed += 1
        except OSError:
            pass
    return removed
