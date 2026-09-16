import time
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
    def __init__(self,driver,course_name,homework,API_KEY,after_finish_question='仅自动保存',
                 api_url='',api_model=''):
        Answer.__init__(self,driver,test_frame=None,course_name=course_name,api=API_KEY,work_choice=None,after_finish_question=after_finish_question,
                    api_url=api_url, api_model=api_model)

        self.homework = homework
        self.driver = driver
        self.course_name = course_name
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
        while len(self.driver.window_handles) == now_window_handles:
            time.sleep(1)
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
                continue
            self.title = self.questionList0[i].find_element(By.CSS_SELECTOR, '[class="mark_name colorDeep fontLabel workTextWrap"]').text
            self.title_text=self.title [self.title.find(")") + 1:]
            # self.title_text=self.title [self.title.find("】") + 1:]
            self.only_title_text.append(self.title_text)
            self.questionType_list.append(self.questionType)

            # print(self.questionType,self.title_content)
            if self.title_text == '':
                print(color.red('未检测到题目内容'), flush=True)
                continue
            self.optionWebElementList = self.questionList0[i].find_elements(By.CSS_SELECTOR,
                                                                                     '[class*="clearfix answerBg"]')
            self.all_optionWebElementList.append(self.optionWebElementList)
            for option_element in self.optionWebElementList:
                self.option_text_list.append(option_element.get_attribute('aria-label')[:-2])
            self.all_title_dit[i] = self.title_and_option_text
            self.num_option_dit[i] = self.option_text_list
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
        if self.after_finish_question == '强制自动提交':
            # 高级设置「答完题后」配置为直接提交：点提交 + 确认弹窗
            print(color.red('已配置为直接提交，3秒后提交，AI 答题不一定完全正确'), flush=True)
            time.sleep(3)
            try:
                self.driver.find_element(By.CSS_SELECTOR, '[class="btnSubmit workBtnIndex"]').click()
                time.sleep(1)
            except Exception:
                print(color.red('当前页面无提交按钮，回退为仅暂时保存'), flush=True)
                self._save_only()
                return
            try:
                self.driver.switch_to.default_content()
                self.driver.find_element(By.XPATH, '//*[@id="popok"]').click()
                time.sleep(2)
                message = self.driver.find_element(By.ID, 'popcontent').text
                if message:
                    print(color.red(f'提交失败，原因：{message}'), flush=True)
                    self.driver.find_element(By.ID, 'popok').click()
                else:
                    print(color.green('作业已直接提交'), flush=True)
            except Exception:
                print(color.red('提交确认弹窗处理异常，请人工确认提交状态'), flush=True)
            return
        if self.after_finish_question != '仅自动保存':
            # 「搜到XX%自动提交」等选项在作业链路不生效（无答题率统计），回退保存
            print(color.yellow(f'作业链路不支持「{self.after_finish_question}」，按仅保存处理'), flush=True)
        print(color.red('暂时保存，AI答题不一定完全正确，请自行确认后再提交'), flush=True)
        self._save_only()

    def _save_only(self):
        for save_element in self.save_elements:
            if save_element.text == '暂时保存':
                save_element.click()


