# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.
import re
import time
from selenium.webdriver.common.by import By
from task.tool import color
from task.tool.common import Common
def duration_to_fast_forward_count(text):
    """把播放器时长文本换算成「快进十秒」按钮的点击次数。

    时长形如 "1:30" / "1:02:30"；播放器未加载时可能是空串或 "--:--"。
    原实现把分秒直接拼接成整数（10:30 → 1030//10=103 次，实际应为 63 次），
    且空文本/占位符会 IndexError/ValueError 中断整页任务。
    """
    nums = [int(x) for x in re.findall(r'\d+', text or '')]
    if len(nums) >= 3:
        total_seconds = nums[-3] * 3600 + nums[-2] * 60 + nums[-1]
    elif len(nums) == 2:
        total_seconds = nums[0] * 60 + nums[1]
    elif len(nums) == 1:
        total_seconds = nums[0]
    else:
        total_seconds = 0
    return total_seconds // 10


class Audio(Common):
    def __init__(self,driver,iframe_element):
        super().__init__(driver,iframe_element,'音频')
    def start(self):
        self.driver.switch_to.frame(self.iframe)
        play_button = self.driver.find_element(By.CSS_SELECTOR, '[class="vjs-play-control vjs-control vjs-button"]')
        play_button.click()
        vjs_duration = self.driver.find_element(By.CLASS_NAME, "vjs-duration-display")
        print('当前音频时长为{}'.format(vjs_duration.text),flush=True)
        # 计算要点击快进十秒的次数，并只取整数部分
        # 例如：时长为1:30，点击快进十秒的次数为9次
        fast_forward_num = duration_to_fast_forward_count(vjs_duration.text)
        vjs_fast_forward_button = self.driver.find_element(By.ID, "vjs-fast-forward-button")
        for i in range(fast_forward_num):
            vjs_fast_forward_button.click()
            time.sleep(0.1)
        # 检测是否完成播放
        while True:
            try:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(
                    self.driver.find_element(By.CSS_SELECTOR, '[id="iframe"]'))
                if self.check_audio_finished():
                    break
            except Exception:
                # 页面跳转/元素引用失效会让检测抛异常；吞掉本轮继续轮询，
                # 避免异常冒泡中断整页任务
                print(color.red('音频完成状态检测异常，本轮重试'), flush=True)
            time.sleep(1)
def play_audio(driver,iframe_element):
    audio = Audio(driver,iframe_element)
    audio.main()

