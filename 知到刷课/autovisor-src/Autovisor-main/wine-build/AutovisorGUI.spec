# -*- mode: python ; coding: utf-8 -*-
# Windows/GitHub Actions 与 wine 通用 onefile GUI 构建清单
# 运行工作目录 = 打包源码目录 (wine-build/src，或 CI 复制的等价目录)
block_cipher = None
a = Analysis(['qt_gui.py'],
             pathex=['.'],
             binaries=[],
             datas=[
                ('resources', 'resources'),
                ('data/mirrors.json', 'data'),
                ('config.ini.example', '.'),
             ],
             hiddenimports=['requests'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['tkinter'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
          name='AutovisorGUI',
          console=False,
          clean_dir=True)
