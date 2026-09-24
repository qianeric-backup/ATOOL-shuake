# encoding=utf-8
"""核心逻辑单元测试:
- modules.paths: 源码/冻结路径解析、资源路径、配置文件初始化
- qt_gui: 配置文件读写往返一致性(不污染项目 configs.ini)
"""
import os
import sys
import tempfile
import unittest
import configparser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class TestPaths(unittest.TestCase):
    def test_runtime_root_source(self):
        from modules import paths
        self.assertFalse(paths.is_frozen())
        root = paths.runtime_root()
        self.assertEqual(root, HERE)

    def test_resource_path(self):
        from modules import paths
        p = paths.resource_path("res", "stealth.min.js")
        self.assertEqual(p, os.path.join(HERE, "res", "stealth.min.js"))
        self.assertTrue(os.path.exists(p))

    def test_config_path_source(self):
        from modules import paths
        self.assertEqual(paths.config_path(), os.path.join(HERE, "configs.ini"))
        self.assertTrue(os.path.exists(paths.config_path()))

    def test_frozen_routes(self):
        # 模拟 PyInstaller 冻结环境
        from modules import paths
        old_frozen = getattr(sys, "frozen", None)
        old_exec = sys.executable
        old_meipass = getattr(sys, "_MEIPASS", None)
        try:
            sys.frozen = True
            sys.executable = os.path.join("D:\\app", "AutovisorGUI.exe")
            sys._MEIPASS = os.path.join("C:\\tmp", "_MEI12345")
            self.assertEqual(paths.runtime_root(), "D:\\app")
            self.assertEqual(paths.resource_path("res", "zhs.ico"),
                             os.path.join("C:\\tmp", "_MEI12345", "res", "zhs.ico"))
            self.assertEqual(paths.get_runtime_path("res", "cookies.json"),
                             os.path.join("D:\\app", "res", "cookies.json"))
        finally:
            if old_frozen is None:
                delattr(sys, "frozen")
            else:
                sys.frozen = old_frozen
            sys.executable = old_exec
            if old_meipass is None:
                if hasattr(sys, "_MEIPASS"):
                    delattr(sys, "_MEIPASS")
            else:
                sys._MEIPASS = old_meipass


class TestConfigIO(unittest.TestCase):
    def _make_cfg(self):
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(HERE, "configs.ini"), encoding="utf-8")
        return cfg

    def test_load_defaults(self):
        from qt_gui import load_form_values
        vals = load_form_values(self._make_cfg())
        self.assertEqual(vals[0], "Edge")      # 浏览器默认 Edge
        self.assertEqual(vals[1], "")          # URL1 默认空
        self.assertEqual(vals[4], "30")        # 时长默认 30
        self.assertEqual(vals[5], "1.0")       # 倍速默认 1.0
        self.assertTrue(vals[6])               # 自动滑块默认 True
        self.assertFalse(vals[7])              # 隐藏窗口默认 False
        self.assertTrue(vals[8])               # 静音默认 True

    def test_roundtrip_in_tempfile(self):
        from qt_gui import save_form_values, read_config
        cfg = self._make_cfg()
        tmp = tempfile.mkdtemp()
        import qt_gui
        old = qt_gui.CONFIG_FILE
        qt_gui.CONFIG_FILE = os.path.join(tmp, "configs.ini")
        try:
            save_form_values(cfg, "Firefox",
                             "https://studyvideoh5.zhihuishu.com/course?x=1",
                             "13800000000", "secret", "45", "1.5",
                             True, False, True)
            cfg2 = read_config()
            self.assertEqual(cfg2.get("browser-option", "driver"), "Firefox")
            self.assertEqual(cfg2.get("course-url", "URL1"),
                             "https://studyvideoh5.zhihuishu.com/course?x=1")
            self.assertEqual(cfg2.get("user-account", "username"), "13800000000")
            self.assertEqual(cfg2.get("user-account", "password"), "secret")
            self.assertEqual(cfg2.get("course-option", "limitMaxTime"), "45")
            self.assertEqual(cfg2.get("course-option", "limitSpeed"), "1.5")
            self.assertEqual(cfg2.get("script-option", "enableAutoCaptcha"), "True")
            self.assertEqual(cfg2.get("script-option", "enableHideWindow"), "False")
            self.assertEqual(cfg2.get("course-option", "soundOff"), "True")
        finally:
            qt_gui.CONFIG_FILE = old


if __name__ == "__main__":
    unittest.main(verbosity=2)