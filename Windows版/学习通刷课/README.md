# 学习通刷课 — Windows 版说明

完整文档见 [`学习通刷课/shuake_src/README.md`](../../学习通刷课/shuake_src/README.md)（配置说明 / 驱动下载 / AI 设置），本文件只列 Windows 专属要点。

## 默认浏览器与驱动

- **默认浏览器：Edge**（未保存配置时自动选择，无需手动设置）
- **默认驱动：msedgedriver.exe**，按顺序自动探测：
  1. 项目目录 `edgedriver_win64\msedgedriver.exe`
  2. 系统 PATH
  3. Selenium Manager 自动下载

## 驱动下载（版本需与浏览器主版本一致）

| 浏览器 | 驱动 | 下载地址 | 放置位置 |
|---|---|---|---|
| Edge（默认） | msedgedriver.exe | https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/ | `edgedriver_win64\msedgedriver.exe`，或任意位置后在设置里填绝对路径，或加入 PATH |
| Chrome | chromedriver.exe | https://googlechromelabs.github.io/chrome-for-testing/ | `chromedriver\chromedriver.exe` |
| Firefox | geckodriver.exe | https://github.com/mozilla/geckodriver/releases | `geckodriver\geckodriver.exe` |

## 启动

- 直接双击 `学习通刷课.exe`（首次运行解压 `task\` 资源到同目录）
- 源码运行：`python qt_ui.py`（需先 `pip install -r requirements.txt`）

**版本匹配规则**：驱动主版本号必须等于浏览器主版本号（如 Edge 131 ↔ msedgedriver 131.x），不匹配时程序日志会打印当前/期望版本与下载链接。
