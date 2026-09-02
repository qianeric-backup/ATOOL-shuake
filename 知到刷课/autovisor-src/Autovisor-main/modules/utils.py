import ctypes
import json
import os
import os.path
from typing import List
from playwright.async_api import Page, Locator
from playwright.async_api import TimeoutError
from playwright._impl._errors import TargetClosedError
from typing import Any
# Windows 特化的 Win32Window 类型注解在 Linux/macOS 不存在，统一用 Any

from modules.configs import Config
import time
# pygetwindow 仅支持 Windows；Linux/macOS 下导入即抛 NotImplementedError，
# 此处统一置为 None，窗口前置/隐藏功能在非 Windows 平台自动降级为跳过。
try:
    import pygetwindow as gw
except NotImplementedError:
    gw = None
from modules.logger import Logger

logger = Logger()


def get_runtime_root():
    return logger.runtime_root


def get_runtime_path(*parts):
    return os.path.join(get_runtime_root(), *parts)

def save_cookies(cookies, filename="cookies.json"):
    """保存登录Cookies到文件"""
    with open(filename, 'w') as f:
        json.dump(cookies, f)

def load_cookies(filename="cookies.json"):
    """从文件加载 Cookies"""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def clear_cookies(filename="cookies.json"):
    if os.path.exists(filename):
        os.remove(filename)

# 将python终端前置（Windows 专属；Linux/macOS 无 Win32 控制台，直接跳过）
def bring_console_to_front():
    if os.name != "nt":
        return
    import ctypes
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
        ctypes.windll.user32.SetForegroundWindow(hwnd)


async def display_window(page: Page) -> None:
    window = await get_browser_window(page)
    if window:
        window.show()
        window.restore()
        window.moveTo(100, 100)
        logger.info("播放窗口已自动前置.", shift=True)
    else:
        logger.warn("未找到播放窗口!")


async def hide_window(page: Page) -> None:
    window = await get_browser_window(page)
    if window:
        window.hide()
        logger.info("播放窗口已自动隐藏,将在需要安全验证时显示.")
    else:
        logger.warn("未找到播放窗口!")


async def get_browser_window(page: Page) -> Any | None:
    if gw is None:
        # 非 Windows 平台无 pygetwindow，跳过窗口控制
        return None
    custom_title = "Autovisor - Playwright"
    await page.wait_for_load_state("domcontentloaded")
    await page.evaluate(f'document.title = "{custom_title}"')
    # 获取所有窗口并尝试匹配 Playwright 窗口
    await page.wait_for_timeout(1000)
    win_list = gw.getWindowsWithTitle(custom_title)
    if win_list:
        return win_list[0]
    else:
        return None


async def evaluate_js(page: Page, wait_selector, js: str, timeout=None, is_hike_class=False) -> None:
    try:
        if wait_selector and is_hike_class is False:
            await page.wait_for_selector(wait_selector, timeout=timeout)
        if is_hike_class is False:
            await page.evaluate(js)
    except TargetClosedError as e:
        logger.debug(f"浏览器关闭时停止执行页面脚本: {logger.summarize_exception(e)}")
        return
    except Exception as e:
        logger.log_exception(f"执行页面脚本失败. Selector: {wait_selector} JS: {js}", e)
        return


async def evaluate_on_element(page: Page, selector: str, js: str, timeout: float = None,
                              is_hike_class=False) -> None:
    try:
        if selector and is_hike_class is False:
            element = page.locator(selector).first
            await element.evaluate(js, timeout=timeout)
    except TargetClosedError as e:
        logger.debug(f"浏览器关闭时停止执行元素脚本: {logger.summarize_exception(e)}")
        return
    except Exception as e:
        logger.log_exception(f"执行元素脚本失败. Selector: {selector} JS: {js}", e)
        return


async def optimize_page(page: Page, config: Config, is_new_version=False, is_hike_class=False) -> None:
    try:
        #await page.wait_for_load_state("domcontentloaded")
        await evaluate_js(page, ".studytime-div", config.pop_js, None, is_hike_class)
        if not is_new_version:
            if not is_hike_class:
                hour = time.localtime().tm_hour
                if hour >= 18 or hour < 7:
                    await evaluate_on_element(page, ".Patternbtn-div", "el=>el.click()", timeout=1500)
                await evaluate_on_element(page, ".exploreTip", "el=>el.remove()", timeout=1500)
                await evaluate_on_element(page, ".ai-helper-Index2", "el=>el.remove()", timeout=1500)
                await evaluate_on_element(page, ".aiMsg.once", "el=>el.remove()", timeout=1500)
                logger.info("页面优化完成!")

    except TargetClosedError as e:
        logger.debug(f"浏览器关闭时停止页面优化: {logger.summarize_exception(e)}")
        return
    except Exception as e:
        logger.log_exception("页面优化失败.", e)
        return


async def get_video_attr(page, attr: str) -> any:
    try:
        await page.wait_for_selector("video", state="attached", timeout=1000)
        attr = await page.evaluate(f'''document.querySelector('video').{attr}''')
        return attr
    except TargetClosedError as e:
        logger.debug(f"浏览器关闭时停止读取视频属性 {attr}: {logger.summarize_exception(e)}")
        return None
    except Exception as e:
        logger.log_exception(f"读取视频属性失败. attr: {attr}", e)
        return None


async def get_lesson_name(page: Page, is_hike_class=False) -> str:
    if is_hike_class:
        #title_ele1 = await page.wait_for_selector("#sourceTit")
        title_ele = await page.wait_for_selector("span")
        await page.wait_for_timeout(500)
        title = await title_ele.get_attribute("title")
    else:
        title_ele = await page.wait_for_selector("#lessonOrder")
        await page.wait_for_timeout(500)
        title = await title_ele.get_attribute("title")
    return title


async def get_filtered_class(page: Page, is_new_version=False, is_hike_class=False, include_all=False) -> List[Locator]:
    try:
        if is_new_version:
            await page.wait_for_selector(".progress-num", timeout=2000)
        if is_hike_class:
            await page.wait_for_selector(".icon-finish", timeout=2000)
        else:
            await page.wait_for_selector(".time_icofinish", timeout=2000)
    except TimeoutError:
        pass

    if is_hike_class:
        all_class = await page.locator(".file-item").all()
        if include_all:
            pass
            # logger.debug(f"Get to-review class: {len(all_class)}")
            # return all_class
        else:
            to_learn_class = []
            for each in all_class:
                isDone = await each.locator(".icon-finish").count()
                if not isDone:
                    to_learn_class.append(each)
            logger.debug(f"Get to-learn class: {len(all_class)}")
            return to_learn_class

    else:
        all_class = await page.locator(".clearfix.video").all()
        if include_all:
            logger.debug(f"Get to-review class: {len(all_class)}")
            return all_class
        else:
            to_learn_class = []
            for each in all_class:
                if is_new_version:
                    progress = await each.locator(".progress-num").text_content()
                    isDone = progress == "100%"
                else:
                    isDone = await each.locator(".time_icofinish").count()
                if not isDone:
                    to_learn_class.append(each)
            logger.debug(f"Get to-learn class: {len(all_class)}")
            return to_learn_class

