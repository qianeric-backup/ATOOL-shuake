# -*- coding: utf-8 -*-
"""account_info.json 配置路径与读写（唯一入口）。

路径规则：
- 打包态（PyInstaller onefile）：launcher 启动时已 chdir 到 exe 同目录
  并把内置 task/ 资源解压到 exe 同级 —— 配置落在
  <exe同目录>/task/tool/account_info.json，持久化保存、重启保留；
  exe 目录没有配置文件时启动自动生成空白模板（ensure_config）。
- 源码态：cwd 下 task/tool/account_info.json（与旧版行为一致）。

注意：AIAsk 旧实现按 __file__ 定位配置，打包后指向 _MEIPASS 临时解压
目录（只读、每次启动重建），导致用户填的 API/代理配置读不到 ——
所有读写统一走本模块。
"""
import json
import os
import sys

# 空白模板字段（与 wine-build/build.sh 内置模板一致）。
# GUI 首次启动 / 配置缺失时生成，用户填写后持久化到 exe 同级。
DEFAULT_CONFIG = {
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
    "AI_PROXY": "",
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
    "theme": "明亮",
}


def _root():
    """项目根（含 task/ 的那一层）：cwd 优先，其次打包态 exe 目录/源码目录。"""
    cwd = os.getcwd()
    if os.path.isdir(os.path.join(cwd, 'task')):
        return cwd
    if getattr(sys, 'frozen', False):
        # launcher 已 chdir 到 exe 同目录；兜底直接用 exe 所在目录
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_config_path():
    """配置文件完整路径（唯一入口）。"""
    return os.path.join(_root(), 'task', 'tool', 'account_info.json')


def ensure_config():
    """运行目录没有配置文件则生成空白模板。返回 True=本次新建。"""
    path = get_config_path()
    if os.path.isfile(path):
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True


def load_config():
    """读取配置；文件缺失/损坏时生成空白模板并返回空 dict（不抛异常）。"""
    path = get_config_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ensure_config()
        return {}


def save_config(data):
    """写配置到持久化路径（目录自动创建）。"""
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
