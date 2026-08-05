"""平台注册表：「已知」与「能跑」必须是两件事（不依赖数据库）。

守的是这个真实缺陷（2026-08-05 修）：

    ALLOWED_PLATFORMS 放行 deepseek/doubao/kimi/tongyi 四个平台，
    而 real 模式下只有 deepseek 有 Provider。
    → 选豆包建任务返回 201，等 worker 领到才 RuntimeError 收成 failed。
    用户看到「抓取失败」，真相是「这个平台压根没接」。

以及：前端此前没有任何接口能问出「哪些平台可用」，只能硬编码。
"""
from __future__ import annotations

import pytest

from app.providers import registry


def test_known_but_not_implemented_is_a_real_state():
    """豆包是「已知平台」但没有 Provider —— 这两个状态不能混为一谈。"""
    assert registry.is_known("doubao")
    assert not registry.is_implemented("doubao")

    assert registry.is_known("deepseek")
    assert registry.is_implemented("deepseek")

    assert not registry.is_known("chatgpt")


def test_real_mode_blocks_unimplemented_platform():
    """real 模式下豆包不可跑 —— 这正是 create_jobs 要挡掉的那一刀。"""
    assert registry.is_runnable("deepseek", crawl_mode="real")
    assert not registry.is_runnable("doubao", crawl_mode="real")
    assert not registry.is_runnable("kimi", crawl_mode="real")
    assert not registry.is_runnable("tongyi", crawl_mode="real")


def test_fake_mode_allows_every_known_platform():
    """fake 模式全走 FakeProvider —— 不能因为「豆包没实现」把造数据也堵死。"""
    for code in registry.known_codes():
        assert registry.is_runnable(code, crawl_mode="fake"), code
    # 未知平台在任何模式下都不可跑
    assert not registry.is_runnable("chatgpt", crawl_mode="fake")


def test_crawl_mode_none_defaults_to_fake():
    """settings.crawl_mode 默认就是 fake，None 要按 fake 解释而不是崩掉。"""
    assert registry.is_runnable("doubao", crawl_mode=None)


def test_build_real_provider_raises_for_unimplemented():
    ctx = registry.ProviderContext(settings=object(), sample_index=1, brand_names=["x"])
    with pytest.raises(RuntimeError) as exc:
        registry.build_real_provider("doubao", ctx)
    # 报错要指出「有哪些是实现了的」，否则排查还得回来翻代码
    assert "deepseek" in str(exc.value)


def test_describe_marks_unavailable_with_reason():
    items = {p["code"]: p for p in registry.describe(crawl_mode="real")}

    assert items["deepseek"]["available"] is True
    assert items["deepseek"]["implemented"] is True
    assert items["deepseek"]["note"] is None

    doubao = items["doubao"]
    assert doubao["available"] is False
    assert doubao["implemented"] is False
    assert doubao["note"], "不可用必须给出原因，否则前端只能显示一个哑的灰块"
    assert doubao["label"] == "豆包", "chip 上要显示中文名，不是 code"


def test_describe_fake_mode_flags_that_data_is_fake():
    """fake 模式下豆包「可跑」，但必须说明产出是假数据 —— 否则等于骗人。"""
    items = {p["code"]: p for p in registry.describe(crawl_mode="fake")}
    doubao = items["doubao"]
    assert doubao["available"] is True
    assert doubao["implemented"] is False
    assert "假数据" in (doubao["note"] or "")


def test_allowed_platforms_is_derived_not_duplicated():
    """schemas 里的 ALLOWED_PLATFORMS 必须来自注册表，不能是另抄的一份常量。"""
    from app.schemas.crawl import ALLOWED_PLATFORMS

    assert tuple(ALLOWED_PLATFORMS) == registry.known_codes()


def test_every_builder_has_a_declared_platform():
    """注册了 builder 却忘了登记 label —— 那个平台前端永远看不到，只能靠这条测出来。"""
    builders = set(registry._REAL_BUILDERS)
    assert builders, "至少要有一个平台是实现了的"
    missing = builders - set(registry.known_codes())
    assert not missing, f"这些平台有 Provider 但没登记进 PLATFORMS：{sorted(missing)}"
