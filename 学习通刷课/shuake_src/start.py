# -*- coding: utf-8 -*-
"""
start.py — Qt（PySide6）版 GUI 入口。

本文件由原生 tkinter 版（现备份为 start_tk.py）升级而来：
  * 界面框架改用 PySide6（Qt），提供与旧版一致的页面布局与全部功能：
    主页 / 设置 / 帮助 / 刷课日志 / 测试成绩 / 题库查询 / 报错日志 / 定时刷课 /
    窗口置顶 / 字体调整 / 子进程运行 main.py 并实时显示日志。
  * 配置读写（task/tool/account_info.json 等）格式与旧版完全兼容。
  * 若需使用旧版界面，可把 start_tk.py 改回 start.py（或直接运行 start_tk.py）。

入口：
  python start.py                直接运行（等价于 qt_ui.py）
  launcher.py                    打包态入口（内部调用 start.start_main）
  launcher.py --worker           打包态子进程刷课入口
"""
import sys


def start_main():
    """GUI 入口（供 launcher.py 调用）— 转 Qt 版"""
    import qt_ui
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('学习通刷课')
    win = qt_ui.StartWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    start_main()