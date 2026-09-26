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
from task.tool.no_secret import DecodeSecret
from task.tool import color
import sys
import io
from task.tool.ai_wen_da import main,AnswerAPI,Question
from task.tool.AIAsk import AIAsk
from task.tool.send_wx import send_error

# 设置默认编码为UTF-8（先冲刷旧缓冲并防止重复包裹导致日志丢失/句柄泄漏）
sys.stdout.flush()
if type(sys.stdout) is not io.TextIOWrapper:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
            for title_num in self.num_answer_dit.keys():
                if self.finish_title(title_num):
                    self.reword_time += 1
                time.sleep(1)
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
            # 题目类型（英文标记归一化为中文，未知题型保持原样走"无法作答"分支）
            self.questionType = self.title[self.title.find("【") + 1: self.title.find("】")]
            self.questionType = QUESTION_TYPE_ALIAS.get(
                self.questionType.strip().lower(), self.questionType)
            # 题目文本
            self.title_text = self.title[self.title.find("】") + 1:]
            self.only_title_text.append(self.title_text)
            self.questionType_list.append(self.questionType)
            if self.questionType in ['单选题', '多选题','判断题']:
                self.all_optionWebElementList.append(
                    self.title_and_option_element.find_elements(By.TAG_NAME, 'li'))
                for option in self.title_and_option_element.find_elements(By.TAG_NAME, 'li'):
                    self.option_text_list.append(re.sub(r'\s+', '', self.decodeSecret.decode(option.text).strip()))
            elif self.questionType in ['简答题', '论述题', '填空题','名词解释', '计算题']:
                self.all_optionWebElementList.append(None)
                self.option_text_list  =['']
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
                return ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                return [raw.strip()] if raw.strip() else []
        return raw

    def use_ai_wen_da(self):
        for i in self.all_title_dit.keys():
            if self.times==0 and self.work_choice!='随机答题':
                print(color.green('\n<===================  分隔线  ===================>\n'), flush=True)
                # 先置空：搜索抛异常时不能沿用上一题的答案（会错答本题）
                self.answer_list = None
                try:
                    self.answer_list = asyncio.run(
                        main(self.questionType_list[i], self.only_title_text[i], self.num_option_dit[i], self.API_KEY,
                             api_url=self.API_URL, api_model=self.API_MODEL))
                except Exception as e:
                    print(color.red(f'第{i+1}题搜索失败：{e}'), flush=True)

                self.answer_list = self._parse_answer_list(self.answer_list)
                if not self.answer_list:
                    try:
                        self.answer_list = asyncio.run(
                            main(self.questionType_list[i], self.only_title_text[i], self.num_option_dit[i], self.API_KEY,
                                 api_url=self.API_URL, api_model=self.API_MODEL))
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
            for no_answer_title in self.no_answer_dit.values():
                title += no_answer_title
            try:
                answers = AIAsk(self.API_KEY, title, 'all', api_url=self.API_URL, api_model=self.API_MODEL)
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
                    if ans_text and ans_text != '[]':
                        # AI 对答不出的题可能输出 '[]'，视为无答案留空
                        self.num_answer_dit[key] = re.split(',', ans_text)
                        # 缓存答案
                        question = Question(
                            type=str(self.questionType_list[key]),  # 题目类型
                            question=self.only_title_text[key],
                            options=self.num_option_dit[key],
                            API=self.API_KEY)
                        AnswerAPI().cache_answer(question, self.num_answer_dit[key])
                    num += 1
            except Exception:
                # AI 兜底失败不应终止整课：无答案的题保持空答案，
                # 后续照常保存/提交，其余题不受影响
                traceback.print_exc()
                print(color.red('AI 兜底搜题失败，无答案的题将留空'), flush=True)
                self.no_answer_dit.clear()


    def finish_title(self, title_num):
        try:
            # 滚动到题目
            self.driver.execute_script("arguments[0].scrollIntoView();", self.questionList0[title_num])
            # pyautogui.scroll(50)
        except:
            pass
        print(color.green(f'正在回答第{title_num + 1}题...'), flush=True)
        answer=self.num_answer_dit[title_num]
        #去重
        print(color.green(f'该题为{self.questionType_list[title_num]}，答案：{answer}'), flush=True)
        option_num=0
        try:
            if self.questionType_list[title_num]=='单选题' or self.questionType_list[title_num]=='判断题':
                for option in self.num_option_dit[title_num]:
                    if answer[0] in option:
                       break
                    option_num+=1
                if self.all_optionWebElementList[title_num][option_num].get_attribute('aria-checked')== 'true':
                    print(color.red('已回答，无需重复回答'),flush=True)
                else:
                    self.all_optionWebElementList[title_num][option_num].click()
                return True
            elif self.questionType_list[title_num] == '多选题':
                self.answer_num=[]
                if len(answer)==1:
                    lst = answer[0]
                else:
                    lst = answer
                for option in self.num_option_dit[title_num]:
                    for ans in lst:
                        if ans in option:
                           self.answer_num .append(option_num)
                    option_num+=1
                self.answer_num=list(set(self.answer_num))
                # 点击正确答案
                for ans in self.answer_num:
                    time.sleep(1)
                    try:
                        if self.all_optionWebElementList[title_num][ans].get_attribute('aria-checked')== 'true':
                            print(color.red('已回答，无需重复回答'), flush=True)
                        else:
                            self.all_optionWebElementList[title_num][ans].click()
                    except:
                        self.all_optionWebElementList[title_num][ans].click()
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
                if self.work_choice is not None:
                    elements = self.questionList0[title_num].find_elements(By.CLASS_NAME, 'InpDIV')
                else:
                    elements = self.questionList0[title_num].find_elements(By.CSS_SELECTOR,
                                                                           '[class="edui-editor-iframeholder edui-default"]')
                text_frames = self.questionList0[title_num].find_elements(By.TAG_NAME, 'iframe')
                if  len(answer)==1:
                    answer=re.split(r' ', answer[0])
                    print(color.red(f'修正答案：{answer}'), flush=True)
                if len(elements)>len(answer):
                    print(color.red('填空题答案数量少于题目数量'), flush=True)
                    return False
                for number in range(len(elements)):
                    self.driver.execute_script("arguments[0].click();", elements[number])
                    self.driver.switch_to.frame(text_frames[number])
                    p_element = self.driver.find_element(By.TAG_NAME, 'p')
                    check_answer = p_element.text
                    if check_answer != '':
                        print(color.red('已回答，无需重复回答'), flush=True)
                        self.driver.switch_to.parent_frame()
                        continue
                    try:
                        p_element.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", p_element)
                    try:
                        p_element.send_keys(answer[number])
                    except:
                        pass
                    self.driver.switch_to.parent_frame()
                    time.sleep(1)
                return True
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

