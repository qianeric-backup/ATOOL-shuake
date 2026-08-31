# -*- coding: utf-8 -*-
"""验证 exe 可启动：启动子进程，等 6 秒，确认进程仍存活（未闪退），然后结束。"""
import subprocess
import time
import sys

exe = r"C:/Users/qianeric/Documents/reasonix-project/云班课刷课/dist/云班课刷课助手.exe"

p = subprocess.Popen([exe], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(6)
rc = p.poll()
if rc is None:
    print("RUNNING OK: exe 启动后 6 秒仍存活（未闪退）")
    p.terminate()
else:
    out, err = p.communicate(timeout=5)
    print("EXE EXITED rc=%s" % rc)
    print("stdout:", out.decode("utf-8", "replace")[:500])
    print("stderr:", err.decode("utf-8", "replace")[:500])
    sys.exit(1)