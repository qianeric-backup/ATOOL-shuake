"""img_capture —— 题干/选项图片采集与多模态喂给 AI

学习通作业题干/选项中常含图片（公式截图、函数图像、表格等），
`.text` 提取不到任何内容，导致搜题不完整、选项匹配失败。
本模块：
1. 收集元素下所有 <img>（绝对 src，去重保序）；
2. 页面内 JS fetch 转 base64 data URL（自动带登录 cookie、免 CORS）；
3. 有本地 tesseract+pytesseract 时做 OCR 提取文字（可选增强）；
4. 无论如何都把 data URL 收集起来，交给 AIAsk(images=...)
   让多模态模型（gpt-4o / qwen-vl / 通义千问 等）直接"看"图。
"""
import base64
import io
import re

from selenium.webdriver.common.by import By


def collect_img_tags(element):
    """返回元素下所有 img 的绝对 src 列表（去重保序）。"""
    srcs = []
    try:
        for img in element.find_elements(By.TAG_NAME, 'img'):
            src = img.get_attribute('src') or ''
            if src and src not in srcs:
                srcs.append(src)
    except Exception:
        pass
    return srcs


def fetch_data_url(driver, src):
    """页面内 fetch 图片 → base64 data URL。

    用 execute_async_script 在页面上下文里 fetch（credentials: include
    自动带学习通登录 cookie），返回 base64 data URL；失败返回 None。
    """
    script = """
    const src = arguments[0], done = arguments[1];
    fetch(src, {credentials: 'include'}).then(r => r.blob()).then(b => {
        const fr = new FileReader();
        fr.onload = () => done(fr.result);
        fr.readAsDataURL(b);
    }).catch(() => done(null));
    """
    try:
        return driver.execute_async_script(script, src)
    except Exception:
        return None


def _ocr_data_url(data_url):
    """本地 OCR（可选增强）：有 pytesseract+tesseract 才生效，否则 None。"""
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return None
    try:
        b64 = data_url.split(',', 1)[1]
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        text = re.sub(r'\s+', '', text).strip()
        return text or None
    except Exception:
        return None


def extract_images(driver, element):
    """返回 (标注文本, data_url 列表)。

    - 标注文本：有 OCR 结果用「[图片内容:...]」，否则「[图片]」占位，
      并入题干/选项文本后，普通题库/AI 也能感知到图片存在；
    - data_url 列表：全部收集，交给 AIAsk(images=...) 多模态直读。
    """
    marks, data_urls = [], []
    for src in collect_img_tags(element):
        data_url = fetch_data_url(driver, src)
        if not data_url:
            marks.append('[图片]')
            continue
        data_urls.append(data_url)
        ocr = _ocr_data_url(data_url)
        marks.append(f'[图片内容:{ocr}]' if ocr else '[图片]')
    return (' '.join(marks), data_urls)
