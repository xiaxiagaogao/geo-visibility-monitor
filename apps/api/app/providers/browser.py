"""浏览器启动的统一入口（P2-06a）。

## 为什么要有这一层

2026-08-15 接豆包时，第一条探针提问就把登录态打掉了（页面跳 `?from_logout=1`）。
在采集节点容器里实测，crawler 的浏览器有**四个**明着写着「我是自动化」的破绽：

===================  ==========================  ============================
检测点                旧 headless（当时的用法）     新 headless + 本模块
===================  ==========================  ============================
navigator.webdriver   ``True``                    ``False``
navigator.plugins     ``0``                       ``5``
window.chrome         ``undefined``               ``object``
User-Agent            ``HeadlessChrome/131…``     ``Chrome/131.0.0.0``
===================  ==========================  ============================

**关键发现：`channel="chromium"`（新 headless 模式）白送 `plugins` 与
`window.chrome`。** 这两项本来只能靠注入脚本伪造，而笨拙的注入本身就是指纹 ——
不一致的覆盖比不覆盖更可疑。所以本模块**不做任何 stealth 注入**，
只做「让浏览器看起来像一个普通浏览器」：

- 用真实的浏览器模式（新 headless），不是精简过的调试模式
- 不主动广播自动化标志（`--enable-automation` / `AutomationControlled`）
- UA 不撒谎说自己是 Headless

这条线是能站住的；伪造 plugins 列表、伪装成 Windows 就跨过去了，本模块不做。

## 还有一条比参数更重要的：出生环境要等于使用环境

`scripts/export_storage_state.py` 用 `launch_persistent_context` 建登录态，
而 provider 原先用 `launch()` + `storage_state=` 装载 —— **会话在一种浏览器里
出生，却在另一种里使用**。本模块同时供两边调用，就是为了消灭这个差异。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("geo.browser")

#: 新 headless。`plugins` 与 `window.chrome` 全靠它 —— 见模块 docstring 的对照表。
#: 环境里没有这个 channel 时会回落到旧 headless（`launch_kwargs` 里有兜底）。
CHROMIUM_CHANNEL = "chromium"

#: 关掉 blink 层那个「我被自动化控制」的标志位。
#: 这一项**只解决 navigator.webdriver**，别指望它管别的。
HARDENED_ARGS: List[str] = [
    "--disable-blink-features=AutomationControlled",
]

#: Playwright 默认会传 `--enable-automation`，它会让 Chrome 顶部出现
#: 「正受到自动测试软件控制」并暴露相关标志。去掉它。
IGNORED_DEFAULT_ARGS: List[str] = ["--enable-automation"]


def strip_headless_marker(ua: str) -> str:
    """把 UA 里的 ``HeadlessChrome/`` 换成 ``Chrome/``。纯函数。

    **UA 是四个破绽里最直白的一个** —— 比 ``navigator.webdriver`` 还明显，
    而且参数改不掉，只能在建 context 时显式覆盖。

    新 headless 报的是 ``HeadlessChrome/131.0.0.0``（主版本 + 三个零），
    换掉标记之后正好是 ``Chrome/131.0.0.0`` —— 与真实 Chrome 的
    UA Reduction 输出**逐字一致**，不需要再编版本号。
    """
    return ua.replace("HeadlessChrome/", "Chrome/")


def launch_kwargs(*, headless: bool = True, use_new_headless: bool = True) -> Dict[str, Any]:
    """给 ``launch`` / ``launch_persistent_context`` 的启动参数。纯函数，可单测。"""
    kw: Dict[str, Any] = {
        "headless": headless,
        "args": list(HARDENED_ARGS),
        "ignore_default_args": list(IGNORED_DEFAULT_ARGS),
    }
    if use_new_headless:
        kw["channel"] = CHROMIUM_CHANNEL
    return kw


_cached_ua: Optional[str] = None


def resolve_user_agent(playwright, *, headless: bool = True) -> Optional[str]:
    """起一个一次性浏览器读出 UA，去掉 Headless 标记后**按进程缓存**。

    为什么要多起一次：建 context 时就得把 UA 交进去，而 UA 里的版本号
    只有浏览器自己知道 —— 写死版本号会在下次升级镜像时悄悄过期，
    变成一个「声称是 131、实际是 133」的新破绽。

    失败返回 ``None``（调用方不覆盖 UA）—— 这是加固，不是必需品，
    不该因为读不到 UA 就让整个抓取起不来。
    """
    global _cached_ua
    if _cached_ua is not None:
        return _cached_ua
    try:
        browser = playwright.chromium.launch(**launch_kwargs(headless=headless))
        try:
            page = browser.new_page()
            raw = page.evaluate("() => navigator.userAgent")
        finally:
            browser.close()
        _cached_ua = strip_headless_marker(raw or "") or None
        if _cached_ua and _cached_ua != raw:
            logger.info("UA 已去掉 Headless 标记: %s", _cached_ua)
        return _cached_ua
    except Exception:  # noqa: BLE001
        logger.warning("读不到 UA，本次不覆盖（不影响抓取）", exc_info=True)
        return None


def context_kwargs(
    *,
    user_agent: Optional[str],
    locale: str = "zh-CN",
    timezone_id: str = "Asia/Shanghai",
    viewport: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """建 context 的参数。纯函数。

    ``timezone_id`` 必须和采集出口所在地区一致 —— 见 `BACKEND.md` §7.2 那次
    「IP 在长沙、时区在伦敦」的事故。
    """
    kw: Dict[str, Any] = {
        "locale": locale,
        "timezone_id": timezone_id,
        "viewport": viewport or {"width": 1280, "height": 900},
    }
    if user_agent:
        kw["user_agent"] = user_agent
    return kw


def launch_persistent(
    playwright,
    *,
    user_data_dir: str,
    headless: bool = True,
    locale: str = "zh-CN",
    timezone_id: str = "Asia/Shanghai",
    viewport: Optional[Dict[str, int]] = None,
):
    """按 **persistent context** 起浏览器 —— 和导出登录态时用的是同一种。

    用 ``user_data_dir`` 而不是 ``storage_state=``：后者等于把会话从一个浏览器
    移植到另一个，而**出生环境与使用环境不一致本身就是信号**。
    """
    ua = resolve_user_agent(playwright, headless=headless)
    kw = launch_kwargs(headless=headless)
    kw.update(context_kwargs(user_agent=ua, locale=locale,
                             timezone_id=timezone_id, viewport=viewport))
    try:
        return playwright.chromium.launch_persistent_context(user_data_dir, **kw)
    except Exception:  # noqa: BLE001
        # 环境里没有 `chromium` channel（老镜像）时回落到旧 headless。
        # **会退化成可被检测的形态**，所以要吼一声，不能静默降级
        logger.warning("新 headless 不可用，回落旧 headless —— 指纹会更容易被识别", exc_info=True)
        kw = launch_kwargs(headless=headless, use_new_headless=False)
        kw.update(context_kwargs(user_agent=ua, locale=locale,
                                 timezone_id=timezone_id, viewport=viewport))
        return playwright.chromium.launch_persistent_context(user_data_dir, **kw)


def seed_storage_state(context, state_path: str, *, timeout_ms: int = 60_000) -> bool:
    """把导出的 ``storage_state`` 灌进一个 **persistent context**。

    ``launch_persistent_context`` **不接受 ``storage_state=``** —— 那是
    ``new_context`` 的参数。而我们又必须用 persistent context（见模块 docstring：
    出生环境要等于使用环境），所以只能手动灌。

    顺序不能反：**先 cookies，再导航到该 origin，最后写 localStorage** ——
    localStorage 是按 origin 隔离的，没导航过去就没有可写的存储区。

    失败只记日志返回 ``False``，不抛 —— 灌不进去的表现是「登录墙」，
    而那条路径 provider 本来就处理得了，不该在这里炸掉整次抓取。
    """
    import json as _json
    from pathlib import Path as _Path

    try:
        state = _json.loads(_Path(state_path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("读不了 storage_state: %s", state_path, exc_info=True)
        return False

    cookies = state.get("cookies") or []
    if cookies:
        try:
            context.add_cookies(cookies)
        except Exception:  # noqa: BLE001
            logger.warning("add_cookies 失败", exc_info=True)
            return False

    origins = state.get("origins") or []
    if not origins:
        return True

    page = context.pages[0] if context.pages else context.new_page()
    ok = True
    for o in origins:
        origin = o.get("origin")
        items = o.get("localStorage") or []
        if not origin or not items:
            continue
        try:
            page.goto(origin, wait_until="domcontentloaded", timeout=timeout_ms)
            page.evaluate(
                """(items) => { for (const it of items) {
                     try { localStorage.setItem(it.name, it.value); } catch (e) {}
                   } }""",
                items,
            )
        except Exception:  # noqa: BLE001
            logger.warning("localStorage 灌入失败 origin=%s", origin, exc_info=True)
            ok = False
    return ok
