# -*- coding: utf-8 -*-
"""Edge 驱动自动获取（微软官方通道 msedgedriver.microsoft.com）。

为什么需要这个模块：
- 项目约定目录（edgedriver_win64/msedgedriver.exe）原本要用户手动找版本、
  下 zip、解压、放到正确目录；
- Edge 每次自动升级后，旧驱动会因「主版本不匹配」直接不可用，表现为
  SessionNotCreatedException: This version of MSEdgeDriver only supports …；
- Selenium Manager 虽能兜底，但在部分网络环境/代理下拿不到。

因此本模块在驱动缺失、或已有驱动与本机 Edge 主版本不一致时，自动下载匹配
版本并放到项目约定目录，调用方无需感知。

版本规则（与 README 一致）：驱动主版本号 == Edge 主版本号。
官方通道的版本解析顺序：
  1. LATEST_RELEASE_<major> —— 该大版本的最新驱动（返回 UTF-16LE 文本；
     仅较新的大版本提供，老版本返回 404 BlobNotFound）
  2. 本机 Edge 的完整 4 段版本号 —— 精确匹配
两者都拿不到时返回 None，由调用方降级到 Selenium Manager。

本模块**从不抛异常、从不中断刷课流程**：任何失败都只返回 None。
"""
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

BASE_URL = "https://msedgedriver.microsoft.com"
USER_AGENT = "Mozilla/5.0 (compatible; ATOOL-shuake edgedriver-setup)"
TIMEOUT = 30            # 单次请求超时（秒）
DOWNLOAD_TIMEOUT = 300  # 下载驱动（约 12MB）超时（秒）

_VERSION_RE = re.compile(r'\d+\.\d+\.\d+\.\d+')


def _no_window():
    """Windows 下隐藏子进程控制台窗口（打包成 exe 后调用驱动不闪黑框）"""
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NO_WINDOW}
    return {}


def _major(version):
    return str(version).split('.')[0] if version else ''


def normalize_version(text):
    """从任意文本里抽出 x.y.z.w 版本号；抽不到返回 None"""
    if not text:
        return None
    m = _VERSION_RE.search(str(text))
    return m.group(0) if m else None


# ------------------------------------------------------------------ 本机 Edge 版本
def _file_version(path):
    """读 Windows 可执行文件的文件版本（ctypes 调 version.dll）"""
    if not os.path.isfile(path):
        return None
    try:
        import ctypes
        from ctypes import wintypes

        ver = ctypes.windll.version
        ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
        ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                            wintypes.DWORD, ctypes.c_void_p]
        ver.GetFileVersionInfoW.restype = wintypes.BOOL
        ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(wintypes.UINT)]
        ver.VerQueryValueW.restype = wintypes.BOOL

        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, '\\', ctypes.byref(ptr),
                                  ctypes.byref(length)):
            return None
        # VS_FIXEDFILEINFO: [0]dwSignature [1]dwStrucVersion
        #                   [2]dwFileVersionMS [3]dwFileVersionLS
        info = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint32))
        ms, ls = info[2], info[3]
        return f'{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}'
    except Exception:
        return None


def _edge_version_windows():
    try:
        import winreg
    except ImportError:
        winreg = None
    if winreg is not None:
        # Edge 自己维护的版本键，最省事也最准
        keys = [
            (winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Edge\BLBeacon',
             'version'),
            (winreg.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients'
             r'\{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}', 'pv'),
            (winreg.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\Microsoft\EdgeUpdate\Clients'
             r'\{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}', 'pv'),
        ]
        for hive, sub, name in keys:
            try:
                with winreg.OpenKey(hive, sub) as k:
                    raw, _ = winreg.QueryValueEx(k, name)
                found = normalize_version(raw)
                if found:
                    return found
            except OSError:
                continue
    for exe in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'):
        found = normalize_version(_file_version(exe))
        if found:
            return found
    return None


def _edge_version_from_cli(*commands):
    for cmd in commands:
        try:
            out = subprocess.run([cmd, '--version'], capture_output=True,
                                 timeout=20, **_no_window())
        except Exception:
            continue
        text = (out.stdout or b'').decode('utf-8', 'replace') + \
               (out.stderr or b'').decode('utf-8', 'replace')
        found = normalize_version(text)
        if found:
            return found
    return None


def _edge_version_macos():
    found = _edge_version_from_cli(
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge')
    if found:
        return found
    try:
        import plistlib
        with open('/Applications/Microsoft Edge.app/Contents/Info.plist',
                  'rb') as f:
            return normalize_version(
                plistlib.load(f).get('CFBundleShortVersionString'))
    except Exception:
        return None


def installed_edge_version():
    """本机 Edge 的完整版本号（如 153.0.4234.48）；识别不到返回 None"""
    if os.name == 'nt':
        return _edge_version_windows()
    if sys.platform == 'darwin':
        return _edge_version_macos()
    return _edge_version_from_cli('microsoft-edge', 'microsoft-edge-stable',
                                  'msedge')


# ------------------------------------------------------------------ 已有驱动版本
def driver_version(driver_path):
    """读已有驱动的版本（执行 `<driver> --version`）；失败返回 None"""
    if not driver_path or not os.path.isfile(driver_path):
        return None
    try:
        out = subprocess.run([driver_path, '--version'], capture_output=True,
                             timeout=20, **_no_window())
    except Exception:
        return None
    text = (out.stdout or b'').decode('utf-8', 'replace') + \
           (out.stderr or b'').decode('utf-8', 'replace')
    return normalize_version(text)


# ------------------------------------------------------------------ 官方通道
def _decode(raw):
    """官方 LATEST_RELEASE_* 返回 UTF-16LE（带 BOM），老端点可能是 UTF-8"""
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff') or b'\x00' in raw[:16]:
        return raw.decode('utf-16', 'replace')
    return raw.decode('utf-8-sig', 'replace')


def _http_get(url, timeout=TIMEOUT):
    """GET 并返回原始字节；任何失败返回 None"""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, 'status', 200) != 200:
                return None
            return resp.read()
    except Exception:
        return None


def latest_release_for_major(major):
    """该大版本在官方通道的最新驱动版本号；没有（老版本 404）返回 None"""
    if not major:
        return None
    raw = _http_get(f'{BASE_URL}/LATEST_RELEASE_{major}')
    return normalize_version(_decode(raw)) if raw else None


def _driver_name():
    return 'msedgedriver.exe' if os.name == 'nt' else 'msedgedriver'


def _platform_dir():
    """项目约定驱动目录名（与 qt_ui._driver_candidates 的 base_dirs 一致）"""
    if os.name == 'nt':
        return 'edgedriver_win64'
    if sys.platform == 'darwin':
        return 'edgedriver_mac64'
    return 'edgedriver_linux64'


def _zip_names():
    """按优先级返回下载包名（ARM 平台先试 arm64，失败自动回退）"""
    machine = platform.machine().lower()
    if os.name == 'nt':
        if 'arm' in machine:
            return ['edgedriver_arm64.zip', 'edgedriver_win64.zip']
        return ['edgedriver_win64.zip']
    if sys.platform == 'darwin':
        if 'arm' in machine:
            return ['edgedriver_mac64_m1.zip', 'edgedriver_mac64.zip']
        return ['edgedriver_mac64.zip']
    return ['edgedriver_linux64.zip']


def _project_root():
    """含 task/ 的那一层（源码态为 shuake_src）"""
    here = os.path.dirname(os.path.abspath(__file__))        # …/task/tool
    return os.path.dirname(os.path.dirname(here))            # …/<project>


def _candidate_dirs():
    """驱动目录的两个扫描位。

    与 qt_ui._driver_candidates / main._find_project_driver 的扫描位一致，
    这样下载下来的驱动两处解析链都能命中：当前工作目录下的
    <dir>，以及源码根的同级目录（学习通刷课/<dir>）。
    打包态没有源码根（__file__ 在 _MEIPASS 临时目录里），只有前者。
    """
    dirs = [os.path.join(os.getcwd(), _platform_dir())]
    if not getattr(sys, 'frozen', False):
        project = _project_root()
        dirs.append(os.path.join(os.path.dirname(project), _platform_dir()))
    return dirs


def _project_driver_dir():
    """驱动写入目录：已有驱动的位置 → README 约定的项目目录 → 当前目录。

    优先写回已有驱动所在目录，避免同一份驱动在两个位置各存一份；都没有时
    用源码根的同级目录（学习通刷课/edgedriver_win64）——它与 cwd 无关，
    是 README 约定的稳定位置；打包态则用 exe 所在目录。
    """
    dirs = _candidate_dirs()
    for d in dirs:
        if os.path.isfile(os.path.join(d, _driver_name())):
            return d
    if not getattr(sys, 'frozen', False):
        project = _project_root()
        return os.path.join(os.path.dirname(project), _platform_dir())
    return dirs[0]


def existing_driver_paths():
    """项目约定目录里已存在的驱动路径（去重）"""
    out, seen = [], set()
    for d in _candidate_dirs():
        p = os.path.normpath(os.path.join(d, _driver_name()))
        if p not in seen and os.path.isfile(p):
            seen.add(p)
            out.append(p)
    return out


def download_edge_driver(version, dest_dir, log=print):
    """下载指定版本的驱动并放入 dest_dir；成功返回驱动路径，失败返回 None"""
    if not version:
        return None
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError:
        return None
    target = os.path.join(dest_dir, _driver_name())

    for zip_name in _zip_names():
        url = f'{BASE_URL}/{version}/{zip_name}'
        log(f'正在下载 Edge 驱动 {version}（约 12MB，请稍候）…')
        raw = _http_get(url, timeout=DOWNLOAD_TIMEOUT)
        if not raw:
            continue

        # 先落到临时文件再解压：避免把半个 zip 当成功
        tmp_zip = None
        try:
            fd, tmp_zip = tempfile.mkstemp(suffix='.zip', prefix='msedgedriver_')
            with os.fdopen(fd, 'wb') as f:
                f.write(raw)
            with zipfile.ZipFile(tmp_zip) as z:
                member = next(
                    (n for n in z.namelist()
                     if os.path.basename(n).lower() == _driver_name().lower()),
                    None)
                if not member:
                    continue
                payload = z.read(member)
        except Exception:
            continue
        finally:
            if tmp_zip and os.path.exists(tmp_zip):
                try:
                    os.remove(tmp_zip)
                except OSError:
                    pass

        # 原子替换：写临时文件后 os.replace，避免留下写坏的驱动
        tmp_out = target + '.new'
        try:
            with open(tmp_out, 'wb') as f:
                f.write(payload)
            try:
                os.chmod(tmp_out, 0o755)
            except OSError:
                pass
            os.replace(tmp_out, target)
        except OSError as e:
            # 常见：驱动正被占用（有 msedgedriver 进程在跑）→ 留给调用方降级
            log(f'驱动写入失败（{e}），跳过自动更新')
            try:
                os.remove(tmp_out)
            except OSError:
                pass
            return None
        log(f'Edge 驱动已就位：{target}')
        return target
    return None


def ensure_edge_driver(current=None, log=print):
    """确保项目目录里有与本机 Edge 主版本匹配的驱动。

    - current 或项目目录里的驱动已匹配 → 原样返回该路径，不做任何改动；
    - 缺失、或主版本与本机 Edge 不一致（Edge 升级后的典型情况）→ 自动
      下载匹配版本并覆盖项目约定目录；
    - 任何一步失败 → 返回 None，调用方照旧降级到 Selenium Manager。
    """
    edge_version = installed_edge_version()
    if not edge_version:
        log('未能识别本机 Edge 版本，跳过自动下载（交由 Selenium Manager 定位）')
        return None
    want_major = _major(edge_version)

    seen = set()
    for path in ([current] if current else []) + existing_driver_paths():
        if not path or path in seen:
            continue
        seen.add(path)
        if not os.path.isfile(path):
            continue
        found = driver_version(path)
        if found and _major(found) == want_major:
            return path

    log(f'本机 Edge {edge_version}，未找到主版本匹配的驱动，开始自动获取…')
    tried = []
    # 1) 该大版本的最新驱动（更常见：Edge 是 153.0.4000.0、驱动是 153.0.4234.48）
    # 2) 本机精确版本
    for version in (latest_release_for_major(want_major), edge_version):
        if not version or version in tried:
            continue
        tried.append(version)
        path = download_edge_driver(version, _project_driver_dir(), log=log)
        if path:
            return path
    log('自动获取 Edge 驱动失败（网络不可用或无对应版本），交由 Selenium Manager 定位')
    return None
