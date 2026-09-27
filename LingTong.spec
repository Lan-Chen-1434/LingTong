# -*- mode: python ; coding: utf-8 -*-
"""灵瞳 PyInstaller 配置（onedir 文件夹版）。

平台相关项通过环境变量传入（CI 与本地打包脚本都这么做）：
    LINGTONG_ICON     图标文件（Windows: assets/icons/app.ico / macOS: app.icns）
    LINGTONG_VERSION  版本号（写入 macOS Info.plist）

资产文件夹（flows/examples/assets）不打进二进制，由 tools/make_release.py
复制到可执行文件旁边——用户要能直接增删流程、替换素材（core/paths.py 在
frozen 模式下会自动从可执行文件向上定位这些文件夹）。
"""
import os

ROOT = os.path.abspath(SPECPATH)
ICON = os.environ.get("LINGTONG_ICON", "") or None
VERSION = os.environ.get("LINGTONG_VERSION", "1.2.4")

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests", "tools", "docs", "pytest",
              # OCR 是可选项（见 docs/打包说明.md「已知限制」），不随包发布；
              # 本地若装了 rapidocr/torch，防止把 300MB+ 的重依赖卷进发布包
              "torch", "torchvision", "rapidocr", "rapidocr_onnxruntime",
              "onnxruntime", "scipy", "pandas", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LingTong",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                      # 不弹控制台窗口
    disable_windowed_traceback=False,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LingTong",
)

# 仅在 macOS 生效：把 onedir 收进 LingTong.app 包（Windows 上 PyInstaller 自动跳过）
app = BUNDLE(
    coll,
    name="LingTong.app",
    icon=ICON,
    bundle_identifier="com.lingtong.app",
    version=VERSION,
    info_plist={
        "CFBundleName": "LingTong",
        "CFBundleDisplayName": "灵瞳",
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
    },
)
