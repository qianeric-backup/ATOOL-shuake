# -*- coding: utf-8 -*-
"""
单 exe 启动入口（PyInstaller --onefile 打包用）。

两种模式：
  1. 无 `--worker` 参数：解包内置只读资源到 exe 同目录的 task/，然后启动 GUI（Qt 版 start）。
  2. 带 `--worker` 参数：直接执行刷课主逻辑（main.main()），供 GUI 以子进程方式调用。

打包命令（Qt 版 / PySide6）：
  python -m PyInstaller --onefile --noconsole --icon="task/img/xuexitong1 .ico" \\
      --add-data "task;task" \\
      --collect-all PySide6 --collect-all PIL --collect-all selenium \\
      launcher.py -n 学习通刷课

说明：Qt 版界面依赖 PySide6，打包体积较旧 tk 版明显增大（约 +40~60MB）。
"""
import os
import sys
import shutil
import tempfile


APP_NAME = "学习通刷课"


def resource_root():
    """返回 exe 同目录（源码运行时为当前目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def extract_resources():
    """
    把 PyInstaller 内置的 task 资源解压到 exe 同目录（若已存在则跳过，
    若内置资源较新则覆盖更新）。
    """
    if getattr(sys, 'frozen', False):
        src = sys._MEIPASS
    else:
        src = os.path.dirname(os.path.abspath(__file__))

    dest_root = resource_root()
    task_src = os.path.join(src, 'task')
    if not os.path.isdir(task_src):
        return

    def sync(src_dir, dst_dir):
        for name in os.listdir(src_dir):
            s = os.path.join(src_dir, name)
            d = os.path.join(dst_dir, name)
            if os.path.isdir(s):
                os.makedirs(d, exist_ok=True)
                sync(s, d)
            else:
                # 目标不存在，或源比目标新（更新打包资源）
                if not os.path.exists(d) or os.path.getmtime(s) > os.path.getmtime(d):
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copy2(s, d)

    sync(task_src, os.path.join(dest_root, 'task'))


def run_worker():
    """刷课工作进程：等价于运行 main.py"""
    # 确保运行目录是 exe 同目录（让 task/ 相对路径可用）
    os.chdir(resource_root())
    import main
    main.run_main()


def run_gui():
    """GUI 主进程"""
    log_path = os.path.join(resource_root(), '启动诊断.log')
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('step1: extract_resources开始\n')
        extract_resources()
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('step2: extract完成, chdir=' + str(resource_root()) + '\n')
        os.chdir(resource_root())
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('step3: import start即将开始\n')
        import start
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('step4: start导入成功, 调用start_main\n')
        start.start_main()
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('step5: start_main返回（异常！GUI不应返回）\n')
    except Exception as e:
        import traceback
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('EXCEPTION: ' + traceback.format_exc())
        raise


def main():
    if '--worker' in sys.argv:
        run_worker()
    else:
        run_gui()


if __name__ == '__main__':
    main()