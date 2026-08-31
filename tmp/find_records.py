# -*- coding: utf-8 -*-
"""扫描并输出任务模块中的反斜杠记录路径，用于修复"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
files = [
    r'学习通刷课/shuake_src/task/quiz_ai.py',
    r'学习通刷课/shuake_src/task/watch_vido.py',
    r'学习通刷课/shuake_src/task/tool/ai_wen_da.py',
]
for p in files:
    print('=====', p.split('/')[-1], '=====')
    lines = io.open(p, encoding='utf-8').read().split('\n')
    for i, l in enumerate(lines, 1):
        if 'record' in l and ('task\\\\' in l):
            print(i, repr(l))