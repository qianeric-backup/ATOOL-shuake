#!/usr/bin/env bash
# 构建 Linux deb 安装包（xuexitong-shuake）
# 结构：程序（源码+.pylibs 依赖随包，离线可用）装 /opt，
#       首启同步到 ~/.local/share/xuexitong-shuake（可写数据目录）
# 用法: bash 学习通刷课/deb-build/build.sh
set -e
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"           # 学习通刷课/
export DEB_SRC="$ROOT/shuake_src"
VER="26.09.16-1"
PKG="xuexitong-shuake_${VER}_amd64"
WORK="pkg/$PKG"

rm -rf pkg "$ROOT/../学习通刷课/dist/${PKG}.deb" 2>/dev/null || true
mkdir -p "$WORK/DEBIAN" \
         "$WORK/opt/xuexitong-shuake" \
         "$WORK/usr/bin" \
         "$WORK/usr/share/applications" \
         "$WORK/usr/share/icons/hicolor/256x256/apps" \
         "$WORK/usr/share/doc/xuexitong-shuake"

# 1) 程序树（源码 + 依赖库），排除运行时用户数据
rsync -a --exclude='.pylibs/__pycache__' --exclude='__pycache__' \
      --exclude='task/tool/cookies.pkl' --exclude='task/tool/account_info.json' \
      --exclude='task/tool/course_name.json' --exclude='error.log' \
      --exclude='task/record' --exclude='*.spec' --exclude='build' --exclude='dist' \
      "$ROOT/shuake_src/" "$WORK/opt/xuexitong-shuake/shuake_src/"
mkdir -p "$WORK/opt/xuexitong-shuake/geckodriver"
cp "$ROOT/geckodriver/geckodriver" "$WORK/opt/xuexitong-shuake/geckodriver/"
chmod +x "$WORK/opt/xuexitong-shuake/geckodriver/geckodriver"

# 首启空白配置模板（同步时目标缺 account_info.json 则落位；凭据不进包）
cat > "$WORK/opt/xuexitong-shuake/account_info.template.json" <<'EOF'
{
  "browser": "", "driver_path": "", "phone_number": "", "password": "",
  "cour": [], "choice": "AI 智能答题", "after_finish_question": "仅自动保存",
  "video_title_choice": "随机答题", "discussion_choice": "跳过讨论",
  "API": "", "API_URL": "", "API_MODEL": "", "speed": "1",
  "homework": "手动选择", "task_type": "作业", "radio_var": 2,
  "font_type": "Helvetica", "font_size": "13",
  "pass_face": 1, "lock_screen": 1, "debug_mode": 1, "uxue_inject": 0,
  "theme": "明亮"
}
EOF

# 2) 同步脚本 + 启动 wrapper
cat > "$WORK/opt/xuexitong-shuake/sync_data.py" <<'PYEOF'
#!/usr/bin/env python3
"""同步程序文件到用户可写目录（~/.local/share/xuexitong-shuake）。
用户数据（账号配置/cookies/课程缓存/记录/日志）只增不覆盖。"""
import os, shutil, sys

SRC = os.environ.get('XUEXITONG_SRC', '/opt/xuexitong-shuake')
DST = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/.local/share/xuexitong-shuake')
USER_FILES = ('task/tool/cookies.pkl', 'task/tool/account_info.json',
              'task/tool/course_name.json', 'error.log')


def ignored(rel):
    rel = rel.replace(os.sep, '/')
    if rel in USER_FILES:
        return True
    if rel.startswith('task/record/'):
        return True
    return False


def sync(src_root, dst_root):
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
    sync(os.path.join(SRC, 'shuake_src'), os.path.join(DST, 'shuake_src'))
    sync(os.path.join(SRC, 'geckodriver'), os.path.join(DST, 'geckodriver'))
    # 首启：落位空白配置模板（真实配置由 GUI 保存后生成，此后不被覆盖）
    acc = os.path.join(DST, 'shuake_src', 'task', 'tool', 'account_info.json')
    if not os.path.exists(acc):
        tpl = os.path.join(SRC, 'account_info.template.json')
        os.makedirs(os.path.dirname(acc), exist_ok=True)
        shutil.copy2(tpl, acc)
        print('已生成默认配置:', acc)
PYEOF

cat > "$WORK/usr/bin/xuexitong-shuake" <<'SHEOF'
#!/usr/bin/env bash
# 学习通刷课（学习助手）Linux 启动器
APP_ROOT="${XUEXITONG_HOME:-$HOME/.local/share/xuexitong-shuake}"
python3 /opt/xuexitong-shuake/sync_data.py "$APP_ROOT" || exit 1
cd "$APP_ROOT/shuake_src" || exit 1
export DISPLAY="${DISPLAY:-:0.0}"
export PYTHONPATH="$PWD/.pylibs"
export LD_LIBRARY_PATH="$PWD/.syslib/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec python3 qt_ui.py "$@"
SHEOF
chmod +x "$WORK/usr/bin/xuexitong-shuake" "$WORK/opt/xuexitong-shuake/sync_data.py"

# 3) 图标（ico → png）与桌面项
python3 - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.environ['DEB_SRC'], '.pylibs'))
from PIL import Image
img = Image.open(os.path.join(os.environ['DEB_SRC'], 'task/img/xuexitong1 .ico'))
img.save('pkg/xuexitong-shuake_26.09.16-1_amd64/usr/share/icons/hicolor/256x256/apps/xuexitong-shuake.png')
print('icon ok', img.size)
PYEOF
cat > "$WORK/usr/share/applications/xuexitong-shuake.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=学习助手
Comment=学习通课程自动学习助手（章节/作业/考试）
Exec=xuexitong-shuake
Icon=xuexitong-shuake
Terminal=false
Categories=Network;Education;
StartupWMClass=学习助手
DESK

# 4) 控制文件与文档
cat > "$WORK/DEBIAN/control" <<'CTRL'
Package: xuexitong-shuake
Version: 26.09.16-1
Section: net
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10)
Installed-Size: 61440
Maintainer: qianeric-backup <qianeric-backup@users.noreply.github.com>
Description: 学习通自动学习助手（学习助手）
 章节视频/文档自动学习、测验与作业/考试自动作答、AI 智能答题
 （任意 OpenAI 兼容接口）、字体解密防乱码、无头静默模式、
 uXueScript 注入模式。Python 依赖随包内置，安装后离线可用。
 需自行安装匹配版本的浏览器驱动或联网自动下载。
CTRL
cp "$ROOT/shuake_src/README.md" "$WORK/usr/share/doc/xuexitong-shuake/"
cat > "$WORK/usr/share/doc/xuexitong-shuake/copyright" <<'C'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: xuexitong-shuake
Source: https://github.com/qianeric-backup/ATOOL-shuake

Files: *
Copyright: 2025 Mortal004 (原项目) / qianeric-backup (修改版)
License: 其余权利受项目 LICENSE 约束；uXueScript 组件为 GPL-3.0-only
C

# 5) 构建
fakeroot dpkg-deb --build --root-owner-group "$WORK" "pkg/${PKG}.deb"
dpkg-deb -I "pkg/${PKG}.deb" | head -8
echo "完成: 学习通刷课/deb-build/pkg/${PKG}.deb"
