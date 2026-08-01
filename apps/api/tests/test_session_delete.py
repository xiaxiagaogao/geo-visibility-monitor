"""抓完即删会话的逻辑（不联网，用假 locator 驱动）。

实测记录（2026-08-01，VPS）：
- 直调 /api/v0/chat_session/delete 需要 Authorization: Bearer <token>，
  缺 token 时返回 **HTTP 200** + {"code":40002,"msg":"Missing Token"} ——
  只看 resp.ok 会被骗（第一版就是这么假装成功的：日志报 200 ok，侧栏纹丝不动）。
- token 不在 cookie 也不在 localStorage，故改走侧栏 UI。
- 确认按钮文案是「删除该对话」，不是「确定」。
"""
from __future__ import annotations

import pytest

from app.providers.deepseek_web import (
    DELETE_CONFIRM_TEXT,
    DELETE_MENU_TEXT,
    SIDEBAR_ITEM_SEL,
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


class _Loc:
    """极简 locator 替身。counts 是一个可变列表，用来模拟「删除后条目消失」。"""

    def __init__(self, counts, buttons=1, log=None):
        self._counts = counts
        self._buttons = buttons
        self.log = log if log is not None else []

    def count(self):
        return self._counts.pop(0) if len(self._counts) > 1 else self._counts[0]

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def locator(self, sel):
        return _Loc([self._buttons], self._buttons, self.log)

    def scroll_into_view_if_needed(self, timeout=None):
        self.log.append("scroll")

    def hover(self, timeout=None):
        self.log.append("hover")

    def click(self, timeout=None):
        self.log.append("click")


class _Page:
    def __init__(self, item_counts, buttons=1, raise_on=None):
        self.log = []
        self._item_counts = item_counts
        self._buttons = buttons
        self._raise_on = raise_on
        self.selectors = []

    def locator(self, sel):
        self.selectors.append(sel)
        return _Loc(self._item_counts, self._buttons, self.log)

    def get_by_text(self, text, exact=False):
        if self._raise_on == text:
            raise RuntimeError(f"菜单里没有 {text}")
        self.log.append(f"text:{text}")
        return _Loc([1], self._buttons, self.log)

    def wait_for_timeout(self, ms):
        pass


def test_happy_path_clicks_menu_then_confirm():
    # 第一次 count()=1（找到），复核时 count()=0（已消失）
    page = _Page(item_counts=[1, 0])
    assert _delete_session(page, REAL_ID) is True
    assert f"text:{DELETE_MENU_TEXT}" in page.log
    assert f"text:{DELETE_CONFIRM_TEXT}" in page.log


def test_targets_by_session_id_not_by_title():
    """必须按 href 精确定位 —— 账号里绝大多数是用户私人对话。"""
    page = _Page(item_counts=[1, 0])
    _delete_session(page, REAL_ID)
    assert any(REAL_ID in s for s in page.selectors)
    assert all(SIDEBAR_ITEM_SEL in s for s in page.selectors)


def test_session_not_in_sidebar():
    page = _Page(item_counts=[0])
    assert _delete_session(page, REAL_ID) is False


def test_no_more_button():
    page = _Page(item_counts=[1, 0], buttons=0)
    assert _delete_session(page, REAL_ID) is False


def test_item_still_present_after_clicking_is_failure():
    """点完了但没消失 —— 不能report成功（第一版就是败在没复核）。"""
    page = _Page(item_counts=[1, 1])
    assert _delete_session(page, REAL_ID) is False


def test_menu_missing_is_swallowed():
    page = _Page(item_counts=[1, 0], raise_on=DELETE_MENU_TEXT)
    assert _delete_session(page, REAL_ID) is False


def test_confirm_missing_is_swallowed():
    """确认按钮文案变了（比如改回「确定」）时不能静默当成功。"""
    page = _Page(item_counts=[1, 0], raise_on=DELETE_CONFIRM_TEXT)
    assert _delete_session(page, REAL_ID) is False
