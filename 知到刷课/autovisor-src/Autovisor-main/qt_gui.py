# encoding=utf-8
"""Autovisor 最简化 Qt 图形界面入口。

功能:
  - 选择浏览器(Chrome/Edge/Firefox), 填写必须配置(课程链接/账号/密码), 选填时长、倍速与开关;
  - 一键写入 configs.ini 并后台启动刷课;
  - 日志实时显示在窗口底部;
  - 打包为单 exe 时自动从内置资源初始化 configs.ini。
"""
import io
import os
import queue
import subprocess
import sys
import threading
import configparser
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QCheckBox, QPushButton,
    QPlainTextEdit, QFormLayout, QHBoxLayout, QVBoxLayout, QMessageBox,
    QComboBox,
)
from PySide6.QtGui import QFont

# 上游 3.18.3 重构后不再有 modules.paths，改为本文件内的路径定义
import os

def _base_dir():
    """运行根目录：打包(onefile/onedir)时为 exe 所在目录，源码态为文件目录。

    onefile 下 __file__ 位于 _MEIPASS 临时解包目录，config.ini/logs 等
    用户数据必须写到 exe 同目录才能在重启后保留。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class _Paths:
    """兼容旧 modules.paths 的轻量 shim（上游 3.18.3 已移除该模块）"""

    @staticmethod
    def runtime_root():
        return _base_dir()

    @staticmethod
    def resource_path(*parts):
        return os.path.join(_base_dir(), *parts)


paths = _Paths()
import Autovisor


# 队列哨兵：刷课线程结束标记，经日志队列送回主线程执行 UI 恢复
GUI_DONE = "__GUI_TASK_DONE__"

# ==== 配置读写 ====
CONFIG_FILE = os.path.join(_base_dir(), "config.ini")  # 上游配置名 config.ini


# 首启空白配置模板（与 config.ini.example 等价的代码内置兜底：
# onefile 打包形态下外部模板可能不可达，用内置字符串保证一定能生成）
_CONFIG_TEMPLATE = """[user-account]
;配置账号密码，留空则打开网页后需手动登录
username =
password =

[browser-option]
;配置浏览器,可选 Edge 或 Chrome
driver = Edge
;指定浏览器所在路径,不填则使用默认路径
EXE_PATH =
;防最小化暂停(默认:True)
keepWindowActive = True

[script-option]
;是否自动过登录时的滑块验证(默认:True)
enableAutoCaptcha = True
;是否自动隐藏浏览器窗口(默认:False)
enableHideWindow = False
;是否展示赞赏码(默认:True)
showDonateCode = True
;平时测试自动做题(需配置 [ai-option])
enableAutoExam = False

[course-option]
;限制每门课程刷课时长/min (不限制:0)
limitMaxTime = 30
;限定播放倍速 (最高:1.8)
limitSpeed = 1.0
;设置是否静音播放 (默认:True)
soundOff = True

[course-url]
;配置要学习的课程链接,支持(智慧)共享课
URL1 =
"""

# Windows exe 首启适配: config.ini 缺失时自动生成空白模板,
# 避免直接弹 ConfigError("未找到配置文件") 退出, 或空配置下
# 点开始刷课报 NoSectionError。优先用随包内置的 config.ini.example,
# 拿不到时回退到上面的代码内置模板。
def ensure_config_file() -> None:
    if os.path.isfile(CONFIG_FILE):
        return
    # 模板随包内置: frozen(onefile) 时位于 _MEIPASS(__file__ 所在目录),
    # 源码态与 _base_dir 同目录
    example = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "config.ini.example")
    try:
        if os.path.isfile(example):
            with open(example, "r", encoding="utf-8-sig") as f:
                content = f.read()
        else:
            content = _CONFIG_TEMPLATE
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError:
        pass  # 生成失败时交由 Autovisor.cli 报原有的 ConfigError


def read_config() -> configparser.ConfigParser:
    ensure_config_file()
    cfg = configparser.ConfigParser()
    # utf-8-sig 同时兼容带/不带 BOM 的写法
    try:
        cfg.read(CONFIG_FILE, encoding="utf-8-sig")
    except Exception:
        cfg.read(CONFIG_FILE, encoding="gbk")
    return cfg


def write_config(cfg: configparser.ConfigParser) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


def load_form_values(cfg: configparser.ConfigParser):
    def get(section, option, default=""):
        try:
            return cfg.get(section, option, raw=True) or default
        except Exception:
            return default

    return (
        get("browser-option", "driver", "Edge"),
        get("course-url", "URL1"),
        get("user-account", "username"),
        get("user-account", "password"),
        get("course-option", "limitMaxTime", "30"),
        get("course-option", "limitSpeed", "1.0"),
        get("script-option", "enableAutoCaptcha", "True") == "True",
        get("script-option", "enableHideWindow", "False") == "True",
        get("course-option", "soundOff", "True") == "True",
        get("ai-option", "api_url", ""),
        get("ai-option", "api_key", ""),
        get("ai-option", "ai_id", ""),
        get("ai-option", "ai_answer_enabled", "True") == "True",
        get("browser-option", "keepWindowActive", "True") == "True",
        get("script-option", "enableAutoExam", "False") == "True",
    )


def save_form_values(cfg: configparser.ConfigParser, driver, course_url, username, password,
                     limit_time, speed, auto_captcha, hide_window, mute,
                     ai_url="", ai_key="", ai_model="", ai_enable=True,
                     bg_keep=True, auto_exam=False, auto_exam_submit=False) -> None:
    cfg.set("browser-option", "driver", driver)
    cfg.set("course-url", "URL1", course_url)
    cfg.set("user-account", "username", username)
    cfg.set("user-account", "password", password)
    cfg.set("course-option", "limitMaxTime", limit_time)
    cfg.set("course-option", "limitSpeed", speed)
    cfg.set("script-option", "enableAutoCaptcha", str(auto_captcha))
    cfg.set("script-option", "enableHideWindow", str(hide_window))
    cfg.set("course-option", "soundOff", str(mute))
    cfg.set("browser-option", "keepWindowActive", str(bool(bg_keep)))
    cfg.set("script-option", "enableAutoExam", str(bool(auto_exam)))
    # 主流程自动做题的"答完自动提交"开关(GUI 的做题链接勾选框共用)
    cfg.set("script-option", "enableAutoExamSubmit", str(bool(auto_exam_submit)))
    if not cfg.has_section("ai-option"):
        cfg.add_section("ai-option")
    cfg.set("ai-option", "api_url", ai_url)
    cfg.set("ai-option", "api_key", ai_key)
    cfg.set("ai-option", "ai_id", ai_model)
    cfg.set("ai-option", "ai_answer_enabled", str(bool(ai_enable)))
    write_config(cfg)


# ==== 日志重定向: 刷课线程的 print 输出 -> 队列 -> UI ====
class QueueWriter(io.StringIO):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self._q = log_queue

    def write(self, s):
        if s and s.strip():
            self._q.put(s)
        return len(s)

    def flush(self):
        pass


def run_shuake(log_queue: queue.Queue, on_done):
    """在后台线程运行刷课主流程, 日志重定向到队列。"""
    ensure_config_file()
    # 告知 AI 模块本次使用的配置路径(GUI 写的就是这个文件, 避免读错)
    try:
        import modules.ai_client as _ai
        _ai.set_config_path(CONFIG_FILE)
    except Exception:
        pass
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = QueueWriter(log_queue)
    sys.stderr = QueueWriter(log_queue)
    try:
        Autovisor.cli()
    except Exception as e:  # 兜底, 避免线程静默死亡
        import traceback
        log_queue.put(f"[GUI] 刷课线程异常: {type(e).__name__}: {e}\n")
        # 只打印一行异常信息无法定位问题(如曾经的 None.isatty), 这里补堆栈
        log_queue.put(traceback.format_exc()[-2000:] + "\n")
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        # 结束回调经队列带回主线程处理（QTimer 轮询 pump_log）,
        # 工作线程直接操作 QWidget/QTimer 违反 Qt 线程规则
        log_queue.put(GUI_DONE)


def run_doexam(log_queue: queue.Queue, on_done, exam_url, engine="firefox",
               submit=False, headless=False):
    """后台线程: 自动做题 (requests SSO + Playwright + 课中题同源 AI)."""
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = QueueWriter(log_queue)
    sys.stderr = QueueWriter(log_queue)
    try:
        import modules.ai_client as ai_client
        import modules.exam_worker as worker

        ai_cfg = ai_client.load_ai_config()
        if not ai_client.is_configured(ai_cfg):
            raise RuntimeError("AI 配置缺失 (api_url/api_key/ai_id)")

        async def _go():
            cookies = worker.sso_cookies()
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser, ctx, page = await worker.open_exam_page(
                    p, exam_url, cookies,
                    engine={"Firefox": "firefox", "Edge": "chromium",
                            "Chrome": "chromium"}.get(engine, "firefox"),
                    headless=True)
                try:
                    result = await worker.run_exam(page, exam_url, ai_cfg, submit=submit)
                    print(f"做题完成: {result}\n")
                finally:
                    await browser.close()

        asyncio.run(_go())
    except Exception as e:
        log_queue.put(f"[做题] 异常: {e}\n")
        import traceback
        log_queue.put(traceback.format_exc()[-2000:] + "\n")
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        log_queue.put(GUI_DONE)


# ==== 主窗口 ====
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("知到刷课助手")
        self.setMinimumSize(600, 520)
        self._running = False
        self._exam_running = False
        self._log_queue = queue.Queue()

        # 顶部标题
        title = QLabel("知到刷课助手")
        title.setAlignment(Qt.AlignCenter)
        f = QFont("Microsoft YaHei", 16, QFont.Bold)
        title.setFont(f)

        # 表单
        form = QFormLayout()
        form.setSpacing(8)

        self.driver_combo = QComboBox()
        self.driver_combo.addItems(["Edge", "Chrome", "Firefox"])

        self.course_edit = QLineEdit()
        self.course_edit.setPlaceholderText("从智慧树课程页复制, 以 zhs 或 course 开头")
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("手机号 / 学号 (留空则需手动登录)")
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.time_edit = QLineEdit()
        self.time_edit.setFixedWidth(72)
        self.speed_edit = QLineEdit()
        self.speed_edit.setFixedWidth(72)

        form.addRow("浏览器:", self.driver_combo)
        form.addRow("课程链接:", self.course_edit)
        form.addRow("账号:", self.user_edit)
        form.addRow("密码:", self.pass_edit)

        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("时长限制(分,0不限):"))
        opt_row.addWidget(self.time_edit)
        opt_row.addSpacing(16)
        opt_row.addWidget(QLabel("倍速(≤1.8):"))
        opt_row.addWidget(self.speed_edit)
        opt_row.addStretch(1)
        form.addRow(opt_row)

        self.captcha_check = QCheckBox("自动滑块验证")
        self.hide_check = QCheckBox("隐藏浏览器窗口")
        self.mute_check = QCheckBox("静音播放")
        self.bg_keep_check = QCheckBox("防最小化暂停")
        self.auto_exam_check = QCheckBox("平时测试自动做题")
        self.auto_exam_check.setToolTip("刷课遇到【平时测试】弹出的做题页时,"
                                        "自动用同一 AI 配置完成作答(答完自动关闭弹窗)")
        check_row = QHBoxLayout()
        check_row.addWidget(self.captcha_check)
        check_row.addWidget(self.hide_check)
        check_row.addWidget(self.mute_check)
        check_row.addWidget(self.bg_keep_check)
        check_row.addWidget(self.auto_exam_check)
        check_row.addStretch(1)
        form.addRow(check_row)

        # 按钮
        self.start_btn = QPushButton("开始刷课")
        self.start_btn.setMinimumHeight(34)
        self.doexam_btn = QPushButton("自动做题")
        self.doexam_btn.setToolTip("打开作业/考试链接, AI 自动作答(与课中题同一 AI 配置)")
        open_btn = QPushButton("打开配置文件")
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.doexam_btn)
        btn_row.addWidget(open_btn)

        # 作业/考试链接 (dohomework)
        self.exam_edit = QLineEdit()
        self.exam_edit.setPlaceholderText("做题链接: https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/...")
        self.exam_submit_check = QCheckBox("答完自动提交")
        exam_row = QHBoxLayout()
        exam_row.addWidget(self.exam_submit_check)
        form.addRow("做题链接:", self.exam_edit)

        # ==== AI 配置（api_url / api_key / AI ID + 拉取/连通性测试）====
        ai_head = QLabel("AI 接口（自动答题：课中题/课程测试）:")
        form.addRow(ai_head)

        self.ai_url_edit = QLineEdit()
        self.ai_url_edit.setPlaceholderText("https://api.deepseek.com/v1 (OpenAI 风格)")
        self.ai_key_edit = QLineEdit()
        self.ai_key_edit.setEchoMode(QLineEdit.Password)
        self.ai_key_edit.setPlaceholderText("sk-...（不回显）")
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setEditable(True)
        form.addRow("API 地址:", self.ai_url_edit)
        form.addRow("API Key:", self.ai_key_edit)
        ai_model_row = QHBoxLayout()
        ai_model_row.addWidget(QLabel("AI ID:"))
        ai_model_row.addWidget(self.ai_model_combo, 1)
        form.addRow(ai_model_row)
        self.ai_refresh_btn = QPushButton("刷新模型列表")
        self.ai_test_btn = QPushButton("测试连通性")
        self.ai_auto_check = QCheckBox("启用 AI 自动答题")
        self.ai_auto_check.setChecked(True)
        ai_btn_row = QHBoxLayout()
        ai_btn_row.addWidget(self.ai_refresh_btn)
        ai_btn_row.addWidget(self.ai_test_btn)
        ai_btn_row.addWidget(self.ai_auto_check)
        ai_btn_row.addStretch(1)
        form.addRow(ai_btn_row)

        # 日志区
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(150)
        log_label = QLabel("运行日志: (随运行写入 exe 旁的 logs/ 目录)")

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(btn_row)
        layout.addWidget(log_label)
        layout.addWidget(self.log_view)

        config = read_config()
        (driver, url, user, pwd, t, sp, cap, hide, mute,
         ai_url, ai_key, ai_model, ai_on, bg_keep, auto_exam) = load_form_values(config)
        idx = self.driver_combo.findText(driver, Qt.MatchFixedString)
        if idx >= 0:
            self.driver_combo.setCurrentIndex(idx)
        self.course_edit.setText(url)
        self.user_edit.setText(user)
        self.pass_edit.setText(pwd)
        self.time_edit.setText(t)
        self.speed_edit.setText(sp)
        self.captcha_check.setChecked(cap)
        self.hide_check.setChecked(hide)
        self.mute_check.setChecked(mute)
        self.bg_keep_check.setChecked(bg_keep)
        self.auto_exam_check.setChecked(auto_exam)
        # 「答完自动提交」开关(主流程自动做题用): 直接读 script-option
        self.exam_submit_check.setChecked(
            config.get("script-option", "enableAutoExamSubmit", fallback="False")
            .strip().lower() == "true")
        self.ai_url_edit.setText(ai_url)
        self.ai_key_edit.setText(ai_key)
        self.ai_model_combo.setCurrentText(ai_model)
        self.ai_auto_check.setChecked(ai_on)

        self.start_btn.clicked.connect(self.on_start)
        self.doexam_btn.clicked.connect(self.on_doexam)
        open_btn.clicked.connect(self.on_open_config)
        self.ai_refresh_btn.clicked.connect(self.on_ai_refresh)
        self.ai_test_btn.clicked.connect(self.on_ai_test)
        if self.ai_url_edit.text().strip() and self.ai_key_edit.text().strip():
            # 启动后自动拉一次模型列表（后台线程；有保存的模型配置）
            QTimer.singleShot(500, lambda: self.on_ai_refresh(auto=True))

        # 日志轮询
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.pump_log)
        self._timer.start(300)

        self._append_log("提示: 填写必要配置后点击“开始刷课”。日志同时写入 "
                         f"{os.path.join(paths.runtime_root(), 'logs')}\n")

    def _append_log(self, text: str):
        self.log_view.appendPlainText(text)

    def pump_log(self):
        try:
            while True:
                item = self._log_queue.get_nowait()
                if item == GUI_DONE:
                    self.on_shuake_done()
                elif item.startswith("[AI] MODELS|"):
                    payload = item[len("[AI] MODELS|"):]
                    ok_flag, _, rest = payload.partition("|")
                    ids = rest.split(";") if (ok_flag == "OK" and rest) else []
                    self._on_ai_models(ids)
                    self._append_log(
                        ("[AI] 拉到 %d 个模型\n" % len(ids)) if ok_flag == "OK"
                        else "[AI] 拉取失败: %s\n" % rest)
                elif item.startswith("[AI] TEST|"):
                    ok_flag, _, rest = item[len("[AI] TEST|"):].partition("|")
                    self._append_log(("[AI] 连通性测试: %s\n" % rest)
                                     if ok_flag == "OK" else
                                     "[AI] 连通性测试失败: %s\n" % rest)
                else:
                    self._append_log(item)
        except queue.Empty:
            pass

    # ---------- AI 配置相关 ----------
    def _ai_save_settings(self):
        """把界面上 AI 设置写入 config.ini（供后台线程读取运行中生效）"""
        cfg = read_config()
        if "ai-option" not in cfg:
            cfg["ai-option"] = {}
        cfg["ai-option"]["api_url"] = self.ai_url_edit.text().strip()
        cfg["ai-option"]["api_key"] = self.ai_key_edit.text().strip()
        cfg["ai-option"]["ai_id"] = self.ai_model_combo.currentText().strip()
        cfg["ai-option"]["ai_answer_enabled"] = str(self.ai_auto_check.isChecked())
        try:
            write_config(cfg)
        except Exception as e:
            self._append_log("[AI] 写入配置失败: %s\n" % e)

    def on_ai_refresh(self, auto=False):
        """拉取该 API 下的所有模型 ID（用后台线程，不阻塞 Qt）"""
        import modules.ai_client as ai_client
        api_url = self.ai_url_edit.text().strip()
        api_key = self.ai_key_edit.text()
        if not api_url or not api_key:
            if not auto:
                QMessageBox.information(self, "AI 配置", "请先填写 API 地址与 API Key 再拉取。")
            return
        if not auto:
            self._ai_save_settings()
        self.ai_refresh_btn.setEnabled(False)
        self._append_log("[AI] 正在拉取模型列表...(auto=%s)\n" % auto)

        def worker():
            try:
                ids = ai_client.list_models(api_url, api_key)
                line = "[AI] MODELS|OK|%s" % ";".join(ids)
            except Exception as e:
                line = "[AI] MODELS|FAIL|%s" % e
            self._log_queue.put(line)

        threading.Thread(target=worker, daemon=True).start()

    def on_ai_test(self):
        """连通性测试：/models 探活 + 用当前 AI ID 发一条 ping"""
        import modules.ai_client as ai_client
        self._ai_save_settings()
        api_url, api_key = self.ai_url_edit.text().strip(), self.ai_key_edit.text()
        model = self.ai_model_combo.currentText().strip()
        self.ai_test_btn.setEnabled(False)
        self._append_log("[AI] 正在测试连通性...\n")

        def worker():
            try:
                ai_client.test_connection(api_url, api_key, model or None)
                line = "[AI] TEST|OK|通过（models 与 chat 均可达）"
            except Exception as e:
                line = "[AI] TEST|FAIL|%s" % e
            self._log_queue.put(line)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ai_models(self, ids):
        current = self.ai_model_combo.currentText().strip()
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(ids)
        if current:
            self.ai_model_combo.setCurrentText(current)
        elif ids:
            self.ai_model_combo.setCurrentText(ids[0])

    def on_open_config(self):
        """跨平台打开配置文件：Windows 用 os.startfile，Linux/macOS 用 xdg-open/open"""
        try:
            if os.name == "nt":
                os.startfile(CONFIG_FILE)  # Windows: 用默认应用打开
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", CONFIG_FILE])
            else:
                subprocess.Popen(["xdg-open", CONFIG_FILE])
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法打开配置文件:\n{CONFIG_FILE}\n{e}")

    def on_start(self):
        if self._running:
            self._append_log("[GUI] 刷课已在运行中, 请勿重复启动。\n")
            return
        url = self.course_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "缺少课程链接",
                                "请先填写课程链接(从智慧树课程页面复制)。\n"
                                "也可以点击“打开配置文件”在 configs.ini 中填写 URL1。")
            return
        try:
            limit = float(self.time_edit.text() or "0")
            speed = float(self.speed_edit.text() or "1.0")
            speed = min(max(speed, 0.5), 1.8)
        except ValueError:
            QMessageBox.warning(self, "格式错误", "时长限制与倍速必须填写数字。")
            return

        cfg = read_config()
        try:
            save_form_values(cfg, self.driver_combo.currentText(),
                             url, self.user_edit.text().strip(),
                             self.pass_edit.text(), str(limit), str(speed),
                             self.captcha_check.isChecked(),
                             self.hide_check.isChecked(),
                             self.mute_check.isChecked(),
                             self.ai_url_edit.text().strip(),
                             self.ai_key_edit.text(),
                             self.ai_model_combo.currentText().strip(),
                             self.ai_auto_check.isChecked(),
                             self.bg_keep_check.isChecked(),
                             self.auto_exam_check.isChecked(),
                             self.exam_submit_check.isChecked())
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入 config.ini 失败:\n{e}")
            return

        self._running = True
        self.start_btn.setEnabled(False)
        self._append_log(f"[{datetime.now():%H:%M:%S}] 配置已保存, 开始刷课...\n")
        threading.Thread(target=run_shuake,
                         args=(self._log_queue, self.on_shuake_done),
                         daemon=True).start()

    def on_shuake_done(self):
        self._running = False
        self.start_btn.setEnabled(True)

    # ---------- 自动做题 ----------
    def on_doexam(self):
        if self._exam_running:
            self._append_log("[做题] 已在做题中, 请勿重复启动。\n")
            return
        exam_url = self.exam_edit.text().strip()
        if "dohomework" not in exam_url:
            QMessageBox.warning(self, "缺少做题链接",
                                "请先粘贴作业/考试做题链接 (dohomework 链接)。")
            return
        # AI 配置即时保存到 config.ini (与课中题同源)
        self._ai_save_settings()
        # 浏览器驱动/账号也顺手保存
        try:
            cfg = read_config()
            save_form_values(cfg, self.driver_combo.currentText(),
                             self.course_edit.text().strip(),
                             self.user_edit.text().strip(),
                             self.pass_edit.text(), "0", "1.0",
                             self.captcha_check.isChecked(),
                             self.hide_check.isChecked(),
                             self.mute_check.isChecked(),
                             self.ai_url_edit.text().strip(),
                             self.ai_key_edit.text(),
                             self.ai_model_combo.currentText().strip(),
                             self.ai_auto_check.isChecked(),
                             self.bg_keep_check.isChecked(),
                             self.auto_exam_check.isChecked(),
                             self.exam_submit_check.isChecked())
        except Exception:
            pass

        import modules.ai_client as _ai
        ai_cfg = _ai.load_ai_config()
        if not _ai.is_configured(ai_cfg):
            QMessageBox.warning(self, "AI 配置缺失",
                                "请先填写 API 地址 / API Key / AI ID (与课中题同一份配置)。")
            return
        engine = self.driver_combo.currentText()
        submit_btn = self.exam_submit_check.isChecked()

        self._exam_running = True
        self.doexam_btn.setEnabled(False)
        self._append_log(f"[{datetime.now():%H:%M:%S}] 开始自动做题...\n")
        threading.Thread(
            target=run_doexam,
            args=(self._log_queue, self.on_doexam_done, exam_url,
                  engine, submit_btn),
            daemon=True).start()

    def on_doexam_done(self):
        self._exam_running = False
        self.doexam_btn.setEnabled(True)

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()


def main():
    ensure_config_file()
    app = QApplication(sys.argv)
    app.setApplicationName("Autovisor")
    try:
        icon_path = paths.resource_path("res", "zhs.ico")
        if os.path.exists(icon_path):
            from PySide6.QtGui import QIcon
            app.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()