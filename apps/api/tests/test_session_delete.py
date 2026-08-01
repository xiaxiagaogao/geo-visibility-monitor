"""抓完即删会话的纯逻辑部分（不联网）。

接口行为来自 2026-08-01 在 VPS 上的实测，见 deepseek_web 里的注释。
最重要的一条：**HTTP 200 不代表成功**，缺 token 时返回
``{"code":40002,"msg":"Missing Token"}`` 但状态码仍是 200 ——
第一版实现只看 resp.ok，日志报「200 ok」而侧栏对话纹丝不动。
"""
from __future__ import annotations

import pytest

from app.providers.deepseek_web import (
    DELETE_SESSION_PATH,
    _delete_session,
    _session_id_from_url,
)

REAL_URL = "https://chat.deepseek.com/a/chat/s/8d3f68ea-edf5-48e6-a913-137b39e6bc01"
REAL_ID = "8d3f68ea-edf5-48e6-a913-137b39e6bc01"


def test_extracts_session_id_from_real_url():
    assert _session_id_from_url(REAL_URL) == REAL_ID


@pytest.mark.parametrize(
    "url",
    [
        "https://chat.deepseek.com/",  # 首页，还没建会话
        "https://chat.deepseek.com/sign_in",
        "",
        None,
    ],
)
def test_no_session_id(url):
    assert _session_id_from_url(url) is None


class _FakePage:
    """记录 evaluate 的入参，并按预设返回。"""

    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.calls = []

    def evaluate(self, script, arg=None):
        self.calls.append((script, arg))
        if self._raises:
            raise self._raises
        return self._result


def test_success():
    page = _FakePage({"status": 200, "code": 0, "msg": None, "had_token": True})
    assert _delete_session(page, REAL_ID) is True
    _, arg = page.calls[0]
    assert arg == {"path": DELETE_SESSION_PATH, "sessionId": REAL_ID}


def test_missing_token_is_not_success_despite_http_200():
    """实测踩过的坑：HTTP 200 + code 40002。"""
    page = _FakePage(
        {"status": 200, "code": 40002, "msg": "Missing Token", "had_token": False}
    )
    assert _delete_session(page, REAL_ID) is False


@pytest.mark.parametrize(
    "result",
    [
        {"status": 200, "code": 40003, "msg": "Forbidden", "had_token": True},
        {"status": 403, "code": None, "msg": None, "had_token": True},
        {"status": 500, "code": None, "msg": None, "had_token": True},
    ],
)
def test_other_failures(result):
    assert _delete_session(_FakePage(result), REAL_ID) is False


def test_code_absent_but_http_200_counts_as_success():
    """有些成功响应不带 code 字段。"""
    page = _FakePage({"status": 200, "code": None, "msg": None, "had_token": True})
    assert _delete_session(page, REAL_ID) is True


def test_swallows_exceptions():
    """删除失败绝不能让整个抓取任务失败 —— 证据已经落盘了。"""
    page = _FakePage(raises=RuntimeError("page closed"))
    assert _delete_session(page, REAL_ID) is False


def test_token_never_returned_to_python():
    """JS 的返回值里只能有状态字段 —— token 不出浏览器，也就进不了日志。"""
    import re

    from app.providers.deepseek_web import _DELETE_JS

    tail = _DELETE_JS[_DELETE_JS.index("return {") :]
    keys = set(re.findall(r"(\w+)\s*:", tail))
    assert keys == {"status", "code", "msg", "had_token"}, f"返回了预期外的字段: {keys}"
    # had_token 必须是布尔转换，不能把 token 本身漏出去
    assert "had_token: Boolean(token)" in tail
