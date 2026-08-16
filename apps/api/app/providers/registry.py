"""平台注册表 —— 「有哪些平台」与「哪些真能跑」的唯一真相源。

这里刻意把两件事分开：

============  ==================================================================
**已知平台**   ``platform`` 列的合法取值。历史数据按它解释，即使 Provider 还没写
**已实现**     real 模式下**真的有 Provider 能跑完一次抓取**
============  ==================================================================

**为什么要有这个文件（2026-08-05）**

在此之前这两件事分散在两处，而且不一致：

- ``schemas/crawl.py`` 的 ``ALLOWED_PLATFORMS`` 放行 deepseek/doubao/kimi/tongyi 四个
- ``crawl_runner._build_provider`` 在 real 模式下只认 deepseek，其余直接 RuntimeError

于是选豆包建任务会 **201 建成功**，等 worker 领到才 failed —— 用户看到的是
「抓取失败」，而真相是「这个平台压根没接」。两者的排查方向完全不同。

同时前端**没有任何接口**能问出「哪些平台可用」，只能把可用性硬编码进代码，
接第二个平台时前后端都要改。

现在两件事都从这里派生：``_build_provider`` 用 ``build_real_provider``，
``create_jobs`` 用 ``ensure_runnable``，``GET /v1/config/platforms`` 用 ``describe``。
**加平台只改这一个文件。**
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.providers.base import BaseProvider
from app.providers.deepseek_web import DeepSeekWebProvider
from app.providers.doubao_web import DoubaoWebProvider
from app.providers.qianwen_web import QianwenWebProvider


@dataclass(frozen=True)
class ProviderContext:
    """构造 Provider 需要的一切，避免注册表反向依赖 db / ORM。"""

    settings: Any
    sample_index: int
    brand_names: List[str]


ProviderBuilder = Callable[[ProviderContext], BaseProvider]


def _build_deepseek(ctx: ProviderContext) -> BaseProvider:
    s = ctx.settings
    return DeepSeekWebProvider(
        headless=s.playwright_headless,
        timeout_ms=s.crawl_timeout_ms,
        storage_state=s.deepseek_storage_state or None,
        user_data_dir=s.deepseek_user_data_dir or None,
        screenshot_dir=s.screenshot_dir or None,
        delete_session_after=s.deepseek_delete_session,
        timezone_id=s.crawl_timezone_id,
    )


def _build_doubao(ctx: ProviderContext) -> BaseProvider:
    s = ctx.settings
    return DoubaoWebProvider(
        headless=s.playwright_headless,
        timeout_ms=s.crawl_timeout_ms,
        storage_state=s.doubao_storage_state or None,
        user_data_dir=s.doubao_user_data_dir or None,
        screenshot_dir=s.screenshot_dir or None,
        delete_session_after=s.doubao_delete_session,
        timezone_id=s.crawl_timezone_id,
    )


def _build_tongyi(ctx: ProviderContext) -> BaseProvider:
    s = ctx.settings
    return QianwenWebProvider(
        headless=s.playwright_headless,
        timeout_ms=s.crawl_timeout_ms,
        storage_state=s.tongyi_storage_state or None,
        # **持久 profile 从第一天就接上** —— 豆包漏了这一项，
        # 结果每条 job 一个临时 profile（PHASE2 现象 C）
        user_data_dir=s.tongyi_user_data_dir or None,
        screenshot_dir=s.screenshot_dir or None,
        delete_session_after=s.tongyi_delete_session,
        timezone_id=s.crawl_timezone_id,
    )


#: 有 real Provider 的平台。**没进这个表 = 没实现**，不需要另外维护一份布尔值。
_REAL_BUILDERS: Dict[str, ProviderBuilder] = {
    "deepseek": _build_deepseek,
    "doubao": _build_doubao,
    "tongyi": _build_tongyi,
}


@dataclass(frozen=True)
class Platform:
    code: str
    label: str
    #: 未实现时给前端的说明；实现了就是 None
    note: Optional[str] = None


#: 已知平台。顺序即前端 chip 的展示顺序。
PLATFORMS: Tuple[Platform, ...] = (
    Platform("deepseek", "DeepSeek"),
    Platform("doubao", "豆包"),
    Platform("kimi", "Kimi", note="Provider 未实现"),
    # 站点已改名叫「千问」（qianwen.com），但平台代码保持 tongyi ——
    # 它在 ALLOWED_PLATFORMS 与历史数据里，改代码等于一次数据迁移
    Platform("tongyi", "通义千问"),
)

_BY_CODE: Dict[str, Platform] = {p.code: p for p in PLATFORMS}


def known_codes() -> Tuple[str, ...]:
    return tuple(p.code for p in PLATFORMS)


def is_known(code: str) -> bool:
    return code in _BY_CODE


def is_implemented(code: str) -> bool:
    """real 模式下这个平台能不能真跑。"""
    return code in _REAL_BUILDERS


def label_of(code: str) -> str:
    p = _BY_CODE.get(code)
    return p.label if p else code


def _is_fake_mode(crawl_mode: Optional[str]) -> bool:
    return (crawl_mode or "fake").lower() == "fake"


def is_runnable(code: str, *, crawl_mode: Optional[str]) -> bool:
    """建了任务之后**能不能真的跑完**。

    fake 模式下所有已知平台都走 FakeProvider，因此都可跑 —— 本机/CI 造数据靠这个，
    不能因为「豆包没实现」就把 fake 测试也堵死。
    """
    if not is_known(code):
        return False
    if _is_fake_mode(crawl_mode):
        return True
    return is_implemented(code)


def build_real_provider(code: str, ctx: ProviderContext) -> BaseProvider:
    """real 模式下构造 Provider；未实现的平台在这里明确报错。"""
    builder = _REAL_BUILDERS.get(code)
    if builder is None:
        raise RuntimeError(
            f"real crawl not implemented for platform={code}; "
            f"implemented={sorted(_REAL_BUILDERS)} or use crawl_mode=fake"
        )
    return builder(ctx)


def describe(*, crawl_mode: Optional[str]) -> List[dict]:
    """给 ``GET /v1/config/platforms``：前端据此渲染 chip 的可点 / 灰显。

    ``available`` 的语义是**「现在建任务能跑完吗」**，不是「代码里有没有这个常量」。
    """
    fake = _is_fake_mode(crawl_mode)
    out: List[dict] = []
    for p in PLATFORMS:
        available = is_runnable(p.code, crawl_mode=crawl_mode)
        if available and fake and not is_implemented(p.code):
            note = "当前为 fake 模式，产出的是假数据"
        elif available:
            note = None
        else:
            note = p.note or "未接入"
        out.append(
            {
                "code": p.code,
                "label": p.label,
                "available": available,
                "implemented": is_implemented(p.code),
                "note": note,
            }
        )
    return out
