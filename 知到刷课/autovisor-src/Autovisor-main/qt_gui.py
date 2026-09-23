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


def read_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    try:
        cfg.read(CONFIG_FILE, encoding="utf-8")
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
    )


def save_form_values(cfg: configparser.ConfigParser, driver, course_url, username, password,
                     limit_time, speed, auto_captcha, hide_window, mute,
                     ai_url="", ai_key="", ai_model="", ai_enable=True) -> None:
    cfg.set("browser-option", "driver", driver)
    cfg.set("course-url", "URL1", course_url)
    cfg.set("user-account", "username", username)
    cfg.set("user-account", "password", password)
    cfg.set("course-option", "limitMaxTime", limit_time)
    cfg.set("course-option", "limitSpeed", speed)
    cfg.set("script-option", "enableAutoCaptcha", str(auto_captcha))
    cfg.set("script-option", "enableHideWindow", str(hide_window))
    cfg.set("course-option", "soundOff", str(mute))
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
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = QueueWriter(log_queue)
    sys.stderr = QueueWriter(log_queue)
    try:
        Autovisor.cli()
    except Exception as e:  # 兜底, 避免线程静默死亡
        log_queue.put(f"[GUI] 刷课线程异常: {e}\n")
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        # 结束回调经队列带回主线程处理（QTimer 轮询 pump_log）,
        # 工作线程直接操作 QWidget/QTimer 违反 Qt 线程规则
        log_queue.put(GUI_DONE)


# ==== 主窗口 ====
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autovisor - 智慧树刷课助手")
        self.setMinimumSize(600, 520)
        self._running = False
        self._log_queue = queue.Queue()

        # 顶部标题
        title = QLabel("Autovisor 智慧树刷课助手")
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
        check_row = QHBoxLayout()
        check_row.addWidget(self.captcha_check)
        check_row.addWidget(self.hide_check)
        check_row.addWidget(self.mute_check)
        check_row.addStretch(1)
        form.addRow(check_row)

        # 按钮
        self.start_btn = QPushButton("开始刷课")
        self.start_btn.setMinimumHeight(34)
        open_btn = QPushButton("打开配置文件")
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(open_btn)

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
         ai_url, ai_key, ai_model, ai_on) = load_form_values(config)
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
        self.ai_url_edit.setText(ai_url)
        self.ai_key_edit.setText(ai_key)
        self.ai_model_combo.setCurrentText(ai_model)
        self.ai_auto_check.setChecked(ai_on)

        self.start_btn.clicked.connect(self.on_start)
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
                             self.ai_auto_check.isChecked())
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

    def closeEvent(self, event):
        self._timer.stop()
        event.accept()


def main():
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