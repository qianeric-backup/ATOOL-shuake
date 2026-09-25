# encoding=utf-8
import argparse
import asyncio
import ctypes
import os
import platform
import sys
import time

from playwright.async_api import (
    BrowserContext,
    Error,
    Page,
    Playwright,
    TimeoutError,
    async_playwright,
)
from playwright._impl._errors import TargetClosedError

from modules import installer, updater
from modules.banner import print_banner
from modules.configs import Config, ConfigError
from modules.course_runner import (
    CourseOutcome,
    detect_catalog_after_verification,
    run_course,
)
from modules.diagnostics import check_browser, check_course
from modules.login import (
    LOGIN_PASSWORD_SELECTOR,
    LOGIN_SUBMIT_SELECTOR,
    LOGIN_USERNAME_SELECTOR,
    accept_login_terms,
    is_login_page,
    wait_for_login_complete,
)
from modules.logger import Logger
from modules.slider import slider_verify
from modules.support import show_donate
from modules.tasks import (
    play_video,
    skip_questions,
    task_monitor,
    video_optimize,
    wait_for_verify,
)
from modules.utils import (
    clear_cookies,
    get_runtime_path,
    hide_window,
    load_cookies,
    optimize_page,
    save_cookies,
)
from modules.version import __version__

# 获取全局事件循环
event_loop_verify = asyncio.Event()
event_loop_answer = asyncio.Event()
COOKIE_PATH = get_runtime_path("data", "cookies.json")
ZHS_COOKIE_URLS = [
    "https://www.zhihuishu.com",
    "https://passport.zhihuishu.com",
    "https://onlineweb.zhihuishu.com",
    "https://studyvideoh5.zhihuishu.com",
    "https://studywisdomh5.zhihuishu.com",
    "https://fusioncourseh5.zhihuishu.com",
    "https://hike.zhihuishu.com",
]


_saved_cookies = None


class PageUnreachableError(RuntimeError):
    """页面在网络层面打不开(net::ERR_TIMED_OUT 等), 重试后仍失败。"""


def _cookies_signature(cookies):
    if not cookies:
        return None
    return frozenset(
        (
            cookie.get("name"),
            cookie.get("domain"),
            cookie.get("path"),
            cookie.get("value"),
        )
        for cookie in cookies
    )


def remember_login_cookies(cookies) -> None:
    """记录已经落盘的凭证, 用于跳过重复写入。"""
    global _saved_cookies
    _saved_cookies = _cookies_signature(cookies)


async def persist_login_cookies(context: BrowserContext) -> bool:
    """凭证有变化时才写盘: 登录完成、Cookie 续期后立即保存, 中断也不丢。

    返回 True = 已落盘(或无需写入), False = 写盘失败。
    """
    global _saved_cookies
    cookies = await context.cookies(ZHS_COOKIE_URLS)
    signature = _cookies_signature(cookies)
    if signature is None or signature == _saved_cookies:
        return True
    try:
        save_cookies(cookies, COOKIE_PATH)
    except Exception as exc:
        logger.log_exception("保存登录 Cookies 失败.", exc)
        return False
    _saved_cookies = signature
    logger.event("保存登录凭证", 条数=len(cookies), 文件=COOKIE_PATH)
    return True


def get_screen_size():
    if os.name == "nt":
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return 1920, 1080


async def init_page(p: Playwright, config, cookies) -> tuple[Page, BrowserContext]:
    driver = "msedge" if config.driver == "edge" else config.driver
    logger.info(f"正在启动{config.driver}浏览器...")
    screen_width, screen_height = get_screen_size()
    logger.event(
        "启动浏览器",
        驱动=config.driver,
        通道=driver,
        可执行文件=config.exe_path or "默认",
        窗口大小=f"{screen_width}x{screen_height}",
    )
    launch_args = {
        "channel": driver,
        "headless": False,
        "executable_path": config.exe_path if config.exe_path else None,
        "args": [
            "--start-maximized",
            f"--window-size={screen_width},{screen_height}",
            "--window-position=0,0",
        ],
    }
    # 兼容 Firefox 驱动: 需其独立引擎且不能用 Chromium/通道 + chrome 专属
    # 参数 (Firefox 会把不认识参数当"待打开网址", 生成 http://1600,900 假窗口)
    is_firefox = (config.driver or "").lower() == "firefox"
    engine = p.firefox if is_firefox else p.chromium
    if is_firefox:
        launch_args.pop("channel", None)
        launch_args["args"] = ["-width", str(screen_width),
                               "-height", str(screen_height)]
        # 本地预装提示: PLAYWRIGHT_BROWSERS_PATH 指向的缓存里找不到 firefox
        # 目录时给出安装建议（不阻塞启动, Playwright 会报更明确的错误）
        browsers_dir = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expanduser("~/.cache/ms-playwright")
        try:
            has_ff = os.path.isdir(browsers_dir) and any(
                d.startswith("firefox") for d in os.listdir(browsers_dir))
        except OSError:
            has_ff = False
        if not has_ff:
            logger.warn("本地未发现 playwright firefox 缓存组件; "
                        "请先执行: python3 -m playwright install firefox")
    elif (config.driver or "").lower() == "chromium":
        # Linux 下 Playwright 自带 chromium; 若设了 channel 反而会找外部二进制
        launch_args.pop("channel", None)
    logger.event("启动浏览器", 引擎="firefox" if is_firefox else "chromium")
    try:
        browser = await engine.launch(**launch_args)
    except TargetClosedError as exc:
        logger.log_exception("首次启动浏览器失败,准备重试.", exc)
        logger.info("检测到浏览器首次启动失败,正在重试...")
        await asyncio.sleep(1)
        browser = await engine.launch(**launch_args)
    logger.event("浏览器已启动", 版本=getattr(browser, "version", "未知"))
    # 使用真实窗口尺寸，避免 Playwright 默认 viewport 覆盖最大化窗口。
    context = await browser.new_context(viewport=None)
    if cookies:
        await context.add_cookies(cookies)
        logger.info("已加载 Cookies!")
    else:
        logger.info("未找到 Cookies,将跳转至登录页.")
    page = await context.new_page()
    logger.debug(f"{config.driver}浏览器启动完成.")
    # 抹去特征
    # stealth.min.js 随包内置: onefile 下位于 _MEIPASS/resources,
    # onedir/源码态位于 exe/脚本目录的 resources/
    stealth_path = os.path.join(
        getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))),
        "resources", "stealth.min.js")
    with open(stealth_path, 'r') as f:
        js = f.read()
    await page.add_init_script(js)
    logger.debug("stealth.js执行完成.")
    # 页面切后台（最小化/其他标签）时浏览器会把 document.hidden 置真、节流
    # 计时器、播放器自身检测到可见性变化就暂停视频或延迟弹题调度；
    # ——伪装为"一直可见"+拦截 blur/visibilitychange 关键事件
    if getattr(config, "keepWindowActive", True):
        await page.add_init_script(KEEP_ACTIVE_JS)
        logger.debug("防后台节流脚本注入完成.")
    page.set_default_timeout(24 * 3600 * 1000)

    return page, context


# 页面层反后台节流（文档级可见性伪装，仅脚本层面；引擎级节流由
# keepWindowActive 的周期性 bring_to_front 兜底）
KEEP_ACTIVE_JS = r"""
(function () {
  try {
    Object.defineProperty(document, 'hidden', {get: function () { return false;
    }, configurable: true});
    Object.defineProperty(document, 'visibilityState', {
      get: function () { return 'visible'; }, configurable: true});
  } catch (e) {}
  document.addEventListener('visibilitychange', function (e) {
    e.stopImmediatePropagation(); e.stopPropagation(); }, true);
  window.addEventListener('blur', function (e) {
    e.stopImmediatePropagation(); e.stopPropagation(); }, true);
})();
"""


async def auto_login(context: BrowserContext, page: Page, config, modules=None) -> None:
    wait_start = time.time()
    if not await goto_with_retry(page, config.login_url):
        raise PageUnreachableError(f"登录页无法打开: {config.login_url}")
    if not is_login_page(page.url):
        logger.info("检测到已登录,跳过登录步骤.")
        return

    if config.username and config.password:
        try:
            username = await page.wait_for_selector(
                LOGIN_USERNAME_SELECTOR, state="visible", timeout=30000
            )
            password = await page.wait_for_selector(
                LOGIN_PASSWORD_SELECTOR, state="visible", timeout=30000
            )
            logger.event("自动登录", 方式="账号密码", 账号="已填写")
            await username.fill(config.username)
            await password.fill(config.password)
            await accept_login_terms(page)
            submit = await page.wait_for_selector(
                LOGIN_SUBMIT_SELECTOR, state="visible", timeout=30000
            )
            await page.wait_for_timeout(500)
            await submit.click()
        except TimeoutError:
            if is_login_page(page.url):
                logger.warn("未找到自动登录控件,请在浏览器中手动完成登录.", shift=True)
                logger.event("自动登录", 方式="手动", 原因="未找到登录控件")

    captcha_task = None
    if config.enableAutoCaptcha and modules:
        logger.event("滑块任务", 状态="启动")
        captcha_task = asyncio.create_task(slider_verify(page, modules))

    try:
        await wait_for_login_complete(page)
    finally:
        if captcha_task:
            if not captcha_task.done():
                captcha_task.cancel()
            await asyncio.gather(captcha_task, return_exceptions=True)

    logger.event("登录完成", 耗时=f"{time.time() - wait_start:.1f}s", 地址=page.url)
    if await persist_login_cookies(context):
        logger.info(f"已保存登录凭证到: {COOKIE_PATH},下次可免密登录.")
    else:
        logger.warn("登录凭证保存失败(本次刷课不受影响, 但下次仍需重新登录).",
                    shift=True)


async def ensure_login(
    context: BrowserContext, page: Page, cookies, config, modules=None
) -> bool:
    if cookies:
        logger.info("正在校验 Cookies 登录状态...")
        if not await goto_with_retry(page, config.login_url,
                                     wait_until="domcontentloaded"):
            raise PageUnreachableError(f"登录页无法打开: {config.login_url}")
        try:
            await wait_for_login_complete(page, timeout=10000)
        except TimeoutError:
            pass
        if not is_login_page(page.url):
            logger.info("使用Cookies登录成功!")
            logger.event("登录状态", 结果="Cookies 有效", 地址=page.url)
            await persist_login_cookies(context)
            return True
        logger.warn("检测到 Cookies 已失效, 将重新登录.", shift=True)
        logger.event("登录状态", 结果="Cookies 失效", 地址=page.url)
        clear_cookies(COOKIE_PATH)
        remember_login_cookies(None)
        cookies = None

    if not config.username or not config.password:
        logger.info("请手动填写账号密码...")
    logger.info("正在等待登录完成...")
    await auto_login(context, page, config, modules)
    logger.info("登录成功!")
    return False


async def goto_with_retry(
    page: Page,
    url: str,
    *,
    wait_until: str = "commit",
    attempts: int = 3,
    delay: float = 5.0,
    timeout_ms: int = 90_000,
) -> bool:
    """打开页面, 网络类错误自动重试; 全部失败返回 False。

    课程页/登录页一次导航超时(net::ERR_TIMED_OUT 等)不应该让整轮刷课以
    "系统出错,请检查后重新启动" 收场: 这里重试并把失败交给调用方决定去留。
    """
    last_msg = ""
    for attempt in range(1, attempts + 1):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return True
        except TargetClosedError:
            raise
        except (Error, TimeoutError) as exc:
            last_msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
            retryable = ("net::" in last_msg
                         or "Timeout" in last_msg
                         or "timeout" in last_msg)
            if attempt >= attempts or not retryable:
                logger.warn(
                    f"打开页面失败({attempt}/{attempts}): {last_msg}", shift=True)
                logger.event("页面加载失败", 地址=url, 原因=last_msg)
                return False
            logger.warn(
                f"页面加载超时/网络异常({attempt}/{attempts}), {delay:.0f} 秒后重试: {url}",
                shift=True)
            await asyncio.sleep(delay)
    return False


async def main(config) -> bool:
    modules, tasks = [], []
    playback_enabled = asyncio.Event()
    all_courses_complete = True
    run_ok = True
    if config.enableAutoCaptcha:
        logger.section("依赖安装")
        logger.info("正在检查依赖库...")
        modules = installer.start(config)
        logger.info("所有依赖库安装完成!")

    # 自动做题(平时测试)所需的 AI 配置与"答完自动提交"开关, 供 watch_exam_pages
    # 与 run_course 的测试任务点处理共用
    exam_ai_cfg = None
    exam_submit = bool(getattr(config, "doExamSubmit", False))

    logger.section("登录")
    async with async_playwright() as p:
        cookies = load_cookies(COOKIE_PATH)
        remember_login_cookies(cookies)
        logger.event("本地凭证", 数量=len(cookies) if cookies else 0, 文件=COOKIE_PATH)
        page, context = await init_page(p, config, cookies)
        monitor_task = None
        try:
            login_by_cookie = await ensure_login(context, page, cookies, config, modules)

            logger.context(登录方式="Cookie" if login_by_cookie else "账号")
            tasks.extend(
                [
                    asyncio.create_task(
                        wait_for_verify(page, config, event_loop_verify)
                    ),
                    asyncio.create_task(video_optimize(page, config)),
                    asyncio.create_task(skip_questions(page, config, event_loop_answer)),
                    asyncio.create_task(play_video(page, playback_enabled)),
                ]
            )
            if getattr(config, "doExam", False):
                # 平时测试自动做题: 弹出的 dohomework 页交给 AI 自动作答
                try:
                    import modules.ai_client as ai_client
                    import modules.exam_integrate as exam_integrate
                    exam_ai_cfg = ai_client.load_ai_config()
                    tasks.append(asyncio.create_task(
                        exam_integrate.watch_exam_pages(
                            context, ai_cfg=exam_ai_cfg, submit=exam_submit)))
                    logger.event(
                        "自动做题", 状态="已启动",
                        弹窗来源="课程页【平时测试】",
                        AI配置="完整" if ai_client.is_configured(exam_ai_cfg) else "不完整",
                        答完自动提交=exam_submit,
                    )
                except Exception as exc:
                    logger.warn(f"自动做题任务启动失败: {exc}")
            logger.event(
                "后台任务启动",
                任务=", ".join(task.get_coro().__name__ for task in tasks),
            )
            if config.enableHideWindow:
                await hide_window(page)
            monitor_task = asyncio.create_task(task_monitor(tasks))

            course_total = len(config.course_urls)
            for index, course_url in enumerate(config.course_urls, 1):
                logger.section(f"课程 {index}/{course_total}")
                logger.context(课程序号=f"{index}/{course_total}", 课程地址=course_url)
                logger.info("正在加载播放页...")
                if not await goto_with_retry(page, course_url):
                    logger.error(
                        "课程页无法打开(网络超时/被拦截), 已停止本轮; "
                        "请检查网络或代理设置后重试.", shift=True)
                    run_ok = False
                    break
                await page.wait_for_timeout(1500)
                if "login" in page.url:
                    logger.warn(
                        "播放页跳转到登录页, 当前登录状态已失效, 正在重新登录.",
                        shift=True,
                    )
                    logger.event("登录失效", 地址=page.url)
                    clear_cookies(COOKIE_PATH)
                    remember_login_cookies(None)
                    await ensure_login(context, page, None, config, modules)
                    logger.info("重新进入播放页...")
                    if not await goto_with_retry(page, course_url):
                        logger.error(
                            "重新登录后课程页仍无法打开(网络超时/被拦截), 已停止本轮.",
                            shift=True)
                        run_ok = False
                        break
                    await page.wait_for_timeout(1500)

                try:
                    catalog = await detect_catalog_after_verification(page, page.url)
                except RuntimeError as exc:
                    # 目录识别失败(链接无效/页面结构变化/加载不完整)不应以
                    # 顶层"系统出错,请检查后重新启动"收场, 给出可操作提示
                    logger.warn(f"未能识别课程页目录: {exc}", shift=True)
                    logger.error(
                        "课程页可能不是有效的智慧树课程链接, 或页面未加载完整; "
                        "已停止本轮, 请检查课程链接后重试.", shift=True)
                    logger.event("课程目录识别失败", 地址=page.url, 原因=str(exc))
                    run_ok = False
                    break
                logger.info(f"检测到 {catalog.name} 课程目录.")
                logger.context(目录类型=catalog.name)
                logger.event("课程目录", 类型=catalog.name, 地址=page.url)
                await persist_login_cookies(context)
                await optimize_page(page, config, catalog)
                logger.info("页面优化完成!")
                if catalog.course_title:
                    title_element = page.locator(catalog.course_title).first
                    if await title_element.count():
                        title = " ".join(
                            (await title_element.text_content() or "").split()
                        )
                        if title:
                            logger.info(f"当前课程:<<{title}>>")
                            logger.context(课程名称=title)
                            logger.event("当前课程", 名称=title)

                playback_enabled.clear()
                outcome = await run_course(
                    page, catalog, config, logger, playback_enabled,
                    ai_cfg=exam_ai_cfg, exam_submit=exam_submit,
                )
                playback_enabled.clear()
                logger.event("课程结果", 结果=outcome.value, 目录类型=catalog.name)
                if outcome is CourseOutcome.FAILED:
                    logger.warn("课程未确认完成,已停止本轮运行.", shift=True)
                    run_ok = False
                    break
                if outcome is CourseOutcome.TIME_LIMIT:
                    all_courses_complete = False
        finally:
            for task in tasks:
                task.cancel()
            if monitor_task:
                monitor_task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if monitor_task:
                await asyncio.gather(monitor_task, return_exceptions=True)
            try:
                await persist_login_cookies(context)
            except Exception as exc:
                logger.log_exception("刷新登录 Cookies 失败.", exc)
            try:
                await context.browser.close()
            except TargetClosedError:
                pass

    logger.section("任务结束")
    logger.event(
        "运行结果",
        正常退出=run_ok,
        全部完成=all_courses_complete,
    )
    logger.clear_context()
    if not run_ok:
        logger.warn("本轮因课时进度未确认而停止.", shift=True)
        return False
    if all_courses_complete:
        logger.info("所有课程已学习完毕!")
    else:
        logger.info("本轮已按每门课程时限结束,仍有课程未完成.", shift=True)
    # 用户要求: 不弹出作者页 QRcode（show_donate 调用已移出主流程）
    print("如果觉得对你有帮助, 请为本项目点亮 star 吧~")
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="Autovisor")
    parser.add_argument("--config", default=None, help="配置文件路径(默认使用程序目录下的 config.ini)")
    parser.add_argument(
        "--check-browser",
        action="store_true",
        help="只检查 Chrome 启动和智慧树登录状态",
    )
    parser.add_argument(
        "--check-course",
        metavar="URL",
        help="阻止进度上报和自动播放,只检查课程目录选择器",
    )
    parser.add_argument(
        "--import-cookies",
        metavar="PATH",
        help="从 Requests CookieJar JSON 安全导入未过期的智慧树 Cookie",
    )
    return parser.parse_args()


def cli() -> int:
    global logger
    args = parse_args()
    print_banner()
    logger = Logger()
    exit_code = 0
    try:
        logger.section("初始化")
        logger.info("程序启动中...")
        logger.event(
            "运行环境",
            版本=__version__,
            Python=platform.python_version(),
            运行方式="打包" if getattr(sys, "frozen", False) else "源码",
            系统=platform.system(),
            系统版本=platform.release(),
            系统架构=platform.machine(),
            启动参数=(f"[{' '.join(sys.argv[1:])}]" if sys.argv[1:] else "无"),
            日志文件=logger.filename,
        )
        updater.check_for_update(logger)
        installer.validate_python_version()
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        config_path = args.config or os.path.join(base_dir, "config.ini")
        mirrors_path = os.path.join(base_dir, "data", "mirrors.json")
        # 告知 AI 模块本次实际使用的配置路径(--config 或非默认位置时不会读错文件)
        try:
            import modules.ai_client as ai_client

            ai_client.set_config_path(config_path)
        except Exception:
            pass
        config = Config(config_path, mirrors_path)
        logger.context(配置文件=config_path)
        logger.event(
            "运行配置",
            驱动=config.driver,
            浏览器路径=config.exe_path or "默认",
            连接现有浏览器=config.attach_existing_chrome,
            账号="已填写" if config.username else "未填写",
            密码="已填写" if config.password else "未填写",
            自动答题=config.enableAutoCaptcha,
            隐藏窗口=config.enableHideWindow,
            静音=config.soundOff,
            倍速=config.limitSpeed,
            时限分钟=config.limitMaxTime,
            课程数=len(config.course_urls),
            镜像源=len(config.mirrors),
        )
        for index, course_url in enumerate(config.course_urls, 1):
            logger.event("课程地址", 序号=f"{index}/{len(config.course_urls)}", 地址=course_url)
        if args.import_cookies:
            from modules.utils import import_zhihuishu_cookies

            count = import_zhihuishu_cookies(args.import_cookies, COOKIE_PATH)
            logger.info(f"已安全导入 {count} 条智慧树 Cookie.", shift=True)
            return 0
        if args.check_browser:
            return asyncio.run(check_browser(config, logger, COOKIE_PATH))
        if args.check_course:
            return asyncio.run(
                check_course(args.check_course, config, logger, COOKIE_PATH)
            )
        if not config.course_urls:
            logger.error("未检测到有效网址或不支持此类网页,请检查配置文件!")
            return 2
        if not asyncio.run(main(config)):
            exit_code = 1
    except TargetClosedError as exc:
        if "BrowserType.launch" in repr(exc):
            logger.log_exception("浏览器相关流程异常结束.", exc)
            logger.error("浏览器启动失败,请检查 Chrome 或 CDP 配置!")
        else:
            logger.debug(f"浏览器关闭结束运行: {logger.summarize_exception(exc)}")
        exit_code = 1
    except PageUnreachableError as exc:
        # 登录页导航重试后仍失败: 明确告诉用户是网络问题, 而不是"系统出错"
        logger.log_exception("智慧树页面无法打开.", exc)
        logger.error("网络无法访问智慧树(超时/被拦截), 请检查网络或代理设置后重试!",
                     shift=True)
        exit_code = 1
    except ConfigError as exc:
        logger.error(f"配置文件无效: {exc}", shift=True)
        logger.info("请完整解压发行包，并确保 config.ini 与 Autovisor.exe 位于同一目录。")
        exit_code = 1
    except Exception as exc:
        logger.log_exception("程序运行时出现未处理异常.", exc, shift=True)
        if isinstance(exc, KeyError):
            logger.error(f"配置文件错误!")
        elif isinstance(exc, FileNotFoundError):
            logger.error(f"依赖文件缺失: {exc.filename},请重新安装程序!")
        elif isinstance(exc, UnicodeDecodeError):
            logger.error("配置文件编码错误,保存时请选择UTF-8或GBK编码!")
        else:
            logger.error("系统出错,请检查后重新启动!")
        exit_code = 1
    finally:
        logger.save()
        # windowed exe(console=False) 下 sys.stdin 为 None, 直接调用 isatty()
        # 会抛 AttributeError 并被 GUI 线程捕获成"刷课线程异常"
        if getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
            try:
                input("程序已结束,按Enter退出...")
            except EOFError:
                # 非交互式运行(重定向/自动化)时 stdin 可能已关闭, 不应视作异常
                pass
    return exit_code


if __name__ == "__main__":
    sys.exit(cli())