"""
AutoRPA 界面主题
=================
深色（纯黑贾维斯风）主题设计令牌 + 全局 QSS。改这里一处即可整体换肤。
"""
from __future__ import annotations

# ------------------------------------------------------------------ 设计令牌
BG = "#0A0E14"            # 主窗口底色
TABSTRIP = "#1B2436"      # 标签栏条底色（偏亮的冷灰，未激活标签平铺其上）

PANEL = "#111722"         # 卡片/面板
PANEL_SOFT = "#0D131C"    # 输入框、凹槽等次级面
PANEL_HOVER = "#1B2432"   # 悬停
BORDER = "#1F2A3A"
BORDER_STRONG = "#2C3A4F"
CANVAS_BG = "#0B1017"

TEXT = "#E6EDF5"
TEXT_SUB = "#8B98A9"
TEXT_MUTED = "#5C6B7E"

PRIMARY = "#00A9CE"       # 贾维斯青（按钮主色）
PRIMARY_DARK = "#0086A5"
PRIMARY_SOFT = "#0E2A33"  # 选中/高亮底

OK = "#22C07A"
OK_SOFT = "#0E2B1F"
WARN = "#F7A524"
WARN_SOFT = "#33270D"
ERR = "#FF4A3D"           # 报错高亮红
ERR_SOFT = "#3A1714"
RUN = "#00E676"           # 运行高亮绿
RUN_SOFT = "#0C2B1C"
INFO = "#3ED0E0"

FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif'
MONO_FAMILY = '"Cascadia Mono", "Consolas", "SF Mono", "Courier New", monospace'

import sys as _sys
if _sys.platform == "darwin":
    UI_FONT = "PingFang SC"          # macOS 中文字体
elif _sys.platform == "win32":
    UI_FONT = "Microsoft YaHei UI"   # Windows 中文字体
else:
    UI_FONT = "Noto Sans CJK SC"     # Linux 兜底


def font(size: float, weight: int = None):
    """当前平台的中文字体 QFont（各处不要硬编码字体名）。"""
    from PySide6.QtGui import QFont
    f = QFont(UI_FONT)
    f.setPointSizeF(size)
    if weight is not None:
        f.setWeight(weight)
    return f


RADIUS = 10
RADIUS_SM = 6

CATEGORY_COLORS = {
    "图像识别": ("#9D8CFF", "#221E3A"),
    "鼠标操作": ("#5C9DFF", "#16233A"),
    "键盘操作": ("#3ED598", "#122B1F"),
    "窗口系统": ("#FFB020", "#33270D"),
    "变量容器": ("#3ED0E0", "#0E2A30"),
    "流程控制": ("#FF6B5E", "#361816"),
    "通用工具": ("#93A1B5", "#1D242E"),
    "文件操作": ("#5EA8FF", "#15233A"),
    "外部调用": ("#8B93FF", "#1E2140"),
}


def cat_color(cat: str) -> str:
    return CATEGORY_COLORS.get(cat, ("#93A1B5", "#1D242E"))[0]


def cat_soft(cat: str) -> str:
    return CATEGORY_COLORS.get(cat, ("#93A1B5", "#1D242E"))[1]


# ------------------------------------------------------------------ 全局样式表
QSS = f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: {TEXT};
}}
QWidget#Root {{ background: {BG}; }}

/* ---------------- 顶部工具栏 ---------------- */
QWidget#TopBar {{
    background: {PANEL};
    border-bottom: 1px solid {BORDER};
}}
QLabel#Brand {{ font-size: 16px; font-weight: 700; color: {TEXT}; }}
QLabel#BrandSub {{ font-size: 11px; color: {TEXT_MUTED}; }}

/* ---------------- 流程标签页（VS Code 风格平铺条） ---------------- */
/* 条底/标签底色/圆弧全部由 ui/flowtabs.py 的 paintEvent 手写绘制（样式表背景
   在滚动视口场景不可靠）；这里只留文字与关闭按钮规则 */
QLabel#FlowTabIcon {{ background: transparent; border: none; }}
/* 激活/未激活标签字体完全统一（同字号同字重），只靠颜色区分 */
QLabel#FlowTabTitle {{ color: {TEXT_SUB}; background: transparent; border: none; font-size: 12px; }}
QWidget#FlowTab[active="true"] QLabel#FlowTabTitle {{ color: {TEXT}; }}
QLabel#FlowTabDot {{ color: {WARN}; background: transparent; border: none; font-size: 9px; }}
QToolButton#FlowTabClose {{ border: none; background: transparent; border-radius: 4px; }}
QToolButton#FlowTabClose:hover {{ background: rgba(255, 255, 255, 0.10); }}

/* ---------------- 卡片 / 面板 ---------------- */
QWidget#Panel, QFrame#Panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QLabel#PanelTitle {{
    font-size: 13px; font-weight: 700; color: {TEXT};
    padding: 0;
}}
QLabel#PanelHint {{ font-size: 11px; color: {TEXT_MUTED}; }}
QFrame#Divider {{ background: {BORDER}; max-height: 1px; border: none; }}
QFrame#VDivider {{ background: {BORDER}; max-width: 1px; border: none; }}

/* ---------------- 按钮 ---------------- */
QPushButton {{
    background: {PANEL};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 6px 12px;
    color: {TEXT};
}}
QPushButton:hover {{ background: {PANEL_HOVER}; border-color: #3D4F68; }}
QPushButton:pressed {{ background: #212C3D; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; background: {PANEL_SOFT}; border-color: {BORDER}; }}

/* 顶栏统一按钮组（100x32）：低饱和深色底 + 细边，hover 微亮，彩色按钮用软色调 */
QPushButton#TopBtn {{
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    color: {TEXT_SUB};
    text-align: left;
    padding: 0 12px;
}}
QPushButton#TopBtn:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: #3D4F68;
    color: {TEXT};
}}
QPushButton#TopBtn:pressed {{ background: rgba(0, 0, 0, 0.28); border-color: {BORDER_STRONG}; }}
QPushButton#TopBtn:disabled {{ color: {TEXT_MUTED}; background: rgba(255, 255, 255, 0.02); border-color: {BORDER}; }}

/* 运行：主题青实色，视觉焦点 */
QPushButton#TopRun {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #23CFF2, stop:1 #0098BD);
    border: 1px solid #4ADCF8;
    border-radius: 8px;
    color: #032530;
    font-weight: 700;
    text-align: left;
    padding: 0 12px;
}}
QPushButton#TopRun:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4BDBF7, stop:1 #0DABD1);
    border-color: #7BEAFF;
}}
QPushButton#TopRun:pressed {{ background: {PRIMARY_DARK}; border-color: {PRIMARY_DARK}; }}
QPushButton#TopRun:disabled {{ background: #123C47; border-color: #123C47; color: #4E6B76; }}

/* 停止：软红调，不刺眼 */
QPushButton#TopStop {{
    background: rgba(255, 74, 61, 0.13);
    border: 1px solid rgba(255, 74, 61, 0.45);
    border-radius: 8px;
    color: #FF7B6E;
    font-weight: 600;
    text-align: left;
    padding: 0 12px;
}}
QPushButton#TopStop:hover {{ background: rgba(255, 74, 61, 0.24); border-color: rgba(255, 74, 61, 0.7); color: #FF9A8F; }}
QPushButton#TopStop:pressed {{ background: rgba(255, 74, 61, 0.32); }}
QPushButton#TopStop:disabled {{ color: {TEXT_MUTED}; background: rgba(255, 255, 255, 0.02); border-color: {BORDER}; }}

/* 拾取坐标：青色调 */
QPushButton#TopPick {{
    background: rgba(0, 169, 206, 0.10);
    border: 1px solid rgba(0, 169, 206, 0.45);
    border-radius: 8px;
    color: #37CBE9;
    text-align: left;
    padding: 0 12px;
}}
QPushButton#TopPick:hover {{ background: rgba(0, 169, 206, 0.20); border-color: {PRIMARY}; color: #7FE3F7; }}
QPushButton#TopPick:pressed {{ background: rgba(0, 169, 206, 0.28); }}

QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1FC9EE, stop:1 #0098BD);
    border: 1px solid #4ADCF8; border-radius: {RADIUS_SM}px;
    color: #032530; font-weight: 700; padding: 6px 16px;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #43D9F5, stop:1 #0DABD1);
    border-color: #7BEAFF;
}}
QPushButton#Primary:pressed {{ background: {PRIMARY_DARK}; border-color: {PRIMARY_DARK}; color: #FFFFFF; }}
QPushButton#Primary:disabled {{ background: #123C47; border-color: #123C47; color: #4E6B76; }}

QPushButton#Danger {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF6E61, stop:1 #E23A2C);
    border: 1px solid #FF9184; border-radius: {RADIUS_SM}px;
    color: #FFFFFF; font-weight: 700; padding: 6px 16px;
}}
QPushButton#Danger:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FF8577, stop:1 #EF4834);
    border-color: #FFAEA4;
}}
QPushButton#Danger:disabled {{ background: #3A2126; border-color: #4A2A30; color: #7A5A5E; }}

QPushButton#Accent {{
    background: rgba(0, 169, 206, 0.10);
    border: 1px solid rgba(0, 169, 206, 0.55); border-radius: {RADIUS_SM}px;
    color: #37CBE9; font-weight: 600;
}}
QPushButton#Accent:hover {{ background: {PRIMARY_SOFT}; border-color: {PRIMARY}; color: #7FE3F7; }}
QPushButton#Accent:disabled {{ color: {TEXT_MUTED}; background: {PANEL_SOFT}; border-color: {BORDER}; }}

QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; padding: 6px 8px; }}
QPushButton#Ghost:hover {{ background: {PANEL_HOVER}; }}

QPushButton#Chip {{
    background: {PANEL_SOFT}; border: 1px solid {BORDER}; border-radius: 999px;
    padding: 4px 11px; font-size: 12px; color: {TEXT_SUB};
}}
QPushButton#Chip:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; background: {PRIMARY_SOFT}; }}
QPushButton#Chip:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; color: #04222B; }}

/* ---------------- 输入控件 ---------------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {PANEL_SOFT};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 5px 9px;
    selection-background-color: {PRIMARY};
    selection-color: #04222B;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {PRIMARY};
}}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{
    background: {PANEL_SOFT}; color: {TEXT_MUTED};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SUB}; margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px; padding: 4px;
    selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT};
    outline: none;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_STRONG}; border-radius: 4px; background: {PANEL_SOFT};
}}
QCheckBox::indicator:hover {{ border-color: {PRIMARY}; }}
QCheckBox::indicator:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; }}

/* ---------------- 滚动条 ---------------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2E3D52; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #41566F; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2E3D52; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------------- 日志控制台 ---------------- */
QPlainTextEdit#Console {{
    background: #0B0F16;
    border: none;
    border-radius: 0;
    font-family: {MONO_FAMILY};
    font-size: 12px;
    padding: 6px 8px;
}}

/* ---------------- 树 / 列表 ---------------- */
QTreeWidget, QListWidget {{
    background: transparent; border: none; outline: none;
}}
QTreeWidget::item, QListWidget::item {{ padding: 2px; border: none; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: transparent; }}
QTreeWidget::branch {{ background: transparent; }}

/* ---------------- 标签页 ---------------- */
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    background: transparent; border: none; padding: 7px 14px;
    color: {TEXT_SUB}; border-bottom: 2px solid transparent; font-size: 12px;
}}
QTabBar::tab:selected {{ color: {PRIMARY}; border-bottom: 2px solid {PRIMARY}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* ---------------- 状态栏 / 分隔器 ---------------- */
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {TEXT_SUB}; font-size: 12px; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ---------------- 提示气泡 ---------------- */
QToolTip {{
    background: #10161F; color: #E6EDF5; border: 1px solid #2C3A4F;
    border-radius: 6px; padding: 6px 9px; font-size: 12px;
}}

/* ---------------- 菜单 ---------------- */
QMenu {{
    background: {PANEL}; border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px; padding: 5px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {PRIMARY_SOFT}; color: {PRIMARY}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
"""
