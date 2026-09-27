# 灵瞳 · 看得懂屏幕的自动化助手

一个**只靠图像识别 + 键鼠模拟**来操作电脑的自动化工具。不需要目标软件开放任何接口，
只要人眼能看见、能点的东西，它就能自动点。

**核心理念**：把功能拆成积木，拖到画布上拼一拼、填几个参数，就是一个能跑的自动化流程。

## 亮点

- 🎯 **50+ 功能积木**：图像识别 / 键鼠 / 窗口 / 数据抓取 / 流程控制，拖拽即用
- 🗂️ **一流程一文件夹**：流程文件、模板图、脚本、日志、产出各就各位，整个文件夹拷走即可复用
- 🧵 **多标签页**：同时编辑多个流程，VS Code 式标签栏，每个标签独立记住视图状态
- ▶️ **运行可控**：后台线程执行，可暂停 / 继续 / 紧急停止（F10 / F12 全局热键）
- ⚡ **渲染节流**：画布重绘合并到 16ms 一帧、日志批量刷新，上千步循环也不卡界面
- 🖥️ **跨平台**：Windows / macOS（Linux 亦可运行，键鼠模拟依赖桌面环境）

---

## 一、快速开始

```bash
# 1. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. 启动图形界面
python main.py

# 3. 命令行检查环境
python main.py --check

# 4. 不开界面直接跑一个流程
python main.py --run flows/我的流程/我的流程.arpa
```

### macOS 额外步骤

macOS 的自动化能力由系统权限把关，首次运行请在 **系统设置 → 隐私与安全性** 中授予：

| 权限 | 用途 |
| --- | --- |
| 辅助功能（Accessibility） | 模拟鼠标点击 / 键盘输入（pyautogui、pynput） |
| 输入监控（Input Monitoring） | 全局热键 F10 / F12 |
| 屏幕录制（Screen Recording） | 截图找图、抓图取图 |

未授权时对应功能会静默失败，界面日志里会有提示。
另外 macOS 没有"窗口标题"概念，窗口相关积木基于 AppleScript，首次使用时系统会请求授权。

---

## 二、界面速览

- **顶部工具条**：新建 / 打开 / 保存 / 另存 / 示例流程 / 拾取坐标 / 运行控制
- **左侧**：模块面板，搜索后拖入画布
- **中间**：画布（流程设计）+ 标签页；多标签独立编辑，双击标签重命名，× 关闭
- **右侧**：步骤参数，选中画布步骤后填写；未保存的标签显示 ● 圆点
- **底部**：运行日志 + 变量表，每次运行的日志同时写入 `<流程>/log/run_时间戳.txt`

## 三、流程文件夹结构

保存流程时按"一流程一文件夹"落盘（另存时直接散存在 flows/ 根目录的文件也会自动归位）：

```
flows/<流程名>/
├── <流程名>.arpa        流程文件
├── input/               输入资源（抓图/选文件时自动收进 input/image）
│   ├── image/
│   ├── excel/
│   └── txt/
├── python_scripts/
├── vba_scripts/
├── log/                 每次运行的 txt 日志（保留最近一个月）
└── output/              运行产出（写入时才创建，不预建空目录）
```

流程参数里写相对路径 = 相对本流程文件夹，例如 `input/image/a.png`。

**清理策略**：只有当流程**整体运行成功且没有任何步骤被跳过**，之后你再保存该流程时，
才会清理一次未被引用的模板图和过期日志；其他情况一律不动你的文件。

## 四、项目结构

```
main.py            入口：GUI / --run 无头运行 / --check 环境检查 / --make-icon
app/               应用组装：DPI 感知、Fusion 主题、启动屏、.arpa 文件关联
core/              领域核心（不依赖 Qt）
├── models.py      Flow / FlowNode 数据模型与 .arpa 存取
├── registry.py    @module 装饰器 + 模块注册中心
├── engine/        执行引擎 + 运行状态机（后台线程、暂停/停止/子流程）
├── drivers/       屏幕 / 键鼠 / 窗口 / OCR 驱动（全部跨平台 + 缺依赖静默降级）
├── paths.py       流程工作区路径约定（flows/ 结构、图片收纳、清理）
├── vartypes.py    变量类型系统（字符串/列表/字典/表格互转）
└── platform.py    Windows / macOS / Linux 差异封装
modules/           功能积木库（按 @module 声明自动出现在界面，新增不用改 UI）
ui/                界面层（PySide6）：主窗口 / 画布 / 参数面板 / 标签页 / 顶栏
examples/          内置示例流程（按模块分类，示例面板一键载入）
flows/             用户流程保存目录
tests/             冒烟与引擎测试（QT_QPA_PLATFORM=offscreen 可跑）
tools/             图标 / 音效生成脚本、发布包组装（make_release.py）
docs/              界面设计稿、打包说明、GitHub Actions 打包教程
.github/           GitHub Actions：推 v* 标签自动打包 Windows/macOS 并发布
LingTong.spec      PyInstaller 配置（onedir 文件夹版）
```

## 五、打包发布

推 `v*` 标签即由 GitHub Actions 自动产出 Windows（zip）与 macOS（tar.gz）
文件夹版安装包，带程序图标与全部示例流程；也可本地执行 `LingTong.spec` +
`tools/make_release.py` 打包。详见 **docs/打包说明.md**。

## 六、开发

```bash
# 运行测试（界面冒烟用 offscreen 平台，不需要显示器）
python tests/test_tabs.py       # 多标签行为
python tests/test_ui_smoke.py   # 界面冒烟
python tests/test_engine.py     # 执行引擎
python tests/test_vartypes.py   # 变量类型
python tests/test_examples.py   # 56 个示例流程全量校验
```

新增一个功能积木只需在 `modules/` 里写一个 `@module(...)` 函数，
声明参数与输入/输出变量，左侧模块面板和执行引擎会自动接管。
