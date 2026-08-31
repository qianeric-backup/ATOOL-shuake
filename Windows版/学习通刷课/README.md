# 学习通刷课脚本（社区简化版）

基于 [Xuexitong_shuake](https://github.com/Mortal004/Xuexitong_shuake) 的重写简化版，去除了作者赞助页、启动时的免责/用户须知弹窗和更新检测弹窗，加入了**自定义 API 地址 / API Key / 模型名**支持，并适配 **Edge、Chrome、Firefox** 三种浏览器。

## 主要功能

- **定时自动刷课**：模拟真实用户观看视频，支持倍速调节（最高 16 倍速），可设定开始与结束时间。
- **连续刷多门课程**：最多连续刷 3 门课程，全程自动操作。
- **AI 自动答题**：章节测验、作业、视频弹题、讨论均可接入任意 OpenAI 兼容 API（DeepSeek、OpenRouter、本地 vLLM 等）自动作答；未配置 AI 时也可用免费题库优先检索。
- **自动跳过人脸认证**：第一次刷脸成功后，后续自动跳过。
- **自动刷直播、播放音频、回复讨论、播放 PPT**。
- **可视化控制**：PySide6（Qt）图形界面，可查看刷课日志、测试成绩、缓存题库与报错日志。

> 说明：本仓库已由原生 tkinter 界面升级为 Qt（PySide6）界面，功能保持一致。旧 tk 界面备份在 `start_tk.py`，如需使用可把 `start_tk.py` 改回 `start.py` 或直接运行 `start_tk.py`。

## 打包为单文件 exe（Qt/PySide6 精简版）

```bash
pip install -r requirements.txt
python -m PyInstaller 学习通刷课.spec --noconfirm --clean
```

产物位于 `dist/学习通刷课.exe`。spec 已精简：不再用 `collect_all('PySide6')` 打包整个 Qt 全家桶，仅收集本项目用到的 `QtCore/QtGui/QtWidgets/QtNetwork` 与必要插件，并排除用不到的 Qt 附加模块（3D/WebEngine/多媒体等），**exe 体积约 136MB**（精简前约 330MB），首次解压与启动明显加快。首次运行会在 exe 同目录解压 `task/` 资源。

> 依赖说明：此版本仍需要 `selenium`（刷课核心），需先 `pip install -r requirements.txt`；若 exe 报 `No module named 'selenium'` 说明打包环境缺少 selenium，装上后重打即可。", "old_string": "> 说明：本仓库已由原生 tkinter 界面升级为 Qt（PySide6）界面，功能保持一致。旧 tk 界面备份在 `start_tk.py`，如需使用可把 `start_tk.py` 改回 `start.py` 或直接运行 `start_tk.py`。", "path": "C:\\Users\\qianeric\\Documents\\reasonix-project\\学习通刷课\\shuake_src\\README.md"}

## 环境要求

- Python 3.x
- 所选浏览器对应的驱动（对应驱动文件），并在设置中正确配置驱动路径。

### 所需 Python 库

```bash
pip install selenium pyautogui requests PySide6 colorama openai", "old_string": "pip install selenium pyautogui requests customtkinter colorama openai", "path": "C:\\Users\\qianeric\\Documents\\reasonix-project\\学习通刷课\\shuake_src\\README.md"}
```

## 配置说明

1. **浏览器与驱动**：在「设置 → 配置设置」中选择浏览器（edge / chrome / firefox），并选择与浏览器版本匹配的驱动文件。
   - Chrome 驱动：https://googlechromelabs.github.io/chrome-for-testing/
   - Edge 驱动：https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/
   - Firefox 驱动：https://github.com/mozilla/geckodriver/releases

2. **API 设置**：在「设置 → 高级设置」中填写：
   - `API Key`：你的 API 密钥（支持任意 OpenAI 兼容接口）。
   - `API 地址`：接口 base URL，留空则使用默认 `https://api.deepseek.com`。
   - `模型名`：**可下拉选择**，填写 API 地址后程序会自动拉取该接口的全部可用模型；也支持手动输入。

### 模型列表自动获取（多协议自适应）

在「高级设置」填写 API 地址后，程序自动探测并拉取模型列表，兼容多种接口协议：

| 协议形态 | 探测端点 | 响应格式示例 |
|---|---|---|
| OpenAI 兼容 | `{地址}/models`、`{地址}/v1/models` | `{"data":[{"id":"gpt-4o"}]}` |
| Ollama | `{地址}/api/tags` | `{"models":[{"name":"llama3"}]}` |
| 极简实现 | `{地址}/models/list` | `{"models":["gpt-4o"]}` |
| 裸列表 | `{地址}/models` | `["gpt-4o","deepseek-chat"]` |

认证自动尝试 `Authorization: Bearer <key>`、`Authorization: <key>`、`X-Api-Key: <key>`、`?api_key=<key>` 四种方式；拉取在后台线程执行不阻塞界面，并在「模型名」旁显示状态（成功列出 N 个 / 失败原因，失败不再静默）。

## 使用说明

1. 在设置页面填写账号密码、课程名称、浏览器/驱动、API 等信息，点击「保存设置」。
2. 回到主页点击「开始刷课」即可。进度与日志会实时显示在窗口中。

## 注意事项

- 刷题答案仅供参考，请自行判断。
- 请使用与浏览器主版本一致的驱动。
- 本工具仅用于学习研究，请遵守学校相关规定，合理安排学习时间。

## Linux 适配说明（跨平台）

本项目已完成 Linux/macOS 跨平台适配，无需依赖 Windows 专属 exe 驱动：

### 运行前置
```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 安装对应浏览器的 Linux 驱动（按需，任选一种）
sudo apt install chromium-driver        # Debian/Ubuntu: Chromium 驱动
sudo apt install firefox-geckodriver    # Debian/Ubuntu: Firefox 驱动
# 或手动下载后放入 PATH：
#   chromedriver / msedgedriver / geckodriver

# 3.（知到/学习通）安装 Playwright 浏览器
python -m playwright install firefox    # 知到刷课用
```

### 在设置里填写驱动
- **Windows**：仍用 .exe 绝对路径（如 `...\chromedriver.exe`）。
- **Linux/macOS**：直接填驱动名（`chromedriver`/`geckodriver`/`msedgedriver`），
  程序会先从系统 PATH 查找，找不到再提示选择文件。

### 兼容性说明
- 所有 `r"task\..."` 反斜杠路径已改为跨平台 `task/...` 正斜杠。
- Windows 专属的 `taskkill` / `ctypes.windll` / `os.startfile` 均已加了
  `os.name` / `sys.platform` 平台判断，Linux 下自动走对应分支。
- 双击 GUI 运行：`python 对应入口.py`（学习通 `shuake_src/qt_ui.py`、
  云班课 `yunbanke_qt/main.py`、知到 `autovisor-src/…/qt_gui.py`）。
