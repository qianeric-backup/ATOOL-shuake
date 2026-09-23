#!/usr/bin/env bash
# wine 交叉打包 知到刷课助手（AutovisorCLI/GUI exe），产物 Autovisor-*.exe
# 结构参照 学习通刷课/wine-build/build.sh：
#   - 构建目录使用 ASCII 路径规避 wine 中文路径问题
#   - 运行时用户数据（config.ini/cookies 等）绝不打包
# 用法: bash wine-build/build.h [--init]   # --init 重新初始化 prefix
set -e
cd "$(dirname "$0")"

export HOME="$PWD/home" XDG_CACHE_HOME="$PWD/cache" WINEPREFIX="$PWD/prefix"
export WINEDLLOVERRIDES="mscoree,mshtml=" WINEDEBUG=-all PIP_DEFAULT_TIMEOUT=120
PY="$PWD/prefix/drive_c/py311/python.exe"
PYVER="3.11.9"

# 1. Windows Python 首次部署（prefix 缺失时）
if [ ! -f "$PY" ]; then
    echo "首次部署: 下载并安装 Windows Python $PYVER 到 wine prefix..."
    mkdir -p "$PWD/home/.cache" "$PWD/prefix"
    INSTALLER="$PWD/home/.cache/python-$PYVER-amd64.exe"
    if [ ! -s "$INSTALLER" ]; then
        curl -L -o "$INSTALLER" \
            "https://www.python.org/ftp/python/$PYVER/python-$PYVER-amd64.exe"
    fi
    wine "$PY" /quiet InstallAllUsers=0 TargetDir='C:\py311' PrependPath=0 \
        Include_test=0 Include_launcher=0 || true
    [ -f "$PY" ] || { echo "python.exe 未就绪, 重试一次"; wine "$PWD/home/.cache/python-$PYVER-amd64.exe" /quiet InstallAllUsers=0 TargetDir='C:\py311' Include_test=0 Include_launcher=0; }
fi

# 2. 同步源码（ASCII 路径；用户数据不进 exe；配置以空模板替代）
rm -rf src dist_out && mkdir -p src
rsync -a --exclude='__pycache__' \
      --exclude='.playwright_browsers' --exclude='.pw-browsers' \
      --exclude='deb-build' --exclude='wine-build' \
      --exclude='logs' --exclude='dist' --exclude='build' \
      --exclude='config.ini' --exclude='data/cookies.json' \
      --exclude='*.zip' --exclude='*.deb' --exclude='*.exe' \
      ../ src/
# 首启空白配置（凭据无所给，构造后用户在 GUI 中填写）
cp ../config.ini.example src/config.ini.example 2>/dev/null || true

# 3. 依赖安装（幂等；PySide6 必须钉 6.9 —— 6.11+ 缺 icuuc.dll 无法在真机启动）
#    playwright python wheel 打入 exe；浏览器二进制首次运行在目标机下载
if ! wine "$PY" -c "import PyInstaller, PySide6, requests, playwright, numpy, cv2" 2>/dev/null; then
    echo "安装构建依赖到 wine prefix..."
    wine "$PY" -m pip install --upgrade pip -q
    wine "$PY" -m pip install -q \
        "pyinstaller>=6.5" "PySide6==6.9.*" requests playwright \
        numpy==1.26.4 opencv-python==4.10.0.82
fi

# 4. PyInstaller spec（onefile GUI 即 qt_gui）— 在 src/ 内构建（相对路径可控）
cd src
cat > "AutovisorGUI.spec" <<'SPEC'
# -*- mode: python ; coding: utf-8 -*-
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
SPEC

wine "$PY" -m PyInstaller "AutovisorGUI.spec" --noconfirm --clean

# 5. 产物归档（exe 放 Autovisor-main/ 项目根；构建中间件留在 wine-build/src）
cp -f dist/AutovisorGUI.exe ../../AutovisorGUI.exe
ls -la ../../AutovisorGUI.exe
echo "完成: AutovisorGUI.exe -> ../../AutovisorGUI.exe"
