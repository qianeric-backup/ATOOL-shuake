import base64
import hashlib
import re
import os
import time
from xml.dom.minidom import parse

import unicodedata
# 自定义包

# 第三方包
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from fontTools.ttLib import TTFont

from task.tool import file
from task.tool import color


def color_red(s):
    return color.red(s)


class DecodeSecret:
    # 参数 statusCode 表示是否开启加密字符解密
    # statusCode 可取三个值分别是 0、1、2
    #   0 表示不启用解密
    #   1 表示启用解密
    #   2 表示程序自动判断是否解密
    def __init__(self, statusCode):
        if statusCode not in (0, 1, 2):
            raise Exception("实例化 DecodeSecret 对象时传入错误参数 " + str(statusCode) + ",可传入数据有：0, 1, 2")
        self._statusCode = statusCode
        self.font_dict_name = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), 'task', 'tool', 'font_dict.txt')
        self._secret_dict = {}
        self._font_dict = {}
        self._decode_miss = 0
        self._decode_total = 0
        self._setFontDict()

    # 获取页面 font_face 的值
    def getFontFace(self, driver):
        if self._statusCode == 0:
            return
        fontFaceStr = ""
        for _attempt in range(3):
            try:
                # 文档级单次查询 head 内的 style 标签，不持有 <head> 元素引用：
                # 原来「先 find_element(head) 再 find_elements 子元素」的两步
                # 写法，在题目页刷新/文档切换时会抛 StaleElementReferenceException
                fontFaceItem = driver.find_elements(
                    By.CSS_SELECTOR, "head [type='text/css']")
                for i in fontFaceItem:
                    strData = i.get_attribute('innerHTML')
                    if not strData:
                        continue
                    # 宽松匹配：只抓 base64 主体（历史写法要求紧跟 ') format
                    # 后缀，页面 CSS 稍变（woff2/换行/去 format）就解析失败，
                    # 导致整份题目不解密、乱码直达 AI
                    m = re.search(r"base64,([A-Za-z0-9+/=]{512,})", strData)
                    if m:
                        fontFaceStr = m.group(1)
                        break
                break
            except StaleElementReferenceException:
                # 页面正在刷新/切换，稍等后整体重查
                time.sleep(1)
        if self._statusCode == 1:
            if fontFaceStr == "":
                print(color_red('未检出题目加密字体（不一定是异常；'
                                '若题目出现乱码请把日志反馈给开发者）'), flush=True)
                return
        elif self._statusCode == 2:
            if fontFaceStr == "":
                self._statusCode = 0
                return
            else:
                self._statusCode = 1
        self._setSecretDict(fontFaceStr)

    """
    函数功能：解析加密后的字体数据，将字形信息和字体编码映射到 self._secret_dict 中

    参数：
        :fontFace: 页面的 @font_face 中 base64 编码的值
    """

    def _setSecretDict(self, fontFace):
        ttf_temp_path = ".temp.ttf"  # 临时文件 temp.ttf 存放路径
        xml_temp_path = ".temp.xml"  # 临时文件 temp.xml 存放路径

        # 将 fontFace 解析为 temp.ttf 文件，再把temp.ttf 文件解析为 temp.xml 文件
        b = base64.b64decode(fontFace)
        with open(ttf_temp_path, "wb") as f:
            f.write(b)
        font = TTFont(ttf_temp_path)
        font.saveXML(xml_temp_path)

        # 将字的十进制code和字形信息映射在 self._secret_dict 中
        domTree = parse(xml_temp_path)
        rootNode = domTree.documentElement
        ttglyph_list = rootNode.getElementsByTagName("TTGlyph")
        for ttglyph in ttglyph_list:
            name = ttglyph.getAttribute('name')
            if name == ".notdef":
                continue
            code = int(re.findall("uni(.*)", name)[0], 16)  # 10进制的值
            ttglyphStr = ""
            contour_list = ttglyph.getElementsByTagName("contour")
            for contour in contour_list:
                ttglyphStr += contour.toxml()
            value = hashlib.md5(ttglyphStr.encode(encoding="utf-8")).hexdigest()
            self._secret_dict[code] = value

        # 删除临时文件
        os.remove(ttf_temp_path)
        os.remove(xml_temp_path)

    """
    函数功能：读取 font_dict.txt 中的数据
        font_dict.txt 中存放的是学习通字体加密前，字形信息的md5值和字体编码的映射
    """

    def _setFontDict(self):
        if self._statusCode == 0:
            return
        self._font_dict = file.get_json_data(self.font_dict_name)

    """
    函数功能：将加密字符串解密
    :string: 被加密的字符串
    :return: 返回解密后的字符串
    """

    def decode(self, string: str):
        # 如果不开启解密则直接返回原字符串
        if self._statusCode == 0:
            return string
        trueStr = ""
        for word in string:
            wordMD5 = self._secret_dict.get(ord(word), None)
            if wordMD5 is None:
                trueStr += word
                continue
            self._decode_total += 1
            trueWordCode = self._font_dict.get(wordMD5, None)
            if trueWordCode is None:
                # 页面字形不在映射库中（学习通更新字体）——保留原字并计数
                self._decode_miss += 1
                trueStr += word
                continue
            trueWor = unicodedata.normalize('NFKC', chr(trueWordCode))
            trueStr += trueWor
        return trueStr

    def decode_stats(self):
        """返回 (未命中数, 解密尝试总数)——映射库过期时用于日志诊断"""
        return self._decode_miss, self._decode_total


if __name__ == '__main__':
    print(ord('长'))