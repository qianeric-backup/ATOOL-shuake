# -*- coding: utf-8 -*-
"""把「平时测试」自动做题接入刷课流程.

课程页(studyvideoh5)点击【平时测试】时会新开
onlineexamh5new `stuExamWeb.html#/webExamList/dohomework/...` 做题页。
本模块监听刷课浏览器 context 的新页面, 命中做题页后交给
modules.exam_worker 的 AI 流程自动作答(与课中题同一 AI 配置),
答完自动关掉该页、让刷课页面继续播放。
"""
import asyncio

import modules.ai_client as ai_client
import modules.exam_worker as worker
from modules.logger import Logger

logger = Logger()

EXAM_URL_MARK = "stuExamWeb.html#/webExamList/dohomework"
# 同一套题最多自动作答次数: 作答全部失败时平台会反复弹同一页, 避免无限重试
MAX_EXAM_ATTEMPTS = 2
# 已尝试过的做题页(标识 -> 次数), 进程级
_exam_attempts = {}


def _exam_key(url: str) -> str:
    return (url or "").split("#")[-1][:120]


def _ai_ready(cfg) -> bool:
    return bool(cfg.get("api_url")) and bool(cfg.get("api_key")) and bool(cfg.get("ai_id"))


async def _handle_new_page(page, ai_cfg, submit) -> None:
    try:
        # 等新页 URL 稳定(stuExamWeb 弹窗会先占位再跳到 dohomework)
        # 注意单位为秒: 这里必须短轮询, 写成 300 会让每题最长等 5 分钟
        for _ in range(15):
            url = ""
            try:
                url = page.url or ""
            except Exception:
                return
            if EXAM_URL_MARK in url:
                break
            if "stuExamWeb" not in url and "onlineexamh5new" not in url:
                return
            await asyncio.sleep(0.3)
    except Exception:
        return
    logger.event("平时测试已弹出, 进入自动做题", 地址=page.url[:120])
    key = _exam_key(page.url)
    attempts = _exam_attempts.get(key, 0)
    if attempts >= MAX_EXAM_ATTEMPTS:
        logger.warn(
            f"同一套题已自动尝试 {attempts} 次仍未答上(通常是 AI 配置无效), "
            "跳过并关闭做题页, 请手动完成该测试.", shift=True)
        logger.event("跳过重复做题页", 地址=page.url[:120], 已尝试=attempts)
        try:
            await page.close()
        except Exception:
            pass
        return
    try:
        result = await worker.run_exam(page, page.url, ai_cfg, submit=submit)
    except Exception as e:
        logger.warn("自动做题失败, 请手动完成该测试.", shift=True)
        logger.event("做题异常", 说明=str(e)[:200])
        _exam_attempts[key] = attempts + 1
    else:
        answered = len((result or {}).get("answered") or [])
        if answered == 0:
            # 一题都没答上: 记一次, 达到上限后不再重试同一套题
            _exam_attempts[key] = attempts + 1
            logger.warn(
                "本次未成功作答任何题目(请检查 AI 配置), 平台可能再次弹出该测试.",
                shift=True)
        else:
            _exam_attempts.pop(key, None)
        logger.event("做题页处理完成, 关闭并返回刷课", shift=True)
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def watch_exam_pages(context, ai_cfg=None, submit=False):
    """长期任务: 监听 context 弹出的做题页并交给 exam_worker 自动作答."""
    if ai_cfg is None:
        ai_cfg = ai_client.load_ai_config()
    if not _ai_ready(ai_cfg):
        logger.warn("自动做题开启但 AI 配置缺失 — 检测到做题页时不会自动作答", shift=True)

    def on_page(page):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        loop.create_task(_handle_new_page(page, ai_cfg, submit))

    context.on("page", on_page)

    # 常驻, 由 task_monitor 统一管理生命周期
    while True:
        await asyncio.sleep(3600)
