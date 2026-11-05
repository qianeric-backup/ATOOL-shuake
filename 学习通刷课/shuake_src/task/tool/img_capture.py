# -*- coding: utf-8 -*-
"""img_capture —— 题干/选项图片采集，转 data URL 交给多模态模型（识图答题）

学习通作业/测验的题干与选项里常直接放图片（公式截图、函数图像、表格、
代码截图、电路图），`.text` 里一个字都取不到，纯文本搜题必然答错或空答案。
本模块负责把这部分图片"搬"给 AI：

1. 触发懒加载：学习通图片多为 `data-src` 懒加载，必须先滚动到视口；
2. 等待解码：`img.complete && naturalWidth` 为真后才取像素；
3. 压缩编码：canvas 缩到最长边 1400px、JPEG 0.9（公式细线仍可读），
   单张超过接口上限再降档重压；canvas 跨域被污染时回退
   `fetch(credentials:'include')` → blob → base64；
4. 过滤噪声：图标/分隔线/加载动画（两边都 < 60px）直接丢弃，按 src 去重；
5. 数量封顶：单题最多 8 张（`image_max` 可配），避免请求体积爆炸；
6. 可选 OCR：装了 pytesseract + tesseract 且配置 `image_ocr=1` 时，
   把图片文字并入题干文本，让纯文本题库接口也能命中。

对外只暴露 `extract_images(driver, element)`：返回 (标注文本, data_url 列表)，
标注文本形如 `[图片]`/`[图片内容:xxx]`，data_url 列表直接喂给
`AIAsk(..., images=[...])`。
"""
import base64
import hashlib
import io
import re
import time

from selenium.webdriver.common.by import By

from task.tool import color

# 单题默认最多几张图（配置项 image_max 可覆盖）
DEFAULT_MAX_IMAGES = 8
# 单张图片 data URL 的字符上限（约 3MB 原图；再多接口容易 400/超时）
MAX_DATA_CHARS = 3_000_000
# 小于这个边长的图视为图标/分隔线（两边都小才丢，避免扔掉细长公式）
MIN_EDGE = 60
# 缩放后的最长边
MAX_EDGE = 1400

_IMG_ATTRS = ('data-src', 'data-original', 'data-actualsrc', 'data-lazy-src',
              'data-url', 'data-echo', 'data-original-src')

_EXTRACT_JS = r"""
const el = arguments[0], opts = arguments[1] || {};
const done = arguments[arguments.length - 1];
const MIN_EDGE = opts.min_edge || 60;
const MAX_EDGE = opts.max_edge || 1400;
const MAX_N = opts.max_images || 8;
const MAX_CHARS = opts.max_chars || 3000000;
const DEADLINE = opts.deadline || 9000;
const LAZY = opts.lazy !== false;

function absolute(u) {
  try { return new URL(u, location.href).href; } catch (e) { return u || ''; }
}

function pickSrc(img) {
  const cands = [img.currentSrc, img.src];
  ['data-src', 'data-original', 'data-actualsrc', 'data-lazy-src',
   'data-url', 'data-echo', 'data-original-src'].forEach(function (a) {
    const v = img.getAttribute(a);
    if (v) cands.push(v);
  });
  const ss = img.getAttribute('srcset') || '';
  if (ss) cands.push(ss.split(',')[0].trim().split(/\s+/)[0]);
  for (let i = 0; i < cands.length; i++) {
    let c = cands[i];
    if (!c) continue;
    c = String(c).trim();
    if (!c) continue;
    // 1x1 透明 gif 占位图（懒加载前）直接跳过
    if (c.indexOf('data:image/gif') === 0 && c.length < 400) continue;
    if (c.indexOf('data:') !== 0) c = absolute(c);
    if (c) return c;
  }
  return '';
}

function compress(img, edge, quality) {
  const w = img.naturalWidth, h = img.naturalHeight;
  if (!w || !h) return null;
  const scale = Math.min(1, edge / Math.max(w, h));
  const cw = Math.max(1, Math.round(w * scale));
  const ch = Math.max(1, Math.round(h * scale));
  const canvas = document.createElement('canvas');
  canvas.width = cw; canvas.height = ch;
  const ctx = canvas.getContext('2d');
  // 白底：公式/表格图多带透明背景，直接转 JPEG 会变黑
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, cw, ch);
  try { ctx.drawImage(img, 0, 0, cw, ch); } catch (e) { return null; }
  try { return canvas.toDataURL('image/jpeg', quality); } catch (e) { return null; }
}

function blobData(src) {
  return fetch(src, {credentials: 'include'}).then(function (r) {
    if (!r.ok) return null;
    return r.blob();
  }).then(function (b) {
    if (!b || !b.size) return null;
    return new Promise(function (res) {
      const fr = new FileReader();
      fr.onload = function () { res(fr.result); };
      fr.onerror = function () { res(null); };
      fr.readAsDataURL(b);
    });
  }).catch(function () { return null; });
}

// 把已经拿到的 data URL 再压一遍：懒加载图（data-src）文字面量常是原图，
// 尺寸/体积远超接口限制，必须过一遍 canvas 缩放；解码失败就用原图
function shrinkDataUrl(dataUrl, edge, quality) {
  if (!dataUrl) return Promise.resolve(null);
  return new Promise(function (res) {
    const im = new Image();
    im.onload = function () {
      const out = compress(im, edge, quality);
      if (!out) return res(dataUrl);
      // 超过目标边长必须缩放（视觉模型按边长计 token，1800px 原图很贵）；
      // 本来就在范围内则保留体积更小的那个（无损 PNG 公式图别白转 JPEG）
      const needResize = Math.max(im.naturalWidth || 0, im.naturalHeight || 0) > edge;
      res((needResize || out.length <= dataUrl.length) ? out : dataUrl);
    };
    im.onerror = function () { res(dataUrl); };
    im.src = dataUrl;
  });
}

function waitLoad(img) {
  return new Promise(function (res) {
    if (img.complete && img.naturalWidth) return res();
    let settled = false;
    const ok = function () { if (!settled) { settled = true; res(); } };
    img.addEventListener('load', ok, {once: true});
    img.addEventListener('error', ok, {once: true});
    setTimeout(ok, 2500);
  });
}

async function run() {
  const started = Date.now();
  const imgs = Array.from(el.querySelectorAll('img'));
  if (!imgs.length) { done([]); return; }
  if (LAZY) {
    // 逐个滚进视口，触发 data-src → src 的懒加载替换
    for (let i = 0; i < imgs.length; i++) {
      try { imgs[i].scrollIntoView({block: 'center'}); } catch (e) {}
    }
    await new Promise(function (r) { setTimeout(r, 400); });
  }
  await Promise.all(imgs.map(waitLoad));
  const out = [];
  const seen = {};
  for (let i = 0; i < imgs.length; i++) {
    if (Date.now() - started > DEADLINE) break;
    if (out.length >= MAX_N) break;
    const img = imgs[i];
    const src = pickSrc(img);
    if (!src) continue;
    const w = img.naturalWidth || 0, h = img.naturalHeight || 0;
    if (w && h && w < MIN_EDGE && h < MIN_EDGE) continue;   // 图标/分隔线
    if (seen[src]) continue;
    seen[src] = 1;
    let data = compress(img, MAX_EDGE, 0.9);
    if (!data) data = await blobData(src);
    // 统一再过一次缩放：懒加载图只有 URL、没有可绘制的 img 像素时，
    // 上面 compress 会返回 null，原图可能是 2000px 以上、体积超标
    data = await shrinkDataUrl(data, MAX_EDGE, 0.9);
    if (data && data.length > MAX_CHARS) {
      data = await shrinkDataUrl(data, Math.round(MAX_EDGE * 0.6), 0.75);
    }
    if (data && data.length > MAX_CHARS) data = null;
    // data 为空也保留 src：跨域图片拿不到像素时，可由 Python 侧决定
    // 是否把 URL 直接交给模型（服务端抓取），比整题丢图更有机会答对
    out.push({src: src, w: w, h: h, data: data});
  }
  done(out);
}

run().catch(function () { done([]); });
"""

_LEGACY_FETCH_JS = """
const src = arguments[0], done = arguments[1];
fetch(src, {credentials: 'include'}).then(function (r) { return r.blob(); })
  .then(function (b) {
    const fr = new FileReader();
    fr.onload = function () { done(fr.result); };
    fr.readAsDataURL(b);
  }).catch(function () { done(null); });
"""


# ----------------------------------------------------------------- 配置开关
# 配置每条题都会问一次（每题要判断开关/图片上限），磁盘读太频繁，
# 加 10 秒缓存：GUI 改设置后最多 10 秒生效
_CFG_TTL = 10.0
_cfg_cache = {'at': 0.0, 'value': None}


def _config():
    now = time.time()
    cached = _cfg_cache['value']
    if cached is not None and now - _cfg_cache['at'] < _CFG_TTL:
        return cached
    try:
        from task.tool.config_path import load_config
        value = load_config() or {}
    except Exception:
        value = {}
    _cfg_cache['value'] = value
    _cfg_cache['at'] = now
    return value


def image_qa_enabled():
    """识图答题总开关（account_info.json 的 image_qa，默认开启）。"""
    value = _config().get('image_qa', 1)
    if isinstance(value, str):
        return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
    return bool(value)


def _max_images():
    try:
        value = int(_config().get('image_max', DEFAULT_MAX_IMAGES))
        return max(1, min(value, 20))
    except (TypeError, ValueError):
        return DEFAULT_MAX_IMAGES


def _url_fallback_enabled():
    """像素取不到时是否退化为图片 URL 直传（默认开）。"""
    value = _config().get('image_url_fallback', 1)
    if isinstance(value, str):
        return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
    return bool(value)


def _ocr_enabled():
    value = _config().get('image_ocr', 0)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


# ----------------------------------------------------------------- 基础能力
def collect_img_tags(element):
    """返回元素下所有 img 的 src 列表（去重保序，不含懒加载属性解析）。"""
    srcs = []
    try:
        for img in element.find_elements(By.TAG_NAME, 'img'):
            src = img.get_attribute('src') or ''
            for attr in _IMG_ATTRS:
                if src and not src.startswith('data:'):
                    break
                src = img.get_attribute(attr) or src
            if src and src not in srcs:
                srcs.append(src)
    except Exception:
        pass
    return srcs


def fetch_data_url(driver, src):
    """单张图片转 base64 data URL（fetch 带 cookie，免 CORS）。"""
    if not src:
        return None
    if src.startswith('data:'):
        return src
    try:
        return driver.execute_async_script(_LEGACY_FETCH_JS, src)
    except Exception:
        return None


def dedupe_images(urls):
    """按内容哈希去重（不同 src 可能指向同一张图）。"""
    out, seen = [], set()
    for u in urls or []:
        if not isinstance(u, str) or not u:
            continue
        key = hashlib.md5(u.encode('utf-8', 'replace')).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def _ocr_data_url(data_url):
    """本地 OCR（可选增强）：需要 pytesseract + tesseract，失败返回 None。"""
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


def _legacy_extract(driver, element, max_images):
    """异步脚本不可用时的老通道逐张抓取（保证不因驱动差异整体失效）。"""
    urls = []
    for src in collect_img_tags(element):
        if len(urls) >= max_images:
            break
        data = fetch_data_url(driver, src)
        if data and len(data) <= MAX_DATA_CHARS:
            urls.append(data)
    return urls


# ----------------------------------------------------------------- 对外入口
def extract_images(driver, element, max_images=None, min_edge=MIN_EDGE,
                   max_edge=MAX_EDGE, lazy=True):
    """采集 element 内所有题目图片。

    返回 (标注文本, data_url 列表)：
    - 标注文本并入题干/选项文本（`[图片]` 或 OCR 结果），让纯文本题库
      与 AI 都知道"这里有一张图"；
    - data_url 列表交给 AIAsk(images=...) 由多模态模型直接看图作答。
    """
    if not image_qa_enabled():
        return '', []
    limit = max_images or _max_images()
    opts = {
        'min_edge': min_edge,
        'max_edge': max_edge,
        'max_images': limit,
        'max_chars': MAX_DATA_CHARS,
        'lazy': bool(lazy),
    }
    raw = None
    try:
        raw = driver.execute_async_script(_EXTRACT_JS, element, opts)
    except Exception as exc:
        print(color.yellow(f'[识图] 图片采集脚本异常（{exc}），改用逐张抓取'), flush=True)
        raw = None

    if raw is None:
        urls = _legacy_extract(driver, element, limit)
        if not urls:
            return '', []
        marks = ['[图片]' for _ in urls]
        return ' '.join(marks), dedupe_images(urls)

    urls, raw_urls = [], []
    for item in raw or []:
        item = item or {}
        data = item.get('data')
        if data and len(data) <= MAX_DATA_CHARS:
            urls.append(data)
        else:
            src = str(item.get('src') or '')
            if src.startswith('http://') or src.startswith('https://'):
                raw_urls.append(src)
    urls = dedupe_images(urls)[:limit]
    if not urls:
        # 一张像素都没拿到（学习通 CDN 不带 CORS 头时会这样）：
        # 退化为 URL 直传，让多模态服务端自己抓图；模型不支持时会自动降级
        if raw_urls and _url_fallback_enabled():
            raw_urls = dedupe_images(raw_urls)[:limit]
            print(color.yellow(f'[识图] 页面内取不到图片数据，改用 {len(raw_urls)} 个图片直链'
                               f'（由模型服务端抓取）'), flush=True)
            return ' '.join('[图片]' for _ in raw_urls), raw_urls
        return '', []

    marks = []
    if _ocr_enabled():
        for data in urls:
            ocr = _ocr_data_url(data)
            marks.append(f'[图片内容:{ocr}]' if ocr else '[图片]')
    else:
        marks = ['[图片]' for _ in urls]
    print(color.green(f'[识图] 已采集 {len(urls)} 张题目图片，'
                      f'将交给多模态模型识别'), flush=True)
    return ' '.join(marks), urls
