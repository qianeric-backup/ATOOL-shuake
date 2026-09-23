# encoding=utf-8
import asyncio
import os
import time
import traceback
import sys
from playwright.async_api import async_playwright, Playwright, Page, BrowserContext
from playwright.async_api import TimeoutError
from playwright._impl._errors import TargetClosedError
from modules.logger import Logger
from modules.configs import Config
from modules.progress import get_course_progress, show_course_progress
from modules.support import show_donate
from modules.utils import optimize_page, get_lesson_name, get_filtered_class, get_video_attr, hide_window, \
     save_cookies, load_cookies, clear_cookies, get_runtime_path
from modules.slider import slider_verify
from modules.tasks import video_optimize, play_video, skip_questions, wait_for_verify, task_monitor
from modules.banner import print_banner
from modules import paths


def auto_captcha_modules():
    """返回 (np, cv2) 模块; 打包后已内置, 无法内置时才尝试运行时安装"""
    try:
        import numpy as np
        import cv2 as cv2
        return np, cv2
    except ImportError:
        from modules import installer
        return installer.start()

# 获取全局事件循环
event_loop_verify = asyncio.Event()
event_loop_answer = asyncio.Event()
COOKIE_PATH = paths.get_runtime_path("res", "cookies.json")


def ensure_firefox_installed() -> None:
    """确保 Playwright 的 Firefox 浏览器二进制已安装; 未装则自动下载(约337MB)。"""
    import subprocess

    def _run(args):
        try:
            return subprocess.call(args, shell=False)
        except Exception as e:
            logger.warn(f"自动安装 Firefox 组件的命令执行失败: {e}")
            return -1

    if getattr(sys, "frozen", False):
        # 冻结环境: 驱动打包在 _MEIPASS/playwright/driver, 用其内置 node + cli.js 安装
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        driver_dir = os.path.join(base, "playwright", "driver")
        # 跨平台: Windows 用 node.exe, Linux/macOS 用 node
        node = (os.path.join(driver_dir, "node.exe")
                if os.name == "nt"
                else os.path.join(driver_dir, "node"))
        cli = os.path.join(driver_dir, "package", "cli.js")
        if os.path.exists(node) and os.path.exists(cli):
            code = _run([node, cli, "install", "firefox"])
        else:
            logger.warn("未找到打包内置的 playwright driver, 无法自动安装 Firefox 组件.")
            code = -1
    else:
        # 源码环境: 直接用 python -m playwright install firefox
        code = _run([sys.executable, "-m", "playwright", "install", "firefox"])
    if code != 0:
        logger.warn("若 Firefox 组件缺失, 刷课将无法启动. 可手动执行: python -m playwright install firefox")


async def wait_for_interruption(event_loop: asyncio.Event) -> float:
    event_loop.clear()
    wait_start = time.time()
    await event_loop.wait()
    return time.time() - wait_start


def cal_time_period(start_time: float, paused_time: float) -> float:
    return max(0.0, time.time() - start_time - paused_time)

async def init_page(p: Playwright, cookies) -> tuple[Page, BrowserContext]:
    """跨平台浏览器启动：
    - Linux/macOS: 不使用 channel（Linux Playwright 无 msedge/chrome channel），
      由 executable_path 或系统默认浏览器驱动。
    - Windows: 保留 channel（msedge/chrome）。
    """
    is_firefox = config.driver == "firefox"
    driver = "firefox" if is_firefox else ("msedge" if config.driver == "edge" else config.driver)
    logger.info(f"正在启动{config.driver}浏览器...")
    launch_args = {
        "channel": driver,
        "headless": False,
        "executable_path": config.exe_path if config.exe_path else None,
        "args": [
            f'--window-size={1600},{900}',
            '--window-position=100,100',  # 窗口位置
        ],
    }
    if os.name != "nt" and not is_firefox:
        # Linux/macOS: 去掉 channel 并交给系统 chromium/默认浏览器（无 channel 概念）
        del launch_args["channel"]
        driver = config.driver
    if is_firefox:
        # Firefox 是独立浏览器类型, 不能走 channel; 且需确保浏览器二进制已安装
        try:
            ensure_firefox_installed()
        except Exception as e:
            logger.warn(f"检查 Firefox 浏览器组件失败: {e}")
        del launch_args["channel"]
        # Firefox 把不认识的参数当"要打开的网址" → 生成 http://1600,900/
        # http://100,100 假标签；改用 Firefox 原生 -width/-height
        launch_args["args"] = ["-width", "1600", "-height", "900"]
    browser_launch = p.firefox if is_firefox else p.chromium
    try:
        browser = await browser_launch.launch(**launch_args)
    except TargetClosedError as e:
        logger.log_exception("首次启动浏览器失败,准备重试.", e)
        logger.info("检测到浏览器首次启动失败,正在重试...")
        await asyncio.sleep(1)
        browser = await browser_launch.launch(**launch_args)
    context = await browser.new_context()
    # 加载 Cookies
    if cookies:
        await context.add_cookies(cookies)
        logger.info("已加载 Cookies!")
    else:
        logger.info("未找到 Cookies,将跳转至登录页.")
    page = await context.new_page()
    logger.debug(f"{config.driver}浏览器启动完成.")
    #抹去特征
    stealth_js = paths.resource_path("res", "stealth.min.js")
    if os.path.exists(stealth_js):
        with open(stealth_js, 'r') as f:
            js = f.read()
        await page.add_init_script(js)
        logger.debug("stealth.js执行完成.")
    else:
        logger.warn("未找到 stealth.min.js, 已跳过防检测脚本注入.")
    page.set_default_timeout(24 * 3600 * 1000)

    return page, context

async def auto_login(context: BrowserContext, page: Page, modules=None):
    cookie_saved = False

    async def request_handler(request):
        nonlocal cookie_saved
        if cookie_saved:
            return
        if "https://www.zhihuishu.com" in request.url:
            cookies = await context.cookies()
            save_cookies(cookies, COOKIE_PATH)
            logger.info(f"已保存登录凭证到: {COOKIE_PATH},下次可免密登录.")
            cookie_saved = True

    await page.goto(config.login_url, wait_until="commit")

    # ---------- 实测（2026-09 Linux/Playwright还原）：登录页已改版 ----------
    # 新版"登录中心"(login.zhihuishu.com, Element-UI)：登录表单为
    #   input[name=mobile] / input[type=password] / 提交按钮 .btn-block__grandient_login
    # 旧版登录墙(.wall-main / #lUsername)仍兼容老入口；两者都探测并用。
    # Firefox 启动参数里残留的 Chrome 专用 --window-size/--window-position
    # 会被 Firefox 当作"要打开的网址"（http://1600,900 假标签）——此为垃圾
    # 标签，判断登录态时要排除。
    def is_junk_url(u):
        # 分辨率探测假页面: http://1600,900/ 或 http://100,100
        return u.startswith('http') and all(ch.isdigit() or ch in ",.,:" for ch in u.split("//", 1)[-1].split("/")[0])

    async def find_login_form_tab():
        for p in list(context.pages):
            try:
                if await p.locator('input[name="mobile"], #lUsername, .wall-main').count():
                    return p
            except Exception:
                continue
        return None

    form_tab = await find_login_form_tab()
    if form_tab and form_tab is not page:
        logger.info("登录表单位于新标签页, 已切换主页面.")
        page = form_tab
        try:
            await page.bring_to_front()
        except Exception:
            pass
    if not form_tab and "login" not in page.url:
        logger.info("检测到已登录,跳过登录步骤.")
        return page

    logged_out = False   # 快速路径：页面可能在 goto 后已是登录态
    try:
        await page.wait_for_selector('input[name="mobile"], #lUsername', state='attached', timeout=15000)
    except Exception:
        if "login" not in page.url:
            logger.info("未出现登录表单, 视为已登录.")
            return page
    page.on('request', request_handler)
    new_ui = bool(await page.locator('input[name="mobile"]').count())
    if config.username and config.password and new_ui:
        # 新版登录中心
        await page.locator('input[name="mobile"]').fill(config.username)
        await page.locator('input[type="password"]').first.fill(config.password)
        # 新版要求先勾选"我已阅读并同意用户协议"，否则登录按钮无效
        try:
            agree_input = page.locator('input.el-checkbox__original').first
            if await agree_input.count() and bool(await agree_input.is_checked()) is False:
                await page.locator('.el-checkbox').first.click()
                await page.wait_for_timeout(300)
                if bool(await agree_input.is_checked()) is False:
                    # 兜底：直接按文字找协议勾选框
                    await page.locator('label:has-text("我已")').first.click()
        except Exception as e:
            logger.debug(f"勾选用户协议失败(可能已勾选): {e}")
        await page.wait_for_timeout(500)
        await page.locator('.btn-block__grandient_login').first.click()
    elif config.username and config.password:
        # 旧版登录墙
        await page.wait_for_selector("#lPassword", state="attached")
        await page.locator('#lUsername').fill(config.username)
        await page.locator('#lPassword').fill(config.password)
        await page.wait_for_selector(".wall-sub-btn", state="attached")
        await page.wait_for_timeout(500)
        await page.locator(".wall-sub-btn").first.click()
    if config.enableAutoCaptcha and modules:
        try:
            # 易盾滑块仅在触发风控时出现，存在才尝试自动验证
            if await page.locator('.yidun_bgimg, .yidun_jigsaw').count():
                await slider_verify(page, modules)
        except Exception as e:
            logger.debug(f"未检测到滑块或自动验证不可用: {e}")
    # ---------- 等待登录完成（手动登录 / 新标签页登录兜底）----------
    # 原实现死等本页 .wall-main 消失（默认超时被设成 24h）：登录发生在其它
    # 标签页、或站点改版后登录墙不再按预期隐藏时，程序会永远卡在
    # “正在等待登录完成”。改为轮询三种成功路径：
    #   1) 本页登录墙消失；
    #   2) 本页 URL 已离开 /login；
    #   3) 用户在其它标签页登录成功——切换主页面引用。
    async def save_login_once():
        nonlocal cookie_saved
        if cookie_saved:
            return
        try:
            cookies = await context.cookies()
            save_cookies(cookies, COOKIE_PATH)
            logger.info(f"已保存登录凭证到: {COOKIE_PATH},下次可免密登录.")
            cookie_saved = True
        except Exception:
            pass

    deadline = asyncio.get_event_loop().time() + 30 * 60  # 最长等 30 分钟
    while asyncio.get_event_loop().time() < deadline:
        # 登录完成判定：标签页"离开包含 login 的 URL、不是分辨率探测垃圾
        # 页、且既无旧版登录墙也无新版登录表单"
        for p in list(context.pages):
            try:
                u = p.url
                if not u or u == "about:blank" or "login" in u or is_junk_url(u):
                    continue
                if await p.locator(".wall-main, input[name=\"mobile\"]").count():
                    continue
            except Exception:
                continue
            if p is not page:
                logger.info("检测到登录完成于其它标签页, 已切换主页面.")
                try:
                    await p.bring_to_front()
                except Exception:
                    pass
            await save_login_once()
            return p
        await asyncio.sleep(1)
    logger.warn("等待登录超时(30分钟), 继续以当前页面状态尝试.")
    return page


async def ensure_login(context: BrowserContext, page: Page, cookies, modules=None):
    if cookies:
        logger.info("正在校验 Cookies 登录状态...")
        await page.goto(config.login_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        if "login" not in page.url:
            logger.info("使用Cookies登录成功!")
            return page
        logger.warn("检测到 Cookies 已失效, 将重新登录.", shift=True)
        clear_cookies(COOKIE_PATH)
        cookies = None

    if not config.username or not config.password:
        logger.info("请手动填写账号密码...")
    logger.info("正在等待登录完成...")
    page = await auto_login(context, page, modules)
    logger.info("登录成功!")
    return page


async def learning_loop(page: Page, start_time, is_new_version=False, is_hike_class=False):
    paused_time = 0.0
    try:
        cur_time = await get_course_progress(page, is_new_version, is_hike_class)
    except TargetClosedError:
        return paused_time
    while cur_time != "100%":
        try:
            limit_time = config.limitMaxTime
            time_period = cal_time_period(start_time, paused_time) / 60
            if 0 < limit_time <= time_period:
                break
            cur_time = await get_course_progress(page, is_new_version, is_hike_class)
            show_course_progress(desc="完成进度:", cur_time=cur_time)
            await asyncio.sleep(0.5)
        except TargetClosedError:
            return paused_time
        except TimeoutError as e:
            if await page.query_selector(".yidun_modal__title"):
                paused_time += await wait_for_interruption(event_loop_verify)
            elif await page.query_selector(".topic-title"):
                paused_time += await wait_for_interruption(event_loop_answer)
            else:
                logger.debug(f"学习进度轮询未命中: {logger.summarize_exception(e)}")
    return paused_time


async def review_loop(page: Page, start_time, is_hike_class=False):
    paused_time = 0.0
    total_time = await get_video_attr(page, "duration")
    if total_time is None:
        return paused_time
    try:
        await page.evaluate(config.reset_curtime)  # 重置视频播放时间
    except TargetClosedError:
        return paused_time
    while True:
        try:
            limit_time = config.limitMaxTime
            cur_time = await get_video_attr(page, "currentTime")
            if cur_time is None or cur_time >= total_time:
                break
            time_period = cal_time_period(start_time, paused_time) / 60
            if 0 < limit_time <= time_period:
                break
            show_course_progress(desc="完成进度:", cur_time=time_period, limit_time=limit_time)
            await asyncio.sleep(0.5)
        except TargetClosedError:
            return paused_time
        except TimeoutError as e:
            if await page.query_selector(".yidun_modal__title"):
                paused_time += await wait_for_interruption(event_loop_verify)
            elif await page.query_selector(".topic-title"):
                paused_time += await wait_for_interruption(event_loop_answer)
            else:
                logger.debug(f"复习进度轮询未命中: {logger.summarize_exception(e)}")
    return paused_time


async def working_loop(page: Page, is_new_version=False, is_hike_class=False):
    # 获取所有课程元素
    if is_hike_class:
        await page.wait_for_selector(".file-item", state="attached")
    else:
        await page.wait_for_selector(".clearfix.video", state="attached")
    to_learn_class = await get_filtered_class(page, is_new_version, is_hike_class)
    learning = True if len(to_learn_class) > 0 else False
    if learning:
        all_class = to_learn_class
    else:
        all_class = await get_filtered_class(page, is_new_version, is_hike_class, include_all=True)
    start_time = time.time()
    paused_time = 0.0
    cur_index = 0

    while cur_index < len(all_class):
        await all_class[cur_index].click()
        if is_hike_class:
            await page.wait_for_selector(".file-item.active", state="attached")
        else:
            await page.wait_for_selector(".current_play", state="attached")
        await page.wait_for_timeout(1000)
        title = await get_lesson_name(page, is_hike_class)
        logger.info(f"正在学习:{title}")
        page.set_default_timeout(10000)
        # 移除视频暂停功能
        await page.wait_for_selector("video", state="attached")
        await page.evaluate(config.remove_pause)
        if learning:
            paused_time += await learning_loop(page, start_time, is_new_version, is_hike_class)
        else:
            paused_time += await review_loop(page, start_time, is_hike_class)
        if is_hike_class is False:
            if "current_play" in await all_class[cur_index].get_attribute('class'):
                cur_index += 1
        else:
            if "active" in await all_class[cur_index].get_attribute('class'):
                cur_index += 1
        reachTimeLimit = await check_time_limit(page, start_time, paused_time, all_class, title, is_hike_class)
        if reachTimeLimit:
            return


async def check_time_limit(page: Page, start_time, paused_time, all_class, title, is_hike_class) -> bool:
    reachTimeLimit = False
    page.set_default_timeout(24 * 3600 * 1000)
    time_period = cal_time_period(start_time, paused_time) / 60
    if 0 < config.limitMaxTime <= time_period:
        logger.info(f"当前课程已达时限:{config.limitMaxTime}min", shift=True)
        logger.info("即将进入下门课程!")
        reachTimeLimit = True
    else:
        class_name = await all_class[-1].get_attribute('class')
        if is_hike_class:
            if "active" in class_name:
                logger.info("已学完本课程全部内容!", shift=True)
                print("==" * 10)
            else:
                logger.info(f"\"{title}\" 已完成!", shift=True)
                logger.info(f"本次课程已学习:{time_period:.1f} min")
        else:
            if "current_play" in class_name:
                logger.info("已学完本课程全部内容!", shift=True)
                print("==" * 10)
            else:
                logger.info(f"\"{title}\" 已完成!", shift=True)
                logger.info(f"本次课程已学习:{time_period:.1f} min")
    return reachTimeLimit


async def main():
    modules, tasks = [], []
    if config.enableAutoCaptcha:
        print("===== Install Log =====")
        modules = auto_captcha_modules()
        logger.info("自动滑块验证依赖加载完成!")
    print("====== Login Log ======")
    async with async_playwright() as p:
        cookies = load_cookies(COOKIE_PATH)
        page, context = await init_page(p, cookies)

        # 等待登录的用户可能在其它标签页完成登录, 需要用返回的主页面继续
        page = await ensure_login(context, page, cookies, modules)

        # 先启动人机验证协程
        verify_task = asyncio.create_task(wait_for_verify(page, config, event_loop_verify))

        # 启动协程任务
        video_optimize_task = asyncio.create_task(video_optimize(page, config))
        skip_ques_task = asyncio.create_task(skip_questions(page, event_loop_answer))
        play_video_task = asyncio.create_task(play_video(page))
        tasks.extend([verify_task, video_optimize_task, skip_ques_task, play_video_task])

        # 隐藏窗口
        if config.enableHideWindow:
            await hide_window(page)

        # 任务监视器
        monitor_task = asyncio.create_task(task_monitor(tasks))

        # 遍历所有课程,加载网页
        for course_url in config.course_urls:
            print("===== Runtime Log =====")
            is_new_version = "fusioncourseh5" in course_url
            is_hike_class = "hike.zhihuishu.com" in course_url  # 判断是否为翻转课
            logger.info("正在加载播放页...")
            await page.goto(course_url, wait_until="commit")
            await page.wait_for_timeout(1500)
            if "login" in page.url:
                logger.warn("播放页跳转到登录页, 当前登录状态已失效, 正在重新登录.", shift=True)
                clear_cookies(COOKIE_PATH)
                await ensure_login(context, page, None, modules)
                logger.info("重新进入播放页...")
                await page.goto(course_url, wait_until="commit")
                await page.wait_for_timeout(1500)
            # 关闭弹窗,优化页面结构
            await optimize_page(page, config, is_new_version, is_hike_class)
            logger.info("页面优化完成!")
            # 获取课程标题
            if not is_new_version and is_hike_class is False:
                title_selector = await page.wait_for_selector(".source-name")
                course_title = await title_selector.text_content()
                logger.info(f"当前课程:<<{course_title}>>")
            if is_hike_class:
                title_selector = await page.wait_for_selector(".course-name")
                course_title = await title_selector.text_content()
                logger.info(f"当前课程:<<{course_title}>>， 是翻转课哎")
            # 启动课程主循环
            await working_loop(page, is_new_version=is_new_version, is_hike_class=is_hike_class)
    print("===== Task Finished =====")
    logger.info("所有课程已学习完毕!")
    show_donate(paths.resource_path("res", "QRcode.jpg"), show=config.showDonateCode)
    # 结束所有协程任务
    await asyncio.gather(*tasks, return_exceptions=True) if tasks else None
    await monitor_task


def run() -> int:
    """刷课主入口; 返回退出码。GUI 模式调用此函数, 不再强制 input() 阻塞。"""
    # main()/init_page() 等模块级函数直接引用全局 logger/config，
    # 不声明 global 的话两者只是局部变量, main() 一进来就 NameError
    global logger, config
    print_banner()
    logger = Logger()
    try:
        print("====== Init Log ======")
        logger.info("程序启动中...")
        config = Config(paths.config_path())
        if not config.course_urls:
            logger.error("未检测到有效网址或不支持此类网页,请检查配置文件!")
            return -1
        asyncio.run(main())
        return 0
    except TargetClosedError as e:
        if "BrowserType.launch" in repr(e):
            logger.log_exception("浏览器相关流程异常结束.", e)
            logger.error("浏览器启动失败,请尝试重新启动!")
            logger.info("如果仍然无法启动,请修改配置文件并使用Chrome浏览器")
        else:
            logger.debug(f"浏览器关闭结束运行: {logger.summarize_exception(e)}")
    except Exception as e:
        logger.log_exception("程序运行时出现未处理异常.", e, shift=True)
        if isinstance(e, KeyError):
            logger.error(f"配置文件错误!")
        elif isinstance(e, FileNotFoundError):
            logger.error(f"依赖文件缺失: {e.filename},请重新安装程序!")
        elif isinstance(e, UnicodeDecodeError):
            logger.error("配置文件编码错误,保存时请选择UTF-8或GBK编码!")
        else:
            logger.error("系统出错,请检查后重新启动!")
    finally:
        logger.save()
    return 1


if __name__ == "__main__":
    sys.exit(run())
