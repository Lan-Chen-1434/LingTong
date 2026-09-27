"""
灵瞳 启动入口
==================
用法::

    python main.py                  # 启动图形界面
    python main.py --run flows/x.arpa   # 不开界面，直接命令行跑一个流程
    python main.py --check          # 检查运行环境依赖
    python main.py --make-icon      # 重新生成程序图标

目录约定
--------
core/       领域核心：模型、引擎、驱动、变量（不依赖 Qt）
modules/    功能积木库（@module 注册，新增模块不用改界面）
ui/         界面层（PySide6）
app/        应用组装：环境初始化 + 主窗口启动
flows/      流程文件保存目录（一流程一文件夹，详见 README）
examples/   内置示例流程
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def check_env() -> int:
    from core.drivers import check_dependencies

    print("灵瞳 运行环境检查")
    print("-" * 44)
    ok_all = True
    for name, ok in check_dependencies().items():
        print(f"  [{'✓' if ok else '×'}] {name}")
        ok_all = ok_all and ok
    print("-" * 44)
    try:
        from PySide6 import QtCore
        print(f"  [✓] PySide6 {QtCore.__version__}（图形界面）")
    except Exception as exc:                            # noqa: BLE001
        ok_all = False
        print(f"  [×] PySide6 缺失：{exc}")
    try:
        import openpyxl
        print(f"  [✓] openpyxl {openpyxl.__version__}（Excel 导出）")
    except Exception:                                   # noqa: BLE001
        print("  [ ] openpyxl 缺失（仅影响导出 xlsx）")
    print("-" * 44)
    print("结论：" + ("环境完整，可以启动。" if ok_all else "存在缺失，请先安装依赖。"))
    return 0 if ok_all else 1


def run_headless(path: str) -> int:
    from core.engine import run_flow_sync
    from core.models import Flow

    if not os.path.isfile(path):
        print(f"流程文件不存在：{path}")
        return 2
    flow = Flow.load(path)
    print(f"开始执行「{flow.name}」…")

    def log(level: str, msg: str) -> None:
        mark = {"ok": "✔", "warn": "▲", "error": "✖"}.get(level, "·")
        print(f"  {mark} {msg}")

    ok = run_flow_sync(flow, logger=log, base_dir=os.path.dirname(os.path.abspath(path)))
    print("执行" + ("成功。" if ok else "失败或被中断。"))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="灵瞳 自动化助手")
    parser.add_argument("flow", nargs="?", metavar="FLOW",
                        help="启动后直接打开指定流程文件（.arpa）")
    parser.add_argument("--run", metavar="FLOW", help="命令行执行指定流程文件（不打开界面）")
    parser.add_argument("--check", action="store_true", help="检查运行环境")
    parser.add_argument("--make-icon", action="store_true", help="重新生成程序图标")
    args = parser.parse_args()

    if args.check:
        return check_env()
    if args.make_icon:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from make_icon import main as icon_main
        icon_main()
        return 0
    if args.run:
        return run_headless(args.run)

    from app.bootstrap import run_gui
    return run_gui(sys.argv, open_flow=args.flow)


if __name__ == "__main__":
    sys.exit(main())
