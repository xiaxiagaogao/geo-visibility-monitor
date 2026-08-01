"""抓完即删会话的纯逻辑部分（不联网）。

接口格式来自 2026-08-01 在 VPS 上的实测抓包，见 deepseek_web.DELETE_SESSION_API。
"""
from __future__ import annotations

import pytest

from app.providers.deepseek_web import (
    DELETE_SESSION_API,
    _delete_session,
    _session_id_from_url,
)

REAL_URL = "https://chat.deepseek.com/a/chat/s/09d05f18-250b-4d5d-a570-a63866c1d65d"
REAL_ID = "09d05f18-250b-4d5d-a570-a63866c1d65d"


def test_extracts_session_id_from_real_url():
    assert _session_id_from_url(REAL_URL) == REAL_ID


@pytest.mark.parametrize(
    "url",
    [
        "https://chat.deepseek.com/",           # 首页，还没建会话
        "https://chat.deepseek.com/sign_in",
        "",
        None,
    ],
)
def test_no_session_id(url):
    assert _session_id_from_url(url) is None


class _FakeResponse:
    def __init__(self, ok=True, status=200, body=""):
        self.ok = ok
        self.status = status
        self._body = body

    def text(self):
        return self._body


class _FakeRequest:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    def post(self, url, data=None, headers=None):
        self.calls.append((url, data, headers))
        if self._raises:
            raise self._raises
        return self._response


class _FakePage:
    def __init__(self, request):
        self.request = request


def test_delete_posts_expected_payload():
    req = _FakeRequest(_FakeResponse(ok=True, status=200))
    assert _delete_session(_FakePage(req), REAL_ID) is True

    url, data, headers = req.calls[0]
    assert url == DELETE_SESSION_API
    assert data == {"chat_session_id": REAL_ID}
    assert headers["content-type"] == "application/json"


def test_delete_reports_failure_without_raising():
    req = _FakeRequest(_FakeResponse(ok=False, status=403, body="forbidden"))
    assert _delete_session(_FakePage(req), REAL_ID) is False


def test_delete_swallows_exceptions():
    """删除失败绝不能让整个抓取任务失败 —— 证据已经落盘了。"""
    req = _FakeRequest(raises=RuntimeError("network down"))
    assert _delete_session(_FakePage(req), REAL_ID) is False
