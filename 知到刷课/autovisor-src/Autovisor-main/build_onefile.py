# encoding=utf-8
"""Autovisor 单文件(onefile)打包脚本。

将以下内容打进单 exe:
  - 源码与 Playwright driver(含 node.exe);
  - res/stealth.min.js、QRcode.jpg、zhs.ico;
  - 默认 configs.ini(首次运行时复制到 exe 旁, 方便用户直接编辑)。

体积精简: 不再 --collect-all PySide6, 仅由 PyInstaller 的 PySide6 hook
自动收集实际 import 的 QtCore/QtGui/QtWidgets 与必要插件。
"""
import os
import shutil
import sys

import PyInstaller.__main__

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "AutovisorGUI"
RES = os.path.join(HERE, "res")
DIST = os.path.join(HERE, "dist")

# 定位 playwright driver(含 node.exe 与 package/ 目录)
import playwright
PW_DRIVER = os.path.join(os.path.dirname(playwright.__file__), "driver")
assert os.path.exists(os.path.join(PW_DRIVER, "node.exe")), (
    f"未找到 playwright driver: {PW_DRIVER}"
)

datas = [
    (RES, "res"),  # stealth.min.js / QRcode.jpg / zhs.ico
    (os.path.join(HERE, "configs.ini"), "."),
    (PW_DRIVER, "playwright/driver"),
]

args = [
    "--name", NAME,
    "--onefile",           # 单 exe
    "--windowed",          # 无控制台黑框, GUI 模式
    "--noconfirm",
    "--clean",
    "--log-level=INFO",
    "--icon", os.path.join(RES, "zhs.ico"),
    "--collect-all", "playwright",   # 连同 driver 一起打入
    "--noupx",
]
# 说明: 去掉 --collect-all PySide6 后, PyInstaller 的 PySide6 hook 会自动
# 只收集 qt_gui.py 实际 import 的模块(QtCore/QtGui/QtWidgets 及其必需插件),
# 不再打入 QtWebEngine / Qt3D / QML / 翻译文件等无用组件, 显著减小体积。

for src, dest in datas:
    args += ["--add-data", f"{src}{os.pathsep}{dest}"]

args.append(os.path.join(HERE, "qt_gui.py"))

sys.argv = ["pyinstaller"] + args
PyInstaller.__main__.run()

# 清理构建中间目录, 只保留 dist 下的单 exe
build_dir = os.path.join(HERE, "build")
if os.path.exists(build_dir):
    shutil.rmtree(build_dir, ignore_errors=True)
spec_file = os.path.join(HERE, NAME + ".spec")
if os.path.exists(spec_file):
    os.remove(spec_file)

exe = os.path.join(DIST, NAME + ".exe")
print(f"\n打包完成: {exe}  大小: {os.path.getsize(exe) / 1024 / 1024:.1f} MB")