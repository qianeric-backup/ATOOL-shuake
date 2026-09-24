# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'C:/Users/qianeric/Documents/reasonix-project/云班课刷课/yunbanke_qt')
from api import Yunbanke

y = Yunbanke('ACCOUNT_PLACEHOLDER', 'PASSWORD_PLACEHOLDER')
user = y.login()
print('登录用户:', user.get('nickName'), '|', user.get('fullName'))
courses = y.list_courses()
print('课程数量:', len(courses))
for c in courses:
    print(' -', c.get('name') or c.get('clazzCourseName'), c.get('id') or c.get('ccId'))