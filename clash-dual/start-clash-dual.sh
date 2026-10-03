#!/usr/bin/env bash
# ============================================================
#  双 clash 进程启动脚本（Linux / macOS）
#  前提：mihomo（或 clash）在 PATH 中；mihomo -v 可验证
#
#  启动后两个独立进程：
#    clash-cn  -> 端口 7890  国内直连（学习通/题库）
#    clash-ai  -> 端口 7892  国外节点（AI 模型接口）
#
#  学习通刷课工具设置页 -> 「AI 代理」填 http://127.0.0.1:7892
# ============================================================
set -e
cd "$(dirname "$0")"

command -v mihomo >/dev/null 2>&1 || { echo "未找到 mihomo，请先安装并加入 PATH"; exit 1; }

echo "启动 国内直连实例 (clash-cn.yaml, 端口 7890) ..."
nohup mihomo -d "$PWD" -f "$PWD/clash-cn.yaml" >/dev/null 2>&1 &

echo "启动 国外 AI 实例 (clash-ai.yaml, 端口 7892) ..."
nohup mihomo -d "$PWD" -f "$PWD/clash-ai.yaml" >/dev/null 2>&1 &

echo "两个 clash 进程已启动。"
echo "  - 学习通刷课设置 -> AI 代理: http://127.0.0.1:7892"
echo "  - 停止: pkill -f 'mihomo.*clash-'"
