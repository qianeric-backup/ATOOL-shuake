# Linux 版（刷课软件合集 — Linux/macOS 适用）

本目录集中存放 **Linux/macOS** 下的源码运行方式与使用说明。
本合集各项目均已做跨平台适配，无需依赖 Windows 专属 exe：
在 Linux/macOS 上用 `python3` 直接运行源码即可，Windows 可执行产物见 `../Windows版/`。

## 目录

| 项目 | 源码入口 | 一键启动 | 依赖要点 |
|---|---|---|---|
| 云班课刷课 | `../云班课刷课/yunbanke_qt/main.py` | `云班课刷课助手/run_linux.sh` | PySide6 + requests，纯 API 刷课，**无需浏览器驱动** |
| 学习通刷课 | `../学习通刷课/shuake_src/qt_ui.py` | `学习通刷课/run_linux.sh` | Selenium + PySide6，需浏览器驱动加入系统 PATH |
| 知到刷课(Autovisor) | `../知到刷课/autovisor-src/Autovisor-main/qt_gui.py` | `知到刷课(Autovisor)/run_linux.sh` | Playwright + PySide6，需 `playwright install` 浏览器 |

## 快速开始

```bash
# 1. 安装 Python 依赖（进入对应源码目录后执行）
pip install -r requirements.txt

# 2. 安装浏览器驱动（学习通必需；云班课不需要，知到用 Playwright 自带）
sudo apt install chromium-driver        # Debian/Ubuntu: Chromium 驱动
sudo apt install firefox-geckodriver    # Debian/Ubuntu: Firefox 驱动
# 或手动下载后可执行文件并加入 PATH（chromedriver / geckodriver / msedgedriver）

# 3.（知到刷课）安装 Playwright 浏览器
python3 -m playwright install firefox

# 4. 启动对应项目
cd 云班课刷课助手 && bash run_linux.sh        # 或 python3 yunbanke_qt/main.py
cd 学习通刷课    && bash run_linux.sh         # 或 python3 shuake_src/qt_ui.py
cd 知到刷课(Autovisor) && bash run_linux.sh   # 或 python3 autovisor-src/Autovisor-main/qt_gui.py
```

> 提示：`run_linux.sh` 启动前会自动检查 python3 与关键依赖，缺失时给出安装提示；
> 三个子目录内另附「启动说明.txt」与完整 README，含各项目功能与配置细节。

## 驱动配置说明

- **Windows**：在程序设置里填 .exe 绝对路径（如 `...\chromedriver.exe`）。
- **Linux/macOS**：直接填驱动名（`chromedriver`/`geckodriver`/`msedgedriver`），
  程序会先从系统 PATH 查找，找不到再提示选择文件。

## 跨平台兼容说明

- 所有 `r"task\..."` 反斜杠路径已改为跨平台 `task/...` 正斜杠。
- Windows 专属的 `taskkill` / `ctypes.windll` / `os.startfile` 均已加了
  `os.name` / `sys.platform` 平台判断，Linux 下自动走对应分支。
- 各项目的功能细节（登录方式、AI 答题、刷课策略等）请阅读对应子目录的 README。

## 免责声明

本合集仅供个人学习研究使用，请遵守相关平台规则与学校规定，合理安排学习时间。