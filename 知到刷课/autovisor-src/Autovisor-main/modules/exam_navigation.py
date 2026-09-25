# -*- coding: utf-8 -*-
"""课程目录里「平时测试」等非视频任务点的自动进入。

智慧树新目录中**视频课时**带 .hasvideo 标记(见 lesson_navigation.WISDOM_CATALOG
的 item 选择器), 而「平时测试 / 章节测试」这类任务点不带该标记 —— 现有的课时
循环只会遍历视频课时, 永远不会点开测试任务点, 所以「自动做题」也永远等不到
做题页。本模块负责在刷课过程中主动识别并点击进入这些任务点, 之后由
modules.exam_integrate(新标签) 或 modules.exam_worker(同页跳转) 自动作答。

设计原则(确保不影响视频刷课):
  * 仅在开启「平时测试自动做题」(config.doExam) 且 AI 配置完整时启用;
  * 只点击"标题命中测试关键词 + 未完成(无 finish 标记)"的目录项;
  * 同一标题每轮课程只尝试一次(避免反复点击卡住刷课);
  * 所有异常都被吞掉并写日志, 绝不让自动做题失败影响视频学习。
"""
import time

import modules.ai_client as ai_client
from modules.lesson_navigation import get_lesson_title

# 目录标题里出现这些词即视为"测试类任务点"
TEST_KEYWORDS = (
    "平时测试", "章节测试", "单元测试", "阶段测试", "课后测试",
    "随堂测验", "测验", "测试", "作业",
)

EXAM_URL_MARK = "stuExamWeb"
LEARN_CLICK_TIMEOUT_MS = 10_000
# 点击后等做题页出现的时间(弹窗/新标签需要一点时间)
EXAM_APPEAR_TIMEOUT_S = 30
# 单次做题的最长等待(做完整套题可能较久)
EXAM_FINISH_TIMEOUT_S = 1200


def _item_selectors(catalog) -> tuple[str, ...]:
    """目录条目选择器(不限定 hasvideo, 以便覆盖测试任务点)。"""
    if catalog.name == "fusion":
        return (".chapter-content-second",)
    if catalog.name == "hike":
        return (".file-item",)
    if catalog.name == "legacy":
        return (".clearfix.video", ".clearfix")
    return (".child-info",)


async def _is_finished(lesson, catalog) -> bool:
    try:
        if catalog.finish and await lesson.locator(catalog.finish).count() > 0:
            return True
    except Exception:
        pass
    return False


async def find_pending_test_items(page, catalog, tried=()) -> list:
    """列出未完成的测试类任务点, 返回 [(标题, locator), ...]。"""
    found = []
    for selector in _item_selectors(catalog):
        try:
            items = page.locator(selector)
            total = await items.count()
        except Exception:
            continue
        for index in range(total):
            lesson = items.nth(index)
            try:
                title = await get_lesson_title(page, lesson, catalog)
            except Exception:
                continue
            if not title or title in tried:
                continue
            if not any(keyword in title for keyword in TEST_KEYWORDS):
                continue
            if await _is_finished(lesson, catalog):
                continue
            found.append((title, lesson))
        if found:
            break
    return found


async def _answer_inline(page, logger, ai_cfg, submit) -> str:
    """同页跳转到做题页的情况: 直接交给 exam_worker 作答。"""
    import modules.exam_worker as worker

    try:
        await worker.run_exam(page, page.url, ai_cfg, submit=submit)
        return "同页做题完成"
    except Exception as exc:
        logger.warn(f"同页自动做题失败(请手动完成该测试): {exc}", shift=True)
        return "同页做题失败"


async def _wait_and_answer(page, logger, ai_cfg, submit) -> str:
    """点击测试任务点后: 等做题页出现(新标签或同页跳转)并完成作答。"""
    context = page.context
    before = len(context.pages)
    deadline = time.monotonic() + EXAM_APPEAR_TIMEOUT_S
    while time.monotonic() < deadline:
        if len(context.pages) > before:
            # 新标签: exam_integrate 已监听 context 的 page 事件, 等它作答并关闭
            finish = time.monotonic() + EXAM_FINISH_TIMEOUT_S
            while time.monotonic() < finish:
                if len(context.pages) <= before:
                    try:
                        await page.bring_to_front()
                    except Exception:
                        pass
                    return "新标签做题完成"
                await page.wait_for_timeout(1000)
            return "新标签做题超时"
        try:
            url = page.url or ""
        except Exception:
            return "页面已关闭"
        if EXAM_URL_MARK in url or "onlineexamh5new" in url:
            return await _answer_inline(page, logger, ai_cfg, submit)
        await page.wait_for_timeout(500)
    return "未弹出做题页"


async def enter_pending_tests(page, catalog, config, logger, *, ai_cfg=None,
                              submit=False, tried=None, max_items=10) -> int:
    """依次进入未完成的测试类任务点并自动作答, 返回处理条数。"""
    if not getattr(config, "doExam", False):
        return 0
    if ai_cfg is None:
        ai_cfg = ai_client.load_ai_config()
    if not ai_client.is_configured(ai_cfg):
        logger.warn(
            "「平时测试自动做题」已开启但 AI 配置不完整(需要 api_url/api_key/ai_id), "
            "跳过测试任务点", shift=True)
        return 0

    tried = tried if tried is not None else set()
    handled = 0
    for _ in range(max_items):
        try:
            items = await find_pending_test_items(page, catalog, tried)
        except Exception as exc:
            logger.warn(f"扫描测试任务点失败: {exc}", shift=True)
            return handled
        if not items:
            break
        title, lesson = items[0]
        tried.add(title)
        logger.info(f'发现未完成的测试任务点:「{title}」, 正在进入并自动作答…', shift=True)
        logger.event("进入平时测试", 标题=title)
        try:
            await lesson.click(timeout=LEARN_CLICK_TIMEOUT_MS)
        except Exception as exc:
            logger.warn(f'点击测试任务点「{title}」失败: {exc}', shift=True)
            logger.event("进入平时测试", 标题=title, 结果="点击失败")
            continue
        result = await _wait_and_answer(page, logger, ai_cfg, submit)
        logger.event("平时测试结果", 标题=title, 结果=result)
        logger.info(f'测试任务点「{title}」处理结果: {result}', shift=True)
        handled += 1
        await page.wait_for_timeout(1500)
    return handled
