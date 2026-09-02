"""mouseinfo 最小替代实现（仅本项目的 sys.path 生效）。

真实的 mouseinfo 包在 Linux 顶层强制 import tkinter 并在缺失时
sys.exit()，而 pyautogui 仅在 mouseInfo() 交互窗口功能中使用它。
本项目（学习通刷课）只用 pyautogui 的按键/滚轮/窗口尺寸等能力，
不需要 MouseInfo 窗口；沙箱环境又无法 apt 安装 python3-tk，
故提供此空实现以保证 `import pyautogui` 可用。
如需完整功能，请删除本文件并安装 python3-tk 与 mouseinfo。
"""


class MouseInfoWindow:  # noqa: D101 - 占位窗口类
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        raise NotImplementedError(
            "mouseinfo stub: 本环境未安装 tkinter，MouseInfo 窗口不可用。"
            "如需该功能请安装 python3-tk 并删除本 stub 文件。"
        )


def displayMouseInfo():  # 兼容旧接口名
    MouseInfoWindow()
