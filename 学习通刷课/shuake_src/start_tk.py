# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.
#激活环境start_venv\Scripts\activate
#打包python -m PyInstaller --onefile --noconsole start.py
#python -m PyInstaller --onefile --noconsole --icon=xuexitong.ico start.py
import json
import random
import signal
import time
from datetime import datetime
import re
import threading
import tkinter as tk
import subprocess
from PIL import Image
from colorama import Fore
from tkinter import ttk, messagebox, filedialog
import requests
import os
import native_tk as ctk
import pickle
import logging # For logging
class ToolTip:
    """简单的悬停提示类"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind('<Enter>', self.show_tip)
        self.widget.bind('<Leave>', self.hide_tip)

    def show_tip(self, event=None):
        # 获取鼠标指针的屏幕坐标
        x = self.widget.winfo_pointerx() + 10
        y = self.widget.winfo_pointery() + 10
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        self.tip_window.wm_attributes("-topmost", True)

        label = tk.Label(self.tip_window, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("微软雅黑", 10))
        label.pack()

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

    def set_text(self, new_text):
        """动态修改提示文本"""
        self.text = new_text
# 设置日志配置
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别为 DEBUG，以便捕获更多信息
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("输出记录.log", encoding='utf-8'), # 写入文件
        # logging.StreamHandler(sys.stdout) # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)
class Start:
    def __init__(self):
        self.timer_active = False
        self.timer_end_time = '03:00:00'
        self.timer_start_time = '04:00:00'
        self.dynamic_rows = []
        self.process = None
        self.colorama_to_tkinter = {
            'RED': 'red',
            'YELLOW': 'yellow',
            'BLUE': 'blue',
            'GREEN': 'green',
            'MAGENTA': 'magenta'
        }
        self.color_value_dict={
            '黑白': ['#2F2F2F', '#F7F7F7', '#555555'],
            '清新绿': ['#2E7D32', '#E8F5E9', '#A5D6A7'],
            '暖阳橙': ['#F57C00', '#FFF3E0', '#FFB74D'],
            '淡雅灰': ['#607D8B', '#ECEFF1', '#B0BEC5'],
            '天空湖': ['#00838F', '#E0F7FA', '#80DEEA'],
            '深邃夜': ['#2C3E50', '#ECF0F1', '#BDC3C7'],
            '紫罗兰': ['#6A1B9A', '#F3E5F5', '#CE93D8']}# 颜色值字典[深，浅,中]
        self.font = ("Helvetica", 13)
        self.record_color_lst= ['黑白']

        self.frame_fg_color = self.color_value_dict[self.record_color_lst[0]][1]
        self.button_color = self.color_value_dict[self.record_color_lst[0]][0]
        self.button_hover_color = self.color_value_dict[self.record_color_lst[0]][2]
        self.root = ctk.CTk()
        ctk.set_appearance_mode("light")
        self.root.update_idletasks()
        _w, _h = 880, 660
        _x = max((self.root.winfo_screenwidth() - _w) // 2, 0)
        _y = max((self.root.winfo_screenheight() - _h) // 2, 0)
        self.root.geometry(f"{_w}x{_h}+{_x}+{_y}")  # 居中显示
        with open(r'task/tool/version_info','r',encoding='utf-8') as f:
            version_info=f.read()
            self.root.title(f'学习通刷课 {version_info}')
        # 初始设定窗口置顶
        self.is_topmost = True
        self.root.wm_attributes("-topmost", self.is_topmost)
        self.main_frame =  ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.set_frame =  ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.help_frame =  ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.vido_frame =  ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.score_frame = ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.question_bank_frame=ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.error_frame=  ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.root.resizable(True, True)  # 允许用户调整窗口大小
         # 跨平台窗口图标：Windows 用 iconbitmap(.ico)，Linux/macOS 用 iconphoto(PNG)
        try:
            ico_path = os.path.join(os.getcwd(), 'task', 'img', 'xuexitong1 .ico')
            if os.name == 'nt':
                self.root.iconbitmap(ico_path)
            else:
                img_ico = os.path.join(os.getcwd(), 'task', 'img', 'xuexitong1.png')
                if os.path.isfile(img_ico):
                    _ph = tk.PhotoImage(file=img_ico)
                    self.root.iconphoto(True, _ph)
                elif os.path.isfile(ico_path):
                    # Linux tkinter 无 .ico 支持，跳过
                    pass
        except Exception:
            pass
        self.root.attributes('-alpha', 1)

        # 加载图标
        self.menu_image = ctk.CTkImage(light_image=Image.open(os.path.join("task", "img", "menu.png")), size=(24, 24))
        self.fold_image = ctk.CTkImage(light_image=Image.open(os.path.join("task", "img", "fold.png")), size=(12, 20))
        self.open_image = ctk.CTkImage(light_image=Image.open(os.path.join("task", "img", "open.png")), size=(12, 20))
        self.show_image = ctk.CTkImage(light_image=Image.open(os.path.join("task", "img", "show.png")), size=(16, 12))
        self.add_image  = ctk.CTkImage(light_image=Image.open(os.path.join("task", "img", "add.png")), size=(18, 19))
        self.image_name_list = ['home_dark.png', 'set.png', 'help.png', 'vido.png', 'score.png', 'find.png',
                                'error.png']
        self.image_list = []
        for name in self.image_name_list:
            self.image_list.append(ctk.CTkImage(light_image=Image.open(rf"task/img/{name}"), size=(20, 20)))

        # ----------------创建菜单页面----------------
        self.navigation_frame = ctk.CTkFrame(self.root, corner_radius=0,fg_color=self.button_hover_color,width=20)
        self.navigation_frame.grid(row=0, column=0,rowspan=2, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(9, weight=1)
        #----------------展开页面----------------
        self.open_frame= ctk.CTkFrame(self.root, corner_radius=0,width=0,fg_color=self.frame_fg_color)
        #设置权重
        self.open_frame.grid_rowconfigure(0, weight=1)
        self.open_button = ctk.CTkButton(self.open_frame, corner_radius=0,width=10,height=40, border_spacing=10,
                                                   text="",font=self.font,image=self.open_image,
                                                    fg_color='transparent',
                                                   hover_color=self.button_color, anchor="n",
                                                   command=self.reopen_frame)
        self.open_button.grid(row=0, column=0, sticky="ew")
        # 创建文件菜单并添加选项
        self.navigation_frame_label = ctk.CTkLabel(self.navigation_frame, text="  MENU   ",image=self.menu_image,
                                                             compound="left",fg_color="transparent",
                                                             font=self.font,anchor="nw")
        self.navigation_frame_label.grid(row=0, column=0, pady=20)
        self.fold_button = ctk.CTkButton(self.navigation_frame, corner_radius=0, width=10, height=40, border_spacing=10,
                                         text='收起\n目录', font=self.font, image=self.fold_image,
                                         fg_color="transparent", text_color=("gray10", "gray90"),
                                         hover_color=self.button_color,
                                         anchor="e", command=self.fold_frame)
        self.fold_button.grid(row=9, column=0, sticky="new")
        self.button_text_list = ["主页","设置","帮助","刷课日志","测试成绩","题库查询","报错日志"]
        self.button_command_list = [self.show_main, self.show_set, self.show_help, lambda:self.show_record('刷课'), lambda:self.show_record('成绩'), self.show_question_bank, self.show_error]
        self.button_name_list = ['home_button','set_button','help_button','vido_button','score_button','question_bank_button','error_button',self.open_button,self.fold_button]
        for i in range(len(self.button_text_list)):
            self.button_name_list[i] = ctk.CTkButton(self.navigation_frame, corner_radius=10,width=20,height=40, border_spacing=10,
                                                   text=self.button_text_list[i],font=self.font,image=self.image_list[i],
                                                   fg_color="transparent", text_color='black',
                                                   hover_color=self.button_color, anchor="w",
                                                    command=self.button_command_list[i])
            self.button_name_list[i].grid(row=i+1, column=0,padx=8, pady=3,sticky="ew")
        #----------------标签页----------------
        self.label_frame=ctk.CTkFrame(self.root,fg_color=self.frame_fg_color,corner_radius=0)
        self.label_frame.grid(row=0,column=1,sticky='nsew')
        self.frame_name_list=[self.main_frame,self.set_frame,self.help_frame,self.vido_frame,
                              self.score_frame,self.question_bank_frame,self.error_frame,
                              self.open_frame,self.navigation_frame,self.label_frame]
        #  当前时间显示
        self.time_label = ctk.CTkLabel(self.label_frame, text="", fg_color='transparent', font=self.font)
        self.time_label.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)

        # ---------------- 主页 ----------------
        # 启动程序按钮
        self.start_button = ctk.CTkButton(self.main_frame, text="▶ 开始刷课",height=40, border_spacing=10,fg_color=self.button_color,
                                          command=self.start, font=self.font,hover_color=self.button_hover_color)
        self.start_button.grid(row=0, column=0,padx=5, pady=10)
        # 定时刷课按钮
        self.timer_button = ctk.CTkButton(self.main_frame, text="⏰ 定时刷课", height=40, border_spacing=10,
                                          fg_color=self.button_color,
                                          command=self.open_timer_window, font=self.font,
                                          hover_color=self.button_hover_color)
        self.timer_button.grid(row=0, column=1, padx=5, pady=10)
        # 关闭程序按钮
        self.close_button = ctk.CTkButton(self.main_frame, text="■ 结束刷课",height=40, border_spacing=10,fg_color=self.button_color, hover_color=self.button_hover_color,
                                          command=self.close,font=self.font)
        # self.close_button.grid(row=0, column=1,padx=5,  pady=10)
        # 创建只读文本框#202022
        self.text_box = ctk.CTkTextbox(self.main_frame,
                                       fg_color='transparent',
                                       height=24 * 20,  # CTkTextbox 使用像素单位
                                       width=40 * 10,  # 需要根据字符宽度估算
                                       font=self.font)
        self.text_box.insert(tk.INSERT, 'WELCOME TO 学习通刷课 ！！！\n请先进入设置页面填写信息！！！')

        # 配置标签样式
        self.text_box.tag_config("center", justify='center')
        self.text_box.tag_add("center", "1.0", "end")
        self.text_box.tag_config("red", foreground="red")
        self.text_box.tag_add("red", "1.0", "end")

        # CTkTextbox 需要额外设置边框颜色（可选）
        self.text_box.configure(border_color='gray', border_width=1)
        self.text_box.configure( state=tk.DISABLED)
        self.text_box.grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky=tk.W+tk.E+tk.N+tk.S)

        # ---------------- 刷课记录 ----------------
        # 下拉选项框（包含可输入部分）
        self.course_vido_entry = ctk.CTkComboBox(self.vido_frame, dropdown_font=self.font, values=[],
                                                 dropdown_fg_color=self.frame_fg_color,
                                                 button_color=self.button_color,
                                                 button_hover_color=self.button_hover_color,
                                                 dropdown_hover_color=self.button_color,
                                                 font=self.font, command=lambda value:self.show_record('刷课'))
        # self.course_vido_entry['state'] = 'normal'
        self.course_name = self.course_vido_entry.get()
        self.course_vido_entry.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W + tk.E)  # 使用 sticky 参数使组件填满整个单元格
        # 按钮
        self.find_button1 = ctk.CTkButton(self.vido_frame, text="查询", command=lambda:self.show_record('刷课'), fg_color=self.button_color,
                                          font=self.font, hover_color=self.button_hover_color)
        self.find_button1.grid(row=0, column=1, padx=1, pady=5, sticky=tk.W)  # 使用 sticky 参数使组件填满整个单元格
        self.delete_button1 = ctk.CTkButton(self.vido_frame, text="删除记录",
                                            command=lambda: self.delete_record('刷课'), fg_color="#F87171", hover_color="#EF4444",
                                            font=self.font)
        self.delete_button1.grid(row=0, column=2, padx=1, pady=5)
        # 配置按钮框架的列权重，使按钮居中
        self.score_frame.rowconfigure(0, weight=1)
        # self.score_frame.columnconfigure(1, weight=1)
        #创建只读文本框
        self.vido_text = ctk.CTkTextbox(self.vido_frame, height=527, width=435,font=self.font,fg_color='transparent')
        self.vido_text.configure(state=tk.DISABLED)
        self.vido_text.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky=tk.W+tk.E+tk.N+tk.S)

        # ---------------- 成绩日志 ----------------
        # 下拉选项框（包含可输入部分）
        self.course_score_entry = ctk.CTkComboBox(self.score_frame, dropdown_font=self.font, font=self.font, values=[],
                                                  dropdown_fg_color=self.frame_fg_color,
                                                  button_color=self.button_color,
                                                  button_hover_color=self.button_hover_color,
                                                  dropdown_hover_color=self.button_color,
                                                  command=lambda value:self.show_record('成绩'))

        # self.course_score_entry['state'] = 'normal'
        self.course_name=self.course_score_entry.get()
        self.course_score_entry.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W+tk.E)  # 使用 sticky 参数使组件填满整个单元格
        # 按钮
        self.find_button2 = ctk.CTkButton(self.score_frame, text="查询", command=lambda:self.show_record('成绩'), fg_color=self.button_color,
                                          font=self.font, hover_color=self.button_hover_color)
        self.find_button2.grid(row=0, column=1, padx=1, pady=5)  # 使用 sticky 参数使组件填满整个单元格
        self.delete_button2=ctk.CTkButton(self.score_frame, text="删除记录", command=lambda: self.delete_record('成绩'), fg_color="#F87171", hover_color="#EF4444",
                                          font=self.font)
        self.delete_button2.grid(row=0, column=2, padx=1, pady=5)
        # 配置按钮框架的列权重，使按钮居中
        self.score_frame.rowconfigure(0, weight=1)
        # self.score_frame.columnconfigure(1, weight=1)
        # 创建只读文本框
        self.score_txt = ctk.CTkTextbox(self.score_frame,height=527,width=435,font=self.font,fg_color='transparent')
        self.score_txt.configure(state=tk.DISABLED)
        self.score_txt.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky=tk.W+tk.E+tk.N+tk.S)  # 使用 sticky 参数使组件填满整个单元格
        self.dit={'刷课':[self.course_vido_entry,'刷课日志',self.vido_text,self.vido_frame],'成绩':[self.course_score_entry,'测试成绩',self.score_txt,self.score_frame]}

        # ---------------- 题库查询 ----------------
        self.tiku_text = ctk.CTkTextbox(self.question_bank_frame, height=600, width=437,font=self.font,fg_color='transparent')
        self.tiku_text.configure(state=tk.DISABLED)
        self.tiku_text.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky=tk.W+tk.E+tk.N+tk.S)
        self.delete_tiku_button = ctk.CTkButton(
            self.question_bank_frame, text="删除所有缓存题目", command=self.delete_huancun,
            fg_color="#F87171", hover_color="#EF4444", corner_radius=16, height=36
        )
        self.delete_tiku_button.grid(row=2, column=0, padx=1, pady=5,columnspan=2,sticky=tk.W+tk.E)

        # ---------------- 设置 ----------------
        # ========== 设置页面（改用CTkFrame模拟分组） ==========
        # 配置设置组
        self.style = ttk.Style()
        self.style.configure('TLabelframe', background=self.frame_fg_color, borderwidth=10)
        self.style.configure('TLabelframe.Label', background=self.frame_fg_color, font=self.font)
        self.style.configure('TLabel', background=self.frame_fg_color)
        self.configuration_set_frame = ctk.CTkFrame(self.set_frame, corner_radius=12, border_width=1,
                                                    fg_color='transparent',
                                                    border_color="#CBD5E1")
        self.configuration_set_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        lbl_cfg = ctk.CTkLabel(self.configuration_set_frame, text="⚙ 配置设置", font=("Microsoft YaHei", 13, "bold"))
        lbl_cfg.grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 4))

        ctk.CTkLabel(self.configuration_set_frame, text="浏览器:", font=self.font).grid(row=1, column=0, padx=6,
                                                                                        pady=4, sticky="w")
        self.browser_entry = ctk.CTkComboBox(
            self.configuration_set_frame, values=['edge', 'chrome', 'firefox'],
            state='readonly', font=self.font, corner_radius=6, dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,command=self.auto_fill_browser_driver,
            button_color=self.button_color, button_hover_color=self.button_hover_color
        )
        self.browser_entry.grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(self.configuration_set_frame, text="驱动地址:", font=self.font).grid(row=2, column=0, padx=6,
                                                                                          pady=4, sticky="w")
        self.browser_driver_entry = ctk.CTkEntry(self.configuration_set_frame, corner_radius=6, width=140)
        self.browser_driver_entry.grid(row=2, column=1, padx=6, pady=4, sticky="w")
        self.open_file_button = ctk.CTkButton(
            self.configuration_set_frame, text="选择文件", width=120,
            fg_color=self.button_color, hover_color=self.button_hover_color, corner_radius=6,
            command=self.select_file
        )
        self.open_file_button.grid(row=3, column=1, padx=6, pady=4, sticky="w")

        # 界面设置组
        self.frame_set_frame = ctk.CTkFrame(self.set_frame, corner_radius=12, border_width=1, fg_color='transparent',
                                            border_color="#CBD5E1")
        self.frame_set_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        lbl_ui = ctk.CTkLabel(self.frame_set_frame, text="🎨 界面设置", font=("Microsoft YaHei", 13, "bold"))
        lbl_ui.grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 4))

        ctk.CTkLabel(self.frame_set_frame, text="字体设置:", font=self.font).grid(row=1, column=0, padx=6, pady=4,
                                                                              sticky="w")
        self.font_entry = ctk.CTkComboBox(
            self.frame_set_frame, values=["Helvetica", "Microsoft YaHei",'微软雅黑', '宋体', '楷体', '黑体'],dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            state='readonly', font=self.font, corner_radius=6,
            button_color=self.button_color, button_hover_color=self.button_hover_color
        )
        self.font_entry.grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(self.frame_set_frame, text="大小设置:", font=self.font).grid(row=2, column=0, padx=6, pady=4,
                                                                              sticky="w")
        self.size_entry = ctk.CTkComboBox(
            self.frame_set_frame, values=['9', '10', '11', '12', '13', '14', '15', '16'], dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            state='readonly', font=self.font, corner_radius=6,
            button_color=self.button_color, button_hover_color=self.button_hover_color
        )
        self.size_entry.grid(row=2, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(self.frame_set_frame, text="窗口置顶:", font=self.font).grid(row=3, column=0, padx=12, pady=4,
                                                                                  sticky="w")
        self.topmost_check = ctk.CTkSwitch(self.frame_set_frame, text="", command=self.toggle_topmost)
        self.topmost_check.grid(row=3, column=1, padx=6, pady=4, sticky="w")
        self.topmost_check.select()

        # 信息设置组
        self.message_set_frame = ctk.CTkFrame(self.set_frame, corner_radius=12, border_width=1, fg_color='transparent',
                                              border_color="#CBD5E1")
        self.message_set_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)
        lbl_info = ctk.CTkLabel(self.message_set_frame, text="🔐 账号信息", font=("Microsoft YaHei", 13, "bold"))
        lbl_info.grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 4))

        ctk.CTkLabel(self.message_set_frame, text="账号:", font=self.font).grid(row=1, column=0, padx=6, pady=4,
                                                                                sticky="w")
        self.phone_number_entry = ctk.CTkEntry(self.message_set_frame, corner_radius=6, width=140)
        self.phone_number_entry.grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(self.message_set_frame, text="密码:", font=self.font).grid(row=2, column=0, padx=6, pady=4,
                                                                                sticky="w")
        self.password_entry = ctk.CTkEntry(self.message_set_frame, show='*', corner_radius=6, width=140,)
        self.password_entry.grid(row=2, column=1, padx=(6,0), pady=4, sticky="w")
        self.show_password_button = ctk.CTkButton(self.message_set_frame, text="", fg_color='transparent',
                                                  image=self.show_image,
                                                  command=self.show_password, font=self.font, width=5, height=10)
        self.show_password_button.grid(row=2, column=2,padx=0, pady=4, sticky=tk.E)
        ctk.CTkLabel(self.message_set_frame, text="课程名称:", font=self.font).grid(row=3, column=0, padx=6, pady=4,
                                                                                    sticky="w")
        self.cour_entry = ctk.CTkComboBox(
            self.message_set_frame, values=[], state='normal',dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            font=self.font, corner_radius=6, button_color=self.button_color
        )
        self.cour_entry.grid(row=3, column=1, padx=6, pady=4, sticky="w")
        self.next_row = 4
        self.add_course_button = ctk.CTkButton(self.message_set_frame, text="", fg_color='transparent',
                                                  image=self.add_image,
                                                  command=lambda: self.add_course(''), width=5, height=5)
        self.add_course_button.grid(row=3, column=2, padx=1, pady=4, sticky=tk.E)
        ToolTip(self.add_course_button, "添加课程")

        # 功能设置组（右侧大区域）
        self.function_set_frame = ctk.CTkFrame(self.set_frame, corner_radius=12, border_width=1, fg_color='transparent',
                                               border_color="#CBD5E1")
        self.function_set_frame.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        lbl_func = ctk.CTkLabel(self.function_set_frame, text="🚀 功能设置", font=("Microsoft YaHei", 13, "bold"))
        lbl_func.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 4))

        self.radio_var = tk.IntVar(value=1)
        self.radio_button_1 = ctk.CTkRadioButton(
            self.function_set_frame, text="自动刷课答题", variable=self.radio_var, value=1,
            command=self.function_choice, font=self.font
        )
        self.radio_button_2 = ctk.CTkRadioButton(
            self.function_set_frame, text="自动完成作业", variable=self.radio_var, value=2,
            command=self.function_choice, font=self.font
        )
        self.radio_button_3 = ctk.CTkRadioButton(
            self.function_set_frame, text="自动完成考试", variable=self.radio_var, value=3,
            command=self.function_choice, font=self.font
        )
        self.radio_button_1.grid(row=1, column=1, columnspan=3, padx=12, pady=6, sticky="w")
        self.radio_button_2.grid(row=2, column=1, columnspan=3, padx=12, pady=6, sticky="w")
        self.radio_button_3.grid(row=3, column=1, columnspan=3, padx=12, pady=6, sticky="w")

        # 高级设置组（右侧大区域）
        self.pady=7
        self.detail_set_frame = ctk.CTkFrame(self.set_frame, corner_radius=12, border_width=1, fg_color='transparent',
                                             border_color="#CBD5E1")
        self.detail_set_frame.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=6, pady=6)
        lbl_func = ctk.CTkLabel(self.detail_set_frame, text="🔧 高级设置", font=("Microsoft YaHei", 13, "bold"))
        lbl_func.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 4))
        # 后续控件动态添加，保持原有变量名
        self.question_label = ctk.CTkLabel(self.detail_set_frame, text="章节测验:", font=self.font)
        self.question_entry = ctk.CTkComboBox(
            self.detail_set_frame, values=["AI 智能答题", '随机答题', "不刷题"],dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            font=self.font, corner_radius=6, state='readonly',
            button_color=self.button_color, command=self.shua_ti_choice
        )
        #答完题后
        self.after_finish_question=ctk.CTkLabel(self.detail_set_frame, text="答完题后:", font=self.font)
        self.after_finish_question_entry = ctk.CTkComboBox(self.detail_set_frame, values=["仅自动保存", '强制自动提交',
        '搜到60%的题自动提交','搜到70%的题自动提交','搜到80%的题自动提交','搜到90%的题自动提交',  '搜到100%的题自动提交'], dropdown_fg_color=self.frame_fg_color,
                                                           dropdown_hover_color=self.button_color,
                                                           font=self.font, corner_radius=6, state='readonly',
                                                           button_color=self.button_color
                                                           )
        self.vido_question_label = ctk.CTkLabel(self.detail_set_frame, text="视频题目:", font=self.font)
        self.vido_question_entry = ctk.CTkComboBox(
            self.detail_set_frame, values=["AI 智能答题", '随机答题'],dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            font=self.font, corner_radius=6, state='readonly',
            button_color=self.button_color, command=lambda _: self.shua_ti_choice('视频题目')
        )
        self.discussion_label = ctk.CTkLabel(self.detail_set_frame, text="讨论:", font=self.font)
        self.discussion_entry = ctk.CTkComboBox(
            self.detail_set_frame, values=["AI 智能答题", '跳过讨论'],dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            font=self.font, corner_radius=6, state='readonly',
            button_color=self.button_color, command=lambda _: self.shua_ti_choice('讨论')
        )
        self.speed_label = ctk.CTkLabel(self.detail_set_frame, text="倍速设置:", font=self.font)
        self.speed_entry = ctk.CTkComboBox(
            self.detail_set_frame, values=['1', '2', '3', '4', '5', '6', '8', '10', '16'],dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            font=self.font, corner_radius=6, state='readonly', command=self.hint,
            button_color=self.button_color
        )
        self.API_label = ctk.CTkLabel(self.detail_set_frame, text="API Key:", font=self.font)
        self.API_entry = ctk.CTkEntry(self.detail_set_frame, show='*', corner_radius=6)
        ToolTip(self.API_entry, "填写你的 API Key，支持任意 OpenAI 兼容接口")
        self.show_api_button = ctk.CTkButton(self.detail_set_frame, text="", fg_color='transparent',
                                             image=self.show_image,
                                             command=self.show_api, font=self.font, width=5, height=10)
        self.API_URL_label = ctk.CTkLabel(self.detail_set_frame, text="API 地址:", font=self.font)
        self.API_URL_entry = ctk.CTkEntry(self.detail_set_frame, corner_radius=6)
        ToolTip(self.API_URL_entry, "API 接口地址，留空则使用默认 https://api.deepseek.com/")
        self.API_MODEL_label = ctk.CTkLabel(self.detail_set_frame, text="模型名:", font=self.font)
        self.API_MODEL_entry = ctk.CTkEntry(self.detail_set_frame, corner_radius=6)
        ToolTip(self.API_MODEL_entry, "可选，留空则根据 API 接口自动获取模型")
        self.pass_face_label = ctk.CTkLabel(self.detail_set_frame, text="跳过人脸:", font=self.font)
        self.pass_face_check = ctk.CTkSwitch(self.detail_set_frame, text="")
        ToolTip(self.pass_face_check, "只有当你的课程需要人脸认证时才开启")
        self.lock_screen_label = ctk.CTkLabel(self.detail_set_frame, text="防锁屏:", font=self.font)
        self.lock_screen_check = ctk.CTkSwitch(self.detail_set_frame, text="")
        self.homework_label = ctk.CTkLabel(self.detail_set_frame, text="选择作业:", font=self.font)
        self.homework_entry = ctk.CTkComboBox(
            self.detail_set_frame, values=['手动选择', '自动选择'],dropdown_fg_color=self.frame_fg_color,
                                           dropdown_hover_color=self.button_color,
            state='readonly', font=self.font, corner_radius=6, command=self.prompt,
            button_color=self.button_color
        )
        # 保存按钮
        self.save_button = ctk.CTkButton(
            self.set_frame, text="💾 保存设置", command=self.save,
            font=("Microsoft YaHei", 13, "bold"), height=40, corner_radius=20,
            fg_color=self.button_color,
            hover_color=self.button_hover_color)
        self.save_button.grid(row=3, column=0, columnspan=2, pady=20, padx=12)

        #设置网格权重
        self.set_frame.rowconfigure(3,weight=1)
        self.frame_set_frame.rowconfigure(3,weight=1)
        self.combobox_lst = [
            self.speed_entry, self.question_entry, self.cour_entry,
            self.size_entry, self.homework_entry, self.font_entry, self.browser_entry,
            self.course_score_entry, self.course_vido_entry, self.vido_question_entry,
            self.discussion_entry,self.after_finish_question_entry
        ]
        self.check_switch=[self.topmost_check,self.pass_face_check,self.lock_screen_check]
        self.button_name_list1=[self.start_button,self.timer_button, self.close_button, self.save_button,
                                self.open_file_button, self.find_button1, self.find_button2,self.delete_button1,self.delete_button2]

        #----------------帮助页面----------------
        with open(r'task/tool/Help.txt', 'r', encoding='utf-8') as f:
            self.text = f.read()
        self.help_txt = ctk.CTkTextbox(self.help_frame,height=600,width=500,font=self.font,fg_color='transparent')
        self.help_txt.grid(pady=20)
        self.help_txt.insert(tk.END, self.text)
        self.help_txt.configure(state=tk.DISABLED)


        #----------------报错日志----------------
        self.error_text = ctk.CTkTextbox(self.error_frame, height=600, width=497,font=self.font,fg_color='transparent')
        self.error_text.configure(state=tk.DISABLED)
        self.error_text.grid(pady=20)

        # 更新时间显示
        self.process_condition=False
        self.update_time()
        self.load_data()
        self.show_main()
        self.function_choice()
        if self.timer_active:
            self.text_box.configure(state=tk.NORMAL)
            self.text_box.insert(tk.END,
                                 f"\n定时刷课已开启:\n  开始时间: {self.timer_start_time}\n  "
                                 f"结束时间: {self.timer_end_time}\n"
                                 f"请勿关闭此窗口，否则定时刷课将无法正常开启")
    def add_course(self, cour_name):
        """添加课程"""
        row = self.next_row
        self.next_row += 1
        if row>=6:
            tk.messagebox.showwarning('警告', '最多只能添加3门课程')
            self.next_row -=1
            return
        cour_entry = ctk.CTkComboBox(
            self.message_set_frame, values=self.data, state='normal', dropdown_fg_color=self.frame_fg_color,
            dropdown_hover_color=self.button_color,
            font=self.font, corner_radius=6, button_color=self.button_color
        )
        cour_entry.set(cour_name)
        cour_entry.grid(row=row, column=1, padx=6, pady=4, sticky="w")
        # 删除按钮（可选，便于移除该行）
        del_btn = ctk.CTkButton(
            self.message_set_frame, text="✖", width=20,
            fg_color="#F87171", hover_color="#EF4444",
                command=lambda: self.delete_course_row(cour_entry, del_btn, row)
        )
        del_btn.grid(row=row, column=2, padx=2, pady=4, sticky=tk.W)
        # 为这个删除按钮创建独立的 ToolTip 实例
        tip = ToolTip(del_btn, "删除该课程")
        self.dynamic_rows.append((cour_entry, del_btn, row, tip))
        # 当添加到第三门课程（row=5）时，禁用上一门课程的删除按钮并修改提示
        if row == 5 and len(self.dynamic_rows) >= 2:
            prev_entry, prev_del_btn, prev_row, prev_tip = self.dynamic_rows[-2]
            prev_del_btn.configure(state='disabled')
            prev_tip.set_text("请先删除最后一个课程")

    def delete_course_row(self, entry, del_btn, row):
        """删除指定的动态行"""
        entry.destroy()
        del_btn.destroy()
        # 从列表中移除（根据 entry 识别）
        for i, (e, d, r, tip) in enumerate(self.dynamic_rows):
            if e == entry:
                self.dynamic_rows.pop(i)
                break
        self.next_row -= 1
        # 删除后，如果 next_row 回到 5（即删除了第三门，只剩两门），恢复第二门删除按钮的可用状态及提示
        if self.next_row == 5 and len(self.dynamic_rows) >= 1:
            # 找到当前最后一门（原第二门）的删除按钮和提示
            last_entry, last_del_btn, last_row, last_tip = self.dynamic_rows[-1]
            last_del_btn.configure(state='normal')
            last_tip.set_text("删除该课程")

    def delete_record(self, file_name):
        #验证文件是否存在
        file_path = fr'task/record/《{self.dit[file_name][0].get()}》的{file_name}记录.txt'
        # 验证文件是否存在
        if os.path.exists(file_path):
            yes_no=tk.messagebox.askyesno('确认','确定要删除吗？删除后无法恢复')
            if yes_no:
                os.remove(file_path)
                tk.messagebox.showinfo('提示', f'{file_name}记录文件已成功删除')
        else:
            tk.messagebox.showwarning('警告', f'指定的{file_name}记录文件不存在')
        self.show_record(file_name)

    def delete_huancun(self):
        try:
            # 检索所有pkl文件
            folder_path = r'task/record'
            tiku_files = [f for f in os.listdir(folder_path)
                          if f.endswith('.pkl') and os.path.isfile(os.path.join(folder_path, f))]
            for tiku_file in tiku_files:
                os.remove(os.path.join(folder_path, tiku_file))
            tk.messagebox.showinfo('提示', f'缓存记录文件已成功删除')

        except:
            tk.messagebox.showwarning('警告', f'删除失败')
        self.show_question_bank()

    def prompt(self,choice):
        """提示用户"""
        if choice=='自动选择':
            tk.messagebox.showinfo('提示', '默认会从第一个未完成的作业开始刷，刷完后只会自动保存不会提交，保存后自动开始刷下一个作业')
        else:
            tk.messagebox.showinfo('提示', '到达作业页面后请手动选择您要刷的作业，刷完后只会自动保存，请确认后手动提交')

    def auto_fill_browser_driver(self, choice):
        """处理浏览器选择变化，自动填充对应的驱动路径"""
        # 清空当前驱动路径
        self.browser_driver_entry.configure(state='normal')
        self.browser_driver_entry.delete(0, tk.END)

        # 根据选择的浏览器自动填充对应的驱动路径
        # Linux/macOS: 直接填系统驱动名（依赖 PATH 中已安装的对应驱动）
        # Windows: 仍填 exe 路径
        if os.name == "nt":
            drv = {
                "edge": r"edgedriver_win64\msedgedriver.exe",
                "chrome": r"chromedriver\chromedriver.exe",
                "firefox": r"geckodriver\geckodriver.exe",
            }[choice]
        else:
            drv = {"edge": "msedgedriver", "chrome": "chromedriver",
                   "firefox": "geckodriver"}[choice]
        self.browser_driver_entry.insert(0, drv)

    def show_password(self):
        if self.password_entry.cget('show') == '*':
            self.password_entry.configure(show='')
        else:
            self.password_entry.configure(show='*')

    def show_api(self):
        if self.API_entry.cget('show') == '*':
            self.API_entry.configure(show='')
        else:
            self.API_entry.configure(show='*')

    def function_choice(self):
        if self.radio_var.get()==1 :
            self.question_label.configure(text='章节测验')
            self.question_label.grid(row=4, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.question_entry.grid(row=4, column=2, padx=5, pady=self.pady, sticky=tk.W)
            if self.question_entry.get()=='AI 智能答题':
                self.after_finish_question.grid(row=5, column=1, padx=5, pady=self.pady, sticky=tk.W)
                self.after_finish_question_entry.grid(row=5, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.after_finish_question_entry.configure(values=["仅自动保存", '强制自动提交',
        '搜到60%的题自动提交','搜到70%的题自动提交','搜到80%的题自动提交','搜到90%的题自动提交',  '搜到100%的题自动提交'])
            self.vido_question_label.grid(row=6, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.vido_question_entry.grid(row=6, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.discussion_label.grid(row=7, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.discussion_entry.grid(row=7, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.question_entry.configure(values=['AI 智能答题','随机答题','不刷题'])
            if self.question_entry.get()=='AI 智能答题' or self.vido_question_entry.get()=='AI 智能答题' or self.discussion_entry.get()=='AI 智能答题':
                self.API_label.grid(row=8, column=1, padx=5, pady=self.pady, sticky=tk.W)
                self.API_entry.grid(row=8, column=2, padx=5, pady=self.pady, sticky=tk.W)
                self.show_api_button.grid(row=8, column=3, pady=self.pady, sticky=tk.W)
                self.API_URL_label.grid(row=9, column=1, padx=5, pady=self.pady, sticky=tk.W)
                self.API_URL_entry.grid(row=9, column=2, padx=5, pady=self.pady, sticky=tk.W)
                self.API_MODEL_label.grid(row=10, column=1, padx=5, pady=self.pady, sticky=tk.W)
                self.API_MODEL_entry.grid(row=10, column=2, padx=5, pady=self.pady, sticky=tk.W)
            else:
                self.API_URL_label.grid_forget()
                self.API_URL_entry.grid_forget()
                self.API_MODEL_label.grid_forget()
                self.API_MODEL_entry.grid_forget()
            self.speed_label.grid(row=11, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.speed_entry.grid(row=11, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.pass_face_label.grid(row=12, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.pass_face_check.grid(row=12, column=2, sticky=tk.W)
            self.lock_screen_label.grid(row=13, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.lock_screen_check.grid(row=13, column=2, sticky=tk.W)
            self.homework_label.grid_forget()
            self.homework_entry.grid_forget()

        elif self.radio_var.get()==2:
            self.question_label.configure(text='作业答题')
            self.question_label.grid(row=4, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.question_entry.grid(row=4, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.question_entry.set('AI 智能答题')
            self.question_entry.configure(values=['AI 智能答题'])
            self.after_finish_question.grid(row=5, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.after_finish_question_entry.grid(row=5, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.after_finish_question_entry.set('仅自动保存')
            self.after_finish_question_entry.configure(values=['仅自动保存'])
            self.API_label.grid(row=7, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.API_entry.grid(row=7, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.show_api_button.grid(row=7, column=3, pady=self.pady, sticky=tk.W)
            self.API_URL_label.grid(row=8, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.API_URL_entry.grid(row=8, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.API_MODEL_label.grid(row=9, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.API_MODEL_entry.grid(row=9, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.homework_label.grid(row=11, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.homework_entry.grid(row=11, column=2, padx=5, pady=self.pady, sticky=tk.W)
            self.speed_label.grid_forget()
            self.speed_entry.grid_forget()
            self.lock_screen_label.grid_forget()
            self.lock_screen_check.grid_forget()
            self.vido_question_label.grid_forget()
            self.vido_question_entry.grid_forget()
            self.discussion_label.grid_forget()
            self.discussion_entry.grid_forget()
        else:
            tk.messagebox.showinfo('提示', '该功能还在开发中...,敬请期待')
            self.radio_var.set(1)
            self.function_choice()

    def shua_ti_choice(self, event):
        if self.question_entry.get() == '随机答题' and event != '视频题目' and event!='讨论':
            tk.messagebox.showinfo('提示',
                                   '请谨慎选择，只有在章节测验不计入总成绩的情况下才能使用，否则因此挂科了请自行承担后果！！！')
        if self.question_entry.get()!='AI 智能答题':
            self.after_finish_question.grid_forget()
            self.after_finish_question_entry.grid_forget()
        else:
            self.after_finish_question.grid(row=5, column=1, padx=5, pady=self.pady, sticky=tk.W)
            self.after_finish_question_entry.grid(row=5, column=2, padx=5, pady=self.pady, sticky=tk.W)
        if self.vido_question_entry.get()=='AI 智能答题' or self.question_entry.get()=='AI 智能答题' or self.discussion_entry.get()=='AI 智能答题':
            if self.vido_question_entry.get()=='AI 智能答题' and event=='视频题目':
                tk.messagebox.showinfo('提示','这个是用于完成视频中弹出的题目，'
                                              '只有在选错答案会回退视频的情况下才建议使用AI智能答题，一般情况请使用随机答题,没有任何影响')
            self.API_label.grid(row=8, column=1, padx=5, pady=5, sticky=tk.W)
            self.API_entry.grid(row=8, column=2, padx=5, pady=5, sticky=tk.W)
            self.show_api_button.grid(row=8, column=3,  pady=5, sticky=tk.W)
            self.API_URL_label.grid(row=9, column=1, padx=5, pady=5, sticky=tk.W)
            self.API_URL_entry.grid(row=9, column=2, padx=5, pady=5, sticky=tk.W)
            self.API_MODEL_label.grid(row=10, column=1, padx=5, pady=5, sticky=tk.W)
            self.API_MODEL_entry.grid(row=10, column=2, padx=5, pady=5, sticky=tk.W)
        else:
            if self.vido_question_entry.get()!='AI 智能答题' and self.question_entry.get()!='AI 智能答题' and self.discussion_entry.get()!='AI 智能答题':
                self.API_label.grid_forget()
                self.API_entry.grid_forget()
                self.show_api_button.grid_forget()
                self.API_URL_label.grid_forget()
                self.API_URL_entry.grid_forget()
                self.API_MODEL_label.grid_forget()
                self.API_MODEL_entry.grid_forget()

    def select_frame_by_name(self, name):
        # set button color for selected button
            for i in range(len(self.button_name_list)-2):
                txt = self.button_text_list[i]
                self.button_name_list[i].configure(fg_color=self.button_color if name == txt else "transparent")

    def toggle_topmost(self):
        """切换窗口始终置顶属性：勾选 = 置顶开启"""
        if self.topmost_check.get():
            self.is_topmost = True
            self.root.wm_attributes("-topmost", True)
        else:
            self.is_topmost = False
            self.root.wm_attributes("-topmost", False)

    def show_frame(self, frame):
        for f in self.frame_name_list[:8]:
            if f != frame:
                f.grid_forget()
            else:
                f.grid(row=1, column=1,sticky='nsew')

    def show_main(self):
        self.select_frame_by_name('主页')
        self.show_frame(self.main_frame)

    def show_record(self, name):
        self.select_frame_by_name(self.dit[name][1])
        self.dit[name][2].configure(state=tk.NORMAL)
        self.dit[name][2].delete('1.0', tk.END)
        try:
            with open(fr'task/record/《{self.dit[name][0].get()}》的{name}记录.txt', 'r', encoding='utf-8') as f:
                content = f.read()
                self.dit[name][2].insert(tk.END, content)
        except FileNotFoundError:
            self.dit[name][2].insert(tk.END, f'暂未查询到《{self.dit[name][0].get()}》的{name}记录')
        self.show_frame(self.dit[name][3])
        self.dit[name][2].configure(state=tk.DISABLED)

    def show_question_bank(self,*key):
        self.select_frame_by_name('题库查询')
        self.tiku_text.configure(state=tk.NORMAL)
        self.tiku_text.delete('1.0', tk.END)
        try:
            # 检索所有pkl文件
            folder_path = r'task/record'
            tiku_files = [f for f in os.listdir(folder_path)
                          if f.endswith('.pkl') and os.path.isfile(os.path.join(folder_path, f))]
            tiku_txt = ''
            for tiku_file in tiku_files:
                if 'ques1' not in tiku_file:
                    continue
                tiku_file_path = os.path.join(folder_path, tiku_file)
                tiku_txt += "问题:  " + pickle.load(open(tiku_file_path, 'rb'))['value']['question'] + '\n'
                tiku_txt += str(pickle.load(open(tiku_file_path, 'rb'))['value']['options']) + '\n'
                tiku_txt += '答案为：' + str(pickle.load(open(tiku_file_path, 'rb'))['value']['answer']) + '\n\n'
            if tiku_txt == '':
                self.tiku_text.insert( tk.END,'暂无缓存的题目')
            self.tiku_text.insert(tk.END, tiku_txt)
        except FileNotFoundError:
            self.tiku_text.insert(tk.END,'暂无缓存的题目')
        self.show_frame(self.question_bank_frame)
        self.tiku_text.configure(state=tk.DISABLED)

    def show_error(self):
        self.select_frame_by_name('报错日志')
        try:
            self.error_text.configure(state=tk.NORMAL)
            with open('error.log', 'r',encoding='utf-8') as f:
                content = f.read()
                self.error_text.delete('1.0', tk.END)
                self.error_text.insert(tk.END, content)
        except FileNotFoundError:
            self.error_text.delete('1.0', tk.END)
            self.error_text.insert(tk.END, '暂无报错记录')
        self.show_frame(self.error_frame)
        self.error_text.configure(state=tk.DISABLED)

    def show_set(self):
        self.select_frame_by_name('设置')
        self.show_frame(self.set_frame)

    def show_help(self):
        self.select_frame_by_name('帮助')
        self.show_frame(self.help_frame)

    def select_file(self):
        file_path = filedialog.askopenfilename(title="选择文件", filetypes=[("可执行文件", "*.exe")] if os.name == "nt" else [("可执行文件", "*")])
        if file_path:
            self.browser_driver_entry.delete(0, tk.END)
            self.browser_driver_entry.insert(tk.END,file_path)

    def start_button_normal(self):
        time.sleep(5)
        self.start_button.configure(state=tk.NORMAL)

    def run_program(self,file_name):
        self.fold_frame()
        """
        运行 main.py 程序，并将其输出实时显示在 GUI 的文本框中。
        """
        # 确保文本框可编辑
        self.text_box.configure(state=tk.NORMAL)
        # 清空文本框内容
        self.text_box.delete('1.0', tk.END)
        def read_output():
            """
            读取 main.py 程序的输出，并将其显示在文本框中。
            """
            # 启动 main.py 程序
            self.process = subprocess.Popen(file_name,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            color_tag = None
            logger.info('======================主程序开始运行======================')
            while True:
                output = self.process.stdout.readline()
                if self.process is None:
                    break
                if output == b'' and self.process.poll() is not None:
                    break
                if output:
                    try:
                        decoded_output = output.decode()
                    except UnicodeDecodeError:
                        decoded_output = output.decode('gbk', errors='ignore')
                    # 处理 [91m 这种颜色标记
                    ansi_color_start = re.search(r'\[(\d+?)m', decoded_output)
                    ansi_color_end = re.search(r'\[0m', decoded_output)
                    if ansi_color_start:
                        ansi_color_code = ansi_color_start.group(1)
                        if ansi_color_code == '91':
                            color_tag = 'red'
                            self.text_box.tag_config(color_tag, foreground=color_tag)
                            decoded_output = decoded_output.replace(ansi_color_start.group(0), "")
                    if ansi_color_end:
                        color_tag = None
                        decoded_output = decoded_output.replace(ansi_color_end.group(0), "")
                    for colorama_func, tkinter_color in self.colorama_to_tkinter.items():
                        start_pattern = re.escape(getattr(Fore, colorama_func) + '')
                        end_pattern = re.escape(Fore.RESET)
                        color_start = re.search(start_pattern, decoded_output)
                        color_end = re.search(end_pattern, decoded_output)
                        if color_start:
                            color_tag = tkinter_color
                            self.text_box.tag_config(color_tag, foreground=color_tag)
                            decoded_output = decoded_output.replace(color_start.group(0), "")
                        if color_end:
                            color_tag = None
                            decoded_output = decoded_output.replace(color_end.group(0), "")
                    decoded_output = decoded_output.replace('', '')
                    if color_tag:
                        self.text_box.insert(tk.END, decoded_output, color_tag)
                    else:
                        self.text_box.insert(tk.END, decoded_output)
                    decoded_output=re.sub(r'[\n\t\r]', '', decoded_output)
                    if decoded_output.strip():
                        logger.info(decoded_output)
                    if '❌' in decoded_output:
                        logger.warning('检测到出错标记: ' + decoded_output.strip())
                    self.text_box.see(tk.END)  # 自动滚动到文本框底部，以显示最新内容
            self.process.stdout.close()
            try:
                self.process.wait()
            except:
                pass
            self.text_box.configure(state=tk.DISABLED)

        # 使用线程来运行读取输出的函数，避免阻塞主事件循环
        self.thread = threading.Thread(target=read_output)
        self.thread.start()


    def start(self):
        self.process_condition=True
        self.close_button.grid(row=0, column=0, padx=5, pady=10)
        self.start_button.grid_forget()
        with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as fil:
            self.account_info = json.load(fil)
            if self.account_info.get('phone_number', '') == '':
                tk.messagebox.showerror('警告', message='请在设置页面填写相关信息再保存，如果已经保存，请在关闭主窗口后，'
                                                        '再右键点击刷课程序用管理员权限运行,进入设置页面填写相关信息')
                return
        # 构造刷课子进程命令：打包态调用自身 exe(--worker)，源码态调用 python main.py
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, '--worker']
        else:
            cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')]
        threading.Thread(target=self.run_program,args=(cmd,)).start()
        threading.Thread(target=self.start_button_normal).start()

    def open_timer_window(self):
        """打开定时刷课设置窗口"""
        timer_window = ctk.CTkToplevel(self.root)
        timer_window.title("⏰ 定时刷课设置")
        timer_window.geometry("350x200")
        timer_window.resizable(False, False)
        timer_window.transient(self.root)
        timer_window.grab_set()
        # 开始时间设置
        ctk.CTkLabel(timer_window, text="开始时间 (HH:MM:SS):", font=self.font).grid(row=0, column=0, padx=10, pady=10,
                                                                                     sticky="w")
        self.start_time_entry = ctk.CTkEntry(timer_window, width=120, font=self.font)
        self.start_time_entry.grid(row=0, column=1, padx=10, pady=10)
        self.start_time_entry.insert(0, self.timer_start_time)
        # 结束时间设置
        ctk.CTkLabel(timer_window, text="结束时间 (HH:MM:SS):", font=self.font).grid(row=1, column=0, padx=10, pady=10,
                                                                                     sticky="w")
        self.end_time_entry = ctk.CTkEntry(timer_window, width=120, font=self.font)
        self.end_time_entry.grid(row=1, column=1, padx=10, pady=10)
        self.end_time_entry.insert(0, self.timer_end_time)
        # 确认按钮
        confirm_btn = ctk.CTkButton(timer_window, text="开启定时", fg_color=self.button_color,
                                    hover_color=self.button_hover_color, font=self.font,
                                    command=lambda: self.set_timer(timer_window))
        confirm_btn.grid(row=2, column=0,  padx=10, pady=20)
        #取消定时
        cancel_btn = ctk.CTkButton(timer_window, text="禁用定时", fg_color=self.button_color,hover_color=self.button_hover_color,font=self.font,
                                    command=lambda: self.close_timer_window(timer_window))
        cancel_btn.grid(row=2, column=1, padx=10, pady=20)

    def set_timer(self, window):
        """设置定时刷课时间"""
        start_time_str = self.start_time_entry.get().strip()
        end_time_str = self.end_time_entry.get().strip()
        # 验证时间格式
        time_pattern = r"^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$"
        if not re.match(time_pattern, start_time_str):
            tk.messagebox.showerror("错误", "开始时间格式不正确，请输入 HH:MM:SS 格式")
            return
        if not re.match(time_pattern, end_time_str):
            tk.messagebox.showerror("错误", "结束时间格式不正确，请输入 HH:MM:SS 格式")
            return
        # 验证结束时间大于开始时间
        start_h, start_m, start_s = map(int, start_time_str.split(":"))
        end_h, end_m, end_s = map(int, end_time_str.split(":"))
        start_total = start_h * 3600 + start_m * 60 + start_s
        end_total = end_h * 3600 + end_m * 60 + end_s
        if start_total==end_total:
            tk.messagebox.showerror("错误", "结束时间不能与开始时间相同")
            return

        self.timer_start_time = start_time_str
        self.timer_end_time = end_time_str
        self.timer_active = True
        self.text_box.configure(state=tk.NORMAL)
        self.text_box.insert(tk.END,
                             f"\n定时刷课已开启:\n  开始时间: {self.timer_start_time}\n  结束时间: {self.timer_end_time}"
                             f"\n请勿关闭此窗口，否则定时刷课将无法正常开启")

        self.text_box.see(tk.END)
        with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as f:
            self.account_info = json.load(f)
        self.account_info['timer_active']='True'
        self.account_info['timer_start']=self.timer_start_time
        self.account_info['timer_end']=self.timer_end_time
        with open(r'task/tool/account_info.json', 'w', encoding='utf-8') as f:
            json.dump(self.account_info, f)
        window.destroy()

    # 关闭定时刷课设置窗口
    def close_timer_window(self, window):
        """关闭定时刷课设置窗口"""
        window.destroy()
        self.timer_active = False
        self.text_box.configure(state=tk.NORMAL)
        self.text_box.insert(tk.END, "\n定时刷课已禁用")
        with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as f:
            self.account_info = json.load(f)
        self.account_info['timer_active']='False'
        with open(r'task/tool/account_info.json', 'w', encoding='utf-8') as f:
            json.dump(self.account_info, f)
    def close(self):

        self.process_condition=False
        self.start_button.grid(row=0, column=0,padx=5,  pady=10)
        self.close_button.grid_forget()
        self.reopen_frame()
        if self.process is not None:
            try:
                if os.name == 'nt':  # Windows 平台
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
                else:  # Unix 平台
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.text_box.insert(tk.END, "程序已成功关闭\n")
                logger.info('======================程序已成功关闭======================')
            except Exception as e:
                self.text_box.insert(tk.END, f"关闭失败: {e}\n")
                logger.error(f"======================程序关闭失败: {e}======================")
            finally:
                self.process = None

    # 每秒更新 GUI 中的时间显示
    def update_time(self):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.configure(text=f"当前时间: {current_time}")
        self.root.after(1000, self.update_time)  # 每秒更新一次
        if self.timer_start_time in current_time and not self.process_condition and self.timer_active:
            self.start()
        if self.timer_end_time in current_time and self.process_condition and self.timer_active:
            self.close()

    def change_font(self):
        self.font = (self.font_entry.get(), int(self.size_entry.get()))
        self.style.configure('TLabelframe.Label',font=self.font)

        def update_font(widget):
            if isinstance(widget,( tk.Label, tk.Button, tk.Text,ttk.Label, tk.Entry, tk.LabelFrame)):
                widget.config(font=self.font)
            elif isinstance(widget,ttk.Checkbutton):
                style=ttk.Style()
                style.configure('TCheckbutton',font=self.font)
                widget.config(style='TCheckbutton')
            for child in widget.winfo_children():
                update_font(child)

        update_font(self.root)

    def save_course(self):
            data = []
            try:
                with open(r'task/tool/course_name.json', 'r') as f:
                    dit = json.load(f)
                    data=dit.get(self.phone_number_entry.get(),[])
            except FileNotFoundError:
                pass
            for content in self.all_courses:
                if content not in data:
                    data.append(content)
            with open(r'task/tool/course_name.json', 'w' , encoding='utf-8')as f:
                dit[self.phone_number_entry.get()]=data
                json.dump(dit, f)

    def save(self):
        try:
            with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as f:
                self.account_info = json.load(f)
        except FileNotFoundError:
            self.account_info = {}
        if self.browser_entry.get()=='':
            tk.messagebox.showerror('警告', message='请选择浏览器')
            return False
        else:
            self.account_info['browser']=self.browser_entry.get()
        if self.browser_driver_entry.get()=='':
            tk.messagebox.showerror('警告', message='请填写驱动的地址')
            return False
        else:
            self.account_info['driver_path']=self.browser_driver_entry.get()
        driver_path = self.browser_driver_entry.get().strip()
        if not os.path.isfile(driver_path):
            tk.messagebox.showerror('警告', message='驱动文件不存在，请选择正确的驱动文件')
            return False
        if self.phone_number_entry.get()=='':
            tk.messagebox.showerror('警告', message='请填写手机号')
            return False
        else:
            self.account_info['phone_number'] = self.phone_number_entry.get().replace('\n','')
        if  self.password_entry.get()=='':
            tk.messagebox.showerror('警告', message='请填写密码')
            return False
        else:
            self.account_info['password'] = self.password_entry.get().replace('\n','')
        if self.cour_entry.get()=='':
            tk.messagebox.showerror('警告', message='请填写课程名称')
            return False
        else:
            courses=[self.cour_entry.get().replace('\n', '')]
            add_courses = [entry.get() for entry, _, _,_ in self.dynamic_rows if entry.get().replace('\n', '')]
            self.all_courses = courses+add_courses
            self.account_info['cour'] = self.all_courses
        if self.question_entry.get() ==''  :
            tk.messagebox.showerror('警告', message='请完成章节测验刷题设置')
            return False
        else:
            self.account_info['choice'] = self.question_entry.get()
        if self.after_finish_question_entry.get()== '' and self.question_entry.get()=='AI 智能答题':
            tk.messagebox.showerror('警告', message='请完成答完题后的设置')
            return False
        else:
            self.account_info['after_finish_question'] = self.after_finish_question_entry.get()
        if self.vido_question_entry.get() =='' and self.radio_var.get()==1 :
            tk.messagebox.showerror('警告', message='请完成视频题目设置')
            return False
        else:
            self.account_info['video_title_choice'] = self.vido_question_entry.get()
        if self.discussion_entry.get() ==''  and self.radio_var.get()==1:
            tk.messagebox.showerror('警告', message='请完成讨论设置')
            return False
        else:
            self.account_info['discussion_choice'] = self.discussion_entry.get()
        if self.question_entry.get() == 'AI 智能答题' or self.vido_question_entry.get() == 'AI 智能答题' or self.discussion_entry.get() == 'AI 智能答题':
            if self.API_entry.get()=='':
                tk.messagebox.showerror('警告', message='请填写API密钥')
                return False
            else:
                self.account_info['API'] = self.API_entry.get()
                self.account_info['API_URL'] = self.API_URL_entry.get()
                self.account_info['API_MODEL'] = self.API_MODEL_entry.get()
        if self.speed_entry.get()==''and self.radio_var.get()==1:
            tk.messagebox.showerror('警告', message='请填写倍数')
            return False
        else:
            self.account_info['speed']=self.speed_entry.get()
        if self.homework_entry.get() == '' and self.radio_var.get() == 2:
            tk.messagebox.showerror('警告', message='请填写作业选择形式')
            return False
        else:
            self.account_info['homework'] = self.homework_entry.get()
        if self.radio_var.get()==1:
            self.account_info['task_type']='章节'
        elif self.radio_var.get()==2:
            self.account_info['task_type']='作业'
        self.account_info['font_type'] = self.font_entry.get()
        self.account_info['font_size'] = self.size_entry.get()
        self.account_info['pass_face'] = self.pass_face_check.get()
        self.account_info['lock_screen'] = self.lock_screen_check.get()
        self.account_info['radio_var']=self.radio_var.get()

        result = tk.messagebox.askokcancel('确认保存', '你确定要保存吗？\n(使用AI可支持全题型作答)')
        if result:
            with open(r'task/tool/account_info.json', 'w', encoding='utf-8') as f:
                json.dump(self.account_info, f)
            with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as fil:
                self.account_info = json.load(fil)
                if self.account_info['phone_number']!='':
                    tk.messagebox.showinfo('', '保存成功')
                else:
                    tk.messagebox.showerror('警告', message='保存失败，请在关闭主窗口后，再右键点击刷课程序用管理员权限打开')

            self.save_course()
            self.change_font()
            self.root.update()

    def load_data(self):
        try:

            with open(r'task/tool/account_info.json', 'r', encoding='utf-8') as fil:
                self.account_info = json.load(fil)
                with open(r'task/tool/course_name.json', 'r') as f:
                    dit = json.load(f)
                    self.data=dit.get(self.account_info['phone_number'],[])
                    if self.data:
                        self.course_score_entry.configure(values= tuple(self.data))
                        self.course_vido_entry.configure(values= tuple(self.data))
                        self.cour_entry.configure(values=tuple(self.data))
                self.course_score_entry.set( self.account_info['cour'][0])
                self.course_vido_entry.set( self.account_info['cour'][0])
                self.browser_entry.set( self.account_info['browser'])
                self.browser_driver_entry.insert(0, self.account_info['driver_path'])
                self.speed_entry.set( self.account_info['speed'])
                self.phone_number_entry.insert( 0,self.account_info['phone_number'])
                self.password_entry.insert(0, self.account_info['password'])
                self.cour_entry.set( self.account_info['cour'][0])
                self.question_entry.set( self.account_info['choice'])
                self.after_finish_question_entry.set( self.account_info['after_finish_question'])
                if self.account_info['video_title_choice']!='':
                    self.vido_question_entry.set( self.account_info['video_title_choice'])
                self.discussion_entry.set( self.account_info['discussion_choice'])
                self.homework_entry.set( self.account_info['homework'])
                self.radio_var.set(self.account_info['radio_var'])
                if self.account_info['pass_face']==0:
                    self.pass_face_check.deselect()
                else:
                    self.pass_face_check.select()
                if self.account_info['lock_screen']==0:
                    self.lock_screen_check.deselect()
                else:
                    self.lock_screen_check.select()
                try:
                    self.API_entry.insert(0, self.account_info.get('API', ''))
                    self.API_URL_entry.insert(0, self.account_info.get('API_URL', ''))
                    self.API_MODEL_entry.insert(0, self.account_info.get('API_MODEL', ''))
                    self.font_entry.set(self.account_info['font_type'])
                    self.size_entry.set(self.account_info['font_size'])
                    self.change_font()
                except:
                    pass
                for cour_name in self.account_info['cour'][1:]:
                    self.add_course(cour_name)
                if self.account_info['timer_active']=='True':
                    self.timer_active=True
                self.timer_start_time=self.account_info['timer_start']
                self.timer_end_time=self.account_info['timer_end']
        except FileNotFoundError:
            pass

    def fold_frame(self):
        self.navigation_frame.grid_forget()
        self.open_frame.grid(row=0, column=0,rowspan=2, sticky="ns")

    def reopen_frame(self):
        self.open_frame.grid_forget()
        self.navigation_frame.grid(row=0, column=0, rowspan=2,sticky="nsew")

    def change_appearance_mode_event(self, theme):
        # 黑白固定配色，无需动态切换
        pass

    def hint(self,speed):
        if int(speed)>2:
            tk.messagebox.showinfo('提示','倍数过高，已完成的任务点可能会被清空，请谨慎使用')
        else:
            pass


def start_main():
    """GUI 入口（供 launcher.py 调用）"""
    start = Start()
    start.root.mainloop()


if __name__ == "__main__":
    start_main()

