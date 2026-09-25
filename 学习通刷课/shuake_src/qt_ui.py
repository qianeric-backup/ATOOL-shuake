# -*- coding: utf-8 -*-
"""
qt_ui.py — PySide6（Qt）版图形界面，功能与 native_tk 版 start.py 完全一致：
主页 / 设置 / 帮助 / 刷课日志 / 测试成绩 / 题库查询 / 报错日志 / 定时刷课 /
窗口置顶 / 字体调整 / 子进程运行 main.py 并实时显示日志。

与旧版差异：
  * 界面框架换为 Qt（原生外观），不再依赖 tkinter / customtkinter。
  * 配置文件（task/tool/account_info.json 等）读写格式与原版完全兼容。
  * 数据文件路径不变（task/record、task/tool 等均在 exe 同目录）。

入口：
  python qt_ui.py           直接运行
  launcher.py --worker      打包态子进程刷课入口
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QCheckBox, QRadioButton, QGridLayout,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QDialog,
    QTreeWidget, QTreeWidgetItem, QStackedWidget,
)

# 资源根目录：优先当前工作目录（打包态 launcher 已 chdir 到 exe 同目录；
# 源码态通常 cwd=shuake_src），若 cwd 下无 task 则回退脚本所在目录。
_APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _path(*parts):
    """取项目内资源路径（兼容源码/打包两种形态，优先 cwd）"""
    if os.path.isdir(os.path.join(os.getcwd(), 'task')):
        return os.path.join(os.getcwd(), *parts)
    return os.path.join(_APP_DIR, *parts)


# ---------------------------------------------------------------- 常量 ----
ACCOUNT_FILE = _path('task', 'tool', 'account_info.json')
COURSE_FILE = _path('task', 'tool', 'course_name.json')
HELP_FILE = _path('task', 'tool', 'Help.txt')
ERROR_LOG = _path('error.log')
VERSION_FILE = _path('task', 'tool', 'version_info')

# 配色方案（与原版 color_value_dict 一致）
# 每个方案为 [按钮/文字色(primary), 页面背景(light), 悬停/次要背景(mid)]
COLOR_SCHEMES = {
    '黑白': ['#FFFFFF', '#FFFFFF', '#E5E7EB'],
    '清新绿': ['#2E7D32', '#E8F5E9', '#A5D6A7'],
    '暖阳橙': ['#F57C00', '#FFF3E0', '#FFB74D'],
    '淡雅灰': ['#607D8B', '#ECEFF1', '#B0BEC5'],
    '天空湖': ['#00838F', '#E0F7FA', '#80DEEA'],
    '深邃夜': ['#2C3E50', '#ECF0F1', '#BDC3C7'],
    '紫罗兰': ['#6A1B9A', '#F3E5F5', '#CE93D8'],
    # 暗黑模式：primary 为亮文字色, light 为深背景, mid 为悬停背景
    '暗黑': ['#E5E7EB', '#111827', '#374151'],
}
DEFAULT_FONT = 'Microsoft YaHei'

AFTER_FINISH_OPTIONS = ['仅自动保存', '强制自动提交', '搜到60%的题自动提交',
                        '搜到70%的题自动提交', '搜到80%的题自动提交',
                        '搜到90%的题自动提交', '搜到100%的题自动提交']

# AI 答题选项名（界面显示）与旧版配置文件里的兼容名
AI_OPTION = 'AI 智能答题'
LEGACY_AI_OPTION = 'DeepSeek AI'


def load_account():
    try:
        with open(ACCOUNT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_account(data):
    with open(ACCOUNT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_course_names():
    try:
        with open(COURSE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------- 定时对话框 ----
class TimerDialog(QDialog):
    """定时刷课设置窗口"""

    def __init__(self, parent, start_time, end_time, font):
        super().__init__(parent)
        self.setWindowTitle('⏰ 定时刷课设置')
        self.setFixedSize(360, 200)
        self.setModal(True)
        self.start_time = start_time
        self.end_time = end_time
        self.result_action = None  # 'enable' / 'disable'

        layout = QGridLayout(self)
        layout.addWidget(QLabel('开始时间 (HH:MM:SS):'), 0, 0)
        self.start_entry = QLineEdit(start_time)
        self.start_entry.setFixedWidth(120)
        layout.addWidget(self.start_entry, 0, 1)

        layout.addWidget(QLabel('结束时间 (HH:MM:SS):'), 1, 0)
        self.end_entry = QLineEdit(end_time)
        self.end_entry.setFixedWidth(120)
        layout.addWidget(self.end_entry, 1, 1)

        row = QHBoxLayout()
        enable_btn = QPushButton('开启定时')
        enable_btn.clicked.connect(self.on_enable)
        disable_btn = QPushButton('禁用定时')
        disable_btn.clicked.connect(self.on_disable)
        row.addWidget(enable_btn)
        row.addWidget(disable_btn)
        layout.addLayout(row, 2, 0, 1, 2)
        self.setFont(font)

    @staticmethod
    def _valid(t):
        return bool(re.match(r'^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$', t))

    def on_enable(self):
        s, e = self.start_entry.text().strip(), self.end_entry.text().strip()
        if not self._valid(s):
            QMessageBox.warning(self, '错误', '开始时间格式不正确，请输入 HH:MM:SS 格式')
            return
        if not self._valid(e):
            QMessageBox.warning(self, '错误', '结束时间格式不正确，请输入 HH:MM:SS 格式')
            return
        if s == e:
            QMessageBox.warning(self, '错误', '结束时间不能与开始时间相同')
            return
        self.start_time, self.end_time = s, e
        self.result_action = 'enable'
        self.accept()

    def on_disable(self):
        self.result_action = 'disable'
        self.accept()


# ---------------------------------------------------------------- 主窗口 ----
class StartWindow(QMainWindow):
    # 自动下载浏览器驱动（按钮 → 后台线程 Selenium Manager 下载/匹配）
    driver_downloaded = Signal(str, str)     # (driver_path, error_msg)
    """学习通刷课 主窗口（PySide6 版）"""
    # 模型列表拉取完成信号（跨线程安全）
    models_fetched = Signal(list, str)  # (model_ids, error_msg)
    # 课程列表拉取完成信号（跨线程安全）
    courses_fetched = Signal(list, str)  # (course_names, error_msg)
    api_tested = Signal(str, str)        # (result_msg, kind)  测试连接结果
    log_signal = Signal(str)             # 跨线程安全写日志（刷课子进程线程 → UI）
    program_finished = Signal()          # 刷课子进程结束（线程 → UI 恢复按钮）

    def __init__(self):
        super().__init__()
        self.timer_active = False
        self.timer_start_time = '04:00:00'
        self.timer_end_time = '03:00:00'
        self.process = None
        self.process_condition = False
        self.is_topmost = True
        self.dynamic_rows = []      # [(combo, del_btn, row)]
        self.next_row = 4           # 第二门课程起始行（与原版一致）
        self._models_cache = {}     # {api_url: [model_ids]} 缓存上次成功结果
        self._chapter_answer_choice = AI_OPTION   # 章节模式下的答题方式（切换模式时保留）
        self._homework_answer_choice = AI_OPTION  # 作业模式下的答题方式
        self.all_courses = []
        self.data = []
        self.account_info = {}
        self._current_mode = 1
        self.pady = 7
        self._suppress_signals = False

        # 主题配色（默认“黑白”亮色，可在界面设置切换“暗黑”）
        self.record_color = '黑白'
        self.frame_bg, self.button_bg, self.hover_bg = COLOR_SCHEMES[self.record_color]
        self.dark_mode = (self.record_color == '暗黑')
        self.font_family = DEFAULT_FONT
        self.font_size = 13
        self.font = QFont(self.font_family, self.font_size)

        self._load_version()
        self._setup_window()
        self._build_layout()
        # 主题下拉框默认值（无保存配置时也保证非空；有配置将由 load_data 覆盖）
        if hasattr(self, 'theme_entry'):
            self.theme_entry.setCurrentText('明亮')
        self._apply_styles()
        self._reload_advanced()     # 按默认模式设置高级控件显隐
        self.load_data()            # 读取保存的配置
        self._setup_io_menu()       # 顶部菜单：导入导出（配置/题库备份）
        self.update_time()
        self.show_main()

    # ------------------------------------------------------------------ 导入导出
    def _setup_io_menu(self):
        """顶部菜单「导入导出」：备份/恢复配置与题库缓存"""
        menu = self.menuBar().addMenu('导入导出')
        for label, kind in (('导出全部（配置+题库）', 'all'),
                            ('仅导出配置', 'config'),
                            ('仅导出题库', 'bank')):
            act = menu.addAction(label)
            act.triggered.connect(lambda _checked=False, k=kind: self._export_data(k))
        menu.addSeparator()
        act = menu.addAction('导入（自动识别类型）')
        act.triggered.connect(self._import_data)

    def _export_data(self, kind):
        from task.tool import config_io
        default_name = 'xuexitong-backup-' + time.strftime('%Y%m%d-%H%M%S') + '.json'
        path, _ = QFileDialog.getSaveFileName(self, '导出备份', default_name,
                                              '备份文件 (*.json)')
        if not path:
            return
        builders = {'all': config_io.export_all,
                    'config': config_io.export_config,
                    'bank': config_io.export_bank}
        try:
            payload = builders[kind]()
        except Exception as e:
            QMessageBox.critical(self, '导出失败', f'读取数据失败：{e}')
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, '导出失败', f'写入文件失败：{e}')
            return
        n_bank = len(payload.get('bank', {}))
        desc = {'config': '内容：仅配置（account_info.json）',
                'bank': f'内容：仅题库（{n_bank} 条缓存）',
                'all': f'内容：配置 + 题库（{n_bank} 条缓存）'}[kind]
        if kind != 'bank':
            desc += '\n⚠️ 配置含 API Key 与学习通账号信息，请妥善保管备份文件'
        QMessageBox.information(self, '导出完成', f'导出成功：{path}\n{desc}')

    def _import_data(self):
        from task.tool import config_io
        path, _ = QFileDialog.getOpenFileName(self, '导入备份', '',
                                              '备份文件 (*.json);;所有文件 (*)')
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, '导入失败', f'读取文件失败：{e}')
            return
        try:
            report = config_io.import_data(payload)
        except Exception as e:
            QMessageBox.critical(self, '导入失败', str(e))
            return
        if payload.get('kind') in ('config', 'all') and payload.get('config'):
            try:
                self.load_data()   # 刷新界面（含主题/各下拉框）
            except Exception:
                pass
        QMessageBox.information(self, '导入完成',
                                report + '\n\n如刷课任务正在运行，重启任务后生效')


    # ------------------------------------------------------------------ 窗口初始化
    def _load_version(self):
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                version = f.read().strip()
        except (FileNotFoundError, OSError):
            version = ''
        self.version = version

    def _setup_window(self):
        self.setWindowTitle(f'学习通刷课助手 {self.version}'.strip())
        self.resize(880, 660)
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move((geo.width() - self.width()) // 2,
                  (geo.height() - self.height()) // 2)
        try:
            icon = QIcon(_path('task', 'img', 'xuexitong1 .ico'))
            if not icon.isNull():
                self.setWindowIcon(icon)
        except Exception:
            pass
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_topmost)

    # ------------------------------------------------------------------ 界面搭建
    def _build_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_grid = QGridLayout(central)
        root_grid.setContentsMargins(0, 0, 0, 0)
        root_grid.setSpacing(0)

        # 左侧导航栏
        nav_frame = QFrame(central)
        nav_frame.setObjectName('navFrame')
        nav_frame.setFixedWidth(170)
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 16, 8, 8)
        nav_layout.setSpacing(6)

        self.nav_title = QLabel('  MENU  ')
        self.nav_title.setObjectName('navTitle')
        nav_layout.addWidget(self.nav_title)
        self._refresh_nav_title()

        self.nav_buttons = {}
        nav_defs = [
            ('主页', self.show_main),
            ('设置', self.show_set),
            ('帮助', self.show_help),
            ('刷课日志', lambda: self.show_record('刷课')),
            ('测试成绩', lambda: self.show_record('成绩')),
            ('题库查询', self.show_question_bank),
            ('报错日志', self.show_error),
        ]
        for text, handler in nav_defs:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(handler)
            self._nav_style(btn)
            self.nav_buttons[text] = btn
            nav_layout.addWidget(btn)
        nav_layout.addStretch(1)
        root_grid.addWidget(nav_frame, 0, 0, 2, 1)

        # 右侧主区域
        content = QFrame(central)
        content_grid = QGridLayout(content)
        content_grid.setContentsMargins(12, 8, 12, 8)
        content_grid.setSpacing(8)

        self.time_label = QLabel('')
        self.time_label.setStyleSheet('font-size: 13px;')
        content_grid.addWidget(self.time_label, 0, 0, 1, 3, Qt.AlignmentFlag.AlignLeft)

        # ---- 各页面 frame 全部提前创建 ----
        self.main_frame = QWidget()
        self.set_frame = QWidget()
        self.help_frame = QWidget()
        self.vido_frame = QWidget()
        self.score_frame = QWidget()
        self.question_bank_frame = QWidget()
        self.error_frame = QWidget()

        self.pages = {
            '主页': self.main_frame,
            '设置': self.set_frame,
            '帮助': self.help_frame,
            '刷课日志': self.vido_frame,
            '测试成绩': self.score_frame,
            '题库查询': self.question_bank_frame,
            '报错日志': self.error_frame,
        }

        self._build_main()
        self._build_set()
        self._build_help()
        self._build_vido()
        self._build_score()
        self._build_question_bank()
        self._build_error()

        self._current_page = None
        for page in self.pages.values():
            content_grid.addWidget(page, 1, 0, 1, 3)
            page.hide()
        root_grid.addWidget(content, 0, 1, 2, 1)
        root_grid.setColumnStretch(1, 1)
        root_grid.setRowStretch(1, 1)

    def _nav_style(self, btn):
        dark_mode = self.dark_mode
        white_mode = self.record_color == '黑白'
        # 白底模式导航文字为黑色，选中态浅灰底黑字（保持白底黑字整体风格）
        # 暗黑模式导航文字为亮灰，选中态深灰底亮字
        if dark_mode:
            text_color = '#D1D5DB'
            hover_bg = '#1F2937'
            sel_bg = '#374151'
            sel_text = '#F3F4F6'
        else:
            text_color = '#111827' if white_mode else self.button_bg
            hover_bg = '#E5E7EB' if white_mode else self.hover_bg
            sel_bg = '#E5E7EB' if white_mode else self.button_bg
            sel_text = '#111827'
        btn.setStyleSheet(
            'QPushButton { text-align: left; padding: 8px 10px; border: none; '
            'border-radius: 6px; color: %s; background: transparent; font-size: 13px; }'
            'QPushButton:hover { background: %s; }'
            'QPushButton:checked { background: %s; color: %s; }'
            % (text_color, hover_bg, sel_bg, sel_text))

    # ---------------------------------------------------------------- 主页
    def _build_main(self):
        grid = QGridLayout(self.main_frame)
        grid.setSpacing(10)

        self.start_button = QPushButton('▶ 开始刷课')
        self.start_button.setMinimumHeight(40)
        self.start_button.clicked.connect(self.start)
        grid.addWidget(self.start_button, 0, 0)

        self.timer_button = QPushButton('⏰ 定时刷课')
        self.timer_button.setMinimumHeight(40)
        self.timer_button.clicked.connect(self.open_timer_window)
        grid.addWidget(self.timer_button, 0, 1)

        self.close_button = QPushButton('■ 结束刷课')
        self.close_button.setMinimumHeight(40)
        self.close_button.clicked.connect(self.close_program)
        self.close_button.hide()
        grid.addWidget(self.close_button, 0, 2)

        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)
        self.text_box.append('WELCOME TO 学习通刷课助手 ！！！\n请先进入设置页面填写信息！！！')
        grid.addWidget(self.text_box, 1, 0, 1, 3)

    # ---------------------------------------------------------------- 设置页
    def _form_label(self, text, order=None, gl=None):
        """表单标签：右对齐 + 固定宽度（保证所有输入框左边缘对齐）"""
        label = QLabel(text)
        label.setFixedWidth(96)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if gl is not None:
            gl.addWidget(label, order, 0, Qt.AlignmentFlag.AlignLeft)
        return label

    def _input_widget(self, widget, fixed_width=240):
        """给 QLineEdit/QComboBox 设置统一的输入框宽度"""
        widget.setFixedWidth(fixed_width)
        return widget

    def _build_set(self):
        """设置页：左侧二级列表（QTreeWidget）+ 右侧分组面板（QStackedWidget）"""
        grid = QGridLayout(self.set_frame)
        grid.setSpacing(8)
        grid.setContentsMargins(8, 8, 8, 8)

        # ---- 左侧二级目录 ----
        self.set_tree = QTreeWidget()
        self.set_tree.setHeaderHidden(True)
        self.set_tree.setFixedWidth(170)
        self.set_tree.setStyleSheet(
            'QTreeWidget { background: %s; border: 1px solid %s;'
            ' border-radius: 8px; font-size: 13px; }'
            'QTreeWidget::item { padding: 6px 4px; }'
            'QTreeWidget::item:selected { background: %s; color: %s; }'
            'QTreeWidget::item:hover { background: %s; }'
            % (self._input_bg(), self._border_color(), self._sel_bg(),
               self._sel_text(), self._hover_bg()))
        root_item = QTreeWidgetItem(['⚙ 设置'])
        root_item.setExpanded(True)
        root_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        self.set_tree.addTopLevelItem(root_item)
        self.set_group_pages = {}
        groups = ['配置设置', '界面设置', '账号信息', '功能设置', '高级设置']
        for g in groups:
            child = QTreeWidgetItem([g])
            root_item.addChild(child)
            page = QWidget()
            page_gl = QGridLayout(page)
            page_gl.setSpacing(10)
            page_gl.setContentsMargins(16, 16, 16, 16)
            self.set_group_pages[g] = (child, page, page_gl)

        # ---- 右侧堆栈 ----
        self.set_stack = QStackedWidget()
        for g in groups:
            self.set_stack.addWidget(self.set_group_pages[g][1])
        self.set_tree.currentItemChanged.connect(self._on_set_tree_change)

        grid.addWidget(self.set_tree, 0, 0, 3, 1)
        grid.addWidget(self.set_stack, 0, 1, 3, 1)
        # 保存按钮固定在底部
        self.save_button = QPushButton('💾 保存设置')
        self.save_button.setMinimumHeight(40)
        self.save_button.clicked.connect(self.save)
        grid.addWidget(self.save_button, 3, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(1, 1)

        # ---------- 配置设置 ----------
        gl = self.set_group_pages['配置设置'][2]
        gl.setColumnMinimumWidth(0, 96)
        gl.setColumnStretch(1, 1)
        self._form_label('浏览器:', 0, gl)
        self.browser_entry = QComboBox()
        self.browser_entry.addItems(['edge', 'chrome', 'firefox'])
        # 未加载配置前的平台默认（Windows→edge，Linux→firefox），并自动填默认驱动
        self.browser_entry.setCurrentText(self._default_browser())
        self.browser_entry.currentTextChanged.connect(self.auto_fill_browser_driver)
        gl.addWidget(self._input_widget(self.browser_entry), 0, 1, Qt.AlignmentFlag.AlignLeft)
        self._form_label('驱动地址:', 1, gl)
        self.browser_driver_entry = QLineEdit()
        self.browser_driver_entry.setPlaceholderText('请选择 driver 可执行文件')
        gl.addWidget(self._input_widget(self.browser_driver_entry), 1, 1, Qt.AlignmentFlag.AlignLeft)
        self.open_file_button = QPushButton('选择文件')
        self.open_file_button.clicked.connect(self.select_file)
        gl.addWidget(self.open_file_button, 1, 2, Qt.AlignmentFlag.AlignLeft)
        self.driver_auto_btn = QPushButton('自动下载驱动')
        self.driver_auto_btn.setToolTip(
            '联网自动匹配/下载当前浏览器驱动，并填入驱动地址\n'
            '(新版本驱动由 Selenium Manager 下载，与浏览器主版本自动对齐)')
        self.driver_auto_btn.clicked.connect(self.auto_download_driver)
        self.driver_downloaded.connect(self._on_driver_downloaded)
        gl.addWidget(self.driver_auto_btn, 1, 3, Qt.AlignmentFlag.AlignLeft)

    def auto_download_driver(self):
        """联网下载/匹配当前浏览器类型的驱动（Selenium Manager）。

        后台线程执行，成功后自动填充到 browser_driver_entry。
        下载/探测过程中禁用按钮，避免用户重复触发。"""
        browser = (self.browser_entry.currentText().strip().lower()
                   or 'edge')
        self.driver_auto_btn.setEnabled(False)
        self._append_log(f'正在联网下载/匹配 {browser} 驱动 ...\n')

        def worker():
            driver_path = ''
            err = ''
            try:
                from selenium.webdriver.common.selenium_manager import \
                    SeleniumManager
                result = SeleniumManager().binary_paths(
                    ['--browser', browser])
                driver_path = (result or {}).get('driver_path', '')
                if not driver_path or not os.path.isfile(driver_path):
                    err = f'Selenium Manager 返回无效路径: {driver_path!r}'
            except Exception as e:
                err = f'{e.__class__.__name__}: {e}'
            self.driver_downloaded.emit(driver_path, err)
        threading.Thread(target=worker, daemon=True).start()

    def _on_driver_downloaded(self, driver_path, err):
        self.driver_auto_btn.setEnabled(True)
        if err:
            self._append_log(f'自动下载驱动失败: {err}\n')
            self._append_log('请手动在驱动地址中选择文件，或设置到 PATH\n')
            return
        if driver_path:
            self.browser_driver_entry.setText(driver_path)
            self._append_log(f'驱动已就绪: {driver_path}\n')

        # ---------- 界面设置 ----------
        gl = self.set_group_pages['界面设置'][2]
        gl.setColumnMinimumWidth(0, 96)
        gl.setColumnStretch(1, 1)
        self._form_label('字体设置:', 0, gl)
        self.font_entry = QComboBox()
        self.font_entry.addItems(['Microsoft YaHei', 'Helvetica', '微软雅黑', '宋体', '楷体', '黑体'])
        self.font_entry.currentTextChanged.connect(self.change_font)
        gl.addWidget(self._input_widget(self.font_entry), 0, 1, Qt.AlignmentFlag.AlignLeft)
        self._form_label('大小设置:', 1, gl)
        self.size_entry = QComboBox()
        self.size_entry.addItems(['9', '10', '11', '12', '13', '14', '15', '16'])
        self.size_entry.currentTextChanged.connect(self.change_font)
        gl.addWidget(self._input_widget(self.size_entry), 1, 1, Qt.AlignmentFlag.AlignLeft)
        self._form_label('窗口置顶:', 2, gl)
        self.topmost_check = QCheckBox('')
        self.topmost_check.setChecked(True)
        self.topmost_check.toggled.connect(self.toggle_topmost)
        gl.addWidget(self.topmost_check, 2, 1, Qt.AlignmentFlag.AlignLeft)

        self._form_label('主题模式:', 3, gl)
        self.theme_entry = QComboBox()
        self.theme_entry.addItems(['明亮', '暗黑'])
        self.theme_entry.currentTextChanged.connect(self.apply_theme)
        gl.addWidget(self._input_widget(self.theme_entry), 3, 1, Qt.AlignmentFlag.AlignLeft)

        # ---------- 账号信息 ----------
        gl = self.set_group_pages['账号信息'][2]
        gl.setColumnMinimumWidth(0, 96)
        gl.setColumnStretch(1, 1)
        self._form_label('手机号:', 0, gl)
        self.phone_number_entry = QLineEdit()
        self.phone_number_entry.editingFinished.connect(self._reload_courses_by_phone)
        gl.addWidget(self._input_widget(self.phone_number_entry), 0, 1, Qt.AlignmentFlag.AlignLeft)
        self._form_label('密码:', 1, gl)
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        gl.addWidget(self._input_widget(self.password_entry), 1, 1, Qt.AlignmentFlag.AlignLeft)
        self.show_password_button = QPushButton('显示')
        self.show_password_button.setCheckable(True)
        self.show_password_button.toggled.connect(self.show_password)
        gl.addWidget(self.show_password_button, 1, 2, Qt.AlignmentFlag.AlignLeft)
        self._form_label('课程名称:', 2, gl)
        self.cour_entry = QComboBox()
        self.cour_entry.setEditable(True)
        gl.addWidget(self._input_widget(self.cour_entry), 2, 1, Qt.AlignmentFlag.AlignLeft)
        self.add_course_button = QPushButton('＋')
        self.add_course_button.setFixedWidth(30)
        self.add_course_button.clicked.connect(lambda: self.add_course(''))
        gl.addWidget(self.add_course_button, 2, 2, Qt.AlignmentFlag.AlignLeft)
        # 『拉取课程』按钮：登录学习通并自动获取首页课程列表
        self.fetch_course_button = QPushButton('📥 拉取课程')
        self.fetch_course_button.setFixedWidth(90)
        self.fetch_course_button.clicked.connect(self.fetch_courses)
        gl.addWidget(self.fetch_course_button, 2, 3, Qt.AlignmentFlag.AlignLeft)
        # 动态课程行：从第 3 行开始（原版从 4 开始，与固定行不冲突）
        self.next_row = 3
        # 兼容 add_course() 引用的 self.info_grid
        self.info_grid = gl

        # ---------- 功能设置 ----------
        gl = self.set_group_pages['功能设置'][2]
        self.radio_button_1 = QRadioButton('自动刷课答题')
        self.radio_button_1.setChecked(True)
        self.radio_button_1.toggled.connect(self.function_choice)
        self.radio_button_2 = QRadioButton('自动完成作业')
        self.radio_button_2.toggled.connect(self.function_choice)
        gl.addWidget(self.radio_button_1, 0, 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self.radio_button_2, 1, 0, Qt.AlignmentFlag.AlignLeft)
        # 考试入口已移至「作业模式 > 高级设置 > 任务类型（作业/考试）」，
        # 此处不再单列「自动完成考试」单选

        # ---------- 高级设置 ----------
        gl = self.set_group_pages['高级设置'][2]
        gl.setColumnMinimumWidth(0, 96)
        gl.setColumnStretch(1, 1)
        self._detail_row_next = 0

        def _row():
            r = self._detail_row_next
            self._detail_row_next += 1
            return r

        self.question_label = QLabel('章节测验:')
        self.question_entry = QComboBox()
        self.question_entry.addItems([AI_OPTION, '随机答题', '不刷题'])
        self.question_entry.currentTextChanged.connect(self.shua_ti_choice)
        gl.addWidget(self.question_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.question_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.after_finish_question = QLabel('答完题后:')
        self.after_finish_question_entry = QComboBox()
        self.after_finish_question_entry.addItems(AFTER_FINISH_OPTIONS)
        gl.addWidget(self.after_finish_question, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.after_finish_question_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.vido_question_label = QLabel('视频题目:')
        self.vido_question_entry = QComboBox()
        self.vido_question_entry.addItems([AI_OPTION, '随机答题'])
        self.vido_question_entry.currentTextChanged.connect(lambda _: self.shua_ti_choice('视频题目'))
        gl.addWidget(self.vido_question_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.vido_question_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.discussion_label = QLabel('讨论:')
        self.discussion_entry = QComboBox()
        self.discussion_entry.addItems([AI_OPTION, '跳过讨论'])
        self.discussion_entry.currentTextChanged.connect(lambda _: self.shua_ti_choice('讨论'))
        gl.addWidget(self.discussion_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.discussion_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.speed_label = QLabel('倍速设置:')
        self.speed_entry = QComboBox()
        self.speed_entry.addItems(['1', '2', '3', '4', '5', '6', '8', '10', '16'])
        self.speed_entry.currentTextChanged.connect(self.hint)
        gl.addWidget(self.speed_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.speed_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.API_label = QLabel('API Key:')
        self.API_entry = QLineEdit()
        self.API_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.API_entry.setPlaceholderText('sk-... 或 OpenAI 兼容密钥')
        self.show_api_button = QPushButton('显示')
        self.show_api_button.setCheckable(True)
        self.show_api_button.toggled.connect(self.show_api)
        # Key 填完/修改后自动重拉模型列表（部分平台无 Key 时 /models 返回 401）
        self.API_entry.editingFinished.connect(self.fetch_models)
        gl.addWidget(self.API_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.API_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self.show_api_button, self._detail_row_next - 1, 2, Qt.AlignmentFlag.AlignLeft)

        self.API_URL_label = QLabel('API 地址:')
        # 可编辑预设下拉：常用平台一键填入，也支持手输任意 OpenAI 兼容地址
        self.API_URL_entry = QComboBox()
        self.API_URL_entry.setEditable(True)
        self.API_URL_entry.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.API_URL_entry.addItems([
            'https://api.deepseek.com',
            'https://api.moonshot.cn/v1',
            'https://open.bigmodel.cn/api/paas/v4',
            'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'https://openrouter.ai/api/v1',
            'https://api.siliconflow.cn/v1',
            'http://127.0.0.1:11434/v1',
            'http://127.0.0.1:8000/v1',
        ])
        self.API_URL_entry.lineEdit().setPlaceholderText('选择常用平台或输入自定义 OpenAI 兼容地址')
        self.API_URL_entry.lineEdit().editingFinished.connect(self.fetch_models)
        self.API_URL_entry.activated.connect(lambda _: self.fetch_models())
        gl.addWidget(self.API_URL_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.API_URL_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.API_MODEL_label = QLabel('模型名:')
        self.API_MODEL_entry = QComboBox()
        self.API_MODEL_entry.setEditable(True)
        self.API_MODEL_entry.addItem('')
        gl.addWidget(self.API_MODEL_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.API_MODEL_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)
        self.refresh_models_button = QPushButton('🔄 刷新模型')
        self.refresh_models_button.setFixedWidth(90)
        self.refresh_models_button.clicked.connect(self.fetch_models)
        self.test_api_button = QPushButton('⚡ 测试连接')
        self.test_api_button.setFixedWidth(96)
        self.test_api_button.clicked.connect(self.test_api_connection)
        _btn_box = QWidget()
        _btn_layout = QHBoxLayout(_btn_box)
        _btn_layout.setContentsMargins(0, 0, 0, 0)
        _btn_layout.addWidget(self.refresh_models_button)
        _btn_layout.addWidget(self.test_api_button)
        gl.addWidget(_btn_box, self._detail_row_next - 1, 2,
                     Qt.AlignmentFlag.AlignLeft)

        # API 状态行：单独占一行（不再与刷新按钮重叠）
        self.api_status_label = QLabel('')
        self.api_status_label.setFixedSize(260, 30)
        self._set_status('', 'idle')
        self.api_status_row = _row()
        gl.addWidget(self.api_status_label, self.api_status_row, 1, Qt.AlignmentFlag.AlignLeft)
        self.models_fetched.connect(self._apply_models)
        self.api_tested.connect(self._apply_api_test)
        self.log_signal.connect(self._append_log)
        self.program_finished.connect(self.restore_buttons)
        self.courses_fetched.connect(self._apply_courses)

        self.pass_face_label = QLabel('跳过人脸:')
        self.pass_face_check = QCheckBox('')
        gl.addWidget(self.pass_face_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self.pass_face_check, self._detail_row_next - 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.lock_screen_label = QLabel('防锁屏:')
        self.lock_screen_check = QCheckBox('')
        gl.addWidget(self.lock_screen_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self.lock_screen_check, self._detail_row_next - 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.debug_label = QLabel('调试模式:')
        self.debug_check = QCheckBox('')
        self.debug_check.setChecked(True)
        self.debug_check.setToolTip(
            '开启：显示浏览器窗口，可观察刷课过程与扫码登录。\n'
            '关闭：浏览器无头静默运行（不显示窗口、不占用鼠标键盘），\n'
            '首次登录/排查问题时建议开启；静默模式下建议同时勾选「跳过人脸」。')
        gl.addWidget(self.debug_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self.debug_check, self._detail_row_next - 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.uxue_label = QLabel('注入模式:')
        self.uxue_check = QCheckBox('')
        self.uxue_check.setToolTip(
            '开启后改用 uXueScript 页面内脚本接管整门课程：\n'
            '自动扫章节树并推进全部任务点（视频播放/倍速锁定/自动静音、\n'
            'PDF 自动滚动、失焦/切屏防暂停守护）。\n'
            '注意：测验(Quiz)任务点在注入模式下会跳过，需要刷题请关闭本选项。\n'
            '与「作业模式」「刷题设置」互斥，注入模式下它们不生效。')
        gl.addWidget(self.uxue_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self.uxue_check, self._detail_row_next - 1, 1, Qt.AlignmentFlag.AlignLeft)

        self.homework_label = QLabel('选择作业:')
        self.homework_entry = QComboBox()
        self.homework_entry.addItems(['手动选择', '自动选择'])
        self.homework_entry.currentTextChanged.connect(self.prompt)
        gl.addWidget(self.homework_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.homework_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        self.task_kind_label = QLabel('任务类型:')
        self.task_kind_entry = QComboBox()
        self.task_kind_entry.addItems(['作业', '考试'])
        self.task_kind_entry.setToolTip(
            '作业模式下的任务类型：\n'
            '作业 —— 遍历/手动打开课程作业并自动作答（原功能）\n'
            '考试 —— 遍历课程考试列表并自动作答（只暂存不自动交卷，交卷需人工确认）\n'
            '考试页结构未对全部院校版本验证，首次使用请人工盯守')
        gl.addWidget(self.task_kind_label, _row(), 0, Qt.AlignmentFlag.AlignLeft)
        gl.addWidget(self._input_widget(self.task_kind_entry), self._detail_row_next - 1, 1,
                     Qt.AlignmentFlag.AlignLeft)

        # 默认选中第一个分组（配置设置）
        first_child = self.set_tree.topLevelItem(0).child(0)
        self.set_tree.setCurrentItem(first_child)
        self._on_set_tree_change(first_child, None)

    def _on_set_tree_change(self, current, _prev):
        """二级列表切换：显示对应分组面板"""
        if current is None:
            return
        for g, (child, page, _gl) in self.set_group_pages.items():
            if current is child:
                self.set_stack.setCurrentWidget(page)
                break

    def _detail_row(self):
        """返回下一个可用的高级设置行号（0 行为标题，从 1 开始）"""
        n = getattr(self, '_detail_row_next', 1)
        self._detail_row_next = n + 1
        return n

    # ---------------------------------------------------------------- 课程拉取
    def fetch_courses(self):
        """登录学习通并拉取首页课程列表（后台线程执行，不阻塞 UI）"""
        phone = self.phone_number_entry.text().strip()
        password = self.password_entry.text()
        if not phone or not password:
            QMessageBox.warning(self, '提示', '请先填写手机号和密码')
            return
        self.fetch_course_button.setEnabled(False)
        self.fetch_course_button.setToolTip('正在拉取课程…')
        self._set_status('正在登录学习通拉取课程…', 'info')
        threading.Thread(target=self._fetch_courses_worker,
                         args=(phone, password), daemon=True).start()

    def _fetch_courses_worker(self, phone, password):
        """后台线程：启动浏览器 → 登录学习通 → 提取首页课程 → 写 course_name.json"""
        import json as _json
        import time as _time
        import traceback
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By

            # 按设置中的浏览器类型拉取课程（Linux 端默认 firefox）
            browser = (self.browser_entry.currentText().strip().lower()
                       or 'edge')
            driver_path = self.browser_driver_entry.text().strip()
            # 跨平台查找驱动：优先用户指定路径；其次系统 PATH（Linux 直接用
            # 无后缀驱动名，Windows 用 *.exe）；最后交给 Selenium Manager 自动管理
            exe_path = driver_path or None
            if exe_path and not (os.path.isfile(exe_path) or shutil.which(exe_path)):
                exe_path = None
            if not exe_path:
                exe_path = shutil.which(
                    {'edge': 'msedgedriver', 'chrome': 'chromedriver',
                     'firefox': 'geckodriver'}.get(browser, 'msedgedriver'))
            if browser == 'chrome':
                from selenium.webdriver.chrome.service import Service as _Service
                from selenium.webdriver.chrome.options import Options as _Options
                driver_cls = webdriver.Chrome
            elif browser == 'firefox':
                from selenium.webdriver.firefox.service import Service as _Service
                from selenium.webdriver.firefox.options import Options as _Options
                driver_cls = webdriver.Firefox
            else:
                from selenium.webdriver.edge.service import Service as _Service
                from selenium.webdriver.edge.options import Options as _Options
                driver_cls = webdriver.Edge

            service = _Service(exe_path)
            options = _Options()
            options.add_argument('--disable-blink-features=AutomationControlled')
            if browser != 'firefox':
                options.add_argument('--disable-web-security')
            driver = driver_cls(service=service, options=options)
            try:
                # 打开学习通首页，模拟登录
                driver.get('https://i.chaoxing.com/')
                _time.sleep(3)
                # 登录表单
                try:
                    phone_input = driver.find_element(By.ID, 'phone')
                    pwd_input = driver.find_element(By.ID, 'pwd')
                    phone_input.send_keys(phone)
                    pwd_input.send_keys(password)
                    login_btn = driver.find_element(By.ID, 'loginBtn')
                    login_btn.click()
                except Exception:
                    pass
                _time.sleep(5)
                # 尝试自动登录兜底（扫码/验证码）
                try:
                    from selenium.common.exceptions import NoSuchElementException
                    if driver.title == '用户登录':
                        # 提示用户扫码（保持浏览器窗口等待）
                        print('请完成登录（扫码/验证码）后自动继续…', flush=True)
                except Exception:
                    pass
                # 等待登录完成并提取课程列表：
                # 手动登录（滑块/扫码/短信）可能耗时较长，最长轮询 150 秒，
                # 期间浏览器保持打开，每 5 秒提取一次，成功立即继续
                selectors = ('[class*="course-name"]', '[class*="courseName"]',
                             '.courseBlock .courseName', 'li.course a',
                             'div[class*="courseCard"]')

                def _extract_course_names():
                    """主文档 + 全部 iframe 内按多选择器提取课程名"""
                    for css in selectors:
                        try:
                            elems = driver.find_elements(By.CSS_SELECTOR, css)
                            names = [(e.get_attribute('title') or e.text or '').strip()
                                     for e in elems]
                            names = [n for n in names if n and len(n) > 1]
                            if names:
                                return list(dict.fromkeys(names))
                        except Exception:
                            pass
                    try:
                        for frame in driver.find_elements(By.TAG_NAME, 'iframe'):
                            try:
                                driver.switch_to.frame(frame)
                            except Exception:
                                continue
                            for css in selectors:
                                try:
                                    elems = driver.find_elements(By.CSS_SELECTOR, css)
                                    names = [(e.get_attribute('title') or e.text or '').strip()
                                             for e in elems]
                                    names = [n for n in names if n and len(n) > 1]
                                    if names:
                                        driver.switch_to.default_content()
                                        return list(dict.fromkeys(names))
                                except Exception:
                                    pass
                            driver.switch_to.default_content()
                    except Exception:
                        pass
                    return []

                courses = []
                deadline = _time.time() + 150
                while _time.time() < deadline:
                    _time.sleep(5)
                    courses = _extract_course_names()
                    if courses:
                        break
                    try:
                        print(f'等待登录/课程加载…（当前页面：{driver.title}）', flush=True)
                    except Exception:
                        pass
                if not courses:
                    self.courses_fetched.emit(
                        [], '已等待 150 秒未提取到课程（请确认登录已完成并进入个人空间页后重试）')
                    return
                # 合并写入 course_name.json
                course_file = _path('task', 'tool', 'course_name.json')
                data = {}
                try:
                    with open(course_file, 'r', encoding='utf-8') as f:
                        data = _json.load(f)
                except (FileNotFoundError, ValueError):
                    data = {}
                old = data.get(phone, [])
                merged = list(dict.fromkeys(old + courses))
                data[phone] = merged
                with open(course_file, 'w', encoding='utf-8') as f:
                    _json.dump(data, f, ensure_ascii=False, indent=2)
                self.courses_fetched.emit(merged, '')
            finally:
                driver.quit()
        except Exception as e:
            traceback.print_exc()
            self.courses_fetched.emit([], '拉取课程失败: ' + str(e))

    def _fill_course_combos(self, courses):
        """填充三个课程下拉框，并尽量保持各框当前选中项不变
        （修复：设置里选了第 N 门课，保存后跳回第一门的问题）"""
        widgets = (self.cour_entry, self.course_vido_entry, self.course_score_entry)
        keeps = [w.currentText() for w in widgets]
        for w, keep in zip(widgets, keeps):
            w.clear()
            w.addItems(courses)
            if keep and keep in courses:
                w.setCurrentText(keep)
            elif courses:
                w.setCurrentText(courses[0])

    def _apply_courses(self, courses, err):
        """主线程：课程拉取完成后刷新课程下拉框"""
        self.fetch_course_button.setEnabled(True)
        self.fetch_course_button.setToolTip('')
        if courses:
            self._fill_course_combos(courses)
            self._set_status(f'获取到 {len(courses)} 门课程', 'ok')
        else:
            # 兜底：拉取失败时载入该手机号的历史课程，下拉框不至于一直为空
            phone = self.phone_number_entry.text().strip()
            cached = load_course_names().get(phone, []) if phone else []
            if cached:
                self._fill_course_combos(cached)
                self._set_status(f'本次拉取失败（{err or "未知错误"}），已载入 {len(cached)} 门历史课程', 'error')
            else:
                self._set_status('课程拉取失败: ' + (err or '未知错误'), 'error')

    # ---------------------------------------------------------------- 课程自动加载
    def _reload_courses_by_phone(self):
        """手机号输入完成（回车/失焦）后，自动加载该手机号历史课程到下拉框"""
        phone = self.phone_number_entry.text().strip()
        if not phone:
            return
        courses = load_course_names().get(phone, [])
        if courses:
            self._fill_course_combos(courses)
            self._set_status(f'已加载该手机号 {len(courses)} 门历史课程', 'ok')
        else:
            self._set_status('该手机号暂无历史课程，可点击「拉取课程」从学习通获取', 'idle')

    # ---------------------------------------------------------------- 模型自动获取
    def fetch_models(self):
        """自动拉取模型列表：后台线程 + requests 多协议探测（不阻塞 UI）"""
        url = self.API_URL_entry.currentText().strip()
        key = self.API_entry.text().strip()
        if not url:
            return
        # 序号自增：连续触发（改地址/改 Key/手动刷新）时旧请求结果自动作废
        self._models_fetch_seq = getattr(self, '_models_fetch_seq', 0) + 1
        seq = self._models_fetch_seq
        self._set_status('正在拉取模型列表…', 'info')
        # 有缓存：先用缓存立即回填，再后台刷新（避免白屏）
        cached = self._models_cache.get(url)
        if cached:
            self._apply_models(cached, '')
        threading.Thread(target=self._fetch_models_worker, args=(url, key, seq),
                         daemon=True).start()

    def _fetch_models_worker(self, url, key, seq=0):
        """requests 多端点/多认证/多格式探测（后台线程执行，失败自动重试一次）"""
        import requests
        ids = []
        err = ''
        base = url.rstrip('/')
        # 端点推导：用户可能填完整 chat 端点（https://api.x/v1/chat/completions），
        # 先剥离尾部 /chat/completions 或 /completions，得到 base（原本就是 base 则不变）
        if base.endswith('/chat/completions'):
            base = base[:-len('/chat/completions')]
        elif base.endswith('/completions'):
            base = base[:-len('/completions')]
        # 探测顺序：OpenAI 兼容标准 /v1/models 优先（SiliconFlow 等根 models 404）
        endpoints = [base + '/v1/models', base + '/models',
                     base + '/api/tags', base + '/models/list']
        auth_headers = []
        if key:
            auth_headers = [
                {'Authorization': 'Bearer ' + key},
                {'Authorization': key},
                {'X-Api-Key': key},
            ]
        # 首轮探测
        ids, err = self._probe_models(endpoints, auth_headers, key, base)
        # 失败 → 自动重试一次（处理偶发网络抖动）
        if not ids:
            ids2, err2 = self._probe_models(endpoints, auth_headers, key, base)
            if ids2:
                ids, err = ids2, ''
            else:
                err = err or err2
        ids = list(dict.fromkeys(ids))
        if seq and seq != getattr(self, '_models_fetch_seq', seq):
            return  # 期间已发起新请求，丢弃过期结果
        if ids:
            self._models_cache[url] = ids  # 缓存本次成功结果
        self.models_fetched.emit(ids, '' if ids else (err or '未获取到可用模型'))

    def _probe_models(self, endpoints, auth_headers, key, base):
        """探测一轮所有端点，返回 (ids, err)"""
        import requests
        ids = []
        err = ''
        for ep in endpoints:
            for hdr in (auth_headers or [{}]):
                try:
                    resp = requests.get(ep, headers=hdr, timeout=8)
                    if resp.status_code != 200:
                        continue
                    parsed = self._parse_models_payload(resp.json())
                    if parsed:
                        ids = parsed
                        break
                except Exception as e:
                    err = str(e)
                if ids:
                    break
            if ids:
                break
        # 兜底：api_key 查询参数
        if not ids:
            try:
                resp = requests.get(base + '/models',
                                    params={'api_key': key} if key else None,
                                    timeout=8)
                if resp.status_code == 200:
                    ids = self._parse_models_payload(resp.json())
            except Exception as e:
                err = str(e)
        return ids, err

    @staticmethod
    def _parse_models_payload(data):
        """兼容多种模型列表响应格式"""
        ids = []
        if isinstance(data, list):
            for m in data:
                if isinstance(m, str):
                    ids.append(m)
                elif isinstance(m, dict):
                    for k in ('id', 'model', 'name', 'model_name'):
                        if m.get(k):
                            ids.append(str(m[k]))
                            break
        elif isinstance(data, dict):
            # OpenAI: {data:[{id},...]} / {data:[{model},...]} / {data:[str,...]}
            # Ollama: {models:[{name:"llama3:latest"},...]}
            # 极简: {models:[str,...]} / {list:[str,...]}
            if isinstance(data.get('data'), list):
                ids = [str(m) if not isinstance(m, dict) else
                       next((str(m[k]) for k in ('id', 'model', 'name', 'model_name')
                             if m.get(k)), '')
                       for m in data['data']]
            elif isinstance(data.get('models'), list):
                ids = [str(m) if not isinstance(m, dict) else
                       next((str(m[k]) for k in ('name', 'id', 'model')
                             if m.get(k)), '')
                       for m in data['models']]
            elif isinstance(data.get('list'), list):
                ids = [str(m) for m in data['list']]
        return [i for i in ids if i]

    def _apply_models(self, ids, err):
        """主线程：填充模型下拉框并显示状态；未选模型时按优先级自动选默认"""
        if ids:
            current = self.API_MODEL_entry.currentText()
            self.API_MODEL_entry.blockSignals(True)
            self.API_MODEL_entry.clear()
            self.API_MODEL_entry.addItem('')
            self.API_MODEL_entry.addItems(ids)
            if current in ids:
                self.API_MODEL_entry.setCurrentText(current)
            else:
                # 自动选默认：常用对话类模型优先，免新手无从下手
                pick = next((m for pref in ('deepseek-chat', 'deepseek-reasoner')
                             if pref in ids), None)
                pick = pick or next(
                    (m for m in ids if 'deepseek' in m.lower()
                     or 'chat' in m.lower() or 'flash' in m.lower()
                     or 'mini' in m.lower()), None) or ids[0]
                self.API_MODEL_entry.setCurrentText(pick)
                current = pick
            self.API_MODEL_entry.blockSignals(False)
            self._set_status(f'已获取 {len(ids)} 个模型，默认选择 {current}（可修改）', 'ok')
        else:
            self._set_status('拉取失败: ' + (err or '未知错误'), 'error')

    # ---------------------------------------------------------------- API 连接测试
    def test_api_connection(self):
        """发一条最小 chat 请求实测 Key/地址/模型是否可用（后台线程，不阻塞 UI）"""
        url = self.API_URL_entry.currentText().strip()
        key = self.API_entry.text().strip()
        model = self.API_MODEL_entry.currentText().strip()
        if not url or not model:
            self._set_status('测试连接：请先填写 API 地址并选择模型', 'error')
            return
        self.test_api_button.setEnabled(False)
        self._set_status('正在测试连接…', 'info')
        threading.Thread(target=self._test_api_worker,
                         args=(url, key, model), daemon=True).start()

    def _test_api_worker(self, url, key, model):
        """OpenAI 兼容 /chat/completions 连通性测试（任意服务商/中转站/本地推理通用）"""
        import requests
        import time as _time
        base = url.rstrip('/')
        if base.endswith('/chat/completions'):
            base = base[:-len('/chat/completions')]
        headers = {'Content-Type': 'application/json'}
        if key:
            headers['Authorization'] = 'Bearer ' + key
        payload = {'model': model,
                   'messages': [{'role': 'user', 'content': '你好，请只回复:OK'}],
                   'max_tokens': 5, 'stream': False}
        t0 = _time.time()
        try:
            resp = requests.post(base + '/chat/completions', json=payload,
                                 headers=headers, timeout=20)
            latency = int((_time.time() - t0) * 1000)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    self.api_tested.emit('响应 200 但非 JSON（地址可能不对）', 'error')
                    return
                if isinstance(data, dict) and (data.get('choices')
                                               or data.get('content')
                                               or data.get('message')):
                    self.api_tested.emit(
                        f'✓ 连接成功 {latency}ms（{model}）', 'ok')
                else:
                    self.api_tested.emit('响应 200 但缺少回复内容：' + str(data)[:80], 'error')
                return
            reason = {401: 'Key 无效或未授权', 403: '无权限访问该模型',
                      404: '地址或模型不存在（检查是否需要 /v1）',
                      429: '请求限流或额度不足'}.get(resp.status_code,
                                                  f'HTTP {resp.status_code}')
            detail = ''
            try:
                j = resp.json()
                detail = str(j.get('error', {}).get('message', j)
                             if isinstance(j, dict) else j)[:100]
            except Exception:
                detail = resp.text[:100]
            self.api_tested.emit(f'{reason}：{detail}', 'error')
        except Exception as e:
            self.api_tested.emit('连接失败：' + str(e)[:120], 'error')

    def _apply_api_test(self, msg, kind):
        """主线程：显示测试连接结果并恢复按钮"""
        self.test_api_button.setEnabled(True)
        self._set_status(msg, kind)

    # ---------------------------------------------------------------- 其余页面
    def _build_help(self):
        grid = QGridLayout(self.help_frame)
        self.help_txt = QTextEdit()
        self.help_txt.setReadOnly(True)
        try:
            with open(HELP_FILE, 'r', encoding='utf-8') as f:
                self.help_txt.setPlainText(f.read())
        except (FileNotFoundError, OSError):
            self.help_txt.setPlainText('帮助文档缺失（task/tool/Help.txt）')
        grid.addWidget(self.help_txt, 0, 0)

    def _build_vido(self):
        grid = QGridLayout(self.vido_frame)
        self.course_vido_entry = QComboBox()
        self.course_vido_entry.setEditable(True)
        self.course_vido_entry.currentTextChanged.connect(lambda _: self.show_record('刷课'))
        grid.addWidget(self.course_vido_entry, 0, 0)

        self.find_button1 = QPushButton('查询')
        self.find_button1.clicked.connect(lambda: self.show_record('刷课'))
        grid.addWidget(self.find_button1, 0, 1)

        self.delete_button1 = QPushButton('删除记录')
        self.delete_button1.clicked.connect(lambda: self.delete_record('刷课'))
        grid.addWidget(self.delete_button1, 0, 2)

        self.vido_text = QTextEdit()
        self.vido_text.setReadOnly(True)
        grid.addWidget(self.vido_text, 1, 0, 1, 3)

    def _build_score(self):
        grid = QGridLayout(self.score_frame)
        self.course_score_entry = QComboBox()
        self.course_score_entry.setEditable(True)
        self.course_score_entry.currentTextChanged.connect(lambda _: self.show_record('成绩'))
        grid.addWidget(self.course_score_entry, 0, 0)

        self.find_button2 = QPushButton('查询')
        self.find_button2.clicked.connect(lambda: self.show_record('成绩'))
        grid.addWidget(self.find_button2, 0, 1)

        self.delete_button2 = QPushButton('删除记录')
        self.delete_button2.clicked.connect(lambda: self.delete_record('成绩'))
        grid.addWidget(self.delete_button2, 0, 2)

        self.score_txt = QTextEdit()
        self.score_txt.setReadOnly(True)
        grid.addWidget(self.score_txt, 1, 0, 1, 3)

    def _build_question_bank(self):
        grid = QGridLayout(self.question_bank_frame)
        self.tiku_text = QTextEdit()
        self.tiku_text.setReadOnly(True)
        grid.addWidget(self.tiku_text, 0, 0, 1, 2)
        self.delete_tiku_button = QPushButton('删除所有缓存题目')
        self.delete_tiku_button.clicked.connect(self.delete_huancun)
        grid.addWidget(self.delete_tiku_button, 1, 0, 1, 2)

    def _build_error(self):
        grid = QGridLayout(self.error_frame)
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        grid.addWidget(self.error_text, 0, 0)

    # ---------------------------------------------------------------- 样式
    # 暗黑模式辅助色（集中管理，便于后续扩展）
    def _input_bg(self):
        return '#1F2937' if self.dark_mode else '#FFFFFF'

    def _input_text(self):
        return '#F3F4F6' if self.dark_mode else '#111827'

    def _border_color(self):
        return '#374151' if self.dark_mode else '#D1D5DB'

    def _hover_bg(self):
        return '#374151' if self.dark_mode else '#F3F4F6'

    def _sel_bg(self):
        return '#4B5563' if self.dark_mode else '#E5E7EB'

    def _sel_text(self):
        return '#F9FAFB' if self.dark_mode else '#111827'

    def _status_color(self, kind):
        """状态标签颜色（kind: idle/info/ok/error），暗黑模式用亮色版本"""
        if self.dark_mode:
            return {'idle': '#9CA3AF', 'info': '#93C5FD',
                    'ok': '#4ADE80', 'error': '#F87171'}[kind]
        return {'idle': '#6B7280', 'info': '#2563EB',
                'ok': '#16A34A', 'error': '#DC2626'}[kind]

    def _set_status(self, text, kind):
        """设置 API 状态标签文本与颜色（随主题切换）"""
        self.api_status_label.setText(text)
        self.api_status_label.setStyleSheet(
            'color: %s; font-size: 12px;' % self._status_color(kind))
    def _apply_styles(self):
        bg, primary, accent = self.frame_bg, self.button_bg, self.hover_bg
        dark_mode = self.dark_mode
        white_mode = self.record_color == '黑白'        # 黑白=白底黑字

        if dark_mode:
            # —— 暗黑模式配色 ——
            card_bg = '#1F2937'          # 卡片/面板背景
            nav_bg = '#111827'           # 导航栏背景（与全局背景一致）
            input_bg = '#1F2937'         # 输入框背景
            input_text = '#F3F4F6'       # 输入框文字
            text_color = '#D1D5DB'       # 普通文字
            title_color = '#F3F4F6'      # 标题
            btn_bg = '#374151'           # 按钮背景
            btn_text = '#F3F4F6'         # 按钮文字
            btn_hover = '#4B5563'        # 按钮悬停
            sel_bg = '#2563EB'           # 高亮/选中背景
            sel_text = '#FFFFFF'         # 选中文字
            border_color = '#374151'
            disabled_bg = '#1F2937'
            disabled_text = '#6B7280'
            focus_border = '#3B82F6'
        else:
            # —— 亮色配色（保持原有逻辑）——
            card_bg = '#FFFFFF' if white_mode else bg
            nav_bg = '#F3F4F6' if white_mode else primary
            input_bg = '#FFFFFF'
            input_text = '#111827'
            text_color = '#111827' if white_mode else '#222'
            title_color = '#111827' if white_mode else primary
            btn_bg = '#FFFFFF' if white_mode else primary
            btn_text = '#111827' if white_mode else '#FFFFFF'
            btn_hover = '#F3F4F6' if white_mode else accent
            sel_bg = '#E5E7EB' if white_mode else primary
            sel_text = '#111827'
            border_color = '#D1D5DB'
            disabled_bg = '#E5E7EB'
            disabled_text = '#9CA3AF'
            focus_border = btn_bg

        self.setStyleSheet(
            'QMainWindow, QWidget { background: %s; color: %s; }'
            'QFrame { background: %s; }'
            # 导航栏
            'QFrame#navFrame { background: %s; border: none; }'
            'QLabel#navTitle { color: %s; font-size: 16px; font-weight: bold;'
            ' padding: 12px 10px 6px 16px; background: transparent; }'
            'QPushButton { background: %s; color: %s; border: 1px solid %s;'
            ' border-radius: 8px; padding: 9px 16px; font-size: 13px; }'
            'QPushButton:hover { background: %s; color: %s; }'
            'QPushButton:pressed { background: %s; color: %s; }'
            'QPushButton:disabled { background: %s; color: %s; }'
            'QPushButton:checked { background: %s; color: %s;'
            ' border: 1px solid %s; }'
            # 分组卡片
            'QFrame#card { background: %s; border: 1px solid %s;'
            ' border-radius: 10px; }'
            'QLabel#cardTitle { background: transparent; font-size: 14px;'
            ' font-weight: bold; color: %s; padding: 6px 8px; }'
            # 输入控件
            'QTextEdit, QLineEdit, QComboBox { background: %s;'
            ' color: %s; border: 1px solid %s; border-radius: 6px;'
            ' padding: 6px; selection-background-color: %s; }'
            'QTextEdit:focus, QLineEdit:focus, QComboBox:focus {'
            ' border: 1px solid %s; }'
            'QComboBox QAbstractItemView { background: %s; color: %s;'
            ' border: 1px solid %s; }'
            'QLabel { background: transparent; color: %s; }'
            'QRadioButton, QCheckBox { color: %s; font-size: 13px; }'
            % (bg, text_color, bg, nav_bg, title_color,
               btn_bg, btn_text, border_color, btn_hover, btn_text,
               sel_bg, sel_text, disabled_bg, disabled_text,
               sel_bg, sel_text, border_color,
               card_bg, border_color, title_color,
               input_bg, input_text, border_color, sel_bg, focus_border,
               input_bg, input_text, border_color,
               text_color, text_color))

    def change_font(self, *_):
        """字体设置变化时更新全局字体"""
        family = self.font_entry.currentText() or DEFAULT_FONT
        try:
            size = int(self.size_entry.currentText())
        except (ValueError, TypeError):
            size = 13
        self.font_family = family
        self.font_size = size
        self.font = QFont(family, size)
        self._apply_styles()
        for btn in self.nav_buttons.values():
            self._nav_style(btn)

    def _refresh_nav_title(self):
        """按当前主题刷新左侧导航栏标题颜色"""
        _title_color = ('#F3F4F6' if self.dark_mode
                        else '#111827' if self.record_color == '黑白'
                        else self.button_bg)
        self.nav_title.setStyleSheet('color: %s; font-size: 16px; font-weight: bold;'
                                     % _title_color)

    def apply_theme(self, theme_name='明亮'):
        """切换明亮/暗黑主题并即时刷新全部样式（可被保存配置恢复时调用）"""
        theme_name = theme_name or '明亮'
        self.record_color = '暗黑' if theme_name == '暗黑' else '黑白'
        self.frame_bg, self.button_bg, self.hover_bg = COLOR_SCHEMES[self.record_color]
        self.dark_mode = (self.record_color == '暗黑')
        self._apply_styles()
        self._refresh_nav_title()
        # 重新应用左侧导航按钮样式
        for btn in self.nav_buttons.values():
            self._nav_style(btn)
        # 设置页二级目录也随主题刷新
        self.set_tree.setStyleSheet(
            'QTreeWidget { background: %s; border: 1px solid %s;'
            ' border-radius: 8px; font-size: 13px; }'
            'QTreeWidget::item { padding: 6px 4px; }'
            'QTreeWidget::item:selected { background: %s; color: %s; }'
            'QTreeWidget::item:hover { background: %s; }'
            % (self._input_bg(), self._border_color(), self._sel_bg(),
               self._sel_text(), self._hover_bg()))

    # ---------------------------------------------------------------- 页面切换
    def _show_page(self, name):
        if self._current_page is not None:
            self._current_page.hide()
        page = self.pages[name]
        page.show()
        self._current_page = page
        for text, btn in self.nav_buttons.items():
            btn.setChecked(text == name)

    def show_main(self):
        self._show_page('主页')

    def show_set(self):
        self._show_page('设置')

    def show_help(self):
        self._show_page('帮助')

    def show_record(self, name):
        page_name = '刷课日志' if name == '刷课' else '测试成绩'
        self._show_page(page_name)
        combo = self.course_vido_entry if name == '刷课' else self.course_score_entry
        text = self.vido_text if name == '刷课' else self.score_txt
        course = combo.currentText().strip()
        record_path = _path('task', 'record', f'《{course}》的{name}记录.txt')
        try:
            with open(record_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (FileNotFoundError, OSError):
            content = f'暂未查询到《{course}》的{name}记录'
        text.setPlainText(content)

    def show_question_bank(self):
        self._show_page('题库查询')
        try:
            folder = _path('task', 'record')
            import pickle
            files = [fn for fn in os.listdir(folder)
                     if fn.endswith('.pkl') and os.path.isfile(os.path.join(folder, fn))]
            content = ''
            for fn in files:
                if 'ques1' not in fn:
                    continue
                with open(os.path.join(folder, fn), 'rb') as f:
                    value = pickle.load(f).get('value', {})
                content += '问题: ' + str(value.get('question', '')) + '\n'
                content += str(value.get('options', '')) + '\n'
                content += '答案为: ' + str(value.get('answer', '')) + '\n\n'
            if not content:
                content = '暂无缓存的题目'
            self.tiku_text.setPlainText(content)
        except FileNotFoundError:
            self.tiku_text.setPlainText('暂无缓存的题目')

    def show_error(self):
        self._show_page('报错日志')
        try:
            with open(ERROR_LOG, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            content = '暂无报错记录'
        self.error_text.setPlainText(content)

    # ---------------------------------------------------------------- 交互逻辑
    def toggle_topmost(self):
        self.is_topmost = self.topmost_check.isChecked()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_topmost)
        self.show()

    def open_timer_window(self):
        dlg = TimerDialog(self, self.timer_start_time, self.timer_end_time, self.font)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.result_action == 'enable':
            self.timer_start_time = dlg.start_time
            self.timer_end_time = dlg.end_time
            self.timer_active = True
            self._append_log(
                f'\n定时刷课已开启:\n  开始时间: {self.timer_start_time}\n'
                f'  结束时间: {self.timer_end_time}\n请勿关闭此窗口，否则定时刷课将无法正常开启')
            data = load_account()
            data.update({'timer_active': 'True', 'timer_start': self.timer_start_time,
                         'timer_end': self.timer_end_time})
            save_account(data)
        else:
            self.timer_active = False
            self._append_log('\n定时刷课已禁用')
            data = load_account()
            data['timer_active'] = 'False'
            save_account(data)

    def _append_log(self, text):
        self.text_box.append(text)
        self.text_box.moveCursor(self.text_box.textCursor().MoveOperation.End)

    # ---------------------------------------------------------------- 刷课进程
    def start(self):
        self.process_condition = True
        self.close_button.show()
        self.start_button.hide()
        self.timer_button.hide()
        data = load_account()
        if not data.get('phone_number'):
            QMessageBox.warning(self, '警告',
                                '请在设置页面填写相关信息再保存，如果已经保存，请在关闭主窗口后，'
                                '再右键点击刷课程序用管理员权限运行')
            self.process_condition = False
            self.start_button.show()
            self.timer_button.show()
            self.close_button.hide()
            return
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, '--worker']
        else:
            cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')]
        threading.Thread(target=self.run_program, args=(cmd,), daemon=True).start()
        # 按钮保持「结束刷课」状态，直到子进程真正结束（run_program 发
        # program_finished 信号恢复），不再定时 5 秒无条件复位

    def restore_buttons(self):
        self.start_button.show()
        self.timer_button.show()
        self.close_button.hide()

    def close_program(self):
        self.process_condition = False
        self.start_button.show()
        self.timer_button.show()
        self.close_button.hide()
        self.show_main()
        if self.process is not None:
            try:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self._append_log('程序已成功关闭\n')
            except Exception as e:
                self._append_log(f'关闭失败: {e}\n')
            finally:
                self.process = None

    def run_program(self, cmd):
        """启动 main.py 子进程并实时读取输出显示到日志框（后台线程）"""
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                cwd=_APP_DIR,
                # 关键：让子进程独立成新会话/进程组。否则它与 GUI 及
                # 桌面会话同组，close_program 的 killpg 会把整个组
                # （含 XFCE 会话组件）一起 SIGTERM——表现为"点结束刷课
                # 把电脑 UI 重启"
                **({} if os.name == 'nt' else {'start_new_session': True}))
        except Exception as e:
            self._append_log(f'启动失败: {e}')
            return
        while True:
            if self.process is None:
                break
            line = self.process.stdout.readline()
            if not line and self.process.poll() is not None:
                break
            if line:
                text = self._strip_ansi(line.decode('utf-8', errors='ignore'))
                self.log_signal.emit(text)   # 跨线程经信号写 UI，禁止直调 QTextEdit
        self.process.stdout.close()
        try:
            self.process.wait()
        except Exception:
            pass
        self.process = None
        if self.process_condition:
            self.log_signal.emit('\n刷课子进程已结束')
        self.program_finished.emit()   # 子进程结束，恢复「开始刷课」按钮

    @staticmethod
    def _strip_ansi(text):
        """剥离 ANSI 色彩码，返回纯文本"""
        return re.sub(r'\x1b\[[0-9;]*m', '', text)

    # ---------------------------------------------------------------- 设置回调
    @staticmethod
    def _default_browser():
        """平台默认浏览器：Windows→edge，Linux/macOS→firefox"""
        return 'edge' if os.name == 'nt' else 'firefox'

    def _driver_candidates(self, driver_kind):
        """返回候选驱动路径列表（跨平台：Windows 用 .exe，Linux/macOS 用无后缀可执行文件）"""
        if driver_kind == 'edge':
            base_dirs = ('edgedriver_win64', 'edgedriver_linux64', 'edgedriver_mac64')
            exe_names = ('msedgedriver.exe', 'msedgedriver')
        elif driver_kind == 'chrome':
            base_dirs = ('chromedriver', 'chromedriver_linux64', 'chromedriver_mac64')
            exe_names = ('chromedriver.exe', 'chromedriver')
        else:  # firefox
            base_dirs = ('geckodriver',)
            exe_names = ('geckodriver.exe', 'geckodriver')

        cands = []
        for base in base_dirs:
            for name in exe_names:
                p = os.path.join(os.getcwd(), base, name)
                if os.path.isfile(p):
                    cands.append(p)
                p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  '..', base, name)
                if os.path.isfile(p2):
                    cands.append(p2)
        return cands

    def auto_fill_browser_driver(self, choice):
        mapping = {
            'edge': 'msedgedriver',
            'chrome': 'chromedriver',
            'firefox': 'geckodriver',
        }
        if choice in mapping:
            # 优先已存在的候选驱动路径；其次系统 PATH / Linux 常见安装位置；
            # 否则填平台后缀（Windows .exe，Linux 无后缀）
            cands = self._driver_candidates(choice)
            if cands:
                self.browser_driver_entry.setText(cands[0])
                return
            if os.name != 'nt':
                name = mapping[choice]
                found = shutil.which(name)
                if not found:
                    for cand in ('/usr/bin/' + name, '/usr/local/bin/' + name,
                                 '/snap/bin/' + name):
                        if os.path.isfile(cand):
                            found = cand
                            break
                if found:
                    self.browser_driver_entry.setText(found)
                    return
                # Linux 下默认填裸驱动名（交给系统 PATH / Selenium Manager 解析）
                self.browser_driver_entry.setText(name)
                return
            ext = '.exe' if os.name == 'nt' else ''
            base = {
                'edge': 'edgedriver_win64' if os.name == 'nt' else 'edgedriver_linux64',
                'chrome': 'chromedriver',
                'firefox': 'geckodriver',
            }[choice]
            self.browser_driver_entry.setText(
                os.path.join(base, mapping[choice] + ext))

    def select_file(self):
        filter_ = ('可执行文件 (*.exe);;所有文件 (*)' if os.name == 'nt'
                   else '可执行文件 (*);;所有文件 (*)')
        path, _ = QFileDialog.getOpenFileName(self, '选择文件', '', filter_)
        if path:
            self.browser_driver_entry.setText(path)

    def show_password(self, checked):
        self.password_entry.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def show_api(self, checked):
        self.API_entry.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def function_choice(self):
        """功能单选变化：1 自动刷课答题 / 2 自动完成作业（含任务类型=考试）"""
        self._current_mode = 2 if self.radio_button_2.isChecked() else 1
        self._reload_advanced()

    def _reload_advanced(self):
        """按当前模式重设高级控件内容与显隐（与原版 function_choice 等价）"""
        self._suppress_signals = True
        try:
            mode = self._current_mode
            if mode == 1:
                self.question_label.setText('章节测验:')
                # 恢复章节模式上次选择的答题方式
                keep = self._chapter_answer_choice
                self.question_entry.clear()
                self.question_entry.addItems([AI_OPTION, '随机答题', '不刷题'])
                if keep in [AI_OPTION, '随机答题', '不刷题']:
                    self.question_entry.setCurrentText(keep)
                keep2 = self.after_finish_question_entry.currentText()
                self.after_finish_question_entry.clear()
                self.after_finish_question_entry.addItems(AFTER_FINISH_OPTIONS)
                if keep2 in AFTER_FINISH_OPTIONS:
                    self.after_finish_question_entry.setCurrentText(keep2)

                self.vido_question_label.show()
                self.vido_question_entry.show()
                self.discussion_label.show()
                self.discussion_entry.show()
                self.speed_label.show()
                self.speed_entry.show()
                self.pass_face_label.show()
                self.pass_face_check.show()
                self.lock_screen_label.show()
                self.lock_screen_check.show()
                self.homework_label.hide()
                self.homework_entry.hide()
                self.task_kind_label.hide()
                self.task_kind_entry.hide()
            else:  # mode == 2 作业
                self.question_label.setText('作业答题:')
                # 恢复作业模式上次选择的答题方式（通常为 AI 智能答题）
                keep = self._homework_answer_choice
                self.question_entry.clear()
                self.question_entry.addItems([AI_OPTION])
                if keep == AI_OPTION:
                    self.question_entry.setCurrentText(keep)
                self.after_finish_question_entry.clear()
                self.after_finish_question_entry.addItems(AFTER_FINISH_OPTIONS)

                self.vido_question_label.hide()
                self.vido_question_entry.hide()
                self.discussion_label.hide()
                self.discussion_entry.hide()
                self.speed_label.hide()
                self.speed_entry.hide()
                self.pass_face_label.hide()
                self.pass_face_check.hide()
                self.lock_screen_label.hide()
                self.lock_screen_check.hide()
                self.homework_label.show()
                self.homework_entry.show()
                self.task_kind_label.show()
                self.task_kind_entry.show()

            # API 组：任一选择 AI 智能答题时显示
            use_ai = (self.question_entry.currentText() == AI_OPTION
                      or self.vido_question_entry.currentText() == AI_OPTION
                      or self.discussion_entry.currentText() == AI_OPTION)
            for w in (self.API_label, self.API_entry, self.show_api_button,
                      self.API_URL_label, self.API_URL_entry,
                      self.API_MODEL_label, self.API_MODEL_entry,
                      self.refresh_models_button, self.test_api_button,
                      self.api_status_label):
                w.setVisible(use_ai)
        finally:
            self._suppress_signals = False

    def shua_ti_choice(self, event=''):
        """章节测验/视频题目/讨论 选择变化"""
        if getattr(self, '_suppress_signals', False):
            return
        if event == '视频题目' and self.vido_question_entry.currentText() == AI_OPTION:
            QMessageBox.information(
                self, '提示',
                '这个是用于完成视频中弹出的题目，只有在选错答案会回退视频的情况下才建议使用'
                'AI 智能答题，一般情况请使用随机答题,没有任何影响')
        # 记录当前模式的答题方式（切换模式时保留）
        if self._current_mode == 1:
            self._chapter_answer_choice = self.question_entry.currentText()
        else:
            self._homework_answer_choice = self.question_entry.currentText()
        self._reload_advanced()

    def hint(self, speed):
        if getattr(self, '_suppress_signals', False):
            return
        if speed and speed.isdigit() and int(speed) > 2:
            QMessageBox.information(self, '提示', '倍数过高，已完成的任务点可能会被清空，请谨慎使用')

    def prompt(self, choice):
        if getattr(self, '_suppress_signals', False):
            return
        if choice == '自动选择':
            QMessageBox.information(self, '提示', '默认会从第一个未完成的作业开始刷，刷完后只会自动保存不会提交，'
                                                  '保存后自动开始刷下一个作业')
        else:
            QMessageBox.information(self, '提示', '到达作业页面后请手动选择您要刷的作业，刷完后只会自动保存，'
                                                  '请确认后手动提交')

    # ---------------------------------------------------------------- 动态课程行
    def add_course(self, cour_name):
        row = self.next_row
        if row >= 6:
            QMessageBox.warning(self, '警告', '最多只能添加3门课程')
            return
        parent = self.info_grid.parentWidget()
        combo = QComboBox(parent)
        combo.setEditable(True)
        combo.setFixedWidth(240)
        combo.addItems(self.data or [''])
        if cour_name:
            combo.setCurrentText(cour_name)
        del_btn = QPushButton('✖')
        del_btn.setFixedWidth(28)
        del_btn.clicked.connect(lambda: self.delete_course_row(combo, del_btn))
        self.info_grid.addWidget(combo, row, 1, Qt.AlignmentFlag.AlignLeft)
        self.info_grid.addWidget(del_btn, row, 2, Qt.AlignmentFlag.AlignLeft)
        self.dynamic_rows.append((combo, del_btn, row))
        self.next_row += 1
        if row == 5 and len(self.dynamic_rows) >= 2:
            prev_combo, prev_del_btn, _ = self.dynamic_rows[-2]
            prev_del_btn.setEnabled(False)

    def delete_course_row(self, combo, del_btn):
        for i, (c, d, _) in enumerate(self.dynamic_rows):
            if c is combo:
                self.dynamic_rows.pop(i)
                break
        combo.deleteLater()
        del_btn.deleteLater()
        self.next_row -= 1
        if self.next_row == 5 and self.dynamic_rows:
            last_combo, last_del, _ = self.dynamic_rows[-1]
            last_del.setEnabled(True)

    # ---------------------------------------------------------------- 删除记录
    def delete_record(self, name):
        combo = self.course_vido_entry if name == '刷课' else self.course_score_entry
        course = combo.currentText().strip()
        if not course:
            QMessageBox.warning(self, '警告', '请先选择课程')
            return
        path = _path('task', 'record', f'《{course}》的{name}记录.txt')
        if os.path.exists(path):
            r = QMessageBox.question(self, '确认', '确定要删除吗？删除后无法恢复',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r == QMessageBox.StandardButton.Yes:
                os.remove(path)
                QMessageBox.information(self, '提示', f'{name}记录文件已成功删除')
        else:
            QMessageBox.warning(self, '警告', f'指定的{name}记录文件不存在')
        self.show_record(name)

    def delete_huancun(self):
        folder = _path('task', 'record')
        try:
            count = 0
            for fn in os.listdir(folder):
                if fn.endswith('.pkl') and os.path.isfile(os.path.join(folder, fn)):
                    os.remove(os.path.join(folder, fn))
                    count += 1
            QMessageBox.information(self, '提示', f'缓存记录文件已成功删除（共 {count} 个）')
        except OSError:
            QMessageBox.warning(self, '警告', '删除失败')
        self.show_question_bank()

    # ---------------------------------------------------------------- 保存/加载
    def _gather(self):
        data = {}
        data['browser'] = self.browser_entry.currentText()
        data['driver_path'] = self.browser_driver_entry.text().strip()
        data['phone_number'] = self.phone_number_entry.text().replace('\n', '')
        data['password'] = self.password_entry.text().replace('\n', '')
        courses = [self.cour_entry.currentText().replace('\n', '')]
        courses += [c.currentText().replace('\n', '') for c, _, _ in self.dynamic_rows
                    if c.currentText().replace('\n', '')]
        self.all_courses = courses
        data['cour'] = [c for c in courses if c]
        data['choice'] = self.question_entry.currentText()
        data['after_finish_question'] = self.after_finish_question_entry.currentText()
        data['video_title_choice'] = self.vido_question_entry.currentText()
        data['discussion_choice'] = self.discussion_entry.currentText()
        data['API'] = self.API_entry.text()
        data['API_URL'] = self.API_URL_entry.currentText().strip()
        data['API_MODEL'] = self.API_MODEL_entry.currentText().strip()
        data['speed'] = self.speed_entry.currentText()
        data['homework'] = self.homework_entry.currentText()
        data['task_type'] = ('章节' if self._current_mode == 1
                             else self.task_kind_entry.currentText())
        data['radio_var'] = self._current_mode
        data['font_type'] = self.font_entry.currentText()
        data['font_size'] = self.size_entry.currentText()
        data['pass_face'] = 1 if self.pass_face_check.isChecked() else 0
        data['lock_screen'] = 1 if self.lock_screen_check.isChecked() else 0
        data['debug_mode'] = 1 if self.debug_check.isChecked() else 0
        data['uxue_inject'] = 1 if self.uxue_check.isChecked() else 0
        data['theme'] = self.theme_entry.currentText() if hasattr(self, 'theme_entry') else '明亮'
        return data

    def save(self):
        errors = []
        browser = self.browser_entry.currentText()
        if not browser or browser == 'edge' and not self.browser_driver_entry.text().strip():
            pass  # 兼容：edge 自动填
        if self.browser_driver_entry.text().strip():
            drv = self.browser_driver_entry.text().strip()
            # 跨平台校验：真实文件 → 系统 PATH 中的驱动名 → 项目约定驱动目录
            # （与 main._find_project_driver 的运行时解析链一致；Linux 默认填的
            # 裸名 "geckodriver" 即落在 学习通刷课/geckodriver/geckodriver）
            ok = os.path.isfile(drv) or shutil.which(drv) is not None
            if not ok:
                # 项目约定驱动目录兜底（Windows/Linux 通用；.exe 后缀不敏感）
                drv_base = os.path.basename(drv).lower()
                for cand in self._driver_candidates(browser.strip().lower()):
                    cand_base = os.path.basename(cand).lower()
                    if cand_base in (drv_base, drv_base + '.exe'):
                        # 解析成功：把输入框回填为解析出的绝对路径，保存的配置更具体
                        drv = cand
                        self.browser_driver_entry.setText(cand)
                        ok = True
                        break
            if not ok:
                errors.append('驱动文件不存在，请选择正确的驱动文件')
        else:
            errors.append('请填写驱动地址')
        if not self.phone_number_entry.text().strip():
            errors.append('请填写手机号')
        if not self.password_entry.text():
            errors.append('请填写密码')
        if not self.cour_entry.currentText().strip():
            errors.append('请填写课程名称')
        if self._current_mode == 1:
            if not self.speed_entry.currentText():
                errors.append('请填写倍数')
            if self.question_entry.currentText() == AI_OPTION \
                    and not self.after_finish_question_entry.currentText():
                errors.append('请完成答完题后的设置')
        if self._current_mode == 2 and not self.homework_entry.currentText():
            errors.append('请填写作业选择形式')
        if (self.question_entry.currentText() == AI_OPTION
                or self.vido_question_entry.currentText() == AI_OPTION
                or self.discussion_entry.currentText() == AI_OPTION):
            # 逐项提示缺失项，避免只报"缺密钥"造成误导
            if not self.API_entry.text().strip():
                errors.append('已选择 AI 智能答题：请填写 API Key')
            if not self.API_URL_entry.currentText().strip():
                errors.append('已选择 AI 智能答题：请填写或选择 API 地址')
            if not self.API_MODEL_entry.currentText().strip():
                errors.append('已选择 AI 智能答题：请选择或填写模型名')
        if errors:
            QMessageBox.warning(self, '警告', '\n'.join(errors))
            return False

        data = self._gather()
        r = QMessageBox.question(self, '确认保存', '你确定要保存吗？\n(使用 AI 智能答题可支持全题型作答)',
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return False
        try:
            save_account(data)
        except (OSError, PermissionError):
            QMessageBox.warning(self, '警告', '保存失败，请在关闭主窗口后，再右键点击刷课程序用管理员权限打开')
            return False
        self.account_info = data
        self.save_course()
        self._reload_courses_by_phone()
        self.change_font()
        QMessageBox.information(self, '', '保存成功')
        return True

    def save_course(self):
        phone = self.phone_number_entry.text()
        if not phone:
            return
        data = load_course_names()
        old = data.get(phone, [])
        for c in self.all_courses:
            if c and c not in old:
                old.append(c)
        data[phone] = old
        try:
            with open(COURSE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_data(self):
        data = load_account()
        if not data:
            # 全新配置：按平台填默认浏览器与驱动（Windows→edge，Linux→firefox）
            browser = self._default_browser()
            self.browser_entry.setCurrentText(browser)
            self.auto_fill_browser_driver(browser)
            return
        self.account_info = data
        self._suppress_signals = True
        try:
            self._apply_saved(data)
        finally:
            self._suppress_signals = False

    def _apply_saved(self, data):
        courses = load_course_names().get(data.get('phone_number', ''), [])
        self.data = courses
        first = (data.get('cour') or [''])[0]

        self.course_score_entry.clear()
        self.course_score_entry.addItems(courses or [first or ''])
        self.course_vido_entry.clear()
        self.course_vido_entry.addItems(courses or [first or ''])
        self.cour_entry.clear()
        self.cour_entry.addItems(courses or [first or ''])
        self.cour_entry.setCurrentText(first or '')

        # 浏览器缺省按平台：Windows→edge，Linux/macOS→firefox
        saved_browser = (data.get('browser') or '').strip().lower()
        if saved_browser not in ('edge', 'chrome', 'firefox'):
            saved_browser = self._default_browser()
        self.browser_entry.setCurrentText(saved_browser)  # 触发 auto_fill 填默认驱动
        # 驱动路径跨平台兼容：本机解析不了（另一平台保存的路径/裸名在本机缺失）时，
        # 自动回填该浏览器在本机的默认驱动（Windows→*.exe，Linux→系统/项目驱动）
        saved_driver = (data.get('driver_path') or '').strip()
        if saved_driver:
            self.browser_driver_entry.setText(saved_driver)
            usable = (os.path.isfile(saved_driver)
                      or shutil.which(saved_driver) is not None)
            if not usable:
                self.auto_fill_browser_driver(saved_browser)
        elif not self.browser_driver_entry.text().strip():
            self.auto_fill_browser_driver(saved_browser)
        self.phone_number_entry.setText(data.get('phone_number', ''))
        self.password_entry.setText(data.get('password', ''))
        self.speed_entry.setCurrentText(data.get('speed', '2'))
        # 旧版配置里的 DeepSeek AI 兼容映射为 AI 智能答题
        self.question_entry.setCurrentText(
            AI_OPTION if data.get('choice') == LEGACY_AI_OPTION
            else data.get('choice', AI_OPTION))
        self.after_finish_question_entry.setCurrentText(
            data.get('after_finish_question', '仅自动保存'))
        if data.get('video_title_choice'):
            self.vido_question_entry.setCurrentText(
                AI_OPTION if data['video_title_choice'] == LEGACY_AI_OPTION
                else data['video_title_choice'])
        self.discussion_entry.setCurrentText(
            AI_OPTION if data.get('discussion_choice') == LEGACY_AI_OPTION
            else data.get('discussion_choice', '跳过讨论'))
        self.homework_entry.setCurrentText(data.get('homework', '手动选择'))

        mode = int(data.get('radio_var', 1))
        legacy_exam = False
        if mode == 3:
            # 旧版「自动完成考试」单选：并入作业模式 + 任务类型=考试
            mode = 2
            legacy_exam = True
        if mode == 2:
            self.radio_button_2.setChecked(True)
        else:
            self.radio_button_1.setChecked(True)
        self._current_mode = mode
        if legacy_exam:
            self.task_kind_entry.setCurrentText('考试')
        elif data.get('task_type') in ('作业', '考试'):
            self.task_kind_entry.setCurrentText(data['task_type'])

        self.pass_face_check.setChecked(bool(data.get('pass_face', 0)))
        self.lock_screen_check.setChecked(bool(data.get('lock_screen', 0)))
        self.debug_check.setChecked(bool(int(data.get('debug_mode', 1))))
        self.uxue_check.setChecked(bool(int(data.get('uxue_inject', 0))))
        # 恢复主题（默认明亮；暗黑时切换）
        saved_theme = data.get('theme', '明亮')
        try:
            if hasattr(self, 'theme_entry'):
                self.theme_entry.setCurrentText(saved_theme)
        except Exception:
            pass
        if saved_theme == '暗黑' and not self.dark_mode:
            self.apply_theme('暗黑')
        elif saved_theme != '暗黑' and self.dark_mode:
            self.apply_theme('明亮')
        self.API_entry.setText(data.get('API', ''))
        self.API_URL_entry.setEditText(data.get('API_URL', ''))
        self.API_MODEL_entry.setCurrentText(data.get('API_MODEL', ''))
        try:
            if data.get('font_type'):
                self.font_entry.setCurrentText(data['font_type'])
            if data.get('font_size'):
                self.size_entry.setCurrentText(data['font_size'])
            self.change_font()
        except Exception:
            pass
        for cour in (data.get('cour') or [])[1:]:
            self.add_course(cour)
        if data.get('timer_active') == 'True':
            self.timer_active = True
        self.timer_start_time = data.get('timer_start', '04:00:00')
        self.timer_end_time = data.get('timer_end', '03:00:00')
        # 同步两种模式的答题方式字段（供 _reload_advanced 切换时恢复）
        self._chapter_answer_choice = self.question_entry.currentText()
        self._homework_answer_choice = self.question_entry.currentText()
        self._reload_advanced()

    # ---------------------------------------------------------------- 时钟
    def update_time(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.time_label.setText(f'当前时间: {now}')
        if self.timer_active and not self.process_condition \
                and self.timer_start_time in now:
            self.start()
        if self.timer_active and self.process_condition \
                and self.timer_end_time in now:
            self.close_program()
        QTimer.singleShot(1000, self.update_time)

    def closeEvent(self, event):
        """关闭窗口时终止后台子进程"""
        if self.process is not None:
            try:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass
        event.accept()


# ---------------------------------------------------------------- 入口 ----
def main():
    app = QApplication(sys.argv)
    app.setApplicationName('学习通刷课助手')
    win = StartWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()