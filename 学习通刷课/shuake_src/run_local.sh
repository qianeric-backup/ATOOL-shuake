#!/usr/bin/env bash
# 本机一键启动 学习通刷课（Qt 版）
# 解决两个环境问题：
#   1. .pylibs  —— openai 装在项目内（系统 Python 受 PEP 668 保护，~/.local 只读）
#   2. .syslib  —— libxcb-cursor0 未装系统库，从 deb 解包到项目内，LD_LIBRARY_PATH 引用
# 用法: bash run_local.sh
set -e
cd "$(dirname "$0")"

export DISPLAY="${DISPLAY:-:0.0}"
export PYTHONPATH="$PWD/.pylibs"
export LD_LIBRARY_PATH="$PWD/.syslib/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec python3 qt_ui.py
