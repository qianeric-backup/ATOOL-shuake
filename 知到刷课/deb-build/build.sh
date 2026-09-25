#!/usr/bin/env bash
# 构建 Linux deb 安装包（知到刷课助手）
# 结构：程序（源码 + vendor(PySide6/playwright/requests) + packages(numpy/cv2)
#       等运行时依赖随包，安装后离线可用）装 /opt；
#       首启同步到 ~/.local/share/autovisor-zhihuishu（可写数据目录）
# 用法: bash 知到刷课/deb-build/build.sh
set -e
cd "$(dirname "$0")"
ROOT="$(cd ../autovisor-src/Autovisor-main && pwd)"   # Autovisor-main/
REPO="$(cd "$ROOT/../../.." && pwd)"       # 仓库根
SRC="$ROOT"
VER="3.18.3-1"
PKG_NAME="zhidao-shuake"
PKG="${PKG_NAME}_${VER}_amd64"
WORK="pkg/$PKG"
VENDOR="$WORK/opt/$PKG_NAME/vendor"
PYGLOBAL_LIBS=/tmp/pylibs                  # pytest 等（不打入包）

rm -rf "$WORK" 2>/dev/null || true
mkdir -p pkg
mkdir -p "$WORK/DEBIAN" \
         "$WORK/opt/$PKG_NAME" \
         "$WORK/usr/bin" \
         "$WORK/usr/share/applications" \
         "$WORK/usr/share/icons/hicolor/256x256/apps" \
         "$WORK/usr/share/doc/$PKG_NAME"

# 1) 程序树（源码 + resources/data/packages），排除运行时用户数据
rsync -a --exclude='__pycache__' \
      --exclude='logs' \
      --exclude='configs.ini' \
      --exclude='data/cookies.json' \
      --exclude='packages/numpy/_pyinstaller' \
      --exclude='packages/numpy/_pytesttester.py' \
      --exclude='packages/numpy/tests' \
      --exclude='config.ini' \
      --exclude='.playwright_browsers' \
      --exclude='.pw-browsers' \
      --exclude='*.deb' \
      --exclude='.pytest_cache' \
      --exclude='res/opencv_python.libs' \
      --exclude='res/cv2' \
      --exclude='res/numpy' \
      --exclude='res/numpy.libs' \
      --exclude='res/numpy-*.dist-info' \
      --exclude='res/opencv_python-*.dist-info' \
      --exclude='res/cookies.json' \
      --exclude='res/bin' \
      --exclude='tests' \
      --exclude='.github' \
      --exclude='uv.lock' \
      --exclude='deb-build' \
      --exclude='.runtime_libs' \
      --exclude='*.zip' \
      --exclude='*.deb' \
      "$SRC/" "$WORK/opt/$PKG_NAME/"

# 2) Python 运行依赖（PySide6 / playwright / requests 引入重 wheel）——
#    直接 pip install --target 到包内 vendor 目录，安装后离线可用
VENDOR="$WORK/opt/$PKG_NAME/vendor"
if [ ! -d "$VENDOR/PySide6" ] || [ ! -d "$VENDOR/playwright" ] || [ ! -d "$VENDOR/requests" ]; then
  # 只装 Essentials（QtWidgets 等），不带 WebEngine 等 Addons 大件
  pip install --target "$VENDOR" \
      "PySide6-Essentials>=6.6,<7" "playwright>=1.40" "requests" \
      -i https://mirrors.aliyun.com/pypi/simple/ -q --break-system-packages 2>&1 | tail -2
  # playwright 的浏览器二进制不入 deb（PLAYWRIGHT_BROWSERS_PATH 由首启装到
  # ~/.cache/ms-playwright），只保留 python 包
fi
# 清 _MEI 之类的临时目录与 pip 元数据缓存
find "$VENDOR" -maxdepth 2 -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

# 3) sync_data.py: 程序文件同步到用户可写目录（用户数据只增不覆盖）
cat > "$WORK/opt/$PKG_NAME/sync_data.py" <<'PYEOF'
#!/usr/bin/env python3
"""同步程序文件到 ~/.local/share/autovisor-zhihuishu。
用户数据（config.ini / cookies.json / logs）只增不覆盖。"""
import os, shutil, sys

SRC = os.environ.get('AUTOVISOR_SRC', f'/opt/autovisor-zhihuishu')
DST = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/.local/share/autovisor-zhihuishu')
USER_FILES = ('config.ini', 'data/cookies.json')


def ignored(rel):
    rel = rel.replace(os.sep, '/')
    if rel in USER_FILES:
        return True
    if rel.startswith('logs/') or rel == 'logs':
        return True
    if rel.endswith('.pyc') or '__pycache__' in rel:
        return True
    return False


def sync(src_root, dst_root):
    if not os.path.isdir(src_root):
        return
    for root, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        rel = os.path.relpath(root, src_root)
        dst_dir = dst_root if rel == '.' else os.path.join(dst_root, rel)
        os.makedirs(dst_dir, exist_ok=True)
        for f in files:
            relf = f if rel == '.' else os.path.normpath(os.path.join(rel, f))
            if ignored(relf):
                continue
            src_f = os.path.join(root, f)
            dst_f = os.path.join(dst_dir, f)
            if (not os.path.exists(dst_f)
                    or os.path.getmtime(src_f) > os.path.getmtime(dst_f)):
                shutil.copy2(src_f, dst_f)


if __name__ == '__main__':
    sync(SRC, DST)
    # 首启：落位配置模板（真实配置由 GUI 保存后生成，此后不被覆盖）
    cfg = os.path.join(DST, 'config.ini')
    if not os.path.exists(cfg):
        tpl = os.path.join(SRC, 'config.ini.example')
        if os.path.exists(tpl):
            shutil.copy2(tpl, cfg)
            print('已生成默认配置:', cfg)
PYEOF
chmod +x "$WORK/opt/$PKG_NAME/sync_data.py"

# 4) 启动 wrapper（/usr/bin/autovisor-zhihuishu）
cat > "$WORK/usr/bin/$PKG_NAME" <<'SHEOF'
#!/usr/bin/env bash
# 知到刷课助手 Linux 启动器
APP_ROOT="${AUTOVISOR_HOME:-$HOME/.local/share/autovisor-zhihuishu}"
/usr/bin/python3 /opt/autovisor-zhihuishu/sync_data.py "$APP_ROOT" || exit 1
cd "$APP_ROOT" || exit 1
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
export PYTHONPATH="$APP_ROOT/vendor"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
# playwright 浏览器组件首次运行自动安装（联网）；失败不阻塞窗口，可重试
if [ ! -d "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell-1200" ] && \
   [ ! -d "$PLAYWRIGHT_BROWSERS_PATH/chromium-1200" ]; then
    echo "首次运行: 正在安装 playwright 浏览器组件, 请联网等待..." >&2
    python3 -m playwright install firefox chromium 2>&1 | tail -1 || true
fi
exec python3 qt_gui.py "$@"
SHEOF
chmod +x "$WORK/usr/bin/$PKG_NAME"

# 5) 图标 + 桌面项
ICON_PNG="$WORK/usr/share/icons/hicolor/256x256/apps/$PKG_NAME.png"
python3 - "$SRC/res/zhs.ico" "$ICON_PNG" <<'PYEOF'
import sys, os
sys.path.insert(0, os.environ.get('VENDOR_PATH', '/dev/null'))
try:
    from PIL import Image  # 若无 PIL 走 PySide6/无 → 手写 ico png 转换
    img = Image.open(sys.argv[1]); img.save(sys.argv[2])
    print('icon png OK')
except Exception as e:
    print('icon 转换失败(可用 ImageMagick 或忽略):', e)
    sys.exit(0)
PYEOF
if [ ! -s "$ICON_PNG" ]; then
  # 用 vendor 内 PySide6 把 ico 转 png（离线方案）
  PYTHONPATH="$VENDOR" python3 - "$SRC/res/zhs.ico" "$ICON_PNG" <<'PYEOF'
import sys
from PySide6.QtGui import QIcon, QImage, QImageReader
import PySide6.QtGui as Qtg
ico_path, out_path = sys.argv[1], sys.argv[2]
reader = QImageReader(ico_path)
img = None; best = 0
icon = QIcon(ico_path)
sizes = [s for s in icon.availableSizes()] or []
if sizes:
    img = icon.pixmap([s for s in sizes if max(s.width(), s.height()) <= 256][-1
                     ] if sizes else (256, 256)).toImage()
if img is None or img.isNull():
    print('icon 转换失败(ico 不可读)')
    import sys; sys.exit(0)
img.save(out_path)
print('icon png:', out_path)
PYEOF
fi
cat > "$WORK/usr/share/applications/$PKG_NAME.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=知到刷课助手
Comment=智慧树知到课程自动学习助手（课中弹题 AI 答题）
Exec=autovisor-zhihuishu
Icon=autovisor-zhihuishu
Terminal=false
Categories=Network;Education;
StartupWMClass=知到刷课助手
DESK

# 6) 控制文件与文档
cat > "$WORK/DEBIAN/control" <<'CTRL'
Package: autovisor-zhihuishu
Version: 3.18.3-1
Section: net
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-requests
Installed-Size: 600000
Maintainer: qianeric-backup <qianeric-backup@users.noreply.github.com>
Description: 知到智慧树自动刷课助手 (上游内核 3.18.3)
 视频自动观看与倍速、课中弹题与课程测试 AI 自动作答（OpenAI 兼容接口,
 可配置/刷新模型列表/连通性测试/随时开关）、滑块验证自动或人工、
 课程卡死自恢复、运行诊断命令 (--check-browser/--check-course)。
 PySide6/playwright/requests 及 numpy、opencv 运行时依赖随包内置。
 浏览器组件首次运行联网自动安装。
CTRL
cp "$SRC/README.md" "$WORK/usr/share/doc/$PKG_NAME/"
cat > "$WORK/usr/share/doc/$PKG_NAME/copyright" <<'C'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: autovisor-zhihuishu
Source: https://github.com/CXRunfree/Autovisor

Files: *
Copyright: 2024-2026 CXRunfree (原项目) / qianeric-backup (本地修改)
License: 项目 LICENSE（GPL-3.0-or-later）
C

# 7) postinst: 生成默认 icon 缓存（桌面文件注册）
cat > "$WORK/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
update-icon-caches /usr/share/icons/hicolor >/dev/null 2>&1 || true
update-desktop-database >/dev/null 2>&1 || true
exit 0
POST
chmod +x "$WORK/DEBIAN/postinst"

# 8) 构建
fakeroot dpkg-deb --build --root-owner-group "$WORK" "pkg/${PKG}.deb"
dpkg-deb -I "pkg/${PKG}.deb" | head -8
du -sh "pkg/${PKG}.deb"
echo "完成: 知到刷课/deb-build/pkg/${PKG}.deb"
