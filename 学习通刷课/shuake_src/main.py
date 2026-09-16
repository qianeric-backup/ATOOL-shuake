# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.

#打包python -m PyInstaller --onefile --collect-all selenium main.py
import json
import os
import shutil
import re
import sys
import time
import traceback
from selenium.webdriver.support import expected_conditions as EC
import pyautogui
from selenium.common import NoSuchDriverException, NoSuchWindowException, WebDriverException, \
    ElementNotInteractableException, SessionNotCreatedException, NoSuchElementException, \
    ElementClickInterceptedException
from selenium.webdriver import ActionChains
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium import webdriver
from task.tool.face import check_face,get_cookie,auto_login_with_cookies
from task.finish_dicussion import finish_discussion
from task.play_audio import play_audio
from task.tool import color
from task.watch_live import watch_live
from task.watch_ppt import __ppt
from task.watch_vido import study_page
from task.quiz_ai import  finish_quiz
from task.tool.send_wx import send_error
from task.do_work import do_work
from task.exam_ai import do_exam
from task.reading import reading
condition=True#用于判断是否调节倍数
error_num=0#错误次数


def _path(*parts):
    """跨平台拼接项目内资源路径（兼容源码/打包两种形态，优先 cwd）"""
    if os.path.isdir(os.path.join(os.getcwd(), 'task')):
        return os.path.join(os.getcwd(), *parts)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)
def login_study(driver,phone_number,password):
    """
    使用指定的手机号和密码登录学习通网站。

    - 调试模式（显示浏览器）：保持原流程——账密登录失败时可人工扫码/验证。
    - 非调试模式（无头静默刷课）：仅账号密码自动登录，失败自动重试 3 次；
      不依赖扫码（无头下扫码不可用，原死等逻辑会永久卡住），密码登录后
      轮询页面标题判断完成（最长 20 秒，避免慢加载误判）。

    参数:
    driver: WebDriver 对象，用于控制浏览器。
    phone_number: 字符串，登录使用的手机号码。
    password: 字符串，登录使用的密码。

    返回:
    bool，登录成功 True / 失败 False（失败时调用方应中止刷课）。
    """
    from task.tool import runtime_flags
    # 打开网页
    driver.get("https://i.chaoxing.com/")
    turn_page(driver,'用户登录')
    print(color.green('正在登录中...'), flush=True)
    # 已有有效 cookie 直接免登录（两种模式通用）
    if driver.title != '用户登录':
        if get_cookie(driver):
            print(color.green('登录成功（cookie 自动登录）'), flush=True)
            return True
    if runtime_flags.HEADLESS:
        # 非调试模式：纯账号密码自动登录 + 重试（不依赖扫码）
        for attempt in range(1, 4):
            try:
                element = driver.find_element(By.ID, 'phone')
                element1 = driver.find_element(By.ID, 'pwd')
                element.clear()
                element.send_keys(phone_number)
                element1.clear()
                element1.send_keys(password)
                try:
                    driver.find_element(By.ID, 'loginBtn').click()
                except Exception:
                    pass
                # 轮询等待登录完成（最长 20 秒）
                for _ in range(20):
                    time.sleep(1)
                    if driver.title != '用户登录':
                        break
                if driver.title != '用户登录':
                    if get_cookie(driver):
                        print(color.green('登录成功'), flush=True)
                        return True
            except Exception:
                traceback.print_exc()
            print(color.yellow(f'账号密码登录未完成（第 {attempt}/3 次），自动重试...'), flush=True)
            try:
                driver.get("https://passport2.chaoxing.com/login")
                time.sleep(2)
            except Exception:
                pass
        print(color.red('账号密码登录失败：请检查设置中的手机号/密码是否正确，'
                        '或开启「调试模式」手动完成一次登录（扫码/验证）'), flush=True)
        return False
    # 调试模式（显示浏览器）：保持原流程，账密失败时可人工扫码/验证
    element = driver.find_element(By.ID, 'phone')
    time.sleep(1)
    element1 = driver.find_element(By.ID, 'pwd')
    element.send_keys(phone_number)  # 替换成你的手机号码
    element1.send_keys(password)  # 替换成你的密码
    # 点击登录
    login_button = driver.find_element(By.ID, 'loginBtn')
    try:
        login_button.click()
    except:
        pass
    time.sleep(3)
    if not auto_login_with_cookies(driver):
        print(color.red('登陆失败，请打开手机端学习通，扫码登录'), flush=True)
        while driver.title=='用户登录':
            time.sleep(1)
    if get_cookie(driver):
        print(color.green('登录成功'), flush=True)
        return True
    return False
    # 转到页面内窗口


def save_course_lst(driver,class_name,course_elements,phone_number):
    try:
        have_task_course_element=driver.find_element(By.ID,'stuNormalCourseListDiv')
    except:
        have_task_course_element=driver
    try:
        new_course_elements=have_task_course_element.find_elements(By.CSS_SELECTOR, f'[class="{class_name}"]')
        if len(new_course_elements)==0:
            # 容器内查不到时回退到外层已找到的课程元素（条件原写反导致误报"获取课程列表失败"）
            new_course_elements=course_elements
        course_list = [course_element.get_attribute('title') for course_element in new_course_elements if
                       course_element.get_attribute('title')!= '']
        if len(course_list)==0:
            course_list=[course_element.text for course_element in new_course_elements if
                       course_element.text!= '']
        if len(course_list) == 0:
            print(color.red(f'获取课程列表失败'), flush=True)
        else:
            try:
                with open(r'task/tool/course_name.json', 'r', encoding='utf-8') as f:
                    dit = json.load(f)
                with open(r'task/tool/course_name.json', 'w', encoding='utf-8') as f:
                    new_list = dit.get(phone_number,[]) + course_list
                    # 去重
                    new_list = list(set(new_list))
                    dit[phone_number]=new_list
                    json.dump(dit, f)
                print(color.green(f'保存课程列表成功,共有{len(new_list)}个课程'), flush=True)
            except:
                print(color.red('保存课程列表失败'), flush=True)
    except:
        print(color.red('保存课程列表失败'), flush=True)

def experience(driver):
    # 体验最新版本
    try:
        element = driver.find_element(By.CLASS_NAME, 'experience')
        time.sleep(1)
        element.click()
        print(color.green('正在体验最新版本'), flush=True)
    except NoSuchElementException:
        pass

def choice_course(driver, course_name,speed,task_type,phone_number):
    # time.sleep(200)
    """
    选择指定名称的课程

    参数:
    driver: WebDriver 对象，用于控制浏览器
    course_name: 字符串，要选择的课程名称

    返回:
    无
    """
    # 点击课程
    try:
        driver.find_element(By.CSS_SELECTOR, '[title="新泛雅"]').click()
        time.sleep(1)
    except:
        try:
            driver.find_element(By.CSS_SELECTOR, '[title*="课程"]').click()
            time.sleep(1)
        except NoSuchElementException:
            try:
                driver.find_element(By.CSS_SELECTOR, '[title*="首页"]').click()
                time.sleep(1)
            except:
                pass
    try:
        time.sleep(3)
        driver.switch_to.frame('frame_content')

        # 选择‘我的课程’并点击
        element = driver.find_element(By.CLASS_NAME, 'course-tab')
        elements = element.find_elements(By.TAG_NAME, 'div')
        for element in elements:
            if element.text == '我学的课':
                element.click()
                break
        element.click()
        time.sleep(1)
    except:
        pass
    try:
        print(color.green(f'正在定位《{course_name}》...'),flush=True)
        # experience(driver)
        # turn_page(driver,'课程')
        # 查找所有课程名称元素：页面加载慢时列表未渲染，轮询三个已知选择器
        course_elements = []
        class_name = "course-name"
        for _ in range(15):
            course_elements = driver.find_elements(By.CLASS_NAME, 'course-name')
            class_name = "course-name"
            if len(course_elements) == 0:
                course_elements = driver.find_elements(By.CLASS_NAME, 'courseName')
                class_name = "courseName"
            if len(course_elements) == 0:
                # turn_page(driver, '个人空间')
                # driver.switch_to.frame('frame_content')
                course_elements = driver.find_elements(By.CSS_SELECTOR, '[class="w_cour_txtH fl"]')
                class_name = "w_cour_txtH fl"
            if len(course_elements) > 0:
                break
            time.sleep(1)
        save_course_lst(driver,class_name,course_elements,phone_number)
        # 遍历所有课程元素
        for course_element in course_elements:
            # 如果课程元素的标题属性与指定的课程名称匹配
            if  course_name in course_element.get_attribute('title') or course_name in course_element.text:
                # 滚动到课程名称元素的位置
                driver.execute_script("arguments[0].scrollIntoView();", course_element)
                if task_type not in ('作业', '考试'):
                    set_speed(speed, driver)
                # 使用 JavaScript 点击课程名称元素
                driver.execute_script("arguments[0].click();", course_element)
                # 打印选择的课程名称
                print(color.green(f'您已选择《{course_name}》'), flush=True)
                break
        else:
            # 体验最新版本
            driver.find_element(By.CSS_SELECTOR, ".experience").click()
            print(color.green('正在体验最新版本'), flush=True)
            if not turn_page(driver,'新泛雅'):
                turn_page(driver,'课程')
            element=driver.find_elements(By.XPATH,'//*[@id="stukc"]/div[1]/div[1]/div/a')
            time.sleep(2)
            if len(element)!=0:
                element[0].click()
                driver.find_element(By.XPATH,'//*[@id="stukc"]/div[1]/div[1]/div/div/ul/li[1]').click()
            choice_course(driver,course_name,speed,task_type,phone_number)
    except :
        #继续教育

        print(color.red(f"未找到《{course_name}》这门课程，请检查名称是否正确，或手动选择你要刷课的课程，打开该课程后等待片刻"),
              flush=True)
        now_window_handles=len(driver.window_handles)
        while len(driver.window_handles)==now_window_handles:
            time.sleep(1)
        time.sleep(1)
        return

def find_mission(driver,task_type,speed):
    # 点击开始学习
    try:
        element = driver.find_element(By.CSS_SELECTOR,'[CLASS="start-study readclosecoursepop"]')
        element.click()
    except:
        pass
    experience(driver)
    # 点击章节/作业标签
    elements=driver.find_elements(By.CLASS_NAME, 'nav_content')
    for element in elements:
        if element.text== task_type:
            element.click()
            break
    # 切换到名为 frame_content-zj 的 iframe
    # 页面加载慢时 iframe 尚未渲染：轮询等待，最终找不到则视为本页
    # 无可处理任务（返回 False），不再冒泡终止整课
    iframe_el = None
    for _ in range(10):
        try:
            iframe_el = driver.find_element(By.TAG_NAME, 'iframe')
            break
        except Exception:
            time.sleep(1)
    if iframe_el is None:
        print(color.red('未检测到课程内容 iframe（页面可能未加载完成），跳过本页'), flush=True)
        return False
    driver.switch_to.frame(iframe_el)
    if task_type in ('作业', '考试'):
        return True
    try:
        # 查找待完成任务点的元素
        element = driver.find_element(By.CSS_SELECTOR, '.catalog_tishi120')
    except:
        print(color.red('所有任务点均已完成'),flush=True)
        return False

    # 打印提示信息，表示已检测到未完成点
    print(color.magenta('已检测到未完成点'),flush=True)
    time.sleep(0.5)
    #滚动到未完成的任务点的位置
    driver.execute_script("arguments[0].scrollIntoView();", element)
    set_speed(speed, driver)
    # 点击待完成任务点的元素
    element.click()
    return True


def turn_page(driver,page_name):
    time.sleep(1)
    for handle in driver.window_handles:
        # print(len(driver.window_handles))
        # 先切换到该窗口
        driver.switch_to.window(handle)
        # 得到该窗口的标题栏字符串，判断是不是我们要操作的那个窗口
        if page_name in driver.title:
            # print(driver.title)
            # 如果是，那么这时候WebDriver对象就是对应的该该窗口，正好，跳出循环，
            return True
        else:
            continue
    return False

def fold(driver):
    """折叠侧边目录"""
    try:
        element = driver.find_element(By.XPATH, '//*[@id="selector"]/div[2]')
        element.click()
        time.sleep(1)
    except:
        pass

def set_speed(speed,driver):
    """播放倍速由视频页 playbackRate 直设统一生效（watch_vido.set_video_rate，
    进页设置 + 轮询每秒校正）。此处仅打印日志并锁定只提示一次。"""
    global condition
    if not condition:
        return
    print(color.blue(f'播放倍速将设为：{speed}x（playbackRate 直设，所有模式生效）'), flush=True)
    condition=False

def page_message(driver):
    """检测页面内容类型，返回包含视频、PPT、测验、直播、讨论、音频、阅读的字典"""
    # 内容类型配置：(名称, 查找方式, 选择器)
    CONTENT_TYPES = [
        ('视频', By.CSS_SELECTOR, '[class="ans-attach-online ans-insertvideo-online"]'),
        ('ppt', By.CSS_SELECTOR, '[class="ans-attach-online insertdoc-online-ppt"]'),
        ('ppt', By.CSS_SELECTOR, '[class="ans-attach-online insertdoc-online-pdf"]'),
        ('测验', By.XPATH, '//iframe[@src="/ananas/modules/work/index.html?v=2025-1028-1629&castscreen=0"]'),
        ('直播', By.CSS_SELECTOR, '[src="/ananas/modules/live/index.html?v=2023-1218-1127"]'),
        ('讨论', By.CSS_SELECTOR, '[src="/ananas/modules/insertbbs/index.html?v=2025-0109-1519&castscreen=0"]'),
        ('音频', By.CSS_SELECTOR, '[class="ans-attach-online ans-insertaudio"]'),
        ('阅读', By.CSS_SELECTOR, '[class="ans-attach-online ans-book"]'),
        ('阅读', By.CSS_SELECTOR, '[src="/ananas/modules/read/indexV2.html?v=2026-0227-1121"]'),
    ]

    driver.switch_to.default_content()
    page_message_dict = {}

    original_wait = driver.timeouts.implicit_wait  # 保存原始等待时间
    driver.implicitly_wait(0)

    try:
        iframe = driver.find_element(By.ID, 'iframe')
        driver.switch_to.frame(iframe)

        for name, by, selector in CONTENT_TYPES:
            if name in page_message_dict:
                continue  # 已找到的类型跳过
            try:
                driver.find_element(by, selector)
                page_message_dict[name] = selector
            except NoSuchElementException:
                pass
    except NoSuchElementException:
        pass
    finally:
        driver.implicitly_wait(original_wait)  # 恢复原始等待时间

    return page_message_dict

def click_next_page(driver, pass_face):
    """点击下一页按钮，处理各种异常情况"""
    global error_num
    NEXT_PAGE_XPATH = '//*[@id="prevNextFocusNext"]'
    try:
        driver.find_element(By.XPATH, NEXT_PAGE_XPATH).click()
        return True
    except ElementNotInteractableException:
        print(color.red('🎉 🎉 该课程全部已完结，撒花！！！'), flush=True)
        return False
    except ElementClickInterceptedException:
        # 下一页按钮被弹窗/浮层遮挡：清理人脸/提示弹窗后用 JS 强制点击
        # （JS click 直接派发 DOM 事件，不受遮挡判定限制）
        print(color.yellow('下一页按钮被弹窗遮挡，清理弹窗后 JS 点击'), flush=True)
        try:
            if pass_face == 1:
                delete_face_popup(driver)
                delete_face_popup(driver, 'maskDiv1 starttippop faceRecognition_1 chapterVideoFaceMaskDiv')
        except Exception:
            pass
        try:
            driver.implicitly_wait(0)
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
                    driver.find_element(By.XPATH, NEXT_PAGE_XPATH))
                return True
            finally:
                driver.implicitly_wait(2)
        except Exception:
            driver.refresh()
            print(color.red('出错了，刷新一下'), flush=True)
            if pass_face == 1:
                delete_face_popup(driver)
                delete_face_popup(driver, 'maskDiv1 starttippop faceRecognition_1 chapterVideoFaceMaskDiv')
            fold(driver)
    # except ElementClickInterceptedException:
    #     print(color.red('点击被拦截，尝试将浏览器最大化,如果还是报错，请在下次打开浏览器后手动把浏览器最大化'), flush=True)
    #     driver.maximize_window()
    #     time.sleep(2)
    #     driver.find_element(By.XPATH, NEXT_PAGE_XPATH).click()
    except NoSuchElementException:
        print(color.red('加载中...'), flush=True)
        driver.implicitly_wait(5)
        error_num+=1
        if error_num==6:
            print(color.red('❌ 出错次数过多'), flush=True)
            return False
        try:
            driver.find_element(By.XPATH, NEXT_PAGE_XPATH).click()
        except Exception as e:
            driver.refresh()
            print(color.red(f'出错了，刷新一下'), flush=True)
            if pass_face == 1:
                delete_face_popup(driver)
                delete_face_popup(driver, 'maskDiv1 starttippop faceRecognition_1 chapterVideoFaceMaskDiv')
            fold(driver)
        finally:
            driver.implicitly_wait(2)
    return True

def run(driver,choice,course_name,API,lock_screen,pass_face,video_title_choice,discussion_choice,after_finish_question,
         API_URL='', API_MODEL=''):
    study_fail = 0
    page_fail = 0
    while True:
      try:
        cond=True
        print(color.green('正在检测页面内容'), flush=True)
        page_message_dict=page_message(driver)
        if len(page_message_dict)==0:
            print(color.red('该页面无法识别'),flush=True)
        else:
            print(color.green(f'该页面含有{list(page_message_dict.keys())}'),flush=True)
            if 'ppt' in page_message_dict.keys():
                __ppt(driver)
            if '直播' in page_message_dict.keys():
                #                    '感谢支持，采纳的账号将赠送免费API'),flush=True)
                watch_live(driver)
            if '音频' in page_message_dict.keys():
                play_audio(driver,page_message_dict['音频'])
            if '讨论' in page_message_dict.keys():
                if discussion_choice!='跳过讨论':
                    finish_discussion(driver,API,page_message_dict['讨论'],discussion_choice,API_URL=API_URL,API_MODEL=API_MODEL)
                else:
                    print(color.yellow(f'您已选择{discussion_choice}'), flush=True)

            if '阅读' in page_message_dict.keys():
                reading(driver,page_message_dict['阅读'])
            if '视频' in page_message_dict.keys():
                try:
                    study_page(driver,course_name,lock_screen,API,video_title_choice,api_url=API_URL,api_model=API_MODEL)
                    study_fail = 0   # 处理成功才清零连续失败计数
                except Exception:
                    # 打印完整堆栈便于诊断，不再吞错误
                    traceback.print_exc()
                    study_fail += 1
                    driver.refresh()
                    if study_fail >= 5:
                        print(color.red('该页连续 5 次处理失败，跳过此页'), flush=True)
                        study_fail = 0
                        cond = True   # 强制跳下一页，避免无限刷新
                    else:
                        print(color.red(f'出错了，刷新一下（连续第 {study_fail} 次，错误详情见上方堆栈）'), flush=True)
                        cond = False
            if '测验' in page_message_dict.keys():
                if choice!='不刷题':
                    finish_quiz(driver, course_name, API, choice,after_finish_question,API_URL=API_URL,API_MODEL=API_MODEL)
                else:
                    print(color.yellow('您已选择不刷题，即将跳过测试题'),flush=True)
        driver.switch_to.default_content()
        if cond:
            print(color.green('跳转下一页'), flush=True)
            if not click_next_page(driver, pass_face):
                break
            # 确认
            try:
                driver.find_element(By.XPATH, '//*[@id="mainid"]/div[1]/div/div[3]/a[2]').click()
            except:
                pass
            page_fail = 0   # 成功翻页清零连续页错误
        else:
            if pass_face==1:
                delete_face_popup(driver)
                delete_face_popup(driver,'maskDiv1 starttippop faceRecognition_1 chapterVideoFaceMaskDiv')
            fold(driver)
        time.sleep(1)
      except Exception:
        # 单页异常兜底：打印堆栈并刷新重试本页，绝不冒泡终止整课；
        # 连续 5 页失败才停止，避免空转
        traceback.print_exc()
        page_fail += 1
        study_fail = 0
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        try:
            driver.refresh()
        except Exception:
            pass
        if pass_face==1:
            delete_face_popup(driver)
            delete_face_popup(driver,'maskDiv1 starttippop faceRecognition_1 chapterVideoFaceMaskDiv')
        fold(driver)
        if page_fail >= 5:
            print(color.red('连续 5 页处理失败，终止本课程（错误详情见上方堆栈）'), flush=True)
            break
        print(color.red(f'本页处理出错（连续第 {page_fail} 次），已刷新重试，详情见上方堆栈'), flush=True)
        time.sleep(3)

def _crx_to_xpi(crx_path, tmp_dir):
    """把 Chrome .crx 扩展转换为 Firefox 可安装的 .xpi。
    步骤：剥离 CRX 头（v2/v3）→ 校验内层 zip → 若是 MV3 service_worker
    背景则移除 background 字段（Firefox 不支持 SW；倍速/防暂停的核心
    逻辑都在 content_scripts，不受影响）→ 重打包为 .xpi"""
    import io
    import zipfile
    with open(crx_path, 'rb') as f:
        data = f.read()
    if data[:4] != b'Cr24':
        return crx_path  # 不是 CRX（本身就是 zip/xpi），原样返回
    version = int.from_bytes(data[4:8], 'little')
    if version == 3:
        zip_start = 12 + int.from_bytes(data[8:12], 'little')
    elif version == 2:
        pubkey_len = int.from_bytes(data[8:12], 'little')
        sig_len = int.from_bytes(data[12:16], 'little')
        zip_start = 16 + pubkey_len + sig_len
    else:
        raise ValueError(f'不支持的 CRX 版本: {version}')
    zin = zipfile.ZipFile(io.BytesIO(data[zip_start:]))
    if 'manifest.json' not in zin.namelist():
        raise ValueError('CRX 内未找到 manifest.json')
    manifest = json.loads(zin.read('manifest.json'))
    mf_changed = False
    bg = manifest.get('background') or {}
    if 'service_worker' in bg:
        manifest.pop('background')
        mf_changed = True
    xpi_path = os.path.join(
        tmp_dir, os.path.splitext(os.path.basename(crx_path))[0] + '.xpi')
    with zipfile.ZipFile(xpi_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            payload = zin.read(item.filename)
            if mf_changed and item.filename == 'manifest.json':
                payload = json.dumps(manifest, ensure_ascii=False).encode()
            zout.writestr(item, payload)
    return xpi_path

def _find_project_driver(name):
    """在项目约定目录里找裸驱动名（与 qt_ui._driver_candidates 的扫描位一致）：
    <cwd>/<驱动名>/<exe> 与 <源码上级>/<驱动名>/<exe>"""
    roots = (os.getcwd(), _path('..'))
    for root in roots:
        for exe in (name, name + '.exe'):
            cand = os.path.join(root, name, exe)
            if os.path.isfile(cand):
                return cand
    return None

def start_browser(browser,driver_path,speed,debug=True):
    # 调试模式关闭时进入无头静默刷课：不显示窗口、不占鼠标键盘
    from task.tool import runtime_flags
    runtime_flags.HEADLESS = not debug
    if runtime_flags.HEADLESS:
        print(color.blue('静默刷课模式（无头浏览器）：不显示窗口，倍速走键盘通道'), flush=True)
    print(color.green('启动浏览器中...'), flush=True)
    if browser == 'chrome':
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
    elif browser == 'firefox':
        from selenium.webdriver.firefox.service import Service
        from selenium.webdriver.firefox.options import Options
    else:
        from selenium.webdriver.edge.service import Service
        from selenium.webdriver.edge.options import Options
    # 创建Driver服务：路径是文件直接用；裸驱动名走系统 PATH 和项目驱动目录
    # （如 学习通刷课/geckodriver/geckodriver）；都找不到则传 None，
    # 交给 Selenium Manager 自动下载/定位（selenium>=4.11）
    if driver_path and not os.path.isfile(driver_path):
        driver_path = (shutil.which(driver_path)
                       or _find_project_driver(driver_path))
    if driver_path and not os.path.isfile(driver_path):
        print(color.yellow(f'驱动 {driver_path} 不存在，改用 Selenium Manager 自动定位'), flush=True)
        driver_path = None
    service = Service(driver_path)
    options = Options()
    if not debug:
        # 无头模式参数：视频自动播放免手势 + 静音 + 大视口防元素点击失败
        if browser == 'firefox':
            options.add_argument('-headless')
            options.add_argument('--window-size=1600,900')
        else:
            options.add_argument('--headless=new')
            options.add_argument('--window-size=1600,900')
            options.add_argument('--mute-audio')
            options.add_argument('--autoplay-policy=no-user-gesture-required')
    if browser != 'firefox':
        options.add_argument("--disable-blink-features=AutomationControlled")  # 禁用自动化控制提示
        if speed!='1':
            options.add_extension(_path('task', 'tool', 'speed.crx'))
        options.add_extension(_path('task', 'tool', 'chrome-extension.crx'))
        options.add_argument("--enable-extensions")
        options.add_argument("--disable-web-security")

    if browser == 'chrome':
        driver = webdriver.Chrome(service=service, options=options)
    elif browser == 'firefox':
        # firefox 不认 Chrome 的 .crx 格式（报 ERROR_CORRUPT_FILE），需剥离
        # CRX 头转成 .xpi；且 Firefox 正式版拒绝未签名扩展的永久安装，
        # 必须 temporary=True（geckodriver 的 profile 本身就是会话级的）
        driver = webdriver.Firefox(service=service, options=options)
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix='xpi_')
        ext_plan = []
        if speed != '1':
            ext_plan.append(('speed.crx', '倍速'))
        ext_plan.append(('chrome-extension.crx', '防暂停'))
        for crx_name, purpose in ext_plan:
            crx = _path('task', 'tool', crx_name)
            if not os.path.isfile(crx):
                continue
            try:
                xpi = _crx_to_xpi(crx, tmpdir)
                driver.install_addon(xpi, temporary=True)
                print(color.green(f'{purpose}扩展安装成功'), flush=True)
            except Exception as e:
                print(color.yellow(f'{purpose}扩展安装失败（{e}），继续运行'), flush=True)
    else:
        # 初始化Edge浏览器
        driver = webdriver.Edge(service=service, options=options)

    driver.implicitly_wait(2)
    return driver

def delete_face_popup(driver,class_name='maskDiv1 chapterVideoFaceQrMaskDiv'):
    try:
        # 等待弹窗容器出现（最长等待10秒）
        popup = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"[class='{class_name}']"))
        )
        # 隐藏弹窗
        # driver.execute_script("arguments[0].style.display='none';", popup)
        driver.execute_script("arguments[0].remove();", popup)
        print(color.green('成功删除人脸弹窗'),flush=True)
    except Exception as e:
        pass

def inject_uxue(driver, speed):
    """注入 uXueScript core.js（无后端模式），由页面内脚本接管整门课程。

    通过伪造 window.__TAURI_INTERNALS__.invoke 接上 Python 侧配置：
    - options 命令返回静音/倍速锁定配置（speed='1' 时不锁定倍速）
    - send_status 命令把章节/任务点进度写入 window.__UXUE_STATUS__ 队列
    同时 hook console.* 把脚本日志写入 window.__UXUE_LOGS__ 供 Python 拉取。
    """
    core_path = _path('task', 'tool', 'uxue_core.js')
    with open(core_path, encoding='utf-8') as f:
        core_js = f.read()
    speed_value = float(speed) if str(speed).replace('.', '', 1).isdigit() else 2.0
    lock_speed = 'true' if str(speed) != '1' else 'false'
    prelude = """
window.__UXUE_STATUS__ = [];
window.__UXUE_LOGS__ = [];
window.confirm = () => true;   // 跳过脚本自带的使用须知弹窗
window.__TAURI_INTERNALS__ = {
  invoke: async (cmd, args) => {
    if (cmd === 'options') {
      return { muteWebview: true, speedLock: %(lock)s, speedValue: %(speed)s };
    }
    if (cmd === 'send_status') {
      const st = (args && args.status) || {};
      window.__UXUE_STATUS__.push(st);
      const p = st.payload || {};
      if (st.kind === 'chapter') {
        console.info('章节进度: ' + (p.title || '') + ' [' + ((p.index || 0) + 1) + '/' + (p.total || 0) + ']');
      } else if (st.kind === 'task') {
        console.info('任务点 #' + ((p.index || 0) + 1) + ' 类别: ' + (p.category || ''));
      } else if (st.kind === 'start') {
        console.info('uXue 注入流程已启动');
      } else if (st.kind === 'finish') {
        console.info('uXue 注入流程：全部章节处理完毕');
      }
      return null;
    }
    return null;   // solve_quiz 等无后端能力：由 core.js 自行跳过 Quiz 任务点
  }
};
(() => {
  const push = (level) => (...a) => {
    try {
      const line = '[' + level + '] ' + a.map(x =>
        (x && typeof x === 'object') ? JSON.stringify(x) : String(x)).join(' ');
      window.__UXUE_LOGS__.push(line);
      if (window.__UXUE_LOGS__.length > 500) {
        window.__UXUE_LOGS__.splice(0, window.__UXUE_LOGS__.length - 500);
      }
    } catch (e) {}
  };
  ['log', 'info', 'warn', 'error'].forEach(l => { console[l] = push(l); });
})();
""" % {'lock': lock_speed, 'speed': speed_value}
    driver.switch_to.default_content()
    driver.execute_script(prelude)
    driver.execute_script(core_js)
    print(color.green('uXueScript core.js 注入成功，页面内脚本已接管课程流程'), flush=True)


def wait_uxue_finished(driver, timeout_hours=6):
    """轮询 uXue 注入脚本的日志与状态队列，直到整课完成/取消/超时。

    返回 True=正常完成；False=取消或超时。
    """
    deadline = time.time() + timeout_hours * 3600
    last_log = time.time()
    while time.time() < deadline:
        try:
            logs = driver.execute_script(
                'return (window.__UXUE_LOGS__ || []).splice(0, 200);') or []
        except WebDriverException:
            # 页面刷新/导航会清空 JS 上下文（注入脚本随之终止）
            print(color.red('页面已刷新/导航，uXue 注入脚本上下文丢失，提前结束'),
                  flush=True)
            return False
        for line in logs:
            print(color.blue(line), flush=True)
        try:
            statuses = driver.execute_script(
                'return (window.__UXUE_STATUS__ || []).splice(0, 50);') or []
        except WebDriverException:
            statuses = []
        for st in statuses:
            kind = st.get('kind')
            if kind == 'finish':
                print(color.green('uXue 注入流程：整门课程处理完成'), flush=True)
                return True
            if kind == 'cancel':
                print(color.yellow('uXue 注入流程已被取消'), flush=True)
                return False
        if logs:
            last_log = time.time()
        elif time.time() - last_log > 300:
            print(color.blue('uXue 注入流程运行中（视频/任务点进行中）...'),
                  flush=True)
            last_log = time.time()
        time.sleep(5)
    print(color.red(f'uXue 注入流程超过 {timeout_hours} 小时仍未完成，提前结束'),
          flush=True)
    return False

def main(browser, driver_path, phone_number, password, choice, course_lst,API,after_finish_question,
         lock_screen,speed, task_type,homework,pass_face,video_title_choice,discussion_choice,
         API_URL='', API_MODEL='', debug=True, uxue_inject=False):
    driver = start_browser(browser, driver_path,speed,debug=debug)
    if not login_study(driver, phone_number, password):
        # 登录失败（含无头模式账密重试 3 次未过）：中止本次刷课
        try:
            driver.quit()
        except Exception:
            pass
        return
    for course_name in course_lst:
        choice_course(driver, course_name, speed,  task_type,phone_number)
        turn_page(driver, course_name)
        experience(driver)
        if uxue_inject:
            # uXueScript 注入模式：页面内脚本自动扫章节树并推进全部任务点
            # （视频播放/倍速锁定/静音、PDF 自动滚动、失焦防暂停守护；
            #   Quiz 任务点无后端能力会自动跳过）
            inject_uxue(driver, speed)
            wait_uxue_finished(driver)
            print(color.yellow('注入模式提示：测验(Quiz)任务点未自动处理，'
                               '如需刷题请关闭注入模式后重跑本课程'), flush=True)
            driver.close()
            turn_page(driver, '个人空间')
            continue
        if pass_face==1:
            with open(rf'task/tool/face_url.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                face_url = data.get(course_name,'')
            check_face(driver,face_url,course_name=course_name)
            check_face(driver,face_url,face_class='maskDiv',course_name=course_name)
        if find_mission(driver,task_type,speed):
            if task_type=='作业':
                do_work(driver,course_name,homework,API,api_url=API_URL,api_model=API_MODEL)
                return
            if task_type=='考试':
                do_exam(driver,course_name,API,mode=homework,api_url=API_URL,api_model=API_MODEL)
                return
            turn_page(driver, '学生学习页面')
            fold(driver)
            pyautogui.hotkey('ctrl', 'm')
            if pass_face==1:
                print(color.green('删除人脸中，请耐心等待...'), flush=True)
                delete_face_popup(driver)
                delete_face_popup(driver,'maskDiv1 starttippop faceRecognition_1 chapterVideoFaceMaskDiv')
            run(driver, choice, course_name, API, lock_screen,pass_face,video_title_choice,discussion_choice,after_finish_question,
                 API_URL, API_MODEL)
        driver.close()
        turn_page(driver, '个人空间')


def extract_browser_versions(error_text):
    """从错误信息中提取浏览器和驱动版本"""

    versions = {
        'driver_supported_version': None,  # 驱动支持的版本
        'browser_version': None,  # 浏览器当前版本
        'browser_type': None  # 浏览器类型
    }

    # 模式1: 匹配ChromeDriver/EdgeDriver支持的版本
    # 兼容两种格式:
    # 1. This version of ChromeDriver only supports Chrome version 140
    # 2. This version of EdgeDriver only supports Microsoft Edge version 120
    driver_pattern = r'This version of (ChromeDriver|Microsoft Edge WebDriver) only supports (?:Chrome|Microsoft Edge) version (\d+)'
    driver_match = re.search(driver_pattern, error_text)

    if driver_match:
        versions['browser_type'] = driver_match.group(1).replace('Driver', '')
        versions['driver_supported_version'] = driver_match.group(2)

    # 模式2: 匹配当前浏览器版本
    # 兼容多种格式:
    # 1. Current browser version is 143.0.7499.193
    # 2. Current Microsoft Edge version is 120.0.2210.91
    browser_pattern = r'Current (?:browser|Microsoft Edge) version is ([\d.]+)'
    browser_match = re.search(browser_pattern, error_text)

    if browser_match:
        versions['browser_version'] = browser_match.group(1)

    return versions

def parse_versions_from_text(error_text):
    """从文本中解析版本信息的完整函数"""

    # 提取版本信息
    versions = extract_browser_versions(error_text)

    # 打印结果
    print(color.red("=" * 50))
    print("版本信息分析结果:")
    print("=" * 50)

    if versions['browser_type']:
        print(f"浏览器类型: {versions['browser_type']}")

    if versions['driver_supported_version']:
        print(f"驱动支持版本: {versions['driver_supported_version']}")

    if versions['browser_version']:
        print(f"浏览器当前版本: {versions['browser_version']}")

    # 给出建议
    print("\n" + "=" * 50)
    print("问题诊断和建议:")
    print("=" * 50)

    if versions['browser_type'] and versions['driver_supported_version'] and versions['browser_version']:
        driver_ver = int(versions['driver_supported_version'])
        browser_main_ver = int(versions['browser_version'].split('.')[0])

        if browser_main_ver > driver_ver:
            print(f"版本不兼容: {versions['browser_type']}浏览器版本(v{browser_main_ver})过高，"
                  f"但驱动仅支持到v{driver_ver}")
            print(f"📋 解决方案:")
            print(f"  1. 下载{versions['browser_type']}Driver {browser_main_ver}的版本")
            print(f"  2. 或降级{versions['browser_type']}浏览器到{driver_ver}版本")
        elif browser_main_ver < driver_ver:
            print(f"⚠️  浏览器版本(v{browser_main_ver})可能过旧")
            print(f"📋 建议: 更新{versions['browser_type']}浏览器到最新版本")
        else:
            print(f"✅ 版本匹配: {versions['browser_type']}浏览器和驱动版本一致")

    print("\n相关下载链接:")
    if versions['browser_type'] == 'Chrome':
        print("  • 谷歌驱动: https://chromedriver.chromium.org/")
        print("  • Chrome浏览器: https://www.google.com/chrome/")
    elif versions['browser_type'] == 'Microsoft Edge Web':
        print("  • Edge驱动: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/")
        print("  • Edge浏览器: https://www.microsoft.com/edge")
    print('\n具体操作步骤见 README 或帮助页面')

    return versions

def run_main():
    try:
        with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as fil:
            account_info = json.load(fil)
        # 浏览器未设置时按平台取默认：Windows→edge，Linux/macOS→firefox
        browser = (account_info.get('browser') or ''
                   or ('edge' if os.name == 'nt' else 'firefox'))
        main(browser, account_info.get('driver_path', ''), account_info['phone_number'], account_info['password'],account_info['choice'],
            account_info['cour'],account_info['API'],account_info['after_finish_question'],account_info['lock_screen'],account_info['speed'],account_info['task_type'],
             account_info['homework'],account_info['pass_face'],account_info['video_title_choice'],account_info['discussion_choice'],
             account_info.get('API_URL',''), account_info.get('API_MODEL',''),
             bool(int(account_info.get('debug_mode', 1))),
             bool(int(account_info.get('uxue_inject', 0))))
    except NoSuchWindowException as e:
        print(color.red('❌ 窗口意外关闭'),flush=True)
    except SessionNotCreatedException as e:
        error_msg = traceback.format_exc()
        send_error(
"\n" + error_msg)
        # 执行分析
        result = parse_versions_from_text(error_msg)

    except WebDriverException as e:
        if 'ERR_INTERNET_DISCONNECTED' in str(e) or 'ERR_NAME_NOT_RESOLVED' in str(e):
            print(color.red('❌ 你网都没连，刷个屁的课啊'),flush=True)
        else:
            print(color.red('❌ 出错了，具体原因请前往错误日志查看'),flush=True)
            with open('error.log', 'a', encoding='utf-8') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' - ERROR: ' + traceback.format_exc() + '\n')
    except PermissionError:
        print(color.red('请关闭该窗口后，再右键点击刷课程序用管理员权限打开'))
    except Exception as e:
        with open('error.log', 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' - ERROR: ' + traceback.format_exc() + '\n')
        print(color.red('❌ 出错了，具体原因请前往错误日志查看'),flush=True)

if __name__ == '__main__':
    run_main()
