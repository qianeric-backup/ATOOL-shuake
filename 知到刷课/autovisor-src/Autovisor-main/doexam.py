# -*- coding: utf-8 -*-
"""知到做题页入口: requests 级 SSO 会话 + Playwright(Firefox/Chromium) 自动作答.

用法:
  # 1. 最新登录 cookie 存 data/exam_cookies.json (或环境变量 ZHS_COOKIE_STR)
  # 2. AI 配置与课中题共用 config.ini [ai-option], 或 --ai-url/--ai-key/--ai-model 覆盖
  python3 doexam.py "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/471177/yoQnbrNW/5pV3Az2w/1000007361/11/0" [--submit] [--engine firefox] [--headless false]
  # 先只打开题目页看结构
  python3 doexam.py --dump <同一链接>
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import modules.ai_client as ai_client
import modules.exam_worker as worker


def main():
    parser = argparse.ArgumentParser(description="知到做题自动作答")
    parser.add_argument("exam_url", help="dohomework 做题页链接")
    parser.add_argument("--dump", action="store_true", help="只打开题目页列题目, 不点答案")
    parser.add_argument("--submit", action="store_true", help="答完后自动提交作业")
    parser.add_argument("--engine", default="firefox", choices=["firefox", "chromium"])
    parser.add_argument("--headless", default="true", help="--headless true/false")
    parser.add_argument("--ai-url", default=None, help="临时覆盖 AI API 地址")
    parser.add_argument("--ai-key", default=None, help="临时覆盖 AI API key")
    parser.add_argument("--ai-model", default=None, help="临时覆盖 AI 模型 ID")
    args = parser.parse_args()

    ai_cfg = ai_client.load_ai_config()
    if args.ai_url:
        ai_cfg["api_url"] = args.ai_url
    if args.ai_key:
        ai_cfg["api_key"] = args.ai_key
    if args.ai_model:
        ai_cfg["ai_id"] = args.ai_model
    if not args.dump and not ai_client.is_configured(ai_cfg):
        print("AI 配置缺失: config.ini [ai-option] 需要填 api_url / api_key / ai_id"
              " (与课中题是同一份配置), 或用 --ai-url/--ai-key/--ai-model 覆盖。",
              file=sys.stderr)
        return 2

    headless = str(args.headless).lower() not in ("false", "no", "0")

    async def go():
        cookies = worker.sso_cookies()
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser, ctx, page = await worker.open_exam_page(
                p, args.exam_url, cookies, engine=args.engine, headless=headless)
            try:
                if args.dump:
                    await page.goto(args.exam_url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_selector(".examPaper_subject", timeout=40000)
                    data = {"questions": 0, "paper": []}
                    blocks = page.locator(".examPaper_subject")
                    n_q = await blocks.count()
                    data["questions"] = n_q
                    for i in range(n_q):
                        block = blocks.nth(i)
                        num_loc = block.locator(".subject_num")
                        q = {
                            "num": (await num_loc.text_content()
                                    if await num_loc.count() else "?"),
                            "type": (await block.locator(".subject_type").text_content() or "").strip(),
                            "title": (await block.locator(".subject_describe").text_content()
                                      or "").strip(),
                            "options": [],
                        }
                        labs = block.locator(".nodeLab")
                        ln = await labs.count()
                        for k in range(ln):
                            q["options"].append(
                                (await labs.nth(k).text_content() or "").strip())
                        data["paper"].append(q)
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    return 0
                result = await worker.run_exam(page, args.exam_url, ai_cfg,
                                               submit=args.submit, dry=not args.dump and False)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            finally:
                await browser.close()

    sys.exit(asyncio.run(go()))


if __name__ == "__main__":
    main()
