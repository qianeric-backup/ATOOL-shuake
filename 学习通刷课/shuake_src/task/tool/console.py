# -*- coding: utf-8 -*-
"""控制台输出编码统一（子进程日志乱码的根治点）。

问题：Windows 下 Python 的 stdout 走管道/重定向时默认用 locale 编码（GBK），
而 GUI（qt_ui / start_tk）按 UTF-8 解码子进程输出 —— 刷课日志、进度回显里的
中文要么被 errors='ignore' 整段丢掉，要么显示成乱码。

做法：把子进程的 stdout/stderr 统一切到 UTF-8，父子两端编码一致。
只在 stdout 不是交互终端时改写（管道/重定向场景）；直接在控制台运行时保持
原样，避免把 GBK 控制台的中文变成乱码。
"""
import io
import sys

_UTF8_NAMES = ('utf-8', 'utf8')


def _is_tty(stream):
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _encoding_of(stream):
    try:
        return (stream.encoding or '').lower().replace('_', '-')
    except Exception:
        return ''


def _switch(stream, name):
    """把单个流切到 UTF-8（3.7+ 用 reconfigure，否则用 buffer 重包一层）"""
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure is not None:
        try:
            # line_buffering：日志按行即时送 GUI，不再整段缓冲后一次性刷出
            reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
            return True
        except (ValueError, OSError):
            pass
    buffer = getattr(stream, 'buffer', None)
    if buffer is None:
        return False
    try:
        setattr(sys, name, io.TextIOWrapper(buffer, encoding='utf-8',
                                            errors='replace',
                                            line_buffering=True))
        return True
    except Exception:
        return False


def ensure_utf8_stdout(force=False):
    """把 sys.stdout / sys.stderr 切到 UTF-8；返回被切换的流名列表。

    :param force: True 时连交互终端也切（默认只在管道/重定向时切）
    """
    switched = []
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        if not force and _is_tty(stream):
            continue
        if _encoding_of(stream) in _UTF8_NAMES:
            continue          # 已经是 UTF-8，不重复包装（幂等）
        if _switch(stream, name):
            switched.append(name)
    return switched
