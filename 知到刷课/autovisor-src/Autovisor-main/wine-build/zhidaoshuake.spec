# -*- mode: python ; coding: utf-8 -*-
# Windows/GitHub Actions 与 wine 通用 onefile GUI 构建清单
# 运行工作目录 = 打包源码目录 (wine-build/src, 或 CI 复制的等价目录)
import os
import sys

from PyInstaller.utils.hooks import collect_data_files
block_cipher = None

# cv2(abi3 扩展)依赖 python3.dll, PyInstaller 不保证收集 -> 显式带上,
# 否则 packages/ 里下载的 cv2 会报 "DLL load failed while importing cv2"
_python3_dll = os.path.join(sys.base_prefix, 'python3.dll')
_binaries = [(_python3_dll, '.')] if os.path.isfile(_python3_dll) else []

a = Analysis(['qt_gui.py'],
             pathex=['.'],
             binaries=_binaries,
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
             # numpy/cv2 必须排除: 自动滑块依赖由 modules.installer 在首次运行时
             # 下载到 exe 旁的 packages/, 打进 exe 会与下载副本冲突
             # (numpy.core.multiarray failed to import); 上游 build.py 同样排除
             excludes=['tkinter', 'numpy', 'cv2'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
          name='zhidaoshuake',
          console=False,
          clean_dir=True)
