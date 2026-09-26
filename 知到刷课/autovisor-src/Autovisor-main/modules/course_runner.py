import time
from enum import Enum

from playwright.async_api import Page

from modules.course_playback import elapsed_minutes, learn_lesson, review_lesson
from modules.lesson_navigation import (
    CatalogSelectors,
    detect_catalog,
    lesson_progress,
    wait_for_lesson_active,
)
from modules.tasks import has_visible_verification, wait_until_verification_hidden
from modules.utils import get_filtered_class, get_lesson_name

# 课时项(<li>)的点击发生在 set_default_timeout(10000) 之前, 不显式限时就会沿用
# 页面默认的 24 小时; 弹窗未关、被遮挡等异常情况下会一直卡在可操作性等待上。
LESSON_CLICK_TIMEOUT_MS = 10_000

# 目录节点在 detect_catalog 里刚确认过存在, 这里只做一次快速复核。
CATALOG_ATTACH_TIMEOUT_MS = 5_000


class CourseOutcome(Enum):
    COMPLETED = "completed"
    TIME_LIMIT = "time_limit"
    FAILED = "failed"


# 等待"平时测试自动作答"结束的上限(秒): 做完整套题可能较久, 但不该无限等
EXAM_WAIT_LIMIT_S = 900


async def _wait_exam_idle(page: Page, logger) -> None:
    """有平时测试正在自动作答时, 先等它结束再操作课程目录。

    平台弹出的做题页会占用/遮挡课程页目录, 此时点击课时必然"激活超时",
    旧版本会因此把整门课判为失败并中断正在进行的作答。
    """
    try:
        from modules.exam_integrate import exam_in_progress
    except Exception:
        return
    waited = 0
    announced = False
    while exam_in_progress() and waited < EXAM_WAIT_LIMIT_S:
        if not announced:
            announced = True
            logger.info("检测到正在自动作答的平时测试, 等它完成后再继续刷课…",
                        shift=True)
        await page.wait_for_timeout(2000)
        waited += 2
    if announced:
        logger.event("等待平时测试结束", 等待秒数=waited, 结果=
                     "已结束" if not exam_in_progress() else "超时继续")


async def detect_catalog_after_verification(
    page: Page, course_url: str
) -> CatalogSelectors:
    deadline = time.monotonic() + 20
    while True:
        if await has_visible_verification(page):
            await wait_until_verification_hidden(page)
            deadline = time.monotonic() + 20
        remaining_ms = int(max(0, deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise RuntimeError("课程目录加载超时，且未检测到可处理的安全验证")
        try:
            return await detect_catalog(
                page, course_url, timeout_ms=min(1000, remaining_ms)
            )
        except RuntimeError:
            continue


async def run_course(
    page: Page,
    catalog: CatalogSelectors,
    config,
    logger,
    playback_enabled,
    ai_cfg=None,
    exam_submit=False,
) -> CourseOutcome:
    await page.wait_for_selector(
        catalog.item, state="attached", timeout=CATALOG_ATTACH_TIMEOUT_MS
    )
    to_learn = await get_filtered_class(page, catalog)
    learning = bool(to_learn)
    lessons = (
        to_learn
        if learning
        else await get_filtered_class(page, catalog, include_all=True)
    )
    logger.event(
        "目录筛选",
        模式="学习" if learning else "复习",
        待学课时=len(to_learn),
        本轮课时=len(lessons),
    )
    if not lessons:
        # 目录里可能只有「平时测试」这类非视频任务点: 先尝试自动做完再判定失败
        try:
            from modules.exam_navigation import enter_pending_tests

            handled = await enter_pending_tests(
                page, catalog, config, logger,
                ai_cfg=ai_cfg, submit=exam_submit,
            )
            if handled:
                logger.event("本次自动完成测试任务点", 数量=handled)
                logger.event("课程结果", 结果="仅测试任务点, 已处理")
                return CourseOutcome.COMPLETED
        except Exception as exc:
            logger.warn(f"处理测试任务点异常: {exc}", shift=True)
        logger.error("课程目录中没有可播放的视频课时.")
        logger.event("课程结果", 结果="无可用课时")
        return CourseOutcome.FAILED

    start_time = time.time()
    paused_time = 0.0
    # 已尝试过的测试任务点标题: 跨课时累计, 避免反复点击同一条目
    tried_tests = set()
    lesson_fail_streak = 0
    for index, lesson in enumerate(lessons):
        position = f"{index + 1}/{len(lessons)}"
        playback_enabled.clear()
        # 若有平时测试正在自动作答, 先等它结束: 做题页会占用主页面/目录,
        # 此时点课时必然激活超时(实测会把整个课程误判为失败)
        await _wait_exam_idle(page, logger)
        # 学习本课时前, 先处理目录里"平时测试"等非视频任务点(默认关闭时不动作)
        try:
            from modules.exam_navigation import enter_pending_tests

            handled = await enter_pending_tests(
                page, catalog, config, logger,
                ai_cfg=ai_cfg, submit=exam_submit, tried=tried_tests,
            )
            if handled:
                logger.event("本次自动完成测试任务点", 数量=handled)
        except Exception as exc:
            logger.warn(f"处理测试任务点异常(不影响视频刷课): {exc}", shift=True)
        await lesson.click(timeout=LESSON_CLICK_TIMEOUT_MS)
        active = await wait_for_lesson_active(lesson, catalog)
        if not active:
            logger.warn("课时切换超时,正在重试一次.", shift=True)
            logger.event(
                "课时激活超时",
                序号=position,
                目录类型=catalog.name,
                选择器=catalog.active,
            )
            # 重试前先等做题结束 + 刷新页面重新定位(做题页/弹窗会让目录失效)
            await _wait_exam_idle(page, logger)
            try:
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                refreshed = await get_filtered_class(
                    page, catalog, include_all=not learning)
                if len(refreshed) > index:
                    lesson = refreshed[index]
                await lesson.click(timeout=LESSON_CLICK_TIMEOUT_MS)
                active = await wait_for_lesson_active(lesson, catalog)
            except Exception as exc:
                logger.debug(f"刷新后重试选中课时失败: {exc}")
        if not active:
            # 单个课时选不中不应终止整门课程(做题页占用/目录重排都很常见):
            # 跳过它继续后面的课时, 连续 3 个都失败才判定本课程失败
            lesson_fail_streak += 1
            logger.warn(
                f"无法选中课时 {position}, 跳过该课时"
                f"(连续第 {lesson_fail_streak} 次)", shift=True)
            logger.event("课时无法选中", 序号=position, 连续失败=lesson_fail_streak)
            if lesson_fail_streak >= 3:
                logger.error(f"连续 3 个课时无法选中, 终止本课程(目录类型: {catalog.name})")
                logger.event("课程结果", 结果="课时无法选中", 序号=position)
                return CourseOutcome.FAILED
            continue
        lesson_fail_streak = 0

        await page.wait_for_timeout(1000)
        title = await get_lesson_name(page, lesson, catalog)
        logger.info(f"正在学习:{title}")
        initial_progress = await lesson_progress(lesson, catalog)
        logger.context(课时序号=position, 课时名称=title)
        logger.event(
            "课时开始",
            序号=position,
            标题=title,
            平台进度=f"{initial_progress}%",
        )
        lesson_start = time.time()
        page.set_default_timeout(10000)
        await page.wait_for_selector("video", state="attached")
        playback_enabled.set()

        if learning:
            added_pause, completed, reached_limit = await learn_lesson(
                page, start_time, paused_time, lesson, catalog, config, logger
            )
        else:
            added_pause, completed, reached_limit = await review_lesson(
                page, start_time, paused_time, config, logger
            )
        paused_time += added_pause

        final_progress = await lesson_progress(lesson, catalog)
        logger.event(
            "课时结果",
            序号=position,
            标题=title,
            完成=completed,
            达到时限=reached_limit,
            平台进度=f"{final_progress}%",
            本课用时=f"{time.time() - lesson_start:.0f}s",
        )
        if reached_limit:
            logger.info(f"当前课程已达时限:{config.limitMaxTime}min", shift=True)
            logger.info("即将进入下门课程!")
            logger.event("课程结果", 结果="达到时限", 课时数=len(lessons))
            return CourseOutcome.TIME_LIMIT
        if not completed:
            logger.warn(
                f'"{title}" 未能确认播放完成,本轮停止切换下一课.',
                shift=True,
            )
            logger.event(
                "课程结果",
                结果="课时未确认完成",
                序号=position,
                平台进度=f"{final_progress}%",
            )
            return CourseOutcome.FAILED

        if index < len(lessons) - 1:
            logger.info(f'"{title}" 已完成!', shift=True)
            logger.info(
                f"本次课程已学习:{elapsed_minutes(start_time, paused_time):.1f} min"
            )

    if learning:
        logger.info("已学完本课程全部内容!", shift=True)
        print("==" * 10)
    else:
        logger.info(f'"{title}" 已完成!', shift=True)
    logger.event("课程结果", 结果="全部完成", 课时数=len(lessons))
    return CourseOutcome.COMPLETED
