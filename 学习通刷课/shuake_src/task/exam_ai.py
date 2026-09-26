# -*- coding: utf-8 -*-
"""考试模块 do_exam：自动遍历考试列表并作答。

与作业模块（do_work）同源设计：
- 继承 quiz_ai.Answer 复用题目解析/作答引擎（题库检索 + AI 兜底）
- 考试列表页（mooc1/exam-ans/mooc2/exam/exam-list，vue 应用）探测
- 答题页与作业 doHomeWorkNew 同构（questionLi singleQuesId + typename）

⚠️ 考试作答页结构未经真实考试全量验证（探测时课程无考试实例），
模块内所有关键步骤均有日志与容错；首次使用请人工盯守。
"""
import time

from selenium.webdriver.common.by import By

from task.quiz_ai import Answer
from task.do_work import turn_page
from task.tool import color


class do_exam(Answer):
    def __init__(self, driver, course_name, API_KEY, api_url='', api_model='',
                 mode='自动选择'):
        Answer.__init__(self, driver, test_frame=None, course_name=course_name,
                        api=API_KEY, work_choice=None,
                        after_finish_question='仅自动保存',
                        api_url=api_url, api_model=api_model)
        self.driver = driver
        self.course_name = course_name
        self.mode = mode
        if mode != '手动选择':
            self.auto_choice_exam()
        else:
            print(color.green('请手动打开要作答的考试，点开即可'), flush=True)
            self.wait_manual_open()
        print(color.green('已完成考试流程,15秒后自动关闭窗口'), flush=True)
        time.sleep(15)

    # ------------------------------------------------------------------
    def wait_manual_open(self):
        now_window_handles = len(self.driver.window_handles)
        # 等待用户手动点开考试：必须带超时，否则无人操作时进程永久挂起
        for _ in range(300):
            if len(self.driver.window_handles) != now_window_handles:
                break
            time.sleep(1)
        else:
            print(color.red('等待手动打开考试超时（5 分钟），本次跳过'), flush=True)
            return
        time.sleep(2)
        self.get_answer_list()

    # ------------------------------------------------------------------
    def _find_exam_items(self):
        """在考试列表页探测考试条目（vue 结构，多选择器兜底）。
        返回 (元素列表, 命中的选择器描述)；找不到返回 ([], '')"""
        selectors = [
            ('li', 'li'),
            ('[class*="exam-item"]', 'exam-item'),
            ('[class*="examLi"]', 'examLi'),
            ('[class*="event_li"]', 'event_li'),
            ('ul li[class]', 'ul li[class]'),
        ]
        for sel, name in selectors:
            try:
                els = self.driver.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                continue
            # 条目应包含"考试/已完成/未完成/Enter"等字样才算考试卡片
            valid = []
            for el in els:
                try:
                    txt = (el.text or '').strip()
                except Exception:
                    continue
                if txt and any(k in txt for k in ('考试', 'Enter', 'Completed',
                                                  'Uncompleted', 'Test')):
                    valid.append(el)
            if valid:
                return valid, name
        return [], ''

    def auto_choice_exam(self):
        """遍历考试列表（当前应已在考试列表页）。全程只读探测+点击进入"""
        # 等待列表渲染
        items = []
        where = ''
        for _ in range(12):
            items, where = self._find_exam_items()
            if items:
                break
            time.sleep(1)
        if not items:
            print(color.red('考试列表为空或未检测到考试条目（可能该课程没有考试，'
                            '或考试均已结束）'), flush=True)
            return
        print(color.green(f'已检测到 {len(items)} 个考试条目（选择器: {where}）'), flush=True)

        for i in range(len(items)):
            if i != 0:
                # 回课程页重新定位（切窗/切帧后旧引用 stale）
                turn_page(self.driver, self.course_name)
                try:
                    self.driver.switch_to.frame(
                        self.driver.find_element(By.TAG_NAME, 'iframe'))
                    items, where = self._find_exam_items()
                except Exception:
                    print(color.red('重新获取考试列表失败，停止自动考试'), flush=True)
                    break
                if not items:
                    print(color.red('重新获取考试列表为空，停止自动考试'), flush=True)
                    break
            exam = items[i]
            try:
                exam_name = (exam.get_attribute('aria-label')
                             or exam.text or '').strip().split('\n')[0]
            except Exception:
                exam_name = f'第{i + 1}个考试'
            print(color.green(f'开始处理第{i + 1}个考试：{exam_name}'), flush=True)
            try:
                self.driver.execute_script('arguments[0].scrollIntoView({block:"center"});',
                                           exam)
                self.driver.execute_script('arguments[0].click();', exam)
            except Exception as e:
                print(color.red(f'点击考试条目失败：{e}'), flush=True)
                continue
            time.sleep(2)
            # 进入答题窗口（新窗口或同窗跳转）
            try:
                self.get_answer_list()
                print(color.green(f'已完成第{i + 1}个考试'), flush=True)
            except Exception:
                import traceback
                traceback.print_exc()
                print(color.red(f'第{i + 1}个考试处理异常，继续下一个'), flush=True)
            # 关闭考试窗口回到课程页（若开了新窗口）
            try:
                if len(self.driver.window_handles) > 1:
                    turn_page(self.driver, '考试')
                    self.driver.close()
            except Exception:
                pass
            time.sleep(1)

    # ------------------------------------------------------------------
    def get_answer_list(self):
        """解析考试答题页题目并作答。答题页与作业 doHomeWorkNew 同构"""
        # 定位答题窗口
        turn_page(self.driver, '考试')
        # 初始化作答状态（同 do_work）
        self.no_answer_dit = {}
        self.num_answer_dit = {}
        self.answer_list = []
        self.num_option_dit = {}
        self.all_title_dit = {}
        self.all_optionWebElementList = []
        self.optionWebElementList = []
        self.questionType_list = []
        self.only_title_text = []
        self.answer_num = []
        # 题目元素：与作业同构，泛化匹配以兼容 exam-ans 新版
        self.questionList0 = []
        for sel in ('[class="padBom50 questionLi fontLabel singleQuesId"]',
                    '[class*="questionLi"][class*="singleQuesId"]',
                    '[class*="singleQuesId"]'):
            self.questionList0 = self.driver.find_elements(By.CSS_SELECTOR, sel)
            if self.questionList0:
                break
        print(color.green(f'考试题目数量：{len(self.questionList0)}'), flush=True)
        if not self.questionList0:
            print(color.red('未解析到题目（页面结构可能与预期不符），'
                            '请人工查看浏览器窗口'), flush=True)
            return
        for i in range(len(self.questionList0)):
            self.title_num = i + 1
            self.option_text_list = []
            self.optionWebElementList = []
            try:
                typename = self.questionList0[i].get_attribute('typename') or ''
            except Exception:
                typename = ''
            # typename 缺失时尝试从题面【】解析
            if not typename:
                try:
                    raw = self.questionList0[i].text or ''
                    if '【' in raw and '】' in raw:
                        typename = raw[raw.find('【') + 1:raw.find('】')]
                except Exception:
                    pass
            typename = typename.strip()
            # 归一化（英文题型标记）
            try:
                from task.quiz_ai import QUESTION_TYPE_ALIAS
                typename = QUESTION_TYPE_ALIAS.get(typename.lower(), typename)
            except Exception:
                pass
            known = ('填空题', '判断题', '单选题', '多选题', '简答题',
                     '名词解释', '论述题', '计算题')
            if typename not in known:
                print(color.red(f'第{i+1}题题型为{typename or "未知"},无法作答'))
                # 占位追加：与题目原始索引 i 对齐（all_title_dit 的 key 就是 i），
                # 否则跳过的未知题型会让后面所有题取到错位的题型/题目文本
                self.only_title_text.append('')
                self.questionType_list.append(typename)
                continue
            self.questionType = typename
            try:
                title_el = self.questionList0[i].find_element(
                    By.CSS_SELECTOR, '[class*="fontLabel"]')
                self.title = title_el.text
            except Exception:
                self.title = self.questionList0[i].text
            self.title_text = self.title
            self.only_title_text.append(self.title_text)
            self.questionType_list.append(self.questionType)
            self.all_title_dit[i] = self.title_text
            # 选项
            try:
                self.optionWebElementList = self.questionList0[i].find_elements(
                    By.CSS_SELECTOR, '[class*="answerBg"]')
            except Exception:
                self.optionWebElementList = []
            self.all_optionWebElementList.append(self.optionWebElementList)
            for opt in self.optionWebElementList:
                try:
                    self.option_text_list.append(
                        (opt.get_attribute('aria-label') or opt.text or '')[:-2])
                except Exception:
                    self.option_text_list.append('')
            self.num_option_dit[i] = self.option_text_list

        print(color.red('正在搜索中，请耐心等待...'), flush=True)
        self.use_ai_wen_da()
        self.use_ai_fallback()
        print(color.green('开始答题'), flush=True)
        for title_num in self.num_answer_dit.keys():
            try:
                self.finish_title(title_num)
            except Exception:
                import traceback
                traceback.print_exc()
                print(color.red(f'第{title_num + 1}题作答失败，跳过'), flush=True)
            time.sleep(0.5)
        # 保存/交卷：考试页按钮探测（暂存优先，不自动正式交卷——交卷由人工确认）
        self.save_exam()

    def save_exam(self):
        """考试保存。只点击「暂存」类按钮，正式交卷留给人工确认
        （考试一旦交卷不可逆，自动交卷风险过高）"""
        candidates = []
        try:
            candidates = self.driver.find_element(
                By.ID, 'submitFocus').find_elements(By.TAG_NAME, 'a')
        except Exception:
            pass
        clicked = False
        for el in candidates:
            try:
                t = (el.text or '').strip()
                if '暂存' in t or ('保存' in t and '交' not in t):
                    el.click()
                    clicked = True
                    print(color.green('已点击暂存保存'), flush=True)
                    break
            except Exception:
                continue
        if not clicked:
            # 全页找「暂存」按钮
            try:
                btns = self.driver.find_elements(By.XPATH,
                                                 '//a[contains(text(),"暂存")] | //button[contains(text(),"暂存")]')
                if btns:
                    btns[0].click()
                    clicked = True
                    print(color.green('已点击暂存保存（全页匹配）'), flush=True)
            except Exception:
                pass
        if not clicked:
            print(color.red('未找到暂存按钮，请人工保存/交卷，15秒后继续'), flush=True)
            time.sleep(15)
