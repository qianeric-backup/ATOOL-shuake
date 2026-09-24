# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.
import json
import random
import re
from selenium.common import  NoAlertPresentException
import time
import ast

from selenium.webdriver.common.action_chains import ActionChains

from task.tool.AIAsk import AIAsk
from task.tool import color
from task.tool import runtime_flags
import pyautogui
from selenium.webdriver.common.by import By
import itertools


def generate_combinations_list(input_list):
    """
    返回列表形式的组合，完整组合放在第一位
    """
    n = len(input_list)

    if n == 3:
        # 三者都出现的情况（放在第一位）
        triple = [input_list.copy()]
        # 两两组合的所有可能
        pairs = [list(combo) for combo in itertools.combinations(input_list, 2)]
        return triple + pairs

    elif n == 4:
        # 取四个元素的情况（放在第一位）
        quadruple = [input_list.copy()]
        # 取三个元素的所有可能
        pairs = [list(combo) for combo in itertools.combinations(input_list, 2)]
        triples = [list(combo) for combo in itertools.combinations(input_list, 3)]
        return quadruple + triples + pairs
    else:
        return [input_list]

def check_internet(driver):
    try:
        internet_choice=driver.find_element(By.CSS_SELECTOR,"[class='ans-vjserrdisplay-opts']")
        # print(color.red('网络异常'), flush=True)
        choice_list=internet_choice.find_elements(By.CSS_SELECTOR,"[name='ans-vjserrdisplay-opt']")
        for choice in choice_list:
            choice.click()
    except:
        pass

def get_answer(API,question,typ,api_url='',api_model=''):
    answer = []
    try:
        answer = AIAsk(API, question, typ, api_url=api_url, api_model=api_model)
    except Exception as e:
        print(f'答题时出错了{e}',flush=True)
    return answer
def finish_video_question(options_txt,options,answer,question_type):
    answer_num = []
    option_num = 0
    if question_type == '单选题' or question_type == '判断题':
        for option in options_txt:
            if answer[0] in option:
                break
            option_num += 1
        if option_num >= len(options_txt):
            # AI 答案与任何选项都不匹配：越界会 IndexError 并被外层裸 except
            # 吞掉导致 submit 不再点击——改为显式跳过本题
            print(color.red(f'答案与选项不匹配，跳过该题'), flush=True)
            return
        answer_num.append(option_num)
    elif question_type == '多选题':
        if len(answer) == 1:
            lst = answer[0]
        else:
            lst = answer
        for option in options_txt:
            for ans in lst:
                if ans in option:
                    answer_num.append(option_num)
            option_num += 1
        answer_num = list(set(answer_num))
    # 点击正确答案
    for ans in answer_num:
        checked=options[ans].find_elements(By.CSS_SELECTOR,'[checked="checked"]')
        if not checked:
            options[ans].click()
            time.sleep(1)
        else:
            print(color.yellow(f'已选择选项{ans}'), flush=True)
            continue
def check_video_question(driver,API,video_title_choice,api_url='',api_model=''):
    try:
        element=driver.find_element(By.CLASS_NAME,'tkTopic')
        print(color.yellow('已检测到视频中有题目'), flush=True)
        question_title = element.find_element(By.CLASS_NAME, 'tkItem_title').text
        try:
            question_type=element.find_element(By.CLASS_NAME,'tkTopic_type').text
        except:
            question_type=element.find_element(By.CLASS_NAME,'tkTopic_title').text
        options = element.find_element(By.CLASS_NAME, 'tkItem_ul')
        options = options.find_elements(By.TAG_NAME, 'li')
        options_txt=[option.text for option in options]
        submit = element.find_element(By.ID, 'videoquiz-submit')
        if video_title_choice in ('AI 智能答题', 'DeepSeek AI'):
            answer = get_answer(API,question_title+'\n'+str(options_txt),question_type,api_url=api_url,api_model=api_model)
            if type(answer) is str:
                try:
                    answer = ast.literal_eval(answer)  # 转换为列表
                except:
                    answer = [answer]
            if not answer:
                print(color.red(f'答题失败,无答案'), flush=True)
                return
            else:
                finish_video_question(options_txt,options,answer,question_type)
                submit.click()
        #随机答题：仅随机模式进入，AI 模式已提交的答案不能被轮点覆盖
        elif video_title_choice == '随机答题':
          try:
            if question_type=='单选题' or question_type=='判断题':
                for option in options:
                    option.click()
                    #提交
                    submit.click()
            elif question_type=='多选题':
                answer_lost=generate_combinations_list(options)
                last_ans_set=set()
                for answer in answer_lost:
                    now_ans_set=set(answer)
                    # 使用 ^ 运算符计算对称差集
                    different_elements = now_ans_set ^ last_ans_set
                    for option in different_elements:
                        option.click()
                    last_ans_set=now_ans_set
                    #提交
                    submit.click()
          except:
              pass
        #继续学习
        try:
            continue_learn=element.find_element(By.ID,'videoquiz-continue')
            continue_learn.click()
        except :
            pass
        try:
            return_video=driver.find_element(By.CSS_SELECTOR, '[class="bntWhiteBorder ans-videoquiz-back fr"]')
            return_video.click()
        except:
            pass
    except:
        return

_LAST_RATE_CALL = [None, 0.0, None, False]
ANTI_BG_JS = (
    "try { Object.defineProperty(document, 'hidden', {get: function(){"
    "return false;}, configurable: true}); } catch (e) {}"
    "try { Object.defineProperty(document, 'visibilityState', "
    "{get: function(){return 'visible';}, configurable: true}); }"
    " catch (e) {}"
    "try { document.addEventListener('visibilitychange',"
    " function(e){e.stopImmediatePropagation();}, true); } catch (e) {}"
    "try { window.addEventListener('blur',"
    " function(e){e.stopImmediatePropagation();}, true); } catch (e) {}"
)


def set_video_rate(driver, speed):
    """真正把倍速应用到 <video>（考虑跨 iframe 的超星视频播放器结构）。

    根因（"提速刷课不生效"的技术真相）：超星视频播放器封在
    mooc1-api.chaoxing.com/ananas/... 嵌套 iframe 里。章节树/外层 document
    里执行 document.querySelectorAll('video') 拿不到任何 video 同源元素，
    倍速一直形同虚设。

    修复:
      1. 按当前 frame 树做深度遍历（Selenium 可跨 iframe 切换），对每个
         document 执行 playbackRate = speed，播放器若重置由每秒轮询校正；
      2. 同步给视频 iframe 内 document 注入"伪前台"脚本——解决"web 页
         不在前端时页面无法自动点击/播放被 JS 停播"的另一层问题；
      3. 缓存去重：同倍速 0.6s 内已过一遍则跳过（高频轮询保护）；
      4. 兜底骚扰链路: 点击真实倍速控件（.speedTab/[data-rate]）。
    """
    try:
        rate = float(speed)
    except Exception:
        rate = 1.0
    if rate <= 0:
        rate = 1.0
    now = time.time()
    try:
        same_once = (_LAST_RATE_CALL[0] == rate
                     and now - _LAST_RATE_CALL[1] < 0.6)
    except Exception:
        same_once = False
    if same_once:
        return
    _LAST_RATE_CALL[0], _LAST_RATE_CALL[1] = rate, now

    script = (
        'document.querySelectorAll("video").forEach(function(v){'
        'try{v.playbackRate=arguments[0];}catch(e){}});'
        + ANTI_BG_JS)

    def dfs(depth: int = 0):
        if depth > 6:
            return
        try:
            driver.execute_script(script, rate)
        except Exception:
            pass
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
        except Exception:
            iframes = []
        for f in iframes:
            try:
                driver.switch_to.frame(f)
            except Exception:
                continue
            dfs(depth + 1)
            driver.switch_to.parent_frame()
    dfs()

    # 兜底：点击真实倍速控件（若播放器内 JS 出风控未响应）
    try:
        _click_rate_widget(driver, rate)
    except Exception:
        pass


def _click_rate_widget(driver, rate):
    """尝试点击真实倍速面板/元素 (即使 video JS 失效也走 UI 真实路径).

    兼容多种媒体播放器的已知控件类名（部分超星版本使用 .speedTab 与
    [data-rate]）。
    返回 bool: 是否点击命中。"""
    selectors = (".speedTab", "[data-rate]", ".rateList [data-rate]",
                 ".videoRate")
    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for el in elems:
            try:
                txt = (el.get_attribute("data-rate")
                       or (el.text or "").strip())
                txt_num = re.sub(r"[^\d.]", "", txt.split("x")[0])
                if not txt_num:
                    continue
                if abs(float(txt_num) - rate) < 0.01:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        return True
            except Exception:
                continue
    return False


def check_vido_play(driver, last_time, current_time):
    global b, pause_start_time
    with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as f:
        account_info = json.load(f)
        speed = account_info['speed']
    if last_time == current_time and current_time != '':
        pause_duration = time.time() - pause_start_time
        b += 1
        if  pause_duration >= 2 and b!=3:
            try:
                print(color.red(f'当前视频播放被暂停,点击继续播放'), flush=True)
                driver.find_element(By.CSS_SELECTOR,
                                    '[class="vjs-play-control vjs-control vjs-button vjs-paused"]').click()
            except :
                print(color.red(f'点击失败'), flush=True)
            pause_start_time = time.time()  # 记录第一次检测到暂停的时间
        elif b == 3 and int(speed)>=2:
        # 当暂停时间间隔小于2秒时，执行原elif的代码
            try:
                if int(speed)>2:
                    print(color.red(f'当前视频已被设置不能调节高倍数，现在将倍数调至2倍'), flush=True)
                    new_speed=2
                    account_info['speed'] = '2'
                else:
                    new_speed=1
                    print(color.red(f'当前视频已被设置不能调节高倍数，现在将倍数调至1倍'), flush=True)
                    account_info['speed'] = '1'
                # 降速写回 account_info 后，轮询每秒的 set_video_rate 校正自动生效
                try:
                    driver.find_element(By.CSS_SELECTOR,
                                        '[class="vjs-play-control vjs-control vjs-button vjs-paused"]').click()
                except:
                    print(color.yellow(f'点击播放失败'), flush=True)
            except:
                pass
            with open(r'task/tool/account_info.json', 'w', encoding='utf-8') as fil:
                json.dump(account_info, fil)
        elif b==3 and int(speed)==1:
            raise Exception('视频播放异常')
    else:
        pause_start_time = 0  # 视频正常播放，重置暂停时间记录
        b=0

def handle_video_error_alert(driver):
    try:
        alert = driver.switch_to.alert
        alert_text = alert.text
        if "视频播放异常" in alert_text:
            print(color.red("检测到视频播放异常弹窗，尝试刷新页面..."))
            alert.accept()
            time.sleep(2)
            driver.refresh()
            # 刷新后需要重新进入 iframe，具体逻辑根据实际情况补充
            raise Exception('视频播放异常')
        else:
            alert.accept()
            raise Exception('视频播放异常')
    except NoAlertPresentException:
        return

def check_vido_finish(driver,i,time_start,total_time,vido_iframe,lock_screen,API,video_title_choice,api_url='',api_model=''):
    last_time = 0
    h = 0
    # 判断是否完成任务
    while True:
        time.sleep(1)
        # 每次切换前先处理可能存在的弹窗
        # handle_video_error_alert(driver)
        driver.switch_to.default_content()
        driver.switch_to.frame('iframe')
        elements2 = driver.find_elements(By.CSS_SELECTOR, '.ans-job-icon-clear')
        element2 = elements2[i]
        # 定位到该元素的上一级（父元素）
        parent_element2 = element2.find_element(By.XPATH, "..")
        # 获取 parent_element2 的class值
        parent_element2_class = parent_element2.get_attribute("class")
        txt = element2.get_attribute('aria-label')
        # print(parent_element2_class, flush=True)
        if txt == '任务点已完成' or 'ans-attach-ct ans-job-finished' in parent_element2_class:
            # pyautogui.scroll(-250)
            print(color.green(f'已完成第{i + 1}个视频'), flush=True)
            time_end = time.time()
            print(color.green('总共耗费了%.2f秒.' % (time_end - time_start)), flush=True)
            break
        else:
            driver.switch_to.default_content()
            # check_face(driver,driver.current_url,'popDiv1 wid640  faceCollectQrPopVideo  popClass faceRecognition_0')
            driver.switch_to.frame('iframe')
            driver.switch_to.frame(vido_iframe)
            # 每秒校正倍速（防播放器重置；check_vido_play 降速后此处同步跟随）
            try:
                with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as f:
                    _speed = json.load(f).get('speed', '1')
            except Exception:
                _speed = '1'
            set_video_rate(driver, _speed)
            check_internet(driver)
            check_video_question(driver,API,video_title_choice,api_url=api_url,api_model=api_model)
            element = driver.find_element(By.CLASS_NAME, 'vjs-current-time-display')
            current_time = element.text
            check_vido_play(driver, last_time, current_time)
            last_time = current_time
            if current_time == total_time:
                if h == 0:
                    h += 1
                    try:
                        print(color.yellow('视频已播放完毕，但任务点仍未完成，开始重播'), flush=True)
                        driver.find_element(By.CSS_SELECTOR,
                                            '[class="vjs-play-control vjs-control vjs-button vjs-paused vjs-ended"]').click()
                    except:
                        print(color.red(f'点击失败'), flush=True)
                else:
                    print(color.green(f'已完成第{i + 1}个视频'), flush=True)
                    time_end = time.time()
                    print(color.green('总共耗费了%.2f秒.' % (time_end - time_start)), flush=True)
                    break
            if lock_screen and not runtime_flags.HEADLESS:
                # 无头模式下没有可见窗口需要保持前台，晃鼠标反而干扰用户
                pyautogui.move(20, 0, )
                pyautogui.move(-20, 0)
    return True

def study_page(driver,course_name,lock_screen,API,video_title_choice,api_url='',api_model=''):
    cond=False
    driver.switch_to.default_content()
    driver.switch_to.frame('iframe')
    # 判断是否完成任务
    # 注意：类名必须用 CSS_SELECTOR（By.CLASS_NAME 含空格会抛 Compound class names 异常，
    # 导致每个视频页都"出错了，刷新一下"）
    elements1 = driver.find_elements(By.CSS_SELECTOR, '.ans-job-icon-clear')
    print(color.magenta(f'已检测到{len(elements1)}个视频包含有任务点'),flush=True)
    if not elements1:
        # 页面无可播放任务：在浏览器内滚动而非 pyautogui（避免 X11 依赖）
        driver.execute_script('window.scrollBy(0, 250);')
        print(color.green('视频已完成,点击下一节'),flush=True)
        return

    for i in range(len(elements1)):
        element1=elements1[i]
        # 定位到该元素的上一级（父元素）
        parent_element = element1.find_element(By.XPATH, "..")
        try:
            # 获取 parent_element 的class值
            parent_element_class=parent_element.get_attribute("class")
            txt = element1.get_attribute('aria-label')
        except:
            txt = ''
            parent_element_class=''
        if txt == '任务点未完成' and 'ans-attach-ct' in parent_element_class:
            vido_iframe=element1.find_element(By.XPATH, "following-sibling::iframe[1]")
            driver.execute_script("arguments[0].scrollIntoView();", vido_iframe)
            driver.switch_to.frame(vido_iframe)
            print(color.green(f'开始播放第{i + 1}个视频'),flush=True)
            time_start=time.time()
            try:
                driver.find_element(By.CLASS_NAME,'vjs-big-play-button').click()
            except:
                pass
            # 倍速直设（此时已在视频 iframe 内）
            try:
                with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as f:
                    _speed = json.load(f).get('speed', '1')
            except Exception:
                _speed = '1'
            set_video_rate(driver, _speed)
            print(color.green(f'已设置播放速率：{_speed}x（playbackRate 直设）'), flush=True)
            #点击我知道了
            driver.switch_to.default_content()
            driver.switch_to.frame('iframe')
            driver.switch_to.frame(vido_iframe)
            time.sleep(1)
            try:
                element=driver.find_element(By.CLASS_NAME,'writeNote_vid_blue')
                element.click()
            except:
                pass
            try:
                print(color.blue('调节音量'), flush=True)
                element = driver.find_element(By.XPATH, '//*[@id="video"]/div[6]/div[6]')
                element.click()
                print(color.green('调节成功'), flush=True)
            except:
                print(color.yellow('未找到音量，或已经调节'), flush=True)
            time.sleep(1)
            element=driver.find_element(By.CLASS_NAME,'vjs-duration-display')
            total_time=element.text
            if  total_time=='' or total_time=='0:00':
                print(color.red('获取视频总时长失败'),flush=True)
                total_time='1'
            else:
                print(color.green(f'该视频总时长为：{total_time}'),flush=True)
            print(color.yellow('请不要将窗口最小化，这有可能导致脚本异常\n视频播放完毕会自动跳转\n正在观看视频中……'),flush=True)
            driver.switch_to.default_content()
            driver.switch_to.frame('iframe')
            global b, pause_start_time   # 显式重置全局，避免上个视频的暂停状态残留
            b = 0
            pause_start_time = 0  # 添加变量记录暂停开始时间
            check_vido_finish(driver,i,time_start,total_time,vido_iframe,lock_screen,API,video_title_choice,api_url=api_url,api_model=api_model)
            cond=  True
        driver.switch_to.default_content()
        # check_face(driver,driver.current_url,'popDiv1 wid640  faceCollectQrPopVideo  popClass faceRecognition_0')
        driver.switch_to.frame('iframe')
    print(color.green('所有视频均已完成'),flush=True)
    if cond and judge_active(driver):
        save_vido(driver,course_name)
        print(color.green('已保存视频观看记录'),flush=True)
    return

def save_vido(driver,course_name):
    driver.switch_to.default_content()
    element = driver.find_element(By.CLASS_NAME, 'prev_title')
    title = element.get_attribute('title')
    try:
        with open(fr'task/record/《{course_name}》的刷课记录.txt', 'a', encoding='utf-8') as f:
            f.write(
                f'已刷完:《{title}》章节中的所有视频\n完成时间：{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))}\n\n')
    except:
        pass

def judge_active(driver):
    driver.switch_to.default_content()
    element=driver.find_element(By.CSS_SELECTOR, '[class="prev_ul clearfix"]')
    elements = element.find_elements(By.CSS_SELECTOR, '[title="视频"]')
    num=len(elements)
    try:
        txt=elements[num-1].get_attribute('class')
    except IndexError:
        txt = 'active'
    if txt=='active':
        return True
    else:
        return False

