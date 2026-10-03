import time
import re
from selenium.webdriver.common.by import By
from task.tool import color
from task.quiz_ai import Answer


def turn_page(driver,page_name):
    for handle in driver.window_handles:
        # 先切换到该窗口
        driver.switch_to.window(handle)
        # 得到该窗口的标题栏字符串，判断是不是我们要操作的那个窗口
        if page_name in driver.title:
            # 如果是，那么这时候WebDriver对象就是对应的该该窗口，正好，跳出循环，
            break

class do_work(Answer):
    MAX_REDO = 2   # 「自动提交并重做」最大重做轮次，防止死循环

    def __init__(self,driver,course_name,homework,API_KEY,after_finish_question='仅自动保存',
                 api_url='',api_model='',redo_answers=None):
        Answer.__init__(self,driver,test_frame=None,course_name=course_name,api=API_KEY,work_choice=None,after_finish_question=after_finish_question,
                    api_url=api_url, api_model=api_model)

        self.homework = homework
        self.driver = driver
        self.course_name = course_name
        self.current_homework_name = None      # 自动模式下当前处理的作业名（重做用）
        self.redo_answers = redo_answers or {} # 错题修正答案 {题目索引i: [答案]}
        self.redo_round = 0                    # 已重做轮次
        if self.homework == '自动选择':
            if not self.auto_choice_homework_question():
                # 实测（2026-09）：「作业」nav 在部分学校加载的是 mobilelearn
                # 活动聚合页（stuActiveList），其中的 group-radio 是活动筛选、
                # bottomList 恒为空——旧版自动遍历逻辑对该页面结构无效。
                # 找不到真实作业列表时回退手动模式，不空跑不乱点
                print(color.red('自动选择未找到可处理的作业列表，已回退手动模式：请手动点开你要刷的作业'), flush=True)
                self.wait_manual_open()
        elif self.homework == '手动选择':
            print(color.green('请手动选择你要刷的作业，点开即可'), flush=True)
            self.wait_manual_open()
        print(color.green(f'已完成作业,15秒后自动关闭窗口'), flush=True)
        time.sleep(15)

    def wait_manual_open(self):
        now_window_handles = len(self.driver.window_handles)
        # 等待用户手动点开作业：必须带超时，否则无人操作时进程永久挂起
        for _ in range(300):
            if len(self.driver.window_handles) != now_window_handles:
                break
            time.sleep(1)
        else:
            print(color.red('等待手动打开作业超时（5 分钟），本次跳过'), flush=True)
            return
        time.sleep(2)
        self.get_answer_list()


    @staticmethod
    def _click_filter_radio(driver, r):
        """点击类型筛选单选。学习通的 radio input 通常 display:none
        （仅显示样式化 label），原生 click 会报 ElementNotInteractable
        （could not be scrolled into view）——先滚动再 JS 点击兜底"""
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", r)
        except Exception:
            pass
        try:
            r.click()
            return True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", r)
                return True
            except Exception:
                return False

    def auto_choice_homework_question(self):
        """自动遍历作业列表。返回 True=已自动处理完成；
        False=当前页面没有真实作业列表（调用方回退手动模式）"""
        # 点击类型筛选中的「作业」项：优先按文本匹配，原版索引兜底
        # （原实现无等待直接 elements[2].click()，页面未渲染完就 IndexError，
        #   或筛选组顺序变化导致点错——表现为"自动选择无效"）
        radios = []
        for _ in range(10):
            radios = self.driver.find_elements(By.CSS_SELECTOR, '[name="group-radio"]')
            if radios:
                break
            time.sleep(1)
        print(color.green(f'检测到 {len(radios)} 个类型筛选单选'), flush=True)
        labels = []
        clicked = False
        for idx, r in enumerate(radios):
            try:
                label = (r.get_attribute('value') or r.get_attribute('aria-label')
                         or r.text
                         or r.find_element(By.XPATH, '..').text or '').strip()
            except Exception:
                label = ''
            labels.append(label)
            if '作业' in label:
                if self._click_filter_radio(self.driver, r):
                    clicked = True
                    print(color.green(f'已点击筛选：{label}'), flush=True)
                    break
        if not clicked and len(radios) > 2:
            if self._click_filter_radio(self.driver, radios[2]):
                clicked = True
                print(color.green(f'未匹配到文本，按原版逻辑点击第 3 个筛选（各筛选项：{labels}）'), flush=True)
        if not clicked:
            print(color.red(f'未找到可点击的作业筛选单选（各筛选项：{labels}）'), flush=True)
            return False
        time.sleep(2)
        # 作业列表可能延迟渲染，轮询等待
        element = None
        for _ in range(10):
            try:
                element = self.driver.find_element(By.CLASS_NAME, 'bottomList')
                break
            except Exception:
                time.sleep(1)
        if element is None:
            print(color.red('未检测到作业列表（bottomList）'), flush=True)
            return False
        # 作业列表
        homework_list = element.find_elements(By.TAG_NAME, 'li')
        if not homework_list:
            # bottomList 存在但没有作业条目（活动聚合页 In progress(0)/Ended(0)
            # 就是这种形态）——当前页面无真实作业，回退手动
            print(color.red('作业列表为空（0 个条目）'), flush=True)
            return False
        print(color.green(f'已检测到{len(homework_list)}个作业'), flush=True)
        for i in range(len(homework_list)):
            if i != 0:
                turn_page(self.driver, self.course_name)
                self.driver.switch_to.frame(self.driver.find_element(By.TAG_NAME, 'iframe'))
                # 重新获取作业列表（切窗/切帧后旧元素引用已 stale）
                try:
                    element = self.driver.find_element(By.CLASS_NAME, 'bottomList')
                    homework_list = element.find_elements(By.TAG_NAME, 'li')
                except Exception:
                    print(color.red('重新获取作业列表失败，停止自动选择'), flush=True)
                    break
            homework = homework_list[i]
            # 获取作业名称
            homework_name = homework.get_attribute('aria-label')
            print(color.green(f'开始处理第{i + 1}个作业：{homework_name}'), flush=True)
            self.current_homework_name = homework_name   # 供「自动提交并重做」重开同名作业
            # 点击作业
            homework.click()
            time.sleep(1)
            self.get_answer_list()
            print(color.green(f'已完成第{i + 1}个作业'), flush=True)
            time.sleep(1)
            self.driver.close()

    def get_answer_list(self):
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
        # 切换到作业窗口
        turn_page(self.driver, '作业作答')
        # 查找作业题目数量
        self.questionList0 = self.driver.find_elements(By.CSS_SELECTOR,
                                                           '[class="padBom50 questionLi fontLabel singleQuesId"]')
        print(color.green(f'作业题目数量：{len(self.questionList0)}'), flush=True)
        for i in range(len(self.questionList0)):
            self.title_num = i + 1
            self.option_text_list = []
            self.optionWebElementList = []
            # 获取题目类型和题目内容
            self.title_and_option_element=self.questionList0[i]
            self.title_and_option_text =self.title_and_option_element.text
            self.questionType = self.questionList0[i].get_attribute('typename')
            if self.questionType not in ['填空题','判断题','单选题','多选题','简答题','名词解释','论述题','计算题']:
                print(color.red(f'第{i+1}题题型为{self.questionType},无法作答'))
                # 占位追加：questionType_list/only_title_text 必须与题目原始索引 i
                # 对齐（all_title_dit/num_option_dit 的 key 就是 i），否则跳过的
                # 未知题型会让后面所有题取到错位的题型/题目文本
                self.only_title_text.append('')
                self.questionType_list.append(self.questionType)
                continue
            self.title = self.questionList0[i].find_element(By.CSS_SELECTOR, '[class="mark_name colorDeep fontLabel workTextWrap"]').text
            self.title_text=self.title [self.title.find(")") + 1:]
            # self.title_text=self.title [self.title.find("】") + 1:]
            self.only_title_text.append(self.title_text)
            self.questionType_list.append(self.questionType)

            # print(self.questionType,self.title_content)
            if self.title_text == '':
                print(color.red('未检测到题目内容'), flush=True)
                # 占位：all_optionWebElementList 的索引必须与 all_title_dit 的
                # key（题目原始索引）一致，否则后面会点到别题的选项
                self.all_optionWebElementList.append(None)
                continue
            self.optionWebElementList = self.questionList0[i].find_elements(By.CSS_SELECTOR,
                                                                                     '[class*="clearfix answerBg"]')
            self.all_optionWebElementList.append(self.optionWebElementList)
            for option_element in self.optionWebElementList:
                # 选项缺 aria-label 时 get_attribute 返回 None，None[:-2] 会 TypeError 崩整卷
                self.option_text_list.append((option_element.get_attribute('aria-label') or '')[:-2])
            self.all_title_dit[i] = self.title_and_option_text
            self.num_option_dit[i] = self.option_text_list
        # 「自动提交并重做」重做轮次：错题直接使用修正答案（跳过搜题）；
        # 详情页未提取到答案的题留空，由 use_ai_fallback 重新搜题兜底
        if self.redo_answers:
            filled = 0
            for i, ans in self.redo_answers.items():
                if (i < len(self.only_title_text) and ans
                        and self.questionType_list[i] in
                        ('单选题', '多选题', '判断题', '简答题', '论述题',
                         '名词解释', '计算题', '填空题')):
                    self.num_answer_dit[i] = ans
                    filled += 1
                    print(color.green(f'重做修正：第{i+1}题使用已知答案 {ans}'), flush=True)
            if filled:
                print(color.green(f'重做轮次：{filled} 道错题已预填修正答案'), flush=True)
        print(color.red('正在搜索中，请耐心等待...'))
        self.use_ai_wen_da()
        self.use_ai_fallback()
        print(color.green('开始答题'), flush=True)
        for title_num in self.num_answer_dit.keys():
            self.finish_title(title_num)
            time.sleep(0.5)
        try:
            self.save_elements = self.driver.find_element(By.ID, 'submitFocus').find_elements(By.TAG_NAME, 'a')
        except Exception:
            # 保存按钮找不到时直接返回，绝不能走到下面引用未定义的 save_elements
            print(color.red('保存失败，请手动保存，15秒后继续'), flush=True)
            time.sleep(15)
            return
        if self.after_finish_question == '强制自动提交' or self.after_finish_question == '自动提交并重做':
            # 高级设置「答完题后」配置为提交：点提交 + 确认弹窗
            print(color.red(f'已配置为{self.after_finish_question}，3秒后提交，AI 答题不一定完全正确'), flush=True)
            time.sleep(3)
            submitted = self._submit_work()
            if not submitted:
                print(color.red('当前页面无提交按钮，回退为仅暂时保存'), flush=True)
                self._save_only()
                return
            if self.after_finish_question == '自动提交并重做':
                # 提交成功后拉取详情页错题，需要重做时进入重做流程
                self._handle_redo_after_submit()
            return
        if self.after_finish_question != '仅自动保存':
            # 「搜到XX%自动提交」等选项在作业链路不生效（无答题率统计），回退保存
            print(color.yellow(f'作业链路不支持「{self.after_finish_question}」，按仅保存处理'), flush=True)
        print(color.red('暂时保存，AI答题不一定完全正确，请自行确认后再提交'), flush=True)
        self._save_only()

    def _submit_work(self):
        """提交作业 + 确认弹窗。返回 True=已提交。"""
        try:
            self.driver.find_element(By.CSS_SELECTOR, '[class="btnSubmit workBtnIndex"]').click()
            time.sleep(1)
        except Exception:
            return False
        try:
            self.driver.switch_to.default_content()
            self.driver.find_element(By.XPATH, '//*[@id="popok"]').click()
            time.sleep(2)
            message = self.driver.find_element(By.ID, 'popcontent').text
            if message:
                print(color.red(f'提交失败，原因：{message}'), flush=True)
                try:
                    self.driver.find_element(By.ID, 'popok').click()
                except Exception:
                    pass
                return False
            print(color.green('作业已提交'), flush=True)
            return True
        except Exception:
            print(color.red('提交确认弹窗处理异常，请人工确认提交状态'), flush=True)
            return True

    # ---- 「自动提交并重做」：详情页错题拉取 ----
    _WRONG_VIEW_BTNS = ('查看成绩', '查看详情', '查看解析', '成绩详情', '查看')
    # 错题标记候选（不同版本学习通 DOM 差异大，宽松匹配）
    _WRONG_MARKERS = ('[class*="wrong"]', '[class*="cuo"]', '.cuo',
                      '[class*="error"]', '[class*="fault"]',
                      '[class*="incorrect"]')
    _ANSWER_PATTERNS = (r'正确答案[:：]\s*(.+)', r'正确答案[为是]\s*(.+)',
                        r'答案[:：]\s*(.+)')

    def _open_result_page(self):
        """提交后找「查看成绩/详情」入口并进入。返回 True=已进入详情页。"""
        candidates = []
        try:
            candidates = self.driver.find_elements(By.TAG_NAME, 'a') + \
                         self.driver.find_elements(By.TAG_NAME, 'button')
        except Exception:
            pass
        for el in candidates:
            try:
                txt = (el.text or '').strip()
            except Exception:
                txt = ''
            if txt and any(k in txt for k in self._WRONG_VIEW_BTNS):
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el)
                    el.click()
                    time.sleep(2)
                    return True
                except Exception:
                    continue
        return False

    def _fetch_wrong_questions(self):
        """进入详情页后解析错题。

        返回 {题目原始索引 i: [正确答案]}；答案文本提取不到时值为 []
        （重做时该题将重新搜题作答，不丢题）。
        """
        wrong = {}
        markers = []
        for css in self._WRONG_MARKERS:
            try:
                markers = self.driver.find_elements(By.CSS_SELECTOR, css)
                if markers:
                    break
            except Exception:
                continue
        if not markers:
            print(color.yellow('详情页未识别到错题标记（页面结构可能不同），'
                               '重做时将重新搜题作答'), flush=True)
            return wrong
        for m in markers:
            try:
                container = m.find_element(By.XPATH, './ancestor::*[contains(@class,"singleQuesId") '
                                                    'or contains(@class,"questionLi") '
                                                    'or contains(@class,"padBom50")]')
            except Exception:
                container = m.find_element(By.XPATH, './ancestor::li') if False else m
            try:
                text = container.text if container is not m else \
                    m.find_element(By.XPATH, '../..').text
            except Exception:
                text = m.text
            # 提取题目序号（第N题 / N.）与答案
            answer = []
            for pat in self._ANSWER_PATTERNS:
                mm = re.search(pat, text)
                if mm:
                    answer = [mm.group(1).strip()]
                    break
            # 题目文本与首轮 only_title_text 匹配定位索引
            idx = self._match_question_index(text)
            if idx is not None:
                wrong[idx] = answer
                print(color.red(f'检测到第{idx+1}题答错'
                                f'{f"，修正答案：{answer}" if answer else "，重做时将重新搜题"}'),
                      flush=True)
        return wrong

    def _match_question_index(self, text):
        """按题目文本模糊匹配首轮解析出的题目索引。"""
        for i, t in enumerate(self.only_title_text):
            if t and (t in text or text in t):
                return i
        # 失败时尝试「第N题」序号
        mm = re.search(r'第\s*(\d+)\s*题', text)
        if mm:
            idx = int(mm.group(1)) - 1
            if 0 <= idx < len(self.only_title_text):
                return idx
        return None

    def _handle_redo_after_submit(self):
        """提交后：拉详情页错题 → 有错题且未到轮次上限则重做修正。"""
        print(color.yellow('正在拉取提交详情，识别错误题目...'), flush=True)
        if not self._open_result_page():
            print(color.yellow('未找到成绩/详情入口，跳过重做'), flush=True)
            return
        wrong = self._fetch_wrong_questions()
        if not wrong:
            print(color.green('本次作业全部答对，无需重做'), flush=True)
            return
        if self.redo_round >= self.MAX_REDO:
            print(color.red(f'已达最大重做轮次（{self.MAX_REDO}），请人工检查详情页错题'), flush=True)
            return
        self.redo_round += 1
        print(color.red(f'第 {self.redo_round} 次重做：{len(wrong)} 道错题待修正'), flush=True)
        self._redo(wrong)

    def _redo(self, wrong_answers):
        """关闭作业窗口 → 回课程页重新打开同一作业 → 带修正答案重做。"""
        try:
            self.driver.close()
        except Exception:
            pass
        time.sleep(2)
        turn_page(self.driver, self.course_name)
        try:
            self.driver.switch_to.frame(self.driver.find_element(By.TAG_NAME, 'iframe'))
        except Exception:
            pass
        if self.homework == '自动选择' and self.current_homework_name:
            self._reopen_homework(self.current_homework_name, wrong_answers)
        else:
            # 手动模式：等待用户重新点开作业
            print(color.green('请重新点开该作业（将修正错题后再次提交）'), flush=True)
            self.wait_manual_open()

    def _reopen_homework(self, name, wrong_answers):
        """自动模式下按作业名重新点开作业并带修正答案重做。"""
        element = None
        for _ in range(10):
            try:
                element = self.driver.find_element(By.CLASS_NAME, 'bottomList')
                break
            except Exception:
                time.sleep(1)
        if element is None:
            print(color.red('重做：未找到作业列表，请手动点开作业'), flush=True)
            self.wait_manual_open()
            return
        for li in element.find_elements(By.TAG_NAME, 'li'):
            try:
                label = (li.get_attribute('aria-label') or '').strip()
            except Exception:
                label = ''
            if label == name:
                try:
                    li.click()
                    time.sleep(1)
                except Exception:
                    self.driver.execute_script("arguments[0].click();", li)
                    time.sleep(1)
                print(color.green(f'重做：已重新打开作业《{name}》'), flush=True)
                self.get_answer_list()
                return
        print(color.red('重做：未在列表中找到同名作业，请手动点开'), flush=True)
        self.wait_manual_open()

    def _save_only(self):
        for save_element in self.save_elements:
            if save_element.text == '暂时保存':
                save_element.click()


