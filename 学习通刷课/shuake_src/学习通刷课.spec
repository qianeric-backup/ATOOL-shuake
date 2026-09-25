# -*- mode: python ; coding: utf-8 -*-
# 学习通刷课 单 exe 打包 spec（Qt/PySide6 精简版）
# 用法: python -m PyInstaller 学习通刷课.spec --noconfirm --clean
#
# 精简说明：不再 collect_all('PySide6')（那会打入整个 Qt 全家桶），
# 只收集本程序真正用到的 Qt 模块（QtCore/QtGui/QtWidgets/QtNetwork），
# 并排除大量用不到的 Qt 附加模块（3D/WebEngine/多媒体/地理/DBus 等），
# 显著减小 exe 体积、加快首次解压与启动速度。

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [('task', 'task')]
binaries = []
hiddenimports = []

# 业务依赖（按需收集，均已 import）
for pkg in ['selenium', 'PIL', 'openai', 'requests', 'pyautogui', 'fontTools', 'colorama']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# PySide6：只收集本项目用到的核心模块（qt_ui 实际 import 了 QtCore/QtGui/QtWidgets/QtNetwork）
hiddenimports += [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtNetwork',
]

# task 子模块全部收集（刷课核心逻辑）
hiddenimports += collect_submodules('task')

# 排除用不到的 Qt 附加模块（体积大头），减小 exe 体积
excludes = [
    'tkinter', 'tkinter.test',
    # Qt 全家桶未使用模块
    'PySide6.Qt3D*', 'PySide6.QtBluetooth', 'PySide6.QtCharts', 'PySide6.QtConcurrent',
    'PySide6.QtDataVisualization', 'PySide6.QtDBus', 'PySide6.QtDesigner',
    'PySide6.QtGraphs*', 'PySide6.QtHelp', 'PySide6.QtHttpServer',
    'PySide6.QtLocation', 'PySide6.QtMultimedia*', 'PySide6.QtNfc',
    'PySide6.QtOpenGL*', 'PySide6.QtPositioning', 'PySide6.QtPrintSupport',
    'PySide6.QtQml*', 'PySide6.QtQuick*', 'PySide6.QtRemoteObjects',
    'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtSerial*',
    'PySide6.QtSpatialAudio', 'PySide6.QtSql', 'PySide6.QtStateMachine',
    'PySide6.QtTest', 'PySide6.QtTextToSpeech', 'PySide6.QtUiTools',
    'PySide6.QtWebChannel', 'PySide6.QtWebEngine*', 'PySide6.QtWebSockets',
    'PySide6.QtWebView', 'PySide6.QtXml', 'PySide6.QtSvgWidgets',
    'PySide6.scripts*', 'PySide6.support*', 'PySide6._config',
]

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='xuexitongshuake',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='task/img/xuexitong1 .ico',
)