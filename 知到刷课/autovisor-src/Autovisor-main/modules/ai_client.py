# -*- coding: utf-8 -*-
"""通用 OpenAI 风格 AI 客户端（课中弹题/课程测试自动作答）.

config.ini 的 [ai-option] 配置:
    api_url = https://api.deepseek.com/v1     # OpenAI 风格 base(url)
    api_key = sk-xxx
    ai_id   = deepseek-chat                   # 模型 ID
    ai_answer_enabled = True                  # 是否启用 AI 自动答题

函数均线程安全、纯 requests 实现，网络错误统一抛 AIClientError，
调用方用 try/except 包裹即可，不会中断刷课协程。
"""
import configparser
import json
import os
import re
import sys

import requests


def runtime_base_dir():
    """运行根目录: 打包(exe)时为 exe 所在目录, 源码态为项目目录。

    frozen(onefile) 下 __file__ 位于 _MEIPASS 临时解包目录, 直接由它推导
    会读不到用户放在 exe 旁的 config.ini —— 表现为 GUI 里 AI 配置已填好、
    连通性测试通过, 但刷课主流程仍报"AI 配置缺失", 课中题/平时测试都不作答。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_runtime_config_path = None


def set_config_path(path) -> None:
    """告知本次运行实际使用的 config.ini 路径。

    主流程(CLI --config / GUI)可能从非默认位置加载配置, 若不告知, 这里的
    候选查找会优先命中运行目录下的 config.ini, 于是 GUI 里填好的 AI 配置
    读不到、自动答题被判定为"配置缺失"。
    """
    global _runtime_config_path
    _runtime_config_path = str(path) if path else None


def config_candidates():
    """config.ini 候选路径(优先级): 本次实际配置 → 运行目录 → 打包内置 → 源码目录"""
    candidates = []
    if _runtime_config_path:
        candidates.append(_runtime_config_path)
    candidates.append(os.path.join(runtime_base_dir(), "config.ini"))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "config.ini"))
    candidates.append(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini"))
    return candidates


BASE_DIR = runtime_base_dir()
DEFAULT_CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
REQ_TIMEOUT_MODELS = 15
REQ_TIMEOUT_ASK = 60

_LAST_ERROR = ""
_msg_lock = None
_UA = "Mozilla/5.0 Playwright-autovisor / requests"


class AIClientError(Exception):
    """AI 请求失败的统一异常类型."""


def summarize(exc):
    """不依赖全局 logger 的统一异常摘要."""
    return f"{type(exc).__name__}: {exc}"


def normalize_base(api_url):
    base = (api_url or "").strip().rstrip("/")
    if not base:
        raise AIClientError("API 地址为空")
    # Anthropic 协议 base(如 https://api.deepseek.com/anthropic) 原样返回
    if is_anthropic_base(base):
        return base
    # 若没带 /v* 结尾，常见 baseURL 需要补 /v1
    if not re.search(r"/v\d+(?:\.\d+)?(?:/.*)?$", base):
        base += "/v1"
    return base


def is_anthropic_base(api_url) -> bool:
    """识别 Anthropic 风格 base (…/anthropic 或 anthropic 网关)."""
    return "/anthropic" in (api_url or "").lower()


def _anthropic_messages(messages, model, api_url, api_key, timeout=REQ_TIMEOUT_ASK,
                        max_tokens=None):
    """Anthropic 协议: POST {base}/v1/messages; 返回文本内容."""
    import requests as _req
    base = normalize_base(api_url)
    if not max_tokens or max_tokens < 1024:
        max_tokens = 2048  # 思考型模型(deepseek-flash 等)需要为 thinking 留够预算
    url = f"{base}/v1/messages"
    sys_text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    user_msgs = [m for m in messages if m.get("role") != "system"]
    payload = {
        "model": model,
        "system": sys_text or None,
        "messages": [{"role": m.get("role", "user"),
                      "content": m.get("content", "")} for m in user_msgs],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    if not sys_text:
        payload.pop("system", None)
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _UA,
    }
    try:
        resp = _req.post(url, headers=headers, json=payload, timeout=timeout)
    except _req.exceptions.RequestException as e:
        raise AIClientError(f"连接失败: {summarize(e)}") from e
    data = _check_resp(resp, "请求补全(anthropic)")
    try:
        content = data.get("content") or []
        # deepseek-flash 等模型会先产生 "thinking"/"finish_reason" 块, 只拼 text
        text = "".join(c.get("text", "") for c in content
                       if isinstance(c, dict) and c.get("type") != "thinking")
        if text:
            return text
        raise AIClientError(f"anthropic 响应无内容: {json.dumps(data, ensure_ascii=False)[:200]}")
    except AIClientError:
        raise
    except Exception as e:
        raise AIClientError(f"anthropic 响应格式异常: {e}") from e


ANTHROPIC_FALLBACK_MODELS = ["deepseek-flash", "deepseek-chat", "deepseek-reasoner"]


def _anthropic_list_models(api_url, api_key, timeout=REQ_TIMEOUT_MODELS):
    """Anthropic 协议: GET {base}/v1/models; 没有该端点(常见 404)时返回兜底列表."""
    import requests as _req
    base = normalize_base(api_url)
    url = f"{base}/v1/models"
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01",
        "Accept": "application/json",
        "User-Agent": _UA,
    }
    try:
        resp = _req.get(url, headers=headers, timeout=timeout)
        data = _check_resp(resp, "拉取模型列表(anthropic)")
        raw = data.get("data") if isinstance(data, dict) else data
        raw = raw or []
    except AIClientError:
        raw = []          # 404 / 空 -> 走兜底
    except Exception:
        raw = []
    ids = []
    for item in raw:
        mid = (item.get("id") or item.get("name") or item.get("model") or "") \
            if isinstance(item, dict) else str(item)
        if mid:
            ids.append(str(mid))
    if not ids:
        # DeepSeek anthropic 网关只提供 /v1/messages, 无 /models: 用常用模型兜底
        ids = list(ANTHROPIC_FALLBACK_MODELS)
    return sorted(set(ids))


def load_ai_config(config_path=None):
    """从 config.ini 读取 [ai-option]; 不存在时返回默认配置。

    未显式指定路径时按 config_candidates() 依次尝试(运行目录 → 打包内置
    → 源码目录), 兼容 exe 单文件分发时 exe 旁才有配置的情况。
    """
    paths = [config_path] if config_path else config_candidates()
    cfg = configparser.ConfigParser()
    for path in paths:
        try:
            if cfg.read(path, encoding="utf-8-sig") or cfg.read(path, encoding="gbk"):
                break
        except Exception:
            continue

    def get(option, default=""):
        try:
            return cfg.get("ai-option", option, raw=True) or default
        except Exception:
            return default

    return {
        "api_url": get("api_url").strip(),
        "api_key": get("api_key").strip(),
        "ai_id": get("ai_id", "").strip(),
        "enabled": get("ai_answer_enabled", "True").strip().lower()
                   in ("true", "1", "yes", "on"),
    }


def is_configured(cfg=None):
    """配置里至少要有 api_url + api_key 才算可用."""
    cfg = cfg or load_ai_config()
    return bool(cfg.get("api_url")) and bool(cfg.get("api_key")) and bool(cfg.get("ai_id"))


def _headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # 某些镜像源对浏览器 UA 403, 用脚本统一的 UA
        "User-Agent": _UA,
    }


def _check_resp(resp, action):
    if resp.status_code >= 400:
        raise AIClientError(f"{action} HTTP {resp.status_code}: {(resp.text or '')[:200]}")
    try:
        return resp.json()
    except ValueError as e:
        raise AIClientError(f"{action} 响应非 JSON: {e}")


def list_models(api_url, api_key, timeout=REQ_TIMEOUT_MODELS):
    """拉取该 API 下的所有模型 ID（用户选择用），返回按字符串排序去重后的列表."""
    import requests as _req
    if not api_url or not api_key:
        raise AIClientError("需要先填写 API 地址和 ApiKey")
    base = normalize_base(api_url)
    if is_anthropic_base(base):
        return _anthropic_list_models(base, api_key, timeout=timeout)
    url = f"{base}/models"
    try:
        resp = _req.get(url, headers=_headers(api_key), timeout=timeout)
    except _req.exceptions.RequestException as e:
        raise AIClientError(f"连接失败: {summarize(e)}") from e
    data = _check_resp(resp, "拉取模型列表")
    raw = data.get("data") if isinstance(data, dict) else data
    if raw is None:
        raw = []
    if isinstance(raw, dict):
        raw = raw.get("models") or []
    ids = []
    for item in raw:
        if isinstance(item, str):
            mid = item
        else:
            mid = (item.get("id") or item.get("name") or item.get("model")
                   or item.get("modelId"))
        if mid:
            ids.append(str(mid))
    if not ids:
        raise AIClientError("接口返回的模型列表为空")
    return sorted(set(ids))


def test_connection(api_url, api_key, model=None, timeout=REQ_TIMEOUT_MODELS):
    """连通性测试: 首选 /models 探活; 若用户提供模型则再走一次最小对话."""
    base = normalize_base(api_url)
    if not api_key:
        raise AIClientError("缺少 ApiKey")
    ids = list_models(base, api_key, timeout=timeout)
    result = {"models": len(ids), "url": f"GET {url if (url:=f'{base}/models') else ''}"}
    if model and model in ids:
        msg = chat_completion(
            [{"role": "user", "content": "ping"}], model,
            api_url=base, api_key=api_key, timeout=timeout, max_tokens=4)
        result["chat"] = bool(msg)
    return result


def chat_completion(messages, model, api_url, api_key, timeout=REQ_TIMEOUT_ASK,
                    max_tokens=512):
    if is_anthropic_base(api_url):
        return _anthropic_messages(messages, model, api_url, api_key,
                                   timeout=timeout, max_tokens=max_tokens)
    import requests as _req
    base = normalize_base(api_url)
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    try:
        resp = _req.post(url, headers=_headers(api_key), json=payload, timeout=timeout)
    except _req.exceptions.RequestException as e:
        raise AIClientError(f"连接失败: {summarize(e)}") from e
    data = _check_resp(resp, "请求补全")
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise AIClientError(f"响应格式异常: {e} 内容: {json.dumps(data, ensure_ascii=False)[:200]}")


_SYSTEM_PROMPT = (
    "你是智慧树网课的答题助手。用户会给出一道题, 请依据题干作答:\n"
    "- 单选题/判断题: 输出正确选项的完整文字 (选项文字, 不带'选项A'等字母)\n"
    "- 多选题: 输出用分号分隔的每个正确选项完整文本\n"
    "- 填空/简答题: 直接输出答案文本\n"
    "只输出题目要求的答案本身, 不带任何解释、不用标点修饰。若无法确定, "
    "结合题干做出最可能的判断并直接输出。"
)


def ask_question(question_type, title, options=None, cfg=None, timeout=REQ_TIMEOUT_ASK):
    """答题: 返回模型写好的答案字符串 (调用方据此在 DOM 上选中选项)."""
    cfg = cfg or load_ai_config()
    if not is_configured(cfg):
        return ""
    user_prompt = f"题型: {question_type or '未知'}\n题目: {title}"
    if options:
        user_prompt += "\n选项:\n" + "\n".join(f"- {opt}" for opt in options)
    answer = chat_completion(
        [{"role": "system", "content": _SYSTEM_PROMPT},
         {"role": "user", "content": user_prompt}],
        cfg["ai_id"], api_url=cfg["api_url"], api_key=cfg["api_key"],
        timeout=timeout,
    ).strip()
    return answer
