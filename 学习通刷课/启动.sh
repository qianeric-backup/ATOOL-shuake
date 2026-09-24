#!/usr/bin/env bash
# 一键启动（Linux/macOS 通用，Windows 请直接双击 exe）
# 用法: bash run_linux.sh
set -e

# 0. 定位源码目录（本脚本位于 Linux版/学习通刷课/，源码在同目录 shuake_src/）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/shuake_src"
[ -f "$SRC_DIR/qt_ui.py" ] || { echo "未找到源码: $SRC_DIR/qt_ui.py"; exit 1; }

# 1. 检查 Python
command -v python3 >/dev/null 2>&1 || { echo "未找到 python3，请先安装 Python 3"; exit 1; }

# 2. libxcb-cursor 兜底（PySide6 xcb 插件依赖；系统缺失时使用用户目录副本）
if [ -d "$HOME/.local/lib/xcblibs/pkg/usr/lib/x86_64-linux-gnu" ]; then
    export LD_LIBRARY_PATH="$HOME/.local/lib/xcblibs/pkg/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi

# 3. 依赖检查（缺失时提示安装；在源码目录内检查——项目自带
#    sitecustomize/mouseinfo 兼容层需位于 sys.path 才能生效）
MISSING=""
cd "$SRC_DIR"
for m in selenium pyautogui PySide6 requests; do
    python3 -c "import $m" >/dev/null 2>&1 || MISSING="$MISSING $m"
done
if [ -n "$MISSING" ]; then
    echo "缺少依赖:$MISSING"
    echo "请先运行: pip install -r requirements.txt"
    exit 1
fi

# 4. 浏览器驱动检查（Linux 用系统 PATH 中的驱动名）
    for d in chromedriver geckodriver msedgedriver; do
        if command -v $d >/dev/null 2>&1; then echo "驱动 $d 已就绪"; fi
    done
    command -v chromedriver >/dev/null 2>&1 || \
        echo "提示: 未找到 chromedriver，请在设置里填写驱动地址"

# 5. 启动
echo "启动 学习通刷课（Qt 版） ..."
python3 qt_ui.py
