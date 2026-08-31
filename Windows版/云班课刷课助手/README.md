# 云班课刷课助手（Qt 简化 UI）

从网页端逆向接口，用 Python + PySide6 重写的简化刷课工具。

## 功能
- 登录（手机号 + 密码，明文直登 coreapi）
- 班课列表
- 班课资源列表（含类型/时长标识）
- 一键刷课：对视频类资源上报学习进度，`watchTo` 拉到 `duration` 即视为观看完成

## 运行
```bash
# 依赖
pip install PySide6 requests

# 启动图形界面
python yunbanke_qt/main.py
```

## 接口逆向结论（2026-08 实测）
网页端（www.mosoteach.cn）实际是 `coreapi.mosoteach.cn` 的 SPA，接口如下：

| 功能 | 方法与路径 | 说明 |
|---|---|---|
| 登录 | `POST /passports/account-login` | body `{"account","password"}`；返回 `token`；后续请求头带 `X-token`。密码直接用明文即可（页面 wasm 加密是前端演示，服务端同样接受明文） |
| 班课列表 | `GET /ccs/joined` | 返回 `{"clazzCourses":[...], "status":true}` |
| 资源列表 | `GET /ccs/{ccId}/resources?roleId=2` | `roleId=2` 学生视角 |
| 视频预览 | `GET /ccs/{ccId}/resources/{resId}/viewer` | 返回播放地址/时长 |
| 观看记录 | `GET /ccs/{ccId}/resources/{resId}/records` | 含已看位置 |
| **进度上报** | `POST /ccs/{ccId}/resources/{resId}/records` | body `{"watchTo":秒,"currentWatchTo":秒,"duration":秒}`；`watchTo>=duration` 即服务端判定完成 |

请求头统一需要：
```
X-token: <token>
X-client-app-id: MTWEB
X-client-version: 6.0.0
X-security-type: SECURITY_TYPE_TOKEN
Content-Type: application/json;charset=utf-8
```

## 文件
- `yunbanke_qt/api.py` —— 接口封装（独立于 UI，可单独测试）
- `yunbanke_qt/main.py` —— Qt 图形界面（登录页 / 主页 / 刷课）
- `yunbanke_qt/test_api.py` —— 命令行冒烟（登录 + 课程量）

## 注意
- 账号当前 `ACCOUNT_PLACEHOLDER` 未加入任何班课，课程列表为空属正常现象，加入班课后即可看到资源并刷课。
- 刷课仅对"视频"类资源生效（按扩展名/资源类型判断），其他类型（文档/课件）不做进度上报。
- 本工具仅供个人学习辅助使用，请遵守相关平台规则。

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
