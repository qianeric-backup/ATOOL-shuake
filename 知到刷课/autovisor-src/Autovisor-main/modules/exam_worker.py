# -*- coding: utf-8 -*-
"""知到考试/作业自动做题 worker.

架构(全部按真实站点逆向):
  1) requests 完成 studentExam SSO(gologin) 换考试网关会话 → cookies
     (Playwright 新开会话会触发 SSO 死循环, 已规避)
  2) Playwright(Firefox 优先, 失败回退 Chromium) 注入 cookies 打开 dohomework 页
  3) 拦截 SPA 自己发出的 POST /student/doHomework 响应,
     rt.examBase.workExamParts[].questionDtos[] 内含:
         eid / questionType{id,name} / name(题干) / questionOptions[{id,content}]
     — 题干在页面 DOM 的 shadow 容器里读不到, 所以用网络数据取题最稳
  4) 逐题: 答题卡 .answerCard_list1 li[(序号-1)] 跳题 → 可见块 .examPaper_subject:visible
       选项行 .nodeLab (+.ABCase 字母 + .node_detail 文本, input[value=选项id])
       AI(与课中题同源 modules.ai_client) 判定字母 → 点选
       填空/简答: block 内 input[type=text]/textarea 直接 fill
     点选后 SPA 自动 POST /answer/saveStudentAnswer
  5) 可选提交: .operateBtn_box .el-button [提交作业] + Element 确认框
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import modules.ai_client as ai_client
from modules.logger import Logger

logger = Logger()


def _runtime_base_dir() -> Path:
    """运行根目录: 打包(exe)时为 exe 所在目录, 源码态为项目目录。

    frozen 下 __file__ 在 _MEIPASS 内, 用它推导会把可写数据(登录凭证)
    指到临时目录, 导致自动做题永远拿不到 CAS 凭据。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE = _runtime_base_dir()


def data_path(name: str) -> Path:
    """data/ 下的运行时数据路径(每次调用时解析, 不随导入时机冻结)。"""
    return _runtime_base_dir() / "data" / name


def course_cookie_file() -> Path:
    """刷课流程保存的登录凭证(含 CASTGC / jt-cas), 自动做题优先用它。"""
    return data_path("cookies.json")


def cas_cookie_file() -> Path:
    """兼容旧用法: 手工导出的 cookie 文件。"""
    return data_path("exam_cookies.json")


# 兼容旧引用的模块级常量(源码态=项目目录; 运行时请用上面的函数)
COURSE_COOKIE_FILE = BASE / "data" / "cookies.json"
CAS_COOKIE_FILE = BASE / "data" / "exam_cookies.json"
DEFAULT_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

EXAM_API = "https://studentexam-api.zhihuishu.com"
TAURUS_API = "https://taurusexam-api.zhihuishu.com"


def _clean(text) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _load_cookie_file(path: Path, cas: dict) -> int:
    """把 cookie 文件(Playwright 导出格式)读进 cas, 返回读入条数。"""
    if not path.is_file():
        return 0
    count = 0
    try:
        for item in json.loads(path.read_text(encoding="utf-8")):
            name = str(item.get("name") or "").strip()
            value = item.get("value")
            if name and value not in (None, ""):
                cas.setdefault(name, str(value))
                count += 1
    except Exception:
        return 0
    return count


def sso_cookies(extra=None) -> dict:
    """CAS gologin 换考试网关会话, 返回 {name:{value,domain,path}}.

    凭据来源(按优先级):
      1. 刷课流程保存的 data/cookies.json —— 正常刷课登录后自动就有;
      2. 手工导出的 data/exam_cookies.json(兼容旧用法);
      3. 环境变量 ZHS_COOKIE_STR。
    """
    import os

    import requests

    cas = {}
    for path in (course_cookie_file(), cas_cookie_file()):
        loaded = _load_cookie_file(path, cas)
        if loaded and (cas.get("CASTGC") or cas.get("jt-cas")):
            logger.debug(f"自动做题凭据来源: {path} ({loaded} 条)")
            break
    env = os.environ.get("ZHS_COOKIE_STR")
    if env:
        for kv in env.split(";"):
            if "=" in kv:
                k, v = kv.strip().split("=", 1)
                cas.setdefault(k, v)
    if extra:
        cas.update(extra)
    if not (cas.get("CASTGC") or cas.get("jt-cas")):
        raise RuntimeError(
            "缺少 CAS 登录凭据: 请先正常刷课登录一次(程序会把登录凭证保存到 "
            f"{course_cookie_file()}), 或手工导出 cookie 到 {cas_cookie_file()} "
            "（也可设置环境变量 ZHS_COOKIE_STR）")

    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA})
    s.cookies.update({k: v for k, v in cas.items() if v})
    fu = "https%3A%2F%2Fonlineexamh5new.zhihuishu.com%2FstuExamWeb.html"
    for base in (EXAM_API + "/studentExam", TAURUS_API + "/taurusExam"):
        try:
            s.get(f"{base}/gateway/f/v1/gologin/login?fromurl={fu}", timeout=25)
        except Exception as e:
            logger.debug(f"SSO 跳转异常: {e}")
    out = {}
    for c in s.cookies:
        out[c.name] = {"value": c.value, "domain": c.domain or ".zhihuishu.com",
                       "path": c.path or "/"}
    for name, val in cas.items():
        out.setdefault(name, {"value": val, "domain": ".zhihuishu.com", "path": "/"})
    logger.event("考试 SSO", 会话就绪=True)
    return out


def parse_exam_url(url: str) -> dict:
    m = re.search(r"dohomework/([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/]+)", url or "")
    if not m:
        raise ValueError("链接里没有 dohomework 参数")
    return {"recruitId": m.group(1), "stuExamId": m.group(2), "examId": m.group(3),
            "courseId": m.group(4), "schoolId": m.group(5), "meetCourseType": m.group(6)}


async def open_exam_page(playwright, url, cookies, engine="firefox", headless=True):
    """启动浏览器注入 cookies; 返回 (browser, ctx, page)."""
    browser = None
    engine = (engine or "firefox").lower()
    if engine == "firefox":
        try:
            browser = await playwright.firefox.launch(headless=headless)
        except Exception as e:
            logger.warn(f"Firefox 启动失败({e.__class__.__name__}), 回退 Chromium.")
    if browser is None:
        browser = await playwright.chromium.launch(headless=headless)
    ctx = await browser.new_context(viewport={"width": 1400, "height": 1000},
                                    user_agent=DEFAULT_UA)
    jars = []
    for name, item in cookies.items():
        jars.append({"name": name, "value": item.get("value") or "",
                     "domain": item.get("domain") or ".zhihuishu.com",
                     "path": item.get("path") or "/", "secure": True})
    await ctx.add_cookies(jars)
    page = await ctx.new_page()
    return browser, ctx, page


def _strip_tokens(answer: str):
    raw = (answer or "").strip()
    if not raw:
        return []
    parts = [p for p in re.split(r"[;；,，、\s]+", raw) if p]
    if len(parts) == 1 and len(parts[0]) > 1:
        strip0 = re.sub(r"[^A-Za-z]", "", parts[0])
        if strip0 and re.fullmatch(r"[A-Za-z]{2,6}", strip0) and len(strip0) == len(parts[0]):
            parts = list(parts[0].upper())
    return parts


def _ai_ask(ai_cfg, qtype, title, options):
    return ai_client.ask_question(qtype, title, options, cfg=ai_cfg)


def _judge_letter(tok: str) -> str:
    """判断题 token → 选项字母(默认 A=对, B=错)."""
    clean = (tok or "").replace("√", "对").replace("×", "错").upper()
    if any(x in clean for x in ("对", "TRUE", "正确")):
        return "A"
    if any(x in clean for x in ("错", "FALSE", "不正确", "误")):
        return "B"
    return clean if len(clean) <= 2 else ""


async def _wait_save(page, timeout_ms=8000):
    """等 SPA 自动 saveStudentAnswer 请求."""
    try:
        await page.wait_for_response(
            lambda r: "saveStudentAnswer" in r.url and r.request.method == "POST",
            timeout=timeout_ms)
    except Exception:
        pass


async def answer_on_view(page, qinfo, ai_cfg):
    """按 qinfo(网络数据) 在可见题块里点选/填空."""
    block = page.locator(".examPaper_subject:visible").first
    if await block.count() == 0:
        logger.warn("当前无可见题块")
        return False
    num_loc = block.locator(".subject_num")
    num_txt = _clean(await num_loc.text_content()) if await num_loc.count() else ""

    qt = qinfo["type"]
    options = qinfo["options"]          # [{id, content, letter}]
    texts = [o["content"] for o in options]
    letters = [o["letter"] for o in options]

    # 填空/简答: 文本输入
    if not options:
        inputs = block.locator("input[type=text], textarea")
        nin = await inputs.count()
        answer = await asyncio.to_thread(_ai_ask, ai_cfg, qt, qinfo["title"], None)
        if not answer:
            logger.warn("AI 未返回答案", 题号=num_txt)
            return False
        tokens = _strip_tokens(answer)
        done = 0
        for i in range(max(nin, 1)):
            v = _clean(tokens[i] if i < len(tokens) else answer)
            try:
                await inputs.nth(i if nin else 0).fill(v, timeout=3000)
                await page.wait_for_timeout(250)
                done += 1
            except Exception as e:
                logger.debug(f"填空失败: {e}")
        if done:
            logger.event("AI 做题", 题号=num_txt, 题型=qt, 填写=done)
        return done > 0

    answer = await asyncio.to_thread(_ai_ask, ai_cfg, qt, qinfo["title"], texts)
    if not answer:
        logger.warn("AI 未返回答案", 题号=num_txt)
        return False
    tokens = _strip_tokens(answer)

    want = set()
    is_judge = len(letters) == 2 and (qinfo.get("isJudge") or
                                      (("对" in " ".join(texts)) and ("错" in " ".join(texts))))
    for tok in tokens:
        tu = (tok or "").upper()
        if qinfo.get("isJudge") and len(tok) >= 1 and (
                any(x in tok for x in "对错真假TRUE正确") or "√" in tok or "×" in tok):
            L = _judge_letter(tok)
            if L:
                want.add(L)
            continue
        if len(tu) <= 2 and tu in letters:
            want.add(tu)
            continue
        for L, t in zip(letters, texts):
            if tu and (tu in t.upper() or t.upper().startswith(tu)):
                want.add(L)
                break
    if not want:
        logger.warn("AI 答案与选项不匹配", 题号=num_txt, 答案=answer)
        return False

    clicked = 0
    for o in options:
        if o["letter"] not in want:
            continue
        node = block.locator(
            f".nodeLab:has(.ABCase:text-is('{o['letter']}.'))").first
        if await node.count() == 0:
            node = block.locator(
                f".nodeLab:has-text(\"{o['content'][:18]}\")").first
        if await node.count() == 0:
            node = block.locator(f".nodeLab input[value='{o['id']}']").first
        try:
            await node.first.click(timeout=4000)
            await page.wait_for_timeout(500)
            if clicked == 0:
                await _wait_save(page)
            clicked += 1
            logger.event("AI 做题", 题号=num_txt, 题型=qt, 选中=o["letter"])
        except Exception as e:
            logger.debug(f"点选失败: {e}")
    return clicked > 0


def _normalize_questions(exam_base: dict, is_judge_detection=None) -> list:
    """把 SPA 收到的 doHomework 数据转成统一格式的题目列表."""
    questions = []
    for part in (exam_base.get("workExamParts") or []):
        for q in (part.get("questionDtos") or []):
            tname = ((q.get("questionType") or {}).get("name") or "单选")
            raw_opts = q.get("questionOptions") or []
            judge = (tname == "判断") or (
                len(raw_opts) == 2 and any(("对" in _clean(o.get("content")))
                                           for o in raw_opts) is True and
                any(("错" in _clean(o.get("content"))) for o in raw_opts))
            opts = []
            for idx, oo in enumerate(raw_opts):
                opts.append({
                    "id": oo.get("id"),
                    "content": _clean(oo.get("content")),
                    "letter": chr(65 + idx),
                })
            blank = not raw_opts
            questions.append({
                "eid": q.get("eid"),
                "title": _clean(q.get("name")),
                "type": "填空" if blank else tname,
                "isJudge": judge,
                "options": opts,
            })
    return questions


async def run_exam(page, url, ai_cfg, submit=False) -> dict:
    """主流程: 打开页面 → 抓题 → 答题卡逐题 AI 作答 → (可选)提交."""
    parse_exam_url(url)
    if not ai_client.is_configured(ai_cfg):
        raise RuntimeError("AI 配置缺失 (api_url/api_key/ai_id)")

    holder = {}

    async def on_resp(r):
        try:
            if "student/doHomework" in r.url and r.request.method == "POST" \
                    and r.status == 200:
                body = await r.json()
                rt = (body.get("rt") or {})
                if isinstance(rt, dict) and isinstance(rt.get("examBase"), dict):
                    holder["json"] = body
        except Exception:
            pass

    page.on("response", on_resp)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_selector(".examPaper_subject", timeout=40000)
    for _ in range(20):
        if holder.get("json"):
            break
        await page.wait_for_timeout(500)
    body = holder.get("json") or {}
    rt = (body.get("rt") or {}) if isinstance(body, dict) else {}
    exam_base = (rt.get("examBase") or {})
    questions = _normalize_questions(exam_base)
    if not questions:
        raise RuntimeError("未从 doHomework 响应取到题目数据 (可能需要重做/已交卷)")

    lis = page.locator(".answerCard_list1 li")
    nums = await lis.count()
    result = {"url": page.url, "answered": [], "failed": [], "total": len(questions)}
    for idx, qinfo in enumerate(questions):
        if idx < nums:
            try:
                await lis.nth(idx).click(timeout=5000)
                await page.wait_for_timeout(1400)
            except Exception as e:
                logger.debug(f"答题卡跳题失败: {e}")
                continue
        try:
            ok = await answer_on_view(page, qinfo, ai_cfg)
        except Exception as e:
            logger.warn("作答异常", 题序=idx + 1, 详情=str(e)[:160])
            ok = False
        (result["answered"] if ok else result["failed"]).append(idx + 1)
        await page.wait_for_timeout(400)

    if submit:
        await submit_paper(page)
    logger.event("做题完成", 总数=len(questions),
                 已答=len(result["answered"]), 失败=len(result["failed"]))
    return result


async def submit_paper(page):
    """点击【提交作业】并在确认框里按确定."""
    try:
        btn = page.locator(".operateBtn_box .el-button").filter(has_text="提交作业").first
        if await btn.count() == 0:
            logger.warn("找不到提交按钮")
            return
        await btn.click(timeout=5000)
        await page.wait_for_timeout(1500)
        box = page.locator(".el-message-box").last
        for _ in range(8):
            if await box.count():
                break
            await page.wait_for_timeout(500)
        if await box.count():
            cbtn = box.locator("button").filter(has_text="确定").first
            if await cbtn.count():
                await cbtn.click(timeout=4000)
        await page.wait_for_timeout(1500)
        logger.event("已提交作业")
    except Exception as e:
        logger.warn(f"提交失败, 请手动提交: {e}")
