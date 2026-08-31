# -*- coding: utf-8 -*-
"""项目测试：语法 + API 类存在性 + 离屏 GUI 全链路（登录-课程-资源回调）。

运行: python -m pytest tests/ -s
"""
import ast
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from yunbanke_qt.main import MainWindow
from yunbanke_qt import api


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_syntax():
    for f in ("api.py", "main.py"):
        src = open(os.path.join(BASE, "yunbanke_qt", f), encoding="utf-8").read()
        ast.parse(src)


def test_api_class():
    assert hasattr(api, "Yunbanke")
    assert hasattr(api.Yunbanke, "login")
    assert hasattr(api.Yunbanke, "list_courses")
    assert hasattr(api.Yunbanke, "list_resources")
    assert hasattr(api.Yunbanke, "report_video_progress")


def test_gui_flow(app):
    win = MainWindow()
    win.show()
    state = {"login": None, "courses": None, "resources": None, "err": None}

    def on_ok(data):
        state["login"] = True
        mp = win.stack.currentWidget()
        mp.courses_loaded.connect(on_courses)

    def on_fail(msg):
        state["err"] = msg
        finish()

    def on_courses(courses):
        state["courses"] = len(courses)
        mp = win.stack.currentWidget()
        if courses:
            mp.lst_courses.setCurrentRow(0)
            mp.load_resources()
            mp.resources_loaded.connect(on_res)
        else:
            finish()

    def on_res(res):
        state["resources"] = len(res)
        finish()

    def finish():
        app.quit()

    win.login_page.login_ok.connect(on_ok)
    win.login_page.login_fail.connect(on_fail)
    win.login_page.edt_account.setText("ACCOUNT_PLACEHOLDER")
    win.login_page.edt_pwd.setText("PASSWORD_PLACEHOLDER")
    from PySide6.QtCore import QTimer

    QTimer.singleShot(300, win.login_page.do_login)
    QTimer.singleShot(20000, finish)   # 超时保护
    app.exec()

    assert state["login"] is True, "登录失败: %s" % state.get("err")
    print("TEST RESULT login=%s courses=%s resources=%s err=%s" % (
        state["login"], state["courses"], state.get("resources"), state.get("err")))
    print("TEST PASS")
    win.close()