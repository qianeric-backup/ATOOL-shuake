#!/usr/bin/env bash
# 仓库根目录一键启动入口（Linux/macOS）
#   ./start.sh            # 交互式菜单
#   ./start.sh 1|2|3      # 直接指定: 1=学习通 2=云班课 3=知到
#   或直接运行:  ./启动-学习通.sh / ./启动-云班课.sh / ./启动-知到.sh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

menu() {
clear
cat <<MENU
================================================
  刷课软件合集 — 一键启动
  $(basename "$ROOT")

  1) 学习通刷课        (qt 窗口 + Selenium)
  2) 云班课刷课助手    (纯 API, 无需浏览器驱动)
  3) 知到刷课(Autovisor)  (playwright 浏览器)
  q) 退出
MENU
printf "请选择 [1/2/3/q] > "
}

run() {
    case "$1" in
        1) bash "$ROOT/学习通刷课/启动.sh" ;;
        2) bash "$ROOT/云班课刷课/启动.sh" ;;
        3) bash "$ROOT/知到刷课/启动.sh" ;;
        *) return ;;
    esac
}

if [ -n "$1" ]; then
    echo "直接启动: $1"
    run "$1"
    exit
fi

while true; do
    menu
    read -r pick
    case "$pick" in
        q|Q|退出) echo "bye"; exit 0 ;;
        *) run "$pick" ;;
    esac
done
