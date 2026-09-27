"""
灵瞳 发布包组装脚本
======================
把 PyInstaller 的输出 + 资产文件夹（assets / examples / flows）组装成最终
发布文件夹并生成压缩包：

* Windows → ``LingTong-v{ver}-win64.zip``
  （zipfile 写入；非 ASCII 文件名自动带 UTF-8 标记，资源管理器解压不乱码）
* macOS   → ``LingTong-v{ver}-macos.tar.gz``
  （PAX 格式记录 UTF-8 文件名。macOS 自带解压工具对「Windows 上生成的、
   含中文文件名的 zip」常按本地编码错误解释，导致解压后文件丢失/乱码——
   因此 macOS 一律发 tar.gz，双击或用 ``tar -xzf`` 解压都不会出问题）

只打包 ``assets``（图标/音效，程序依赖）和 ``examples``（内置示例流程）。
``flows/``（用户流程工作区）和 ``tests/`` 不打进发布包：flows/ 在程序
启动时自动创建（见 ui/main_window.py），tests/ 与运行无关。

用法::

    python tools/make_release.py --version 1.2.4 [--dist dist] [--out release]

发布包结构::

    LingTong-v1.2.4-win64/
    ├── LingTong.exe  _internal/
    ├── assets/   examples/
    LingTong-v1.2.4-macos/
    ├── LingTong.app/
    └── assets/   examples/
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ASSET_DIRS = ("assets", "examples")
SKIP_DIR_NAMES = {"__pycache__", ".git", ".workbuddy", ".DS_Store"}
# 打包时不需要带上历史运行痕迹（结构会在保存/运行时按需重建）
DROP_DIR_NAMES = {"log", "output"}


def _copy_assets(dst: str) -> None:
    """复制资产文件夹；跳过缓存目录，flows/examples 里的 log/output 不带。"""
    for name in ASSET_DIRS:
        src = os.path.join(ROOT, name)
        if not os.path.isdir(src):
            continue
        target = os.path.join(dst, name)
        rel_root = src

        def _ignore(dirpath: str, names):
            base = os.path.basename(dirpath)
            if base in DROP_DIR_NAMES and dirpath.startswith(rel_root):
                # 只丢 flows/<流程>/ 和 examples/<示例>/ 下的 log/output，
                # 程序自身的 log/output 概念不会出现，但保险起见全局生效
                return names
            ignored = [n for n in names
                       if n in SKIP_DIR_NAMES or n.endswith(".pyc")]
            return ignored

        shutil.copytree(src, target, ignore=_ignore,
                        ignore_dangling_symlinks=True)


def assemble(version: str, dist: str, out: str) -> str:
    """组装发布文件夹，返回文件夹路径。"""
    is_mac = sys.platform == "darwin"
    suffix = "macos" if is_mac else "win64"
    folder = os.path.join(out, f"LingTong-v{version}-{suffix}")

    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)

    if is_mac:
        app_src = os.path.join(dist, "LingTong.app")
        if not os.path.isdir(app_src):
            raise SystemExit(f"找不到 {app_src}，请先运行 PyInstaller 打包")
        shutil.copytree(app_src, os.path.join(folder, "LingTong.app"),
                        symlinks=True)
    else:
        app_src = os.path.join(dist, "LingTong")
        if not os.path.isdir(app_src):
            raise SystemExit(f"找不到 {app_src}，请先运行 PyInstaller 打包")
        # Windows onedir 的内容（exe + _internal/）直接铺在发布文件夹根上
        for item in os.listdir(app_src):
            src_item = os.path.join(app_src, item)
            dst_item = os.path.join(folder, item)
            if os.path.isdir(src_item):
                shutil.copytree(src_item, dst_item)
            else:
                shutil.copy2(src_item, dst_item)

    _copy_assets(folder)
    return folder


def make_archive(folder: str) -> str:
    """按平台生成压缩包，返回压缩包路径。"""
    if sys.platform == "darwin":
        out = folder + ".tar.gz"
        with tarfile.open(out, "w:gz", format=tarfile.PAX_FORMAT) as tf:
            tf.add(folder, arcname=os.path.basename(folder))
    else:
        out = folder + ".zip"
        base = os.path.dirname(folder)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zf:
            for dirpath, dirnames, filenames in os.walk(folder):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
                for f in filenames:
                    full = os.path.join(dirpath, f)
                    arc = os.path.relpath(full, base)
                    zf.write(full, arc)
    return out


def main() -> None:
    # Windows 控制台默认 cp1252，直接 print 中文会 UnicodeEncodeError
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="组装灵瞳发布包")
    ap.add_argument("--version", required=True, help="版本号，如 1.2.4")
    ap.add_argument("--dist", default=os.path.join(ROOT, "dist"),
                    help="PyInstaller 输出目录（默认 dist/）")
    ap.add_argument("--out", default=os.path.join(ROOT, "release"),
                    help="发布包输出目录（默认 release/）")
    args = ap.parse_args()

    folder = assemble(args.version, args.dist, args.out)
    archive = make_archive(folder)
    size = os.path.getsize(archive) / 1024 / 1024
    print(f"发布文件夹：{folder}")
    print(f"压缩包：{archive}（{size:.1f} MB）")


if __name__ == "__main__":
    main()
