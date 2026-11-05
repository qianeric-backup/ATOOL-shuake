# -*- coding: utf-8 -*-
"""学习通刷课 交付验收脚本（识图 + 空答案修复）

覆盖：
  A. 全量语法编译 / 模块导入
  B. finish_title 空答案护栏与选项映射（含多选/判断）
  C. img_capture 采集、去重、开关、跨域 URL 兜底、老通道回退
  D. AIAsk 多模态消息体 + 三级降级
  E. ai_wen_da 纯图片题路由与题干占位剥离
运行：python3 acceptance.py  （在 shuake_src 下）
"""
import base64
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__)) or '.'
sys.path.insert(0, ROOT)

FAIL = []
PASS = []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(('  ✅ ' if cond else '  ❌ ') + name + (f'  [{detail}]' if detail and not cond else ''))


# ---------------------------------------------------------------- A. 编译/导入
def test_compile():
    print('\n[A] 语法编译与模块导入')
    r = subprocess.run([sys.executable, '-m', 'compileall', '-q', 'task', 'qt_ui.py'],
                       capture_output=True, text=True)
    check('compileall 全量编译', r.returncode == 0, r.stderr[-300:])
    mods = ['task.quiz_ai', 'task.do_work', 'task.exam_ai', 'task.watch_vido',
            'task.finish_dicussion', 'task.tool.img_capture', 'task.tool.AIAsk',
            'task.tool.ai_wen_da']
    for m in mods:
        try:
            __import__(m)
            check(f'import {m}', True)
        except Exception as e:  # noqa: BLE001
            check(f'import {m}', False, f'{type(e).__name__}: {e}')


# ------------------------------------------------- B. finish_title 空答案护栏
def test_finish_title():
    print('\n[B] finish_title 空答案护栏与选项映射')
    from task.quiz_ai import Answer

    class El:
        def __init__(self, checked='false'):
            self.checked = checked
            self.clicked = 0

        def get_attribute(self, k):
            return self.checked if k == 'aria-checked' else None

    class Driver:
        def execute_script(self, *a, **k):
            return None

        def execute_async_script(self, *a, **k):
            return []

    DEFAULT_OPTS = ('A. TCP', 'B. UDP', 'C. ICMP', 'D. ARP')

    def build(answer, qtype='单选题', opts=DEFAULT_OPTS):
        if opts is None:          # 用例里 None = 用默认四选项
            opts = DEFAULT_OPTS
        a = Answer.__new__(Answer)
        a.driver = Driver()
        a.questionList0 = [El()]
        a.questionType_list = [qtype]
        a.num_option_dit = {0: list(opts or [])}
        a.num_answer_dit = {0: answer}
        a.all_optionWebElementList = [[El() for _ in (opts or [])]]
        a.reword_time = 0
        a.course_name = 'acceptance'
        a.only_title_text = ['q']
        a.question_images = {}
        a._click_option = lambda el, desc: (setattr(el, 'clicked', 1), True)[1]
        return a

    cases = [
        ('空列表 [] 不抛 IndexError', [], '单选题', None, False, [0, 0, 0, 0]),
        ("空串 [''] 视为无答案", [''], '单选题', None, False, [0, 0, 0, 0]),
        ('答案原文匹配', ['B. UDP'], '单选题', None, True, [0, 1, 0, 0]),
        ('答案字母映射', ['A'], '单选题', None, True, [1, 0, 0, 0]),
        ('多选字母串 AC', ['AC'], '多选题', None, True, [1, 0, 1, 0]),
        ('判断 对→正确', ['对'], '判断题', ('A. 正确', 'B. 错误'), True, [1, 0]),
        ('选项缺失不崩', ['A'], '单选题', (), False, []),
        ('答案不匹配跳过', ['完全不相关'], '单选题', None, False, [0, 0, 0, 0]),
    ]
    for name, ans, qtype, opts, expect_ret, expect_click in cases:
        a = build(ans, qtype, opts)
        try:
            ret = a.finish_title(0)
            got = [e.clicked for e in (a.all_optionWebElementList[0] or [])]
            ok = (ret == expect_ret) and (expect_click is None or got == expect_click)
            check(name, ok, f'ret={ret} click={got}')
        except Exception as e:  # noqa: BLE001
            check(name, False, f'{type(e).__name__}: {e}')


# ------------------------------------------------------- C. img_capture 采集
def test_img_capture():
    print('\n[C] 图片采集（识图）')
    from task.tool import img_capture as ic

    def mk(tag):
        return 'data:image/jpeg;base64,' + base64.b64encode(tag * 400).decode()

    data = mk(b'a')

    class Driver:
        def __init__(self, payload):
            self.payload = payload

        def execute_async_script(self, *a, **k):
            return self.payload

        def execute_script(self, *a, **k):
            return None

    class El:
        def find_elements(self, *a, **k):
            return []

    payload = [
        {'src': 'http://cdn/1.png', 'w': 800, 'h': 600, 'data': mk(b'a')},
        {'src': 'http://cdn/1.png', 'w': 800, 'h': 600, 'data': mk(b'a')},    # 同图重复
        {'src': 'http://cdn/2.png', 'w': 2000, 'h': 1000, 'data': mk(b'b')},  # 另一张
    ]
    mark, urls = ic.extract_images(Driver(payload), El())
    check('采集返回标注文本', mark == '[图片] [图片]', mark)
    check('按内容去重（3→2）', len(urls) == 2, str(len(urls)))

    _, urls_lim = ic.extract_images(Driver(payload), El(), max_images=1)
    check('单题上限生效', len(urls_lim) == 1, str(len(urls_lim)))

    # 跨域取不到像素 → URL 直链兜底
    no_px = [{'src': 'http://p.ananas/x.png', 'w': 400, 'h': 300, 'data': None}]
    mark2, urls2 = ic.extract_images(Driver(no_px), El())
    check('无像素时 URL 直链兜底', urls2 == ['http://p.ananas/x.png'], str(urls2))

    # 开关关闭
    orig = ic._config
    ic._config = lambda: {'image_qa': 0}
    check('image_qa=0 时完全不采集', ic.extract_images(Driver(payload), El()) == ('', []))
    ic._config = orig

    # 脚本异常 → 老通道回退，不抛异常
    class Boom(Driver):
        def execute_async_script(self, *a, **k):
            raise RuntimeError('script timeout')

    try:
        check('脚本异常回退老通道', ic.extract_images(Boom(payload), El()) == ('', []))
    except Exception as e:  # noqa: BLE001
        check('脚本异常回退老通道', False, str(e))

    # 配置读取有缓存（性能）
    import time
    t0 = time.time()
    for _ in range(300):
        ic.image_qa_enabled()
    check('配置读取带缓存(<0.1s/300次)', time.time() - t0 < 0.1, f'{time.time()-t0:.3f}s')


# ------------------------------------------------------------- D. AIAsk 多模态
def test_aiask():
    print('\n[D] AIAsk 多模态请求与降级')
    import task.tool.AIAsk as A

    A.get_ai_proxy = lambda *a, **k: ''
    DATA = 'data:image/jpeg;base64,' + 'A' * 300
    URL = 'https://p.ananas.chaoxing.com/a.png'
    calls = []

    class Resp:
        def __init__(self, c):
            self.choices = [type('C', (), {'message': type('M', (), {'content': c})()})()]

    class Comp:
        def create(self, **kw):
            content = kw['messages'][0]['content']
            urls = ([b['image_url']['url'] for b in content if b.get('type') == 'image_url']
                    if isinstance(content, list) else [])
            calls.append(urls)
            if any(u.startswith('https') for u in urls):
                raise Exception('Error code: 400 - failed to download image: HTTP 403')
            return Resp('["A"]')

    class FakeOpenAI:
        def __init__(self, **kw):
            self.chat = type('Ch', (), {'completions': Comp()})()

    A.OpenAI = FakeOpenAI

    calls.clear()
    out = A.AIAsk('sk', '题', '单选题', api_url='https://x', api_model='deepseek-flash',
                  images=[DATA, URL])
    check('混合图片首次含 2 张', len(calls[0]) == 2, str(calls[0]))
    check('直链 403 → 自动改 base64 重试', len(calls) == 2 and len(calls[1]) == 1, str(calls))
    check('降级后仍拿到答案', out == '["A"]', str(out))

    calls.clear()
    out = A.AIAsk('sk', '题', '单选题', api_url='https://x', api_model='deepseek-flash',
                  images=[DATA])
    check('纯 base64 单次成功', len(calls) == 1 and out == '["A"]', str(calls))

    # 纯文本模型：vision 失败后文本作答
    class TextOnly:
        def create(self, **kw):
            content = kw['messages'][0]['content']
            calls.append('vision' if isinstance(content, list) else 'text')
            if isinstance(content, list):
                raise Exception('Error code: 400 model does not support image input')
            return Resp('["B"]')

    class FakeOpenAI2:
        def __init__(self, **kw):
            self.chat = type('Ch', (), {'completions': TextOnly()})()

    A.OpenAI = FakeOpenAI2
    calls.clear()
    out = A.AIAsk('sk', '题', '单选题', api_url='https://x', api_model='deepseek-chat',
                  images=[DATA])
    check('纯文本模型自动降级且不中断', calls == ['vision', 'text'] and out == '["B"]', str(calls))

    check('图片参数过滤（None/非法/超限）',
          A._prepare_images([None, '', 'bogus', DATA]) == [DATA])
    distinct = ['data:image/jpeg;base64,' + ('B' * (300 + i)) for i in range(20)]
    check('图片数量封顶 8 张',
          len(A._prepare_images(distinct)) == A.MAX_VISION_IMAGES,
          str(len(A._prepare_images(distinct))))
    check('相同图片去重（20→1）', len(A._prepare_images([DATA] * 20)) == 1)


# --------------------------------------------------- E. ai_wen_da 纯图片题路由
def test_ai_wen_da():
    print('\n[E] 纯图片题路由与题干占位剥离')
    import asyncio
    import task.tool.ai_wen_da as W

    seen = {}
    real_text_only = W.AutoAnswer._text_only

    class FakeAA:
        async def auto_answer_question(self, q):
            seen['q'] = q
            return {'haveAnswer': True, 'answerType': 'choice', 'matchedIndices': [1],
                    'form': type('X', (), {'form': 'AI', 'answer': ['B'], 'duration': 1,
                                           'msg': ''})()}

    W.AutoAnswer = FakeAA
    out = asyncio.run(W.main('单选题', '计算下图 [图片]', ['A. 1', 'B. 2 [图片]'], 'sk',
                             images=['data:image/jpeg;base64,AAA']))
    check('题干/选项中的 [图片] 占位被剥离', seen['q'].question == '计算下图'
          and seen['q'].options == ['A. 1', 'B. 2'], f"{seen['q'].question} {seen['q'].options}")
    check('图片透传到 Question.images', len(seen['q'].images) == 1)
    check('答案按选项原文返回', out == ['B. 2'], str(out))

    asyncio.run(W.main('单选题', '（本题题干为图片，请以附图内容为准）[图片]',
                       ['A. 1', 'B. 2'], 'sk', images=['data:x']))
    check('纯图片题占位替换', seen['q'].question == '（题干为图片）', seen['q'].question)

    # 纯图片题判定：占位剥离后为空
    check('_text_only 剥离占位', real_text_only('（题干为图片）[图片内容:AB]') == '')


if __name__ == '__main__':
    os.chdir(ROOT)
    test_compile()
    test_finish_title()
    test_img_capture()
    test_aiask()
    test_ai_wen_da()
    print(f'\n==== 验收结果：通过 {len(PASS)} / 共 {len(PASS) + len(FAIL)} ====')
    if FAIL:
        print('失败项：')
        for f in FAIL:
            print('  -', f)
        sys.exit(1)
    print('全部通过 ✅')
