#!/usr/bin/env bash
# 一键启动（Linux/macOS 通用，Windows 请直接双击 exe）
# 用法: bash run_linux.sh
set -e

# 0. 定位源码目录（本脚本位于 Linux版/知到刷课(Autovisor)/，源码在仓库根 知到刷课/autovisor-src/Autovisor-main/）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/../../知到刷课/autovisor-src/Autovisor-main"
[ -f "$SRC_DIR/qt_gui.py" ] || { echo "未找到源码: $SRC_DIR/qt_gui.py"; exit 1; }

# 1. 检查 Python
command -v python3 >/dev/null 2>&1 || { echo "未找到 python3，请先安装 Python 3"; exit 1; }

# 2. libxcb-cursor 兜底（PySide6 xcb 插件依赖；系统缺失时使用用户目录副本）
if [ -d "$HOME/.local/lib/xcblibs/pkg/usr/lib/x86_64-linux-gnu" ]; then
    export LD_LIBRARY_PATH="$HOME/.local/lib/xcblibs/pkg/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi

# 3. 依赖检查（缺失时提示安装）
MISSING=""
for m in playwright PySide6 requests; do
    python3 -c "import $m" >/dev/null 2>&1 || MISSING="$MISSING $m"
done
if [ -n "$MISSING" ]; then
    echo "缺少依赖:$MISSING"
    echo "请先运行: pip install -r requirements.txt"
    exit 1
fi

# 4. 浏览器驱动检查（Linux 用系统 PATH 中的驱动名）
    # 知到刷课使用 Playwright（自带浏览器驱动管理）
    python3 -m playwright install --dry-run >/dev/null 2>&1 || \
        echo "提示: 首次运行请执行 python3 -m playwright install firefox"

# 5. 启动
echo "启动 知到刷课（Autovisor） ..."
cd "$SRC_DIR"
python3 qt_gui.py
