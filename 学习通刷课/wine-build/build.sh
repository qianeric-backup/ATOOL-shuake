#!/usr/bin/env bash
# wine 交叉打包 学习通刷课.exe（Windows x64）全流程
# 前提：wine 已安装；本目录已有初始化好的 prefix（含 Windows Python 3.11 + 依赖）
# 用法: bash wine-build/build.sh
set -e
cd "$(dirname "$0")"

export HOME="$PWD/home" XDG_CACHE_HOME="$PWD/cache" WINEPREFIX="$PWD/prefix"
export WINEDLLOVERRIDES="mscoree,mshtml=" WINEDEBUG=-all PIP_DEFAULT_TIMEOUT=120
PY="$PWD/prefix/drive_c/py311/python.exe"

# 1. 同步源码到 ASCII 构建目录（wine 对中文路径偶发问题，规避之）
#    运行时用户数据（账号密码/cookies/课程缓存）绝不进 exe；
#    account_info.json 以空白模板替代（GUI 首启由用户填写）
rm -rf src dist_out && mkdir -p src
rsync -a --exclude='.pylibs' --exclude='.syslib' --exclude='__pycache__' \
      --exclude='MicrosoftEdge' --exclude='msedgedriver' --exclude='geckodriver' \
      --exclude='dist' --exclude='build' \
      --exclude='task/tool/cookies.pkl' \
      --exclude='task/tool/account_info.json' \
      --exclude='task/tool/course_name.json' \
      ../shuake_src/ src/
cat > src/task/tool/account_info.json <<'EOF'
{
  "browser": "",
  "driver_path": "",
  "phone_number": "",
  "password": "",
  "cour": [],
  "choice": "AI 智能答题",
  "after_finish_question": "仅自动保存",
  "video_title_choice": "随机答题",
  "discussion_choice": "跳过讨论",
  "API": "",
  "API_URL": "",
  "API_MODEL": "",
  "speed": "1",
  "homework": "手动选择",
  "task_type": "章节",
  "radio_var": 1,
  "font_type": "Helvetica",
  "font_size": "13",
  "pass_face": 1,
  "lock_screen": 1,
  "debug_mode": 1,
  "uxue_inject": 0,
  "theme": "明亮"
}
EOF

# 2. 依赖检查（首次搭建 prefix 时用；日常重打包可跳过）
#    wine "$PY" -m pip install pyinstaller selenium requests colorama openai \
#        pyautogui pillow fonttools "PySide6==6.9.*"
#    注意：必须钉住 PySide6==6.9.*——6.11 的 Qt6Core.dll 引入 icuuc.dll 依赖，
#    且 wheel 不附带，真机 Windows 上 exe 会因缺 DLL 无法启动。

# 3. 打包（onefile，产物 dist/学习通刷课.exe）
cd src && wine "$PY" -m PyInstaller "学习通刷课.spec" --noconfirm --clean

# 4. 归档产物
cd .. && mkdir -p ../dist && cp src/dist/学习通刷课.exe ../dist/学习通刷课.exe
echo "完成：学习通刷课/dist/学习通刷课.exe"

# 5.（可选）wine 试运行验证：直接跑会因 wine↔XFCE 窗管交互卡死，
#    需用虚拟桌面模式：
#    cd src/dist && wine explorer /desktop=shuake,1600x900 学习通刷课.exe
