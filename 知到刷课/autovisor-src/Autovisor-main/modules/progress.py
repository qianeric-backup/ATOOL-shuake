# encoding=utf-8
import random
import sys
import time

from playwright.async_api import Page, TimeoutError
from modules.lesson_navigation import (
    CatalogSelectors,
    lesson_progress,
    parse_progress_value,
)
from modules.logger import Logger

logger = Logger()


def _is_interactive() -> bool:
    """stdout 是否为真实终端(GUI/管道接管时不是)。"""
    try:
        return bool(sys.stdout) and sys.stdout.isatty()
    except Exception:
        return False


# desc -> (上次打印的百分比, 上次打印时间)
_last_printed = {}


def _should_print(desc: str, percent: int, min_delta: int = 5,
                  min_interval: float = 20.0) -> bool:
    """非交互环境下给进度条降频。

    GUI 把 stdout 接到日志框, 而进度条用 "\\r" 原地刷新——在日志框里不会
    覆盖同一行, 于是每 0.5 秒堆出一行(用户看到的是几十行重复的 "6%")。
    这里改成: 只有进度变化 >= min_delta% 或超过 min_interval 秒才输出一次。
    """
    if _is_interactive():
        return True
    last = _last_printed.get(desc)
    now = time.time()
    if (last is None or abs(percent - last[0]) >= min_delta
            or now - last[1] >= min_interval):
        _last_printed[desc] = (percent, now)
        return True
    return False


def _emit(line: str) -> None:
    """交互终端原地刷新; 非交互(日志框)整行输出, 避免 \\r 堆叠刷屏。"""
    if _is_interactive():
        print(line, end="", flush=True)
    else:
        print(line.rstrip(), flush=True)


# 视频区域内移动鼠标
async def move_mouse(page: Page):
    try:
        await page.wait_for_selector(".videoArea", state="attached", timeout=5000)
        elem = page.locator(".videoArea")
        await elem.hover(timeout=4000)
        pos = await elem.bounding_box()
        if not pos:
            return
        # Calculate the target position to move the mouse
        target_x = pos['x'] + random.uniform(-10, 10)
        target_y = pos['y'] + random.uniform(-10, 10)
        await page.mouse.move(target_x, target_y)
    except TimeoutError:
        return


# 获取课程进度
async def get_course_progress(page: Page, catalog: CatalogSelectors) -> str:
    await move_mouse(page)
    current_lesson = page.locator(catalog.active).first
    if await current_lesson.count() == 0:
        return "0%"
    return f"{await lesson_progress(current_lesson, catalog)}%"


# 打印课程播放进度
def show_course_progress(desc, cur_time=None, limit_time=0):
    assert limit_time >= 0, "limit_time 必须为非负数!"
    if limit_time == 0:
        cur_time = "0%" if cur_time == '' or cur_time is None else cur_time
        percent = parse_progress_value(str(cur_time).rstrip("%"))
        if not _should_print(desc, percent):
            return
        length = int(percent * 30 // 100)
        progress = ("█" * length).ljust(30, " ")
        _emit(f"\r{desc} |{progress}| {percent}%\t".ljust(50))
    else:
        cur_time = 0 if cur_time == '' or cur_time is None else cur_time
        if isinstance(cur_time, str):
            cur_time = 0
        left_time = round(limit_time - cur_time, 1)
        percent = int(cur_time / limit_time * 100)
        if left_time <= 0:
            percent = 100
        percent = max(0, min(percent, 100))
        if not _should_print(desc, percent):
            return
        length = int(percent * 20 // 100)
        progress = ("█" * length).ljust(20, " ")
        _emit(f"\r{desc} |{progress}| {percent}%\t剩余 {left_time} min\t".ljust(50))


# 打印通用版进度条
def show_progress(desc, current, total, suffix="", width=30):
    if total <= 0:
        _emit(f"\r{desc} 已下载 {current} bytes\t{suffix}".ljust(50))
        return
    percent = int(current / total * 100)
    if not _should_print(desc, percent):
        return
    length = int(percent * width // 100)
    progress = ("█" * length).ljust(width, " ")
    _emit(f"\r{desc} |{progress}| {percent}%\t{suffix}".ljust(50))
