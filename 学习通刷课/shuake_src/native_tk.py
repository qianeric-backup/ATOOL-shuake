# -*- coding: utf-8 -*-
"""
native_tk.py — 原生 tkinter/ttk 适配层，替代 customtkinter
提供与 ctk 兼容的控件类（CTkFrame/CTkLabel/CTkButton/CTkEntry/CTkTextbox/
CTkComboBox/CTkSwitch/CTkRadioButton/CTkToplevel/CTk/CTkImage），
内部全部使用 tk 原生控件实现，外观为系统原生风格（黑白配色）。

用法：在 start.py 中把 `import customtkinter as ctk` 改为 `import native_tk as ctk`
"""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


# 默认黑白配色（与 start.py 一致）
DARK = "#2F2F2F"     # 深色（按钮/导航）
LIGHT = "#F7F7F7"    # 浅色（内容区背景）
MID = "#555555"      # 中灰（hover/边框）


def set_appearance_mode(mode):
    """兼容 ctk.set_appearance_mode —— 原生 tk 无需外观模式，no-op"""
    pass


class CTkImage:
    """兼容 ctk.CTkImage：内部转为 PIL PhotoImage"""
    def __init__(self, light_image=None, dark_image=None, size=None):
        self._light = light_image
        self._dark = dark_image if dark_image is not None else light_image
        self._size = size or (light_image.size if light_image else (20, 20))
        self._photo = None  # 延迟创建（需 root 存在后）

    def _get_photo(self, master=None):
        if self._photo is None:
            img = self._light
            if self._size and img.size != tuple(self._size):
                img = img.resize(self._size, Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img, master=master)
        return self._photo


class CTkFrame(tk.Frame):
    """原生 Frame，兼容 ctk 参数（fg_color/corner_radius/border_width/border_color）"""
    def __init__(self, master, fg_color=None, corner_radius=0, border_width=None,
                 border_color=None, **kw):
        bg = fg_color if fg_color and fg_color != 'transparent' else LIGHT
        kw.setdefault('bg', bg)
        kw.setdefault('padx', border_width or 0)
        kw.setdefault('pady', border_width or 0)
        super().__init__(master, **kw)
        if border_width and border_color:
            self.configure(highlightbackground=border_color, highlightthickness=border_width)


class CTkLabel(tk.Label):
    """原生 Label，兼容 ctk 参数（fg_color/text_color/font/anchor/compound/image）"""
    def __init__(self, master, text="", fg_color=None, text_color=None, font=None,
                 anchor=None, compound=None, image=None, **kw):
        bg = fg_color if fg_color and fg_color != 'transparent' else 'SystemButtonFace'
        fg = text_color if text_color else 'black'
        kw.setdefault('bg', bg)
        kw.setdefault('fg', fg)
        if font:
            kw['font'] = font
        if anchor:
            kw['anchor'] = anchor
        if compound:
            kw['compound'] = compound
        if image is not None:
            photo = image._get_photo(master) if hasattr(image, '_get_photo') else image
            kw['image'] = photo
            self._img_ref = photo  # 防 GC
        super().__init__(master, **kw)
        if text:
            self.configure(text=text)


class CTkButton(tk.Button):
    """原生 Button，兼容 ctk 参数（fg_color/hover_color/text_color/corner_radius/border_spacing/anchor/image/command）"""
    def __init__(self, master, text="", fg_color=None, hover_color=None, text_color=None,
                 font=None, corner_radius=None, border_spacing=None, anchor=None,
                 image=None, compound=None, command=None, **kw):
        bg = fg_color if fg_color and fg_color != 'transparent' else 'SystemButtonFace'
        fg = text_color if text_color else 'black'
        if isinstance(fg, (tuple, list)):  # ctk 的 ("gray10","gray90")
            fg = fg[0]
        kw.setdefault('bg', bg)
        kw.setdefault('fg', fg)
        kw.setdefault('activebackground', hover_color if hover_color else bg)
        kw.setdefault('activeforeground', fg)
        kw.setdefault('relief', 'raised')
        kw.setdefault('bd', 1)
        kw.setdefault('cursor', 'hand2')
        if font:
            kw['font'] = font
        if anchor:
            kw['anchor'] = anchor
        if command:
            kw['command'] = command
        if image is not None:
            photo = image._get_photo(master) if hasattr(image, '_get_photo') else image
            kw['image'] = photo
            self._img_ref = photo
            if compound:
                kw['compound'] = compound
                kw['text'] = text
        super().__init__(master, **kw)
        if text and (not image or not compound):
            self.configure(text=text)
        if border_spacing:
            self.configure(padx=border_spacing // 2, pady=border_spacing // 2)


class CTkEntry(tk.Entry):
    """原生 Entry，兼容 ctk 参数（fg_color/text_color/corner_radius/width/show）"""
    def __init__(self, master, fg_color=None, text_color=None, corner_radius=None,
                 width=None, show=None, font=None, **kw):
        if show:
            kw['show'] = show
        if width:
            kw['width'] = width
        if font:
            kw['font'] = font
        super().__init__(master, **kw)


class CTkTextbox(tk.Text):
    """原生 Text（只读场景），兼容 ctk 参数（fg_color/corner_radius）"""
    def __init__(self, master, fg_color=None, corner_radius=None, **kw):
        bg = fg_color if fg_color and fg_color != 'transparent' else 'white'
        kw.setdefault('bg', bg)
        kw.setdefault('wrap', 'word')
        kw.setdefault('relief', 'sunken')
        kw.setdefault('bd', 1)
        super().__init__(master, **kw)


_CTK_COMBO_IGNORE = {
    'dropdown_font', 'dropdown_fg_color', 'dropdown_hover_color',
    'button_color', 'button_hover_color', 'corner_radius', 'border_width',
    'border_color', 'bg_color', 'fg_color', 'hover_color', 'font',
    'dropdown_font_family', 'dropdown_font_size',
}


class CTkComboBox(ttk.Combobox):
    """原生 Combobox：过滤 ctk 专有参数，只透传 values/state/width/command"""
    def __init__(self, master, values=None, state=None, font=None, command=None,
                 width=None, **kw):
        # font 不作为 ttk 构造参数（ttk 用 style 控制），忽略
        clean = {k: v for k, v in kw.items() if k not in _CTK_COMBO_IGNORE}
        clean['values'] = values or []
        if width:
            clean['width'] = width
        super().__init__(master, **clean)
        if state == 'readonly':
            self.configure(state='readonly')
        if command:
            self.bind('<<ComboboxSelected>>', lambda e: command(self.get()))

    def configure(self, **kw):
        clean = {k: v for k, v in kw.items() if k not in _CTK_COMBO_IGNORE}
        if 'values' in clean:
            super().configure(values=clean.pop('values'))
        if 'state' in clean:
            super().configure(state=clean.pop('state'))
        if clean:
            super().configure(**clean)


class CTkSwitch(tk.Checkbutton):
    """原生 Checkbutton 模拟开关，兼容 ctk（select/deselect/get/command）"""
    def __init__(self, master, text="", command=None, **kw):
        self._var = tk.BooleanVar(master, False)
        kv = dict(kw)
        if command:
            kv['command'] = command
        super().__init__(master, text=text, variable=self._var,
                         bg='SystemButtonFace', activebackground='SystemButtonFace', **kv)

    def select(self):
        self._var.set(True)

    def deselect(self):
        self._var.set(False)

    def get(self):
        return self._var.get()


class CTkRadioButton(tk.Radiobutton):
    """原生 Radiobutton，兼容 ctk（variable/value/text/command）"""
    def __init__(self, master, text="", variable=None, value=None, command=None, **kw):
        kv = dict(kw)
        kv.setdefault('bg', 'SystemButtonFace')
        kv.setdefault('activebackground', 'SystemButtonFace')
        super().__init__(master, text=text, variable=variable, value=value, **kv)
        if command:
            self.configure(command=command)


class CTkToplevel(tk.Toplevel):
    """原生 Toplevel，兼容 ctk"""
    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)


class CTk(tk.Tk):
    """原生 Tk 根窗口"""
    def __init__(self, **kw):
        super().__init__()
        self.configure(bg=LIGHT)

# ---- ctk → tk 参数映射的 configure 兼容层 ----
def _tk_configure(self, **kw):
    """把 ctk 专有参数映射为 tk 原生参数，其余透传"""
    mp = {
        'fg_color': 'bg',
        'text_color': 'fg',
        'border_color': 'highlightbackground',
        'border_width': 'highlightthickness',
        'corner_radius': None,   # 原生无圆角，忽略
        'border_spacing': None,
        'hover_color': 'activebackground',
        'progress_color': None,
        'dropdown_fg_color': None,
        'dropdown_hover_color': None,
        'button_color': None,
        'button_hover_color': None,
        'bg_color': None,
    }
    real = {}
    for k, v in kw.items():
        if k in mp:
            t = mp[k]
            if t:
                if v and v != 'transparent':
                    real[t] = v
            # None → 忽略
        else:
            real[k] = v
    # 空则跳过，避免 TclError
    if real:
        super(self.__class__, self).configure(**real)

# 应用到各控件类（仅当没有自定义 configure 时）
for _cls_name in ['CTkTextbox', 'CTkFrame', 'CTkButton', 'CTkLabel', 'CTkEntry', 'CTkComboBox', 'CTkSwitch', 'CTkRadioButton']:
    _cls = globals().get(_cls_name)
    if _cls is not None and 'configure' not in vars(_cls):
        import types as _types
        _cls.configure = _tk_configure
