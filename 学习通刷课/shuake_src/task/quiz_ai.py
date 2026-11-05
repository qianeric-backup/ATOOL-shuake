# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.
import random
import time
import re
import ast
import asyncio
import traceback

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from task.tool.no_secret import DecodeSecret
from task.tool import color
import sys
from task.tool.ai_wen_da import main,AnswerAPI,Question
from task.tool.AIAsk import AIAsk
from task.tool.img_capture import extract_images, dedupe_images
from task.tool.send_wx import send_error
from task.tool.console import ensure_utf8_stdout

# stdout 统一 UTF-8。原写法用 `type(sys.stdout) is not io.TextIOWrapper` 判断，
# 而正常解释器的 sys.stdout 本来就是 io.TextIOWrapper，条件恒为假、从未生效
# （所以那条"修复"实际没起作用）；详见 task/tool/console.py
ensure_utf8_stdout()

# 题型归一化：新版学习通页面在【】里输出英文题型标记
# （如 TrueorFalse / SingleChoice / MultipleChoice / ShortAnswer / Completion），
# 旧版为中文。统一映射为中文，供题库检索与作答分支使用
QUESTION_TYPE_ALIAS = {
    'singlechoice': '单选题',
    'multiplechoice': '多选题',
    'multichoice': '多选题',
    'trueorfalse': '判断题',
    'judgement': '判断题',
    'judge': '判断题',
    'shortanswer': '简答题',
    'calculation': '计算题',
    'calculate': '计算题',
    'completion': '填空题',
    'gapfilling': '填空题',
}



class Answer:
    def __init__(self, driver, test_frame, course_name, api,work_choice,after_finish_question,times=0,
                 api_url='', api_model=''):
        self.driver=driver
        self.test_frame = test_frame
        self.decodeSecret = None
        self.questionList0 = []
        self.no_answer_dit = {}# 存储无答案的题目
        self.answer_list = []
        self.course_name = course_name
        self.driver=driver
        self.frame=test_frame
        self.API_KEY=api
        self.API_URL=api_url
        self.API_MODEL=api_model
        self.work_choice=work_choice
        # 原始设置值单独保留：重做时（main 里递归构造 Answer）必须传回原始字符串，
        # 否则第二次构造会对已被转成 float 的同名字段执行 re.search → TypeError
        self._raw_after_finish_question = after_finish_question
        # 使用正则表达式提取百分比数字
        match = re.search(r'(\d+)%', str(after_finish_question))
        if match:
            self.after_finish_question = int(match.group(1)) / 100
        else:
            self.after_finish_question=after_finish_question

        self.ans_rate =None
        self.all_title_dit={}
        self.num_option_dit = {}
        self.questionType_list = []
        self.all_title = ''
        self.num_answer_dit = {}
        self.only_title_text = []
        self.reword_time = 0
        self.all_optionWebElementList = []
        self.question_images = {}   # 题号 -> 题干/选项图片 data URL 列表
        self.times = times
        if self.work_choice is not None:
            self.main()

    def main(self):
        # 滚动到测试
        try:
            self.driver.execute_script("arguments[0].scrollIntoView();",self.test_frame)

        except:
            return
        # 判断是否完成任务
        try:
            element = self.frame.find_element(By.XPATH, 'preceding-sibling::div[1]')
            txt = element.get_attribute('aria-label')
        except:
            self.driver.switch_to.frame(self.test_frame)
            self.driver.switch_to.frame('frame_content')
            element = self.driver.find_element(By.CLASS_NAME, 'testTit_status')
            txt = element.text
            time.sleep(3)
            self.driver.switch_to.default_content()
            self.driver.switch_to.frame('iframe')
        if '已完成' in txt:
            print(color.green('测试已完成'), flush=True)
            return
        else:
            self.get_title_option()
            print(color.red('正在搜索中，请耐心等待...'))
            self.use_ai_wen_da()
            self.use_ai_fallback()
            print(color.green('开始答题'), flush=True)
            skipped = 0
            for title_num in self.num_answer_dit.keys():
                # 空答案的题不进 finish_title：旧代码会让 answer[0] 抛
                # IndexError('list index out of range')，整卷作答中断
                if not self._answer_items(self.num_answer_dit.get(title_num)):
                    skipped += 1
                    print(color.red(f'第{title_num + 1}题无答案，跳过'), flush=True)
                    continue
                if self.finish_title(title_num):
                    self.reword_time += 1
                time.sleep(1)
            if skipped:
                print(color.red(f'共{skipped}题未搜到答案，已留空，请人工补答后再提交'), flush=True)
                self._dump_unanswered()
            self.ans_rate = (self.reword_time / len(self.questionList0)
                             if self.questionList0 else 0.0)
            print(self.reword_time, '/', len(self.questionList0))
            message = self.submit()
            if not message and self.times<3:
                print(color.green('开始第{}次重新做题'.format(self.times+1)))
                self.driver.switch_to.frame('iframe')
                print(color.green('重新做题'), flush=True)
                Answer(self.driver, self.frame, self.course_name, self.API_KEY, self.work_choice,
                       self._raw_after_finish_question, self.times+1)
            elif self.times>=3:
                print(color.red('测试答题失败，已重试3次'), flush=True)
    def _dump_unanswered(self):
        """把未搜到答案的题目落盘，便于人工补答（失败不影响主流程）。"""
        try:
            pending = [(tn, self.num_answer_dit.get(tn))
                       for tn in self.num_answer_dit
                       if not self._answer_items(self.num_answer_dit.get(tn))]
            if not pending:
                return
            path = fr'task/record/《{self.course_name}》未答题目.txt'
            with open(path, 'a', encoding='utf-8') as f:
                f.write(f'\n=== {time.strftime("%Y-%m-%d %H:%M:%S")} 共{len(pending)}题未答 ===\n')
                for tn, _ in pending:
                    qtype = (self.questionType_list[tn]
                             if tn < len(self.questionType_list) else '')
                    text = self.only_title_text[tn] if tn < len(self.only_title_text) else ''
                    options = self.num_option_dit.get(tn) or []
                    f.write(f'第{tn + 1}题[{qtype}] {text}\n')
                    for oi, opt in enumerate(options):
                        # 页面选项文本通常自带 "A."/"A、" 前缀，避免重复加字母
                        prefix = '' if re.match(r'^\s*[A-Ha-h]\s*[\.、,，:：]', opt) else chr(
                            ord('A') + oi) + '. '
                        f.write(f'    {prefix}{opt}\n')
                    f.write('\n')
            print(color.yellow(f'未答题目已记录到 {path}'), flush=True)
        except Exception:
            pass

    def get_title_option(self):
        self.driver.switch_to.frame(self.frame)
        self.driver.switch_to.frame('frame_content')
        # 实例化 DecodeSecret 类
        self.decodeSecret = DecodeSecret(1)
        print(color.yellow("启用字体解密"), flush=True)
        self.decodeSecret.getFontFace(self.driver)
        if not getattr(self.decodeSecret, '_secret_dict', {1: 1}):
            print(color.red('本页未提取到加密字库：被混淆的题目字符将保持乱码，'
                            'AI 将按上下文尽力作答'), flush=True)
        # 获取页面中的所有题目
        self.questionList0 = self.driver.find_elements(By.CSS_SELECTOR, '[class="singleQuesId"]')
        print(color.yellow("当前测试共有{}题".format(len(self.questionList0))), flush=True)

        for i in range(len(self.questionList0)):
            self.title_num = i + 1
            self.option_text_list = []
            self.title_and_option_element = self.questionList0[i]
            self.title_and_option_text = re.sub(r'\s+', '',
                                               self.decodeSecret.decode(self.title_and_option_element.text).strip())
            self.title_element = self.title_and_option_element.find_element(By.CSS_SELECTOR,
                                                                            '[class="clearfix font-cxsecret fontLabel"]')
            self.title = re.sub(r'\s+', '', self.decodeSecret.decode(self.title_element.text).strip())
            # 题干图片：采集并转 data URL（多模态 AI 直读），标注并入题干文本。
            # lazy=True：先把图滚进视口触发学习通的 data-src 懒加载
            _title_mark, _title_imgs = extract_images(self.driver, self.title_element, lazy=True)
            # 题目类型（英文标记归一化为中文，未知题型保持原样走"无法作答"分支）
            self.questionType = self.title[self.title.find("【") + 1: self.title.find("】")]
            self.questionType = QUESTION_TYPE_ALIAS.get(
                self.questionType.strip().lower(), self.questionType)
            # 题目文本
            self.title_text = self.title[self.title.find("】") + 1:]
            if _title_mark:
                self.title_text = self.title_text + ' ' + _title_mark
                # 题干只有图片时，纯文本题库检索不到任何内容，这里给出可读占位，
                # 避免 free API 用空题干乱配到别的题，同时提示 AI 以图片为准
                if not self.title_text.replace(_title_mark, '').strip():
                    self.title_text = '（本题题干为图片，请以附图内容为准）' + _title_mark
            self.only_title_text.append(self.title_text)
            self.questionType_list.append(self.questionType)
            if self.questionType in ['单选题', '多选题','判断题']:
                _option_elements = self.title_and_option_element.find_elements(By.TAG_NAME, 'li')
                self.all_optionWebElementList.append(_option_elements)
                _opt_imgs = []
                for option in _option_elements:
                    # lazy=False：题干那次已经把整题图片滚进视口，选项不必重复滚动
                    _opt_mark, _opt_urls = extract_images(self.driver, option, lazy=False)
                    _opt_imgs.extend(_opt_urls)
                    option_text = re.sub(r'\s+', '',
                                         self.decodeSecret.decode(option.text).strip())
                    if _opt_mark:
                        option_text = option_text + ' ' + _opt_mark
                    self.option_text_list.append(option_text)
                # 同一张图可能既被题干容器命中又被选项命中，按内容哈希去重
                self.question_images[i] = dedupe_images(_title_imgs + _opt_imgs)
            elif self.questionType in ['简答题', '论述题', '填空题','名词解释', '计算题']:
                self.all_optionWebElementList.append(None)
                self.option_text_list  =['']
                self.question_images[i] = dedupe_images(_title_imgs)
            else:
                print(color.red(f'第{i+1}题题型为{self.questionType},无法作答'))
                # 占位必须追加，否则后面 supported 题在 all_optionWebElementList
                # 中整体错位，会点到别的题的选项
                self.all_optionWebElementList.append(None)
                continue
            self.all_title_dit[i] = self.title_and_option_text
            self.num_option_dit[i] = self.option_text_list

    @staticmethod
    def _parse_answer_list(raw):
        """解析题库/AI 返回的答案。

        字符串按 Python 字面量解析（'["A"]' / "['A']"）；遇到格式漂移
        （自然语言、"答案：A"、带换行等非字面量）时退化为原字符串单元素
        列表，避免 ValueError/SyntaxError 冒泡导致整卷不答。
        """
        if isinstance(raw, str):
            try:
                raw = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                raw = [raw]
        # literal_eval('"A"') 会返回字符串而不是列表（AI 偶发输出 "A"），
        # 后续 answer[0] 会退化成取第一个字符，这里统一成列表
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, (list, tuple)):
            raw = [raw]
        # 过滤 None/空白/'[]' 之类伪答案，保证返回值元素均为可用字符串
        items = []
        for item in raw:
            text = str(item).strip()
            if text and text not in ('[]', 'None', 'null', '无', '不确定'):
                items.append(text)
        return items

    @staticmethod
    def _answer_items(answer):
        """把任意形态的答案统一成非空字符串列表（str/list/tuple/嵌套）。"""
        if answer is None:
            return []
        if isinstance(answer, str):
            raw = [answer]
        elif isinstance(answer, (list, tuple)):
            raw = list(answer)
        else:
            raw = [answer]
        items = []
        for item in raw:
            if isinstance(item, (list, tuple)):
                items.extend(Answer._answer_items(item))
                continue
            text = str(item).strip()
            if text and text not in ('[]', 'None', 'null', '无', '不确定'):
                items.append(text)
        return items

    @staticmethod
    def _letters_of(text):
        """抽出 A-H 字母（大写），用于答案字母→选项下标映射。"""
        return re.sub(r'[^A-Ha-h]', '', str(text)).upper()

    _JUDGEMENT_ALIAS = {
        '对': '正确', '√': '正确', '是': '正确', 'true': '正确', 't': '正确', 'y': '正确',
        '错': '错误', '×': '错误', '否': '错误', 'false': '错误', 'f': '错误', 'n': '错误',
    }

    def _pick_option_index(self, items, options, multiple=False, judgement=False):
        """把答案条目映射成选项下标列表。

        匹配优先级：
        1) 与选项文本完全相等（最常见：AI 直接返回选项原文）
        2) 选项文本包含答案文本（长度 ≥2 才允许，避免 'A' 命中 'ABNORMAL'）
        3) 纯 A-H 字母串 → 按字母序映射下标（图片选项/无文字选项场景）
        任何一条对不上都不抛异常，只丢弃该条目，由调用方决定跳过本题。
        """
        options = options or []
        count = len(options)
        picked = []
        for item in items:
            if judgement:
                # 判断题 AI 常回 对/错/√/×/T/F，页面选项文本是 正确/错误
                item = self._JUDGEMENT_ALIAS.get(str(item).strip().lower(), item)
            index = None
            for i, opt in enumerate(options):
                if item == opt:
                    index = i
                    break
            if index is None and len(item) >= 2:
                for i, opt in enumerate(options):
                    if opt and item in opt:
                        index = i
                        break
            if index is None:
                letters = self._letters_of(item)
                # 仅当答案本身就是字母串（如 'ABD'、'A.'）时才走字母映射，
                # 否则 'TCP' 这类文本答案会被误映射到 C/P 之外的非法下标
                if letters and re.fullmatch(r'[A-H]+', letters) and len(letters) == len(
                        re.sub(r'[^A-Za-z]', '', item)):
                    candidates = [ord(ch) - ord('A') for ch in letters]
                    if multiple:
                        picked.extend([c for c in candidates if 0 <= c < count])
                        continue
                    if 0 <= candidates[0] < count:
                        index = candidates[0]
            if index is not None and 0 <= index < count and index not in picked:
                picked.append(index)
        return picked

    def _click_option(self, li_element, desc):
        """遮挡安全点击。

        学习通答题页有悬浮遮罩/提示条，原生 .click() 会被判定为
        element click intercepted（日志：not clickable at point (452, ...)）。
        策略：先 scrollIntoView 居中 → JS 直接派发 click（绕过 Selenium
        可点击性判定）→ 校验 aria-checked 是否生效；未生效再用
        ActionChains 真实鼠标事件链（部分选项绑定 mouseup 才响应）兜底。
        """
        # 1) 滚动到视口中央，确保元素可见且坐标有效
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", li_element)
            time.sleep(0.3)
        except Exception:
            pass
        # 2) JS 直点（不受遮挡影响）
        try:
            self.driver.execute_script("arguments[0].click();", li_element)
        except Exception:
            return False
        time.sleep(0.4)
        if li_element.get_attribute('aria-checked') == 'true':
            return True
        # 3) 校验未通过：真实鼠标事件链兜底（覆盖 onmouseup 绑定选项）
        try:
            ActionChains(self.driver).move_to_element(li_element).click().perform()
        except Exception:
            pass
        time.sleep(0.4)
        if li_element.get_attribute('aria-checked') == 'true':
            return True
        print(color.yellow(f'{desc} 点击后未确认选中，尝试强制点击'), flush=True)
        try:
            self.driver.execute_script(
                "arguments[0].click(); arguments[0].dispatchEvent("
                "new MouseEvent('click', {bubbles: true}));", li_element)
        except Exception:
            pass
        return li_element.get_attribute('aria-checked') == 'true'

    def use_ai_wen_da(self):
        for i in self.all_title_dit.keys():
            if i in self.num_answer_dit:
                # 「自动提交并重做」重做轮次：该题已由修正答案填充，跳过搜题
                continue
            if self.times==0 and self.work_choice!='随机答题':
                print(color.green('\n<===================  分隔线  ===================>\n'), flush=True)
                # 先置空：搜索抛异常时不能沿用上一题的答案（会错答本题）
                self.answer_list = None
                try:
                    self.answer_list = asyncio.run(
                        main(self.questionType_list[i], self.only_title_text[i], self.num_option_dit[i], self.API_KEY,
                             api_url=self.API_URL, api_model=self.API_MODEL,
                             images=self.question_images.get(i, [])))
                except Exception as e:
                    print(color.red(f'第{i+1}题搜索失败：{e}'), flush=True)

                self.answer_list = self._parse_answer_list(self.answer_list)
                if not self.answer_list:
                    try:
                        self.answer_list = asyncio.run(
                            main(self.questionType_list[i], self.only_title_text[i], self.num_option_dit[i], self.API_KEY,
                                 api_url=self.API_URL, api_model=self.API_MODEL,
                                 images=self.question_images.get(i, [])))
                    except Exception as e:
                        print(color.red(f'第{i+1}题搜索失败：{e}'), flush=True)
                    self.answer_list = self._parse_answer_list(self.answer_list)
            elif self.work_choice!='随机答题':
                self.answer_list=[]
            elif self.work_choice=='随机答题':
                options = self.num_option_dit.get(i) or []
                if options:
                    self.answer_list=[random.choice(options)]
                    print(color.red(f'本次采用随机答题,随机答案为：{self.answer_list}'),flush=True)
                else:
                    # 选项未渲染（判断题/页面未加载完）时不能 random.choice 空列表
                    self.answer_list=[]
                    print(color.red(f'第{i+1}题无可选项，跳过该题'), flush=True)
            if not self.answer_list:
                self.num_answer_dit[i] = []
                # print(color.red('无答案，跳过'), flush=True)
                continue
            else:
                self.num_answer_dit[i] = self.answer_list

    def use_ai_fallback(self):
        for i, answer in self.num_answer_dit.items():
            if not answer:
                self.no_answer_dit[i] = self.all_title_dit[i]
        if len(self.no_answer_dit) > 0:
            print(color.red('正在使用AI搜题，请耐心等待...'), flush=True)
            title = ''
            num = 0
            _batch_images = []
            for no_answer_key, no_answer_title in self.no_answer_dit.items():
                title += no_answer_title
                _batch_images += self.question_images.get(no_answer_key, [])
            try:
                answers = AIAsk(self.API_KEY, title, 'all', api_url=self.API_URL,
                                api_model=self.API_MODEL, images=_batch_images or None)
                if not answers or answers.strip() in ('[]', ''):
                    # AI 请求失败返回 '[]'：视为无答案，留空跳过，不填脏数据
                    print(color.red('AI 兜底未返回有效答案，无答案的题将留空'), flush=True)
                    self.no_answer_dit.clear()
                    return
                # answers='C/B/ABCD/ABCD/实体经济/'
                parts = re.split(r'/', answers)
                for key, no_answer_title in self.no_answer_dit.items():
                    if num >= len(parts):
                        break   # AI 返回的答案数不足时只跳过剩余题，不越界
                    ans_text = parts[num].strip()
                    # 计数器必须无条件推进：AI 对某题返回 '[]' 时若跳过自增，
                    # 后续答案会整体错位一题，答到别题上
                    num += 1
                    if ans_text and ans_text != '[]':
                        # AI 对答不出的题可能输出 '[]'，视为无答案留空
                        self.num_answer_dit[key] = self._parse_answer_list(
                            re.split(r'[,，]', ans_text))
                        if not self.num_answer_dit[key]:
                            continue
                        # 缓存答案
                        question = Question(
                            type=str(self.questionType_list[key]),  # 题目类型
                            question=self.only_title_text[key],
                            options=self.num_option_dit[key],
                            API=self.API_KEY)
                        AnswerAPI().cache_answer(question, self.num_answer_dit[key])
            except Exception:
                # AI 兜底失败不应终止整课：无答案的题保持空答案，
                # 后续照常保存/提交，其余题不受影响
                traceback.print_exc()
                print(color.red('AI 兜底搜题失败，无答案的题将留空'), flush=True)
                self.no_answer_dit.clear()


    # ---------------- 填空题（UEditor 富文本）----------------
    @staticmethod
    def _split_blank_answer(answer):
        """多空答案拆分：AI/题库给的多空答案用中英文逗号或换行分隔。

        旧实现用空格 split，会把"位同步 帧定界"这类含空格的单个答案切碎，
        也可能把整段答案塞进第一个空——这里改为只认逗号/分号。
        """
        if not answer:
            return []
        if isinstance(answer, (list, tuple)):
            if len(answer) > 1:
                return [str(a).strip() for a in answer if str(a).strip()]
            answer = answer[0] if answer else ''
        letter = str(answer)
        parts = [p.strip() for p in re.split(r'[,，;；\n]+', letter) if p.strip()]
        return parts

    def _fill_one_blank(self, textarea_id, text):
        """写入单个空位。返回 (成功?, UEditor 当前内容)。"""
        res = self.driver.execute_script(
            '''const id = arguments[0], txt = arguments[1];
               const ta = document.getElementById(id);
               if (!ta) return {ok: false, why: 'no-textarea', content: ''};
               const all = (window.UE && window.UE.instants) || {};
               let inst = null;
               Object.keys(all).forEach(function(k){
                   const i2 = all[k];
                   if (!inst && i2 && i2.key === id) inst = i2;
               });
               if (inst && typeof inst.setContent === 'function') {
                   try {
                       inst.setContent('<p>' + txt + '</p>');
                       let c = '';
                       try { c = inst.getContent() || ''; } catch (e) { c = ''; }
                       return {ok: true, why: 'ue-setContent', content: c};
                   } catch (e) {
                       return {ok: false, why: 'setContent:' + e.message, content: ''};
                   }
               }
               // 编辑器实例缺失（懒加载未完成）：直接写数据载体并派发事件
               try {
                   ta.value = '<p>' + txt + '</p>';
                   ta.dispatchEvent(new Event('input', {bubbles: true}));
                   ta.dispatchEvent(new Event('change', {bubbles: true}));
                   return {ok: true, why: 'textarea-direct', content: ta.value};
               } catch (e) {
                   return {ok: false, why: 'textarea:' + e.message, content: ''};
               }''', textarea_id, text)
        return bool(res and res.get('ok')), (res or {}).get('content')

    def _read_one_blank(self, textarea_id):
        """回读空位当前内容（优先 UEditor 实例，其次 textarea.value）。"""
        return self.driver.execute_script(
            '''const id = arguments[0];
               const ta = document.getElementById(id);
               if (!ta) return '';
               const all = (window.UE && window.UE.instants) || {};
               let inst = null;
               Object.keys(all).forEach(function(k){
                   const i2 = all[k];
                   if (!inst && i2 && i2.key === id) inst = i2;
               });
               if (inst && typeof inst.getContent === 'function') {
                   try { return inst.getContent() || ''; } catch (e) { return ta.value || ''; }
               }
               return ta.value || '';''', textarea_id)

    def fill_blank_question(self, title_num, answer):
        """填空题作答：按 textarea（= 空位）逐个写入，并回读校验。"""
        question = self.questionList0[title_num]
        textareas = [ta for ta in question.find_elements(By.TAG_NAME, 'textarea')
                     if (ta.get_attribute('id') or '').startswith('answerEditor')]
        if not textareas:
            # 兜底：整页找顺序在本题范围之后的编辑器（个别页面 textarea 挂在题目外层）
            print(color.red('填空题未找到输入框（answerEditor），已跳过该题'), flush=True)
            return False
        # textarea 在 DOM 中的顺序即空号顺序（answerEditor<题目ID><空号>），
        # 不能从 id 里切空号：题目 ID 本身是纯数字，与序号连写无法区分边界。
        blank_ids = [ta.get_attribute('id') for ta in textareas]
        parts = self._split_blank_answer(answer)
        if not parts:
            print(color.red('填空题无可用答案，已跳过该题'), flush=True)
            return False
        if len(parts) < len(blank_ids):
            print(color.red(f'填空题答案数量({len(parts)})少于题目空数({len(blank_ids)})，'
                            f'先填前 {len(parts)} 个空'), flush=True)
        elif len(parts) > len(blank_ids):
            print(color.yellow(f'填空题答案数量({len(parts)})多于题目空数({len(blank_ids)})，'
                               f'按空位数截断'), flush=True)
            parts = parts[:len(blank_ids)]
        filled = 0
        for number, ta_id in enumerate(blank_ids):
            if number >= len(parts):
                break
            try:
                before = (self._read_one_blank(ta_id) or '').strip()
            except Exception:
                before = ''
            if before:
                print(color.red(f'第{number + 1}空已回答，无需重复回答'), flush=True)
                filled += 1
                continue
            ok, content = self._fill_one_blank(ta_id, parts[number])
            if ok and content:
                print(color.green(f'填空题第{number + 1}空已填入：{parts[number]}'), flush=True)
                filled += 1
            else:
                print(color.red(f'填空题第{number + 1}空写入失败' +
                                (f'（{content}）' if content else '')), flush=True)
            time.sleep(0.5)
        if filled == 0:
            print(color.red('填空题全部空位写入失败，该题未作答'), flush=True)
            return False
        if filled < len(blank_ids):
            print(color.yellow(f'填空题仅完成 {filled}/{len(blank_ids)} 个空'), flush=True)
        return True

    def _fill_one_blank_keyboard(self, iframe_el, text):
        """备用通道：真实键入（需要 iframe body 可聚焦；UEditor 内 p 不可键盘交互）。

        保留作为 UE 实例拿不到时的兜底手段，成功与否由回读判定。
        """
        try:
            self.driver.switch_to.frame(iframe_el)
            bodies = self.driver.find_elements(By.TAG_NAME, 'body')
            if not bodies:
                self.driver.switch_to.default_content()
                return False
            body = bodies[0]
            self.driver.execute_script("arguments[0].click();", body)
            self.driver.execute_script("arguments[0].focus();", body)
            body.send_keys(text)
            body.send_keys(Keys.TAB)
            self.driver.switch_to.default_content()
            return True
        except Exception:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
            return False

    def finish_title(self, title_num):
        try:
            # 滚动到题目
            self.driver.execute_script("arguments[0].scrollIntoView();", self.questionList0[title_num])
            # pyautogui.scroll(50)
        except:
            pass
        print(color.green(f'正在回答第{title_num + 1}题...'), flush=True)
        answer=self.num_answer_dit.get(title_num) or []
        # 去重
        print(color.green(f'该题为{self.questionType_list[title_num]}，答案：{answer}'), flush=True)
        # 空答案护栏：题库未收录且 AI 兜底也失败时 answer 为 []（或 ['']），
        # 旧代码直接 answer[0] → IndexError: list index out of range 中断整卷
        items = self._answer_items(answer)
        if not items:
            print(color.red(f'第{title_num + 1}题无可用答案，已跳过（可人工补答）'), flush=True)
            return False
        option_num=0
        try:
            if self.questionType_list[title_num]=='单选题' or self.questionType_list[title_num]=='判断题':
                _opts = self.num_option_dit.get(title_num) or []
                _opts_el = (self.all_optionWebElementList[title_num]
                            if title_num < len(self.all_optionWebElementList) else None)
                if not _opts:
                    print(color.red(f'第{title_num+1}题未取到选项文本，跳过该题'), flush=True)
                    return False
                picked = self._pick_option_index(
                    items[:1], _opts,
                    judgement=(self.questionType_list[title_num] == '判断题'))
                if not picked:
                    print(color.red(f'答案{items[:1]}与任何选项都不匹配，跳过该题'), flush=True)
                    return False
                option_num = picked[0]
                if not _opts_el or option_num >= len(_opts_el):
                    print(color.red(f'第{title_num+1}题选项元素缺失（页面未渲染完），跳过该题'), flush=True)
                    return False
                if _opts_el[option_num].get_attribute('aria-checked') == 'true':
                    print(color.red('已回答，无需重复回答'),flush=True)
                else:
                    self._click_option(_opts_el[option_num],
                                       f'第{title_num+1}题选项{option_num+1}')
                return True
            elif self.questionType_list[title_num] == '多选题':
                _opts = self.num_option_dit.get(title_num) or []
                _opts_el = (self.all_optionWebElementList[title_num]
                            if title_num < len(self.all_optionWebElementList) else None)
                if not _opts:
                    print(color.red(f'第{title_num+1}题未取到选项文本，跳过该题'), flush=True)
                    return False
                self.answer_num = self._pick_option_index(items, _opts, multiple=True)
                if not self.answer_num:
                    print(color.red(f'多选题答案{items}与任何选项都不匹配，跳过该题'), flush=True)
                    return False
                if _opts_el:
                    self.answer_num = [i for i in self.answer_num if i < len(_opts_el)]
                if not self.answer_num:
                    print(color.red(f'第{title_num+1}题选项元素缺失（页面未渲染完），跳过该题'), flush=True)
                    return False
                # 点击正确答案
                for ans in self.answer_num:
                    time.sleep(1)
                    try:
                        if _opts_el[ans].get_attribute('aria-checked')== 'true':
                            print(color.red('已回答，无需重复回答'), flush=True)
                        else:
                            self._click_option(_opts_el[ans],
                                               f'第{title_num+1}题选项{ans+1}')
                    except Exception:
                        try:
                            self.driver.execute_script(
                                "arguments[0].click();", _opts_el[ans])
                        except Exception:
                            pass
                return True

            elif self.questionType_list[title_num] in ('简答题', '论述题', '名词解释', '计算题'):
                answer_text = ' '.join(answer) if isinstance(answer, list) else str(answer)
                text_frame = self.questionList0[title_num].find_element(By.TAG_NAME, 'iframe')
                # 富文本 iframe 可能未渲染（UMEditor 懒加载）或已 stale，
                # switch_to.frame 会抛 NoSuchFrameError——改用 JS 直写
                # contentDocument，不依赖 frame 切换
                try:
                    self.driver.switch_to.frame(text_frame)
                    p_element = self.driver.find_element(By.TAG_NAME, 'p')
                    check_answer = p_element.text
                    if check_answer != '':
                        print(color.red('已回答，无需重复回答'), flush=True)
                        self.driver.switch_to.parent_frame()
                        return True
                    p_element.click()
                    p_element.send_keys(answer_text)
                    self.driver.switch_to.parent_frame()
                    return True
                except Exception:
                    try:
                        self.driver.switch_to.default_content()
                    except Exception:
                        pass
                written = self.driver.execute_script(
                    '''const f = arguments[0], text = arguments[1];
                       const doc = f.contentDocument || (f.contentWindow && f.contentWindow.document);
                       if (!doc || !doc.body) return false;
                       if (doc.body.innerText.trim()) return 'answered';
                       doc.body.innerHTML = text;
                       return true;''', text_frame, answer_text)
                if written == 'answered':
                    print(color.red('已回答，无需重复回答'), flush=True)
                    return True
                if written is True:
                    return True
                print(color.red('该题富文本编辑框不可写，已跳过'), flush=True)
                return False
            elif self.questionType_list[title_num]=='填空题':
                # 学习通填空题用的是 UEditor 富文本编辑器（不是 input/InpDIV）：
                # 每空一个 .edui-editor，真实数据载体是隐藏 textarea
                # name="answerEditor<题目ID><空序号>"，内容必须经 UE.instants 的
                # setContent 写入——旧的 p_element.send_keys 会被 Selenium 拒绝
                # （ElementNotInteractableException: <p> is not reachable by keyboard），
                # 且异常被吞掉，表现为"填空题整题不填"。
                return self.fill_blank_question(title_num, answer)
            else:
                print(color.red(f'该题为{self.questionType}，暂时无法作答'), flush=True)
                return False
        except Exception as e:
            print(color.red(f'答题时出错了{e}'), flush=True)
            return False

    _SAVE_BTN_CSS = ('[class*="btnSave"]', '[class*="btnSave"][class*="work"]',
                     '//a[contains(text(),"暂存")]',
                     '//a[contains(text(),"保存")]')
    _SUBMIT_BTN_CSS = ('[class*="btnSubmit"]', '[class*="btnSubmit"][class*="work"]',
                       '//a[contains(text(),"提交")]')

    def _click_btn(self, css_list, desc):
        """多候选宽松匹配点击（页面按钮 class 顺序/附加类不固定，
        严格 [class="a b"] 匹配会 NoSuchElementException 崩掉整卷）"""
        for css in css_list:
            by = By.XPATH if css.startswith('//') else By.CSS_SELECTOR
            try:
                self.driver.find_element(by, css).click()
                return True
            except Exception:
                continue
        print(color.red(f'未找到{desc}按钮（页面结构可能与预期不符），'
                        f'请人工保存/提交，本卷继续'), flush=True)
        return False

    def submit(self):
        formatted_result = "{:.2%}".format(self.ans_rate)
        print(color.red(f'本次答题率为{formatted_result}'), flush=True)
        if self.after_finish_question=='仅自动保存':
            print(color.yellow('3秒后保存'), flush=True)
            time.sleep(3)
            self._click_btn(self._SAVE_BTN_CSS, '暂存保存')
        elif (self.after_finish_question=='强制自动提交' or self.work_choice =='随机答题'
              or (isinstance(self.after_finish_question, (int, float))
                  and self.ans_rate >= self.after_finish_question)):
            # 点击提交
            print(color.yellow('3秒后提交'), flush=True)
            time.sleep(3)
            if not self._click_btn(self._SUBMIT_BTN_CSS, '提交'):
                return True
            time.sleep(1)
            try:
                # 点击确认
                self.driver.switch_to.default_content()
                self.driver.find_element(By.XPATH, '//*[@id="popok"]').click()
                time.sleep(2)
                message =self.driver.find_element(By.ID, 'popcontent').text
                if message:
                    print(color.red(f'提交失败，原因：{message}'), flush=True)
                    self.driver.find_element(By.ID, 'popok').click()
                    return False
                self.save_score()
            except Exception:
                print(color.red('提交确认弹窗处理异常，请人工确认提交状态'), flush=True)
                return True
        else:
            print(color.yellow(f'答题率未达到提交要求{self.after_finish_question}'), flush=True)
            print(color.yellow('3秒后保存'), flush=True)
            time.sleep(3)
            self._click_btn(self._SAVE_BTN_CSS, '暂存保存')

        return True

    def save_score(self):
        element = self.driver.find_element(By.CLASS_NAME, 'prev_title')
        title = element.get_attribute('title')
        self.driver.switch_to.frame('iframe')
        self.driver.switch_to.frame(self.frame)
        self.driver.switch_to.frame('frame_content')
        try:
            with open(fr'task/record/《{self.course_name}》的成绩记录.txt', 'a', encoding='utf-8') as f:
                element = self.driver.find_element(By.CSS_SELECTOR, '.achievement i')
                score = element.text
                f.write(
                    f'已完成:《{title}》章节中的测试题，完成时间：{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))}\n测试得分：{score}分(本次使用{self.work_choice})\n\n')
        except:
            print(color.yellow('未查询到本次测试成绩'), flush=True)
            try:
                with open(fr'task/record/《{self.course_name}》的成绩记录.txt', 'a', encoding='utf-8') as f:
                    f.write(
                    f'已完成:《{title}》章节的测试题，完成时间：{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))}\n测试得分：未查询到(本次使用{self.work_choice})\n\n')
            except:
                pass
        self.driver.switch_to.default_content()

def finish_quiz(driver, course_name, API, choice,after_finish_question, API_URL='', API_MODEL=''):
    driver.switch_to.default_content()
    driver.switch_to.frame('iframe')
    test_frames = driver.find_elements(By.XPATH,
                                       '//iframe[@src="/ananas/modules/work/index.html?v=2025-1028-1629&castscreen=0"]')
    print(color.magenta(f'已检测到{len(test_frames)}个测试'), flush=True)
    for test_frame in test_frames:
        try:
            Answer(driver, test_frame, course_name, API, choice,after_finish_question,
                       api_url=API_URL, api_model=API_MODEL)
        except:
            error_msg = traceback.format_exc()
            send_error(error_msg)
            print(color.yellow('出错了，具体原因请前往错误日志查看，请自行保存或提交,15秒后继续'), flush=True)
            time.sleep(15)

