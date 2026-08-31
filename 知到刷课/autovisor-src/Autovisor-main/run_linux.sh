#!/usr/bin/env bash
# 一键启动（Linux/macOS 通用，Windows 请直接双击 exe）
# 用法: bash run_linux.sh
set -e

# 1. 检查 Python
command -v python3 >/dev/null 2>&1 || { echo "未找到 python3，请先安装 Python 3"; exit 1; }

# 2. 依赖检查（缺失时提示安装）
MISSING=""
for m in playwright PySide6 requests; do
    python3 -c "import $m" >/dev/null 2>&1 || MISSING="$MISSING $m"
done
if [ -n "$MISSING" ]; then
    echo "缺少依赖:$MISSING"
    echo "请先运行: pip install -r requirements.txt"
    exit 1
fi

# 3. 浏览器驱动检查（Linux 用系统 PATH 中的驱动名）
    # 知到刷课使用 Playwright（自带浏览器驱动管理）
    python3 -m playwright install --dry-run >/dev/null 2>&1 || \
        echo "提示: 首次运行请执行 python3 -m playwright install firefox"

# 4. 启动
echo "启动 知到刷课（Autovisor） ..."
python3 qt_gui.py
