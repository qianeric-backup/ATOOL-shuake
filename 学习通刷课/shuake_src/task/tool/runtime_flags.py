# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.
"""运行时全局标志（跨模块共享，避免循环导入）。

调用方必须以属性方式读写（import 模块本身而非 from-import 名称）：
    from task.tool import runtime_flags
    runtime_flags.HEADLESS = True
    if runtime_flags.HEADLESS: ...
"""

# True = 无头静默刷课（GUI「调试模式」关闭）：不显示浏览器窗口，
# 并跳过所有依赖真实屏幕焦点的 pyautogui 操作（倍速按键改为 WebDriver 通道）
HEADLESS = False
