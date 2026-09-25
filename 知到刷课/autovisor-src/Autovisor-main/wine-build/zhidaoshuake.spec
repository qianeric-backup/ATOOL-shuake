# -*- mode: python ; coding: utf-8 -*-
# Windows/GitHub Actions 与 wine 通用 onefile GUI 构建清单
# 运行工作目录 = 打包源码目录 (wine-build/src，或 CI 复制的等价目录)
from PyInstaller.utils.hooks import collect_data_files
block_cipher = None

a = Analysis(['qt_gui.py'],
             pathex=['.'],
             binaries=[],
             datas=[
                ('resources', 'resources'),
                ('data/mirrors.json', 'data'),
                ('config.ini.example', '.'),
                # playwright 自带的 node/js driver 二进制需要连包散发给 exe
                # （Windows 上 Edge/Chrome 走 channel 直接访问系统浏览器编译），
                # 否则 exe 单独跑会报 playwright 未就绪
                *collect_data_files('playwright', include_py_files=True),
             ],
             # PIL(modules/support.py) 与 pygetwindow(modules/utils.py, win32 分支)
             # 是条件/延迟导入; Pillow/pygetwindow 未安装时静态分析会静默跳过,
             # 导致 exe 启动 ModuleNotFoundError, 故依赖必须在构建环境装齐
             hiddenimports=['requests', 'pygetwindow'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['tkinter'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
          name='zhidaoshuake',
          console=False,
          clean_dir=True)
