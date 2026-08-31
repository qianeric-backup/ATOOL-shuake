# -*- coding: utf-8 -*-
"""
云班课 coreapi 接口封装（逆向自网页端 https://www.mosoteach.cn）
==============================================================
逆向结论：
  - 网页端登录: POST https://coreapi.mosoteach.cn/passports/account-login
      body: {"account": "手机号", "password": "明文密码"}
      响应: {"user": {...}, "token": "xxx", "status": true}
      之后所有请求带 header `X-token: <token>`
  - 班级课程列表: GET /ccs/joined                      -> {clazzCourses:[...]}
  - 资源列表:     GET /ccs/{ccId}/resources?roleId=2   -> 资源数组
  - 视频预览:     GET /ccs/{ccId}/resources/{resId}/viewer
  - 观看记录:     GET /ccs/{ccId}/resources/{resId}/records
  - 进度上报:     POST /ccs/{ccId}/resources/{resId}/records
      body: {"watchTo": 秒, "currentWatchTo": 秒, "duration": 秒}
      当 watchTo >= duration 时服务端判定为"已完成/已看完"

另: 密码字段确实可直接用明文（网页前端是 wasm 加密后传 ciphertext，
    但服务端同样接受明文 password —— 已实测登录成功）。
"""
import requests

BASE_URL = "https://coreapi.mosoteach.cn"
LOGIN_URL = BASE_URL + "/passports/account-login"
CC_JOINED_URL = BASE_URL + "/ccs/joined"
RES_LIST_URL = BASE_URL + "/ccs/{cc_id}/resources"
RES_VIEWER_URL = BASE_URL + "/ccs/{cc_id}/resources/{res_id}/viewer"
RES_RECORDS_URL = BASE_URL + "/ccs/{cc_id}/resources/{res_id}/records"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

STUDENT_ROLE_ID = 2  # 学生视角


class YunbankeError(Exception):
    pass


class Yunbanke:
    """云班课 API 客户端。"""

    def __init__(self, account="", password="", token=None):
        self.account = account
        self.password = password
        self.token = token
        self.user = None
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json;charset=utf-8",
            "X-client-app-id": "MTWEB",
            "X-client-version": "6.0.0",
            "X-security-type": "SECURITY_TYPE_TOKEN",
        })

    # ---------- 请求 ----------
    def _req(self, method, url, **kw):
        headers = kw.pop("headers", None) or {}
        if self.token:
            headers.setdefault("X-token", self.token)
        kw.setdefault("timeout", 20)
        resp = self._session.request(method, url, headers=headers, **kw)
        try:
            data = resp.json()
        except ValueError:
            raise YunbankeError("响应非 JSON: HTTP %d" % resp.status_code)
        return data

    # ---------- 登录 ----------
    def login(self, account=None, password=None):
        """登录并保存 token。account/password 缺省使用构造参数。返回用户信息 dict。"""
        self.account = account or self.account
        self.password = password or self.password
        if not self.account or not self.password:
            raise YunbankeError("缺少账号或密码")
        data = self._req("POST", LOGIN_URL,
                         json={"account": self.account, "password": self.password})
        if not data.get("status"):
            raise YunbankeError("登录失败: %s" % data.get("errorMessage", data))
        self.user = data.get("user", {})
        self.token = data.get("token")
        return self.user

    # ---------- 课程 ----------
    def list_courses(self):
        """返回加入的班课列表（clazzCourses）。"""
        data = self._req("GET", CC_JOINED_URL)
        if not data.get("status"):
            raise YunbankeError("获取课程失败: %s" % data.get("errorMessage", data))
        return data.get("clazzCourses", [])

    # ---------- 资源 ----------
    def list_resources(self, cc_id, role_id=STUDENT_ROLE_ID):
        """返回某班课的资源列表。"""
        data = self._req("GET", RES_LIST_URL.format(cc_id=cc_id),
                         params={"roleId": role_id})
        if not data.get("status"):
            raise YunbankeError("获取资源失败: %s" % data.get("errorMessage", data))
        # 兼容不同字段
        return data.get("resources") or data.get("data") or []

    def get_resource_detail(self, cc_id, res_id):
        data = self._req("GET", RES_LIST_URL.format(cc_id=cc_id) + "/" + res_id)
        return data

    def get_viewer_url(self, cc_id, res_id):
        """获取资源预览/视频播放地址。"""
        data = self._req("GET", RES_VIEWER_URL.format(cc_id=cc_id, res_id=res_id))
        return data

    def get_video_records(self, cc_id, res_id):
        """获取视频观看记录（含已看位置）。"""
        data = self._req("GET", RES_RECORDS_URL.format(cc_id=cc_id, res_id=res_id))
        return data

    def report_video_progress(self, cc_id, res_id, watch_to, current_watch_to,
                              duration):
        """上报视频学习进度。watch_to 达到 duration 即视为完成。"""
        body = {
            "watchTo": int(watch_to),
            "currentWatchTo": int(current_watch_to),
            "duration": int(duration),
        }
        data = self._req("POST", RES_RECORDS_URL.format(cc_id=cc_id, res_id=res_id),
                         json=body)
        return data


# ---------- 资源类型辅助 ----------
RES_TYPES = {
    "mp4": "视频",
    "wmv": "视频",
    "avi": "视频",
    "mov": "视频",
    "mkv": "视频",
    "flv": "视频",
    "ppt": "课件",
    "pptx": "课件",
    "doc": "文档",
    "docx": "文档",
    "pdf": "文档",
    "xls": "表格",
    "xlsx": "表格",
    "zip": "压缩包",
    "rar": "压缩包",
    "url": "链接",
    "other": "其他",
}


def res_type_name(resource):
    """根据资源对象或文件名推断类型。"""
    name = (resource.get("name") or resource.get("resName") or
            resource.get("fileName") or resource.get("title") or "")
    ext = name.split(".")[-1].lower() if "." in name else ""
    if "video" in str(resource.get("resType") or "").lower():
        return "视频"
    if "file" in str(resource.get("resType") or "").lower():
        return "文件"
    return RES_TYPES.get(ext, "其他")


def is_video(resource):
    return res_type_name(resource) == "视频"