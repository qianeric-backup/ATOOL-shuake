@echo off
rem ============================================================
rem  双 clash 进程启动脚本（Windows）
rem  前提：本目录下有 mihomo.exe（或把 mihomo.exe 路径改到你的安装位置）
rem
rem  启动后两个独立进程：
rem    clash-cn  -> 端口 7890  国内直连（学习通/题库）
rem    clash-ai  -> 端口 7892  国外节点（AI 模型接口）
rem
rem  学习通刷课工具设置页 -> 「AI 代理」填 http://127.0.0.1:7892
rem ============================================================
setlocal

if not exist mihomo.exe (
    echo [错误] 本目录缺少 mihomo.exe，请从 https://github.com/MetaCubeX/mihomo/releases 下载
    echo        并放到本目录（或修改下方 start 命令中的路径）
    pause
    exit /b 1
)

echo 启动 国内直连实例 (clash-cn.yaml, 端口 7890) ...
start "clash-cn" mihomo.exe -d "%~dp0" -f "%~dp0clash-cn.yaml"

echo 启动 国外 AI 实例 (clash-ai.yaml, 端口 7892) ...
start "clash-ai" mihomo.exe -d "%~dp0" -f "%~dp0clash-ai.yaml"

echo.
echo 两个 clash 进程已启动。
echo   - 学习通刷课设置 -> AI 代理: http://127.0.0.1:7892
echo   - 若 7890/7892 端口被占用，请修改对应 yaml 的 mixed-port 与工具里的 AI 代理地址
pause
