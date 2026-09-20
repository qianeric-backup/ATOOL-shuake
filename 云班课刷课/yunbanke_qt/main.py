# -*- coding: utf-8 -*-
"""
云班课刷课助手 - Qt 简化 UI
============================
登录 -> 课程列表 -> 资源列表 -> 一键刷课（视频学习进度上报）

依赖: PySide6 + requests
运行: python main.py
"""
import os
import sys
import threading
import traceback

from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QPushButton, QLabel, QListWidget,
    QListWidgetItem, QStackedWidget, QProgressBar,
    QCheckBox, QSplitter, QFrame,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from api import Yunbanke, YunbankeError, res_type_name, is_video


def _ui_font_family():
    """跨平台界面字体：Windows 用微软雅黑，Linux/macOS 用系统默认无衬线字体。"""
    if sys.platform.startswith('win'):
        return 'Microsoft YaHei'
    if sys.platform.startswith('darwin'):
        return 'PingFang SC'
    # Linux / 其他：优先中文无衬线字体，其次通用 sans
    families = QFontDatabase.families() or []
    for family in ('Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'Noto Sans',
                   'Sans Serif'):
        if family in families:
            return family
    return 'Sans Serif'


# ---------------------------------------------------------------
# 工作线程桥接：threading.Thread + QObject 信号
#   Python 线程里直接 emit Qt 信号，PySide 自动按队列投递到主线程，
#   不依赖 QThread/moveToThread，最稳妥。
# ---------------------------------------------------------------
_worker_bridges = []


class _Bridge(QObject):
    finished = Signal()


def run_in_thread(fn):
    """在独立线程执行 fn；线程结束后发 finished 信号（连接方负责刷新 UI）。"""
    bridge = _Bridge()
    _worker_bridges.append(bridge)

    def wrapper():
        try:
            fn()
        except Exception:
            traceback.print_exc()
        finally:
            bridge.finished.emit()

    th = threading.Thread(target=wrapper, daemon=True)
    th.start()
    return bridge


def _release_bridge(bridge):
    try:
        _worker_bridges.remove(bridge)
    except ValueError:
        pass
    bridge.deleteLater()


# ---------------------------------------------------------------
# 登录页
# ---------------------------------------------------------------
class LoginPage(QWidget):
    login_ok = Signal(dict)     # 登录成功
    login_fail = Signal(str)    # 登录失败

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        title = QLabel("云班课刷课助手")
        title.setFont(QFont(_ui_font_family(), 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        form = QFormLayout()
        self.edt_account = QLineEdit()
        self.edt_account.setPlaceholderText("手机号")
        self.edt_pwd = QLineEdit()
        self.edt_pwd.setPlaceholderText("密码")
        self.edt_pwd.setEchoMode(QLineEdit.Password)
        form.addRow("账号", self.edt_account)
        form.addRow("密码", self.edt_pwd)
        lay.addLayout(form)

        self.btn_login = QPushButton("登 录")
        lay.addWidget(self.btn_login)

        self.lbl_msg = QLabel("")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        self.lbl_msg.setStyleSheet("color:#e53935;")
        lay.addWidget(self.lbl_msg)
        lay.addStretch(1)

        self.btn_login.clicked.connect(self.do_login)
        self.login_fail.connect(self._on_login_fail)

        # 预填上次账号密码
        cfg = self._load_cfg()
        if cfg.get("account"):
            self.edt_account.setText(cfg["account"])
        if cfg.get("password"):
            self.edt_pwd.setText(cfg["password"])

    @staticmethod
    def _cfg_path():
        # PyInstaller --onefile 打包后 __file__ 在临时解压目录，程序退出即删，
        # 配置会丢失；frozen 时改用 exe 所在目录
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "config.ini")

    def _load_cfg(self):
        cfg = {}
        try:
            with open(self._cfg_path(), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k] = v
        except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError):
            pass
        return cfg

    def do_login(self):
        account = self.edt_account.text().strip()
        pwd = self.edt_pwd.text()
        if not account or not pwd:
            self.lbl_msg.setText("请输入账号和密码")
            return
        self.btn_login.setEnabled(False)
        self.lbl_msg.setText("正在登录...")

        def worker():
            try:
                y = Yunbanke(account, pwd)
                user = y.login()
                # 保存配置
                try:
                    with open(self._cfg_path(), "w", encoding="utf-8") as f:
                        f.write("account=%s\npassword=%s\n" % (account, pwd))
                except OSError:
                    pass
                self.login_ok.emit({"y": y, "user": user})
            except Exception as e:
                self.login_fail.emit(str(e))

        bridge = run_in_thread(worker)
        bridge.finished.connect(lambda: _release_bridge(bridge))

    def _on_login_fail(self, msg):
        self.lbl_msg.setText(msg)
        self.btn_login.setEnabled(True)


# ---------------------------------------------------------------
# 主页：课程 + 资源 + 刷课
# ---------------------------------------------------------------
class MainPage(QWidget):
    status = Signal(str)                 # 状态栏文字
    courses_loaded = Signal(list)
    resources_loaded = Signal(list)
    logout_requested = Signal()          # 请求退出登录
    # 进度条必须经信号投递回 GUI 线程：刷课跑在 threading.Thread 里，
    # 直接调用 QProgressBar 方法违反 Qt 线程规则（随机崩溃/未知行为）
    progress_shown = Signal(bool)
    progress_max = Signal(int)
    progress_val = Signal(int)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.y: Yunbanke = data["y"]
        self.user = data["user"]
        self.courses = []
        self.resources = []
        self._stop = False
        self._busy = False

        lay = QVBoxLayout(self)

        # 顶部：用户信息 + 刷新/退出
        top = QHBoxLayout()
        nick = self.user.get("nickName") or self.user.get("fullName") or ""
        self.lbl_user = QLabel("用户: %s" % nick)
        top.addWidget(self.lbl_user)
        top.addStretch(1)
        self.btn_refresh = QPushButton("刷新课程")
        top.addWidget(self.btn_refresh)
        self.btn_back = QPushButton("退出登录")
        top.addWidget(self.btn_back)
        lay.addLayout(top)

        # 中部：左课程 / 右资源
        split = QSplitter(Qt.Horizontal)
        self.lst_courses = QListWidget()
        self.lst_resources = QListWidget()
        split.addWidget(self._make_panel("班课列表", self.lst_courses))
        split.addWidget(self._make_panel("学习资源", self.lst_resources))
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

        # 底部：刷课控制
        bottom = QHBoxLayout()
        self.chk_video = QCheckBox("仅刷视频")
        self.chk_video.setChecked(True)
        bottom.addWidget(self.chk_video)
        self.btn_load_res = QPushButton("加载该课资源")
        bottom.addWidget(self.btn_load_res)
        self.btn_brush = QPushButton("一键刷课(当前班课)")
        self.btn_brush.setStyleSheet(
            "background:#43a047;color:white;font-weight:bold;padding:6px;")
        bottom.addWidget(self.btn_brush)
        self.btn_brush_all = QPushButton("刷全部课程")
        bottom.addWidget(self.btn_brush_all)
        lay.addLayout(bottom)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        self.lbl_status = QLabel("准备就绪")
        lay.addWidget(self.lbl_status)

        # 信号
        self.btn_refresh.clicked.connect(self.load_courses)
        self.btn_back.clicked.connect(self.logout_requested)
        self.btn_load_res.clicked.connect(self.load_resources)
        self.btn_brush.clicked.connect(self.brush_current)
        self.btn_brush_all.clicked.connect(self.brush_all)
        self.lst_courses.itemClicked.connect(lambda _it: self.load_resources())
        self.status.connect(self.lbl_status.setText)
        self.courses_loaded.connect(self._fill_courses)
        self.resources_loaded.connect(self._fill_resources)
        self.progress_shown.connect(self.progress.setVisible)
        self.progress_max.connect(self.progress.setMaximum)
        self.progress_val.connect(self.progress.setValue)

        self.load_courses()

    @staticmethod
    def _make_panel(title, widget):
        frame = QFrame()
        v = QVBoxLayout(frame)
        v.addWidget(QLabel(title))
        v.addWidget(widget)
        return frame

    # ---------- 数据加载 ----------
    def _set_busy(self, busy):
        """并发抑制：所有走后台线程的入口共用 _busy 标记并禁用相关按钮，
        防止多个线程共用非线程安全的 requests.Session / 结果乱序。"""
        self._busy = busy
        for w in (self.btn_refresh, self.btn_load_res, self.btn_brush,
                  self.btn_brush_all):
            w.setEnabled(not busy)

    def load_courses(self):
        if self._busy:
            self.status.emit("有任务进行中，请稍候...")
            return
        self._set_busy(True)
        self.status.emit("正在加载课程...")
        self.lst_courses.clear()

        def fn():
            try:
                self.courses = self.y.list_courses()
                self.courses_loaded.emit(self.courses)
                self.status.emit("课程加载完成（%d 门）" % len(self.courses))
                if not self.courses:
                    self.status.emit(
                        "当前账号未加入任何班课（课程显示为空，可能账号未加入班级或被移出）")
            except Exception as e:
                traceback.print_exc()
                self.status.emit("加载课程失败: %s" % e)

        bridge = run_in_thread(fn)
        bridge.finished.connect(lambda: self._task_done(bridge))

    def _task_done(self, bridge):
        """后台任务结束（含异常路径）统一恢复界面状态。"""
        self._set_busy(False)
        _release_bridge(bridge)

    def _fill_courses(self, courses):
        self.lst_courses.clear()
        for c in courses:
            name = (c.get("clazzCourseName") or c.get("name") or c.get("title")
                    or "未命名")
            cc_id = c.get("id") or c.get("ccId") or c.get("clazzCourseId") or ""
            item = QListWidgetItem("%s  (%s)" % (name, cc_id))
            item.setData(Qt.UserRole, c)
            self.lst_courses.addItem(item)
        if courses:
            self.lst_courses.setCurrentRow(0)

    def load_resources(self):
        if self._busy:
            self.status.emit("有任务进行中，请稍候...")
            return
        item = self.lst_courses.currentItem()
        if not item:
            self.status.emit("请先选择一门班课")
            return
        self._set_busy(True)
        cc = item.data(Qt.UserRole)
        cc_id = cc.get("id") or cc.get("ccId") or cc.get("clazzCourseId")
        self.status.emit("正在加载资源...")
        self.lst_resources.clear()

        def fn():
            try:
                res = self.y.list_resources(cc_id)
                self.resources = res if isinstance(res, list) else []
                self.resources_loaded.emit(self.resources)
                self.status.emit("资源加载完成（%d 项）" % len(self.resources))
            except Exception as e:
                traceback.print_exc()
                self.status.emit("加载资源失败: %s" % e)

        bridge = run_in_thread(fn)
        bridge.finished.connect(lambda: self._task_done(bridge))

    def _fill_resources(self, resources):
        self.lst_resources.clear()
        for r in resources:
            name = (r.get("resName") or r.get("name") or r.get("fileName")
                    or r.get("title") or "未命名")
            t = res_type_name(r)
            dur = r.get("duration") or r.get("videoDuration") or ""
            line = "%s  [%s]  %s" % (name, t, dur if dur else "")
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, r)
            self.lst_resources.addItem(item)

    # ---------- 刷课 ----------
    def brush_current(self):
        if self._busy:
            self.status.emit("有任务进行中，请稍候...")
            return
        item = self.lst_courses.currentItem()
        if not item:
            self.status.emit("请先选择班课")
            return
        self._set_busy(True)
        self._stop = False     # 新任务开始：清掉上次手动停止的标记
        cc = item.data(Qt.UserRole)
        cc_id = cc.get("id") or cc.get("ccId") or cc.get("clazzCourseId")
        bridge = run_in_thread(
            lambda: self._brush_cc(cc_id, only_video=self.chk_video.isChecked()))
        bridge.finished.connect(lambda: self._task_done(bridge))

    def brush_all(self):
        if not self.courses:
            self.status.emit("没有可刷的课程")
            return
        if self._busy:
            self.status.emit("有任务进行中，请稍候...")
            return
        self._set_busy(True)
        self._stop = False
        # 快照当前列表：后台遍历期间"刷新课程"重新赋值 self.courses
        # 会导致新旧列表交错
        snapshot = list(self.courses)
        bridge = run_in_thread(lambda: self._brush_all_fn(snapshot))
        bridge.finished.connect(lambda: self._task_done(bridge))

    def stop(self):
        """请求后台刷课尽快退出（退出登录 / 即将销毁页面时调用）。"""
        self._stop = True

    def _brush_all_fn(self, courses):
        total_video = 0
        total_done = 0
        for cc in courses:
            if self._stop:
                break
            cc_id = cc.get("id") or cc.get("ccId") or cc.get("clazzCourseId")
            n_video, n_done = self._brush_cc(cc_id, only_video=True)
            total_video += n_video
            total_done += n_done
        self.status.emit("全部完成：视频 %d 个，完成 %d 个" % (total_video, total_done))

    def _brush_cc(self, cc_id, only_video=True):
        """刷单个班课的视频资源。返回 (视频总数, 完成数)。"""
        try:
            res_list = self.y.list_resources(cc_id)
        except Exception as e:
            self.status.emit("获取 %s 资源失败: %s" % (cc_id, e))
            return 0, 0
        if not isinstance(res_list, list):
            return 0, 0

        videos = [r for r in res_list if (not only_video or is_video(r))]
        n = len(videos)
        self.status.emit("开始刷课：%s 共 %d 个视频" % (cc_id, n))
        self.progress_shown.emit(True)
        self.progress_max.emit(max(1, n))
        self.progress_val.emit(0)
        done = 0
        i = 0
        for r in videos:
            if self._stop:
                break
            i += 1
            rid = r.get("id") or r.get("resId") or r.get("resOid") or ""
            duration = r.get("duration") or r.get("videoDuration") or 0
            name = r.get("resName") or r.get("name") or "视频"
            if not rid:
                # 空的 resId 会拼出畸形 URL（404/错路径），跳过而不是浪费整轮
                self.status.emit("跳过（无资源ID）: %s" % name)
                self.progress_val.emit(i)
                continue
            try:
                if not duration:
                    # 时长未知：先查观看记录/预览，取服务端时长
                    for getter in (self.y.get_video_records, self.y.get_viewer_url):
                        try:
                            rec = getter(cc_id, rid)
                            cand = (rec.get("duration")
                                    or (rec.get("data") or {}).get("duration") or 0)
                            if cand:
                                duration = cand
                                break
                        except Exception:
                            continue
                if not duration:
                    self.status.emit("跳过（无时长信息）: %s" % name)
                    self.progress_val.emit(i)
                    continue
                # 直接把观看位置拉到尽头 -> 服务端判定完成
                res = self.y.report_video_progress(
                    cc_id, rid, watch_to=duration, current_watch_to=duration,
                    duration=duration)
                if res.get("status") is False:
                    self.status.emit("上报被拒绝 %s: %s"
                                     % (name, res.get("errorMessage")))
                else:
                    done += 1
                    self.status.emit("已完成 %d/%d : %s" % (i, n, name))
            except Exception as e:
                self.status.emit("刷课失败 %s: %s" % (name, e))
            self.progress_val.emit(i)
        self.progress_shown.emit(False)
        return n, done


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("云班课刷课助手")
        self.resize(780, 540)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._dying_pages = []   # 已退出登录、等待后台线程结束后销毁的旧主页
        self.login_page = LoginPage()
        self.login_page.login_ok.connect(self.on_login_ok)
        self.stack.addWidget(self.login_page)

    def on_login_ok(self, data):
        self.login_page.btn_login.setEnabled(True)
        main_page = MainPage(data)
        main_page.logout_requested.connect(self.go_login)
        self.stack.addWidget(main_page)
        self.stack.setCurrentWidget(main_page)

    def go_login(self):
        # 回到登录页并清掉旧主页
        while self.stack.count() > 1:
            w = self.stack.widget(1)
            if hasattr(w, "stop"):
                w.stop()   # 通知后台刷课线程尽快退出，避免对已销毁对象 emit
            self.stack.removeWidget(w)
            # 线程可能仍卡在一次网络请求上（最长 20s 超时），
            # 立即 deleteLater 会造成 "Internal C++ object already deleted"
            self._dying_pages.append(w)
            QTimer.singleShot(30000, w.deleteLater)
            QTimer.singleShot(31000, lambda ww=w: self._dying_pages.remove(ww)
                              if ww in self._dying_pages else None)
        self.stack.setCurrentWidget(self.login_page)
        self.login_page.btn_login.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()