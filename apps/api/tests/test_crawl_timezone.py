"""浏览器上报的时区（2026-08-15）。纯构造，不需要数据库也不需要 playwright。

为什么要有这条：采集出口迁到大陆之后，页面看到的仍然是
`Intl.DateTimeFormat().resolvedOptions().timeZone == "UTC"`（offset 0）——
因为 Provider 只设了 `locale="zh-CN"`，从没设 `timezone_id`，
Playwright 就取了容器的系统时区，而容器是 UTC。

于是服务端看到的是「IP 在长沙、语言中文、时区在伦敦」。
这条用例钉住「时区跟着出口走」这件事，别再退回去。
"""
from __future__ import annotations

from app.core.config import Settings
from app.providers.registry import ProviderContext, build_real_provider


def _provider(**over):
    settings = Settings(**over)
    return build_real_provider(
        "deepseek",
        ProviderContext(settings=settings, sample_index=1, brand_names=["安踏"]),
    )


def test_default_timezone_matches_the_mainland_exit():
    assert _provider().timezone_id == "Asia/Shanghai"


def test_timezone_is_configurable_for_the_cold_standby():
    """VPS 上那台冷备的出口是新加坡。切过去时时区也要跟着改 ——
    否则只是把一种不一致换成另一种。"""
    assert _provider(crawl_timezone_id="Asia/Singapore").timezone_id == "Asia/Singapore"


def test_timezone_is_never_empty():
    """空串会让 Playwright 回落到容器的系统时区（UTC），正是要修的那个默认。"""
    assert Settings().crawl_timezone_id.strip()
