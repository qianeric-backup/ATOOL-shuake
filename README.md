# 刷课软件合集（ATOOL-shuake）

学习平台刷课工具合集，覆盖 **学习通 / 云班课 / 知到** 三个平台。同一套源码做跨平台适配：Windows 用户从 [Releases](https://github.com/qianeric-backup/ATOOL-shuake/releases) 下载 exe，Linux/macOS 用户在本目录执行 `./start.sh`（或各项目 `启动.sh`）。

## 目录结构

| 目录 | 说明 |
|---|---|
| `学习通刷课/` | 超星学习通刷课（Qt 界面 + Selenium 驱动浏览器）；`shuake_src/` 为源码，`deb-build/`、`wine-build/` 为打包脚本，`用户须知（使用前一定要看）.docx` 为使用前必读 |
| `云班课刷课/` | 云班课刷课助手（从网页端逆向接口，Python + PySide6 重写，纯 API 上报学习进度，无需浏览器驱动）；`yunbanke_qt/` 为源码 |
| `知到刷课/` | 知到智慧树刷课（Autovisor，Playwright 驱动）；`autovisor-src/` 为源码 |

## 快速开始

- **Windows**：到 [GitHub Releases](https://github.com/qianeric-backup/ATOOL-shuake/releases) 下载对应 exe 双击使用。
- **Linux/macOS**：直接在本目录执行 `./start.sh`（或各项目的 `启动.sh`）

## 注意事项

- 使用前先读各项目的 README 与用户须知；刷课行为请自行评估平台风控风险。
- 含真实登录态的配置/Cookie 仅本地留存，不入库。


## 一键启动（推荐）

在仓库根目录：

```bash
./start.sh            # 交互式菜单（学习通/云班课/知到 三选一）
./start.sh 2          # 或直接指定编号快速启动
./学习通刷课/启动.sh    # 各项目独立快捷入口
./云班课刷课/启动.sh
./知到刷课/启动.sh
```

Windows 版 exe 从 [Releases](https://github.com/qianeric-backup/ATOOL-shuake/releases) 页下载 tartag（Tag 触发的 CI 产物）。
