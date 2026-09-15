import json
import os
import random
import re

from task.tool import color
from openai import OpenAI


# 默认配置
DEFAULT_API_URL = "https://api.deepseek.com"
DEFAULT_MODELS = ["deepseek-chat", "deepseek-reasoner"]

# 缓存模型列表，避免每次提问都请求 /models
_model_cache = None
_model_cache_url = None


def _load_config():
    """从 account_info.json 读取 API 配置"""
    config = {}
    try:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tool', 'account_info.json')
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        pass
    return config


def get_api_url(api_url=None):
    """规范化 API 地址（OpenAI 兼容接口通用）：
    - 去首尾空白与尾部斜杠；
    - 若误填了完整端点（以 /chat/completions 结尾）则剥掉该后缀，
      避免与 OpenAI SDK 的自动拼接叠加成 /chat/completions/chat/completions
      而得到 404 接口不存在"""
    if api_url:
        url = api_url.strip()
    else:
        config = _load_config()
        url = config.get('API_URL', '').strip()
    url = url.rstrip('/')
    if url.lower().endswith('/chat/completions'):
        url = url[:-len('/chat/completions')].rstrip('/')
    return url or DEFAULT_API_URL


def get_model_list(api_url=None, api_key=None):
    """从 API 接口自动获取模型列表

    返回模型 id 字符串列表；获取失败时返回空列表（调用方自行回退默认模型）。
    """
    global _model_cache, _model_cache_url
    api_url = get_api_url(api_url)
    if _model_cache and _model_cache_url == api_url:
        return _model_cache
    if not api_key:
        return []
    try:
        client = OpenAI(api_key=api_key, base_url=api_url)
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        if model_ids:
            _model_cache = model_ids
            _model_cache_url = api_url
            return model_ids
    except Exception as e:
        print(color.yellow(f'获取模型列表失败（{e}），将使用默认模型'), flush=True)
    return []


def get_model(api_model=None, api_url=None, api_key=None):
    """选择要使用的模型

    1. 用户显式指定的模型优先；
    2. 否则从接口自动获取模型列表，优先挑选 chat/对话类模型；
    3. 获取失败或列表为空时回退默认模型。
    """
    config = _load_config()
    if api_model and str(api_model).strip():
        return str(api_model).strip()
    if not api_key:
        api_key = config.get('API', '')
    model_list = get_model_list(api_url, api_key)
    if model_list:
        # 优先选择带 chat / instruct / 对话语义的模型
        for priority in ('chat', 'instruct', 'deepseek'):
            for model_id in model_list:
                if priority in model_id.lower():
                    return model_id
        return model_list[0]
    return DEFAULT_MODELS[0]


def DeepSeekAsk(API_KEY, title, _type, api_url=None, api_model=None):
    """通用 AI 答题函数（兼容任意 OpenAI 风格接口）

    :param API_KEY: API 密钥
    :param title: 题目内容
    :param _type: 题目类型
    :param api_url: API 地址（留空则使用配置文件 API_URL 或默认 deepseek 地址）
    :param api_model: 模型名称（留空则自动从接口获取）
    """
    if not API_KEY:
        print(color.red('请输入正确的 API Key'), flush=True)
        return '[]'

    if _type in ['单选题', '判断题']:
        prompt = ('不要其他话语，我仅需要这些题目的选择答案，返回的答案必须是列表格式，列表中的每个元素都是字符串,'
                  '答案必须从给你的选项中选择，并且只能是其中一个答案，不能自己编造答案,'
                  '最终你给出的答案格式应当类似于下面这样：["答案"]\n')
    elif _type == '多选题':
        prompt = ('不要其他话语，我仅仅需要这些题目的选择答案哟，返回的答案必须是列表格式，列表中的每个元素都是字符串,'
                  '答案必须从给你的选项中选择，可以选择多个答案，不能自己编造答案,'
                  '最终你给出的答案格式应当类似于下面这样：["答案1","答案2",...]\n')
    elif _type in ['简答题', '论述题', '填空题']:
        prompt = ('不要其他话语，我仅仅需要这些题目的选择答案哟，返回的答案必须是列表格式，列表中的每个元素都是字符串,'
                  '只需给出文字答案即可,不要有多余的内容,答案要都在列表内，不要在列表后再加什么内容,'
                  '最终你给出的答案格式应当类似于下面这样：["答案"]\n')
    elif _type == '填空题':
        prompt = ('不要其他话语，我仅仅需要这些题目的选择答案哟，返回的答案必须是列表格式，列表中的每个元素都是字符串,'
                  '只需给出文字答案即可,不要有多余的内容,答案要都在列表内，不要在列表后再加什么内容,有多少个空，列表中就要有多少个元素,'
                  '最终你给出的答案格式应当类似于下面这样：["答案"]或["答案1","答案2",...]\n')
    else:
        prompt = '''请根据以下题目要求回答问题：
                                                  1.不要其他话语，我仅仅需要这些题目的选择答案哟

                            2.所有题目的答案必须从选项 A、B、C、D 中选择。多选题必须选多个答案，其答案紧挨着即可不用用'/'隔开

                            3.对于判断题，答案只能是 A 或 B，分别对应题目中的 A（对） 和 B（错）。

                            4.简答题只需给出文字答案即可,不要有多余的内容,论述题同样，论述题的答案字数在五十字左右,不要出现字母或题号数字

                            5.填空题的每个答案用“,”隔开

                            6.如果题目重复出现，只需回答一次，不要重复回答。

                            7.请严格按照题目编号顺序给出答案,1,2,3,4这样的题目序号顺序给出选择的答案。
                            每个题目的答案用“/”隔开,答案中不要题号，只需要答案，不用重复问题,不要给多了答案，有多少道题就给多少答案，
                            /的数量是能保持比题目数量少一个，不能多也不能少,不要有换行符

                            8.最终你给出的答案格式应当类似于下面这样：A/B,C,D/C/论述题答案/D/填空题答案1,填空题答案2,...

                            9.请你注意每道题目开头的【】里面内容判断这道题目是什么类型的题目
                                                    \n'''
    prompt += title

    api_url = get_api_url(api_url)
    model = get_model(api_model, api_url, API_KEY)

    try:
        message = {"role": "user", "content": prompt}
        client = OpenAI(api_key=API_KEY, base_url=api_url)
        response = client.chat.completions.create(
            model=model,
            messages=[message],
            temperature=1.3,
            stream=False
        )
        answer = response.choices[0].message.content
    except Exception as e:
        print(color.red(f'AI 请求失败：{e}'), flush=True)
        print(color.red(f'（实际请求 base_url={api_url}，模型={model}；'
                        f'API_URL 应填 OpenAI 兼容根地址，如 https://open.bigmodel.cn/api/paas/v4，'
                        f'不要带 /chat/completions 后缀）'), flush=True)
        return '[]'

    match = re.search(r'\[(.*?)\]', answer)
    if match:
        answer = match.group(0)
    print(answer, flush=True)
    return answer