# encoding=utf-8
import os
import shutil
import sys


def is_frozen() -> bool:
    """是否处于 PyInstaller 打包状态"""
    return getattr(sys, "frozen", False)


def runtime_root() -> str:
    """可写的运行根目录: 冻结时是 exe 所在目录, 源码时是项目根目录"""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(*parts) -> str:
    """只读资源路径: 冻结时优先从解压目录(_MEIPASS)读取打包进来的资源"""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None) or runtime_root()
    else:
        base = runtime_root()
    return os.path.join(base, *parts)


def config_path() -> str:
    """配置文件路径: 优先使用 exe 旁边的 configs.ini(可写), 不存在则从打包资源复制"""
    path = os.path.join(runtime_root(), "configs.ini")
    if not os.path.exists(path):
        bundled = resource_path("configs.ini")
        if os.path.exists(bundled):
            try:
                shutil.copyfile(bundled, path)
                print(f"已生成默认配置文件: {path}")
            except OSError as e:
                print(f"生成配置文件失败: {e}")
    return path


def get_runtime_path(*parts) -> str:
    """运行根目录下的可写文件路径(如 res/cookies.json)"""
    return os.path.join(runtime_root(), *parts)