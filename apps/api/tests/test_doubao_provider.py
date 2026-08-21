"""豆包 Provider 的接线与常量（P2-06a）。不需要 playwright，本机可跑。

真正的抓取逻辑要在采集节点上验（真浏览器 + 真登录态），这里钉的是
**「接错线」这类静默失效**：常量抄错、注册表漏登记、登录墙没归对类。

选择器常量全部来自 2026-08-15 在节点上的实测，见模块与 `PHASE2` 的记录。
"""
from __future__ import annotations

import time

import pytest

from app.core.config import Settings
from app.providers import registry
from app.providers.doubao_web import (
    ANSWER_SELECTOR,
    DELETE_MENU_TEXT,
    DOUBAO_URL,
    INPUT_SELECTOR,
    STREAMING_ATTR,
    DoubaoAnswerTimeout,
    DoubaoLoginRequired,
    DoubaoWebProvider,
    _wait_for_answer,
)


# ---------------------------------------------------------------- 选择器


def test_input_selector_is_placeholder_scoped_not_bare_textarea():
    """**页面上有两个 `textarea`，第二个是 `aria-hidden` 的隐藏替身。**

    照抄 DeepSeek 的裸 `textarea` 会点到假的 —— 2026-08-15 实测踩过，
    表现是 `Locator.click` 超时（element is not visible）。
    """
    assert INPUT_SELECTOR != "textarea"
    assert "placeholder=" in INPUT_SELECTOR


def test_answer_selector_uses_the_stable_class_not_the_hash():
    """答案气泡的 class 是 `container-qX9Csx md-box-root` ——
    前一半是 CSS Modules 生成的哈希，**每次构建都会变**，不能用。"""
    assert ANSWER_SELECTOR == ".md-box-root"
    assert "container-" not in ANSWER_SELECTOR


def test_streaming_attr_is_the_completion_signal():
    """豆包给了状态位，比 DeepSeek 的长度轮询准 —— 但仍保留长度兜底，
    因为状态位是它的实现细节，改版时会先于选择器失效。"""
    assert STREAMING_ATTR == "data-streaming"


def test_delete_menu_text_matches_the_real_menu():
    """实测菜单：置顶 / 分享 / 重命名 / 移动到项目 / 删除。"""
    assert DELETE_MENU_TEXT == "删除"


def test_url_is_the_chat_entry():
    assert DOUBAO_URL.startswith("https://www.doubao.com/chat")


# ---------------------------------------------------------------- 注册表


def test_doubao_is_registered_and_runnable_in_real_mode():
    assert registry.is_known("doubao")
    assert registry.is_implemented("doubao")
    assert registry.is_runnable("doubao", crawl_mode="real")


def test_registry_builds_a_doubao_provider_with_settings_wired():
    """**接线漏一项不会报错，只会让那个设置永远是默认值。**"""
    s = Settings(
        crawl_mode="real",
        doubao_storage_state="/data/doubao_storage.json",
        doubao_user_data_dir="/data/doubao_profile",
        crawl_timezone_id="Asia/Shanghai",
        crawl_timeout_ms=99_000,
        doubao_delete_session=False,
    )
    pv = registry.build_real_provider(
        "doubao", registry.ProviderContext(settings=s, sample_index=1, brand_names=["安踏"])
    )

    assert isinstance(pv, DoubaoWebProvider)
    assert pv.platform == "doubao"
    assert pv.storage_state == "/data/doubao_storage.json"
    assert pv.timezone_id == "Asia/Shanghai"
    assert pv.timeout_ms == 99_000
    assert pv.delete_session_after is False
    # **`user_data_dir` 是承重项，不是可选装饰**（2026-08-16 起）：
    # 它为空时 provider 每条 job 开一个临时 profile 再删掉，于是豆包看到的是
    # 「老会话 + 空白设备」这个自相矛盾的组合。接线在这里断掉不会报错，
    # 只会让 deploy.sh 里那个环境变量**静默失效**，而表现是「抓着抓着就不答了」——
    # 排查方向会完全跑偏（run 294/295 的教训，见 PHASE2）。
    assert pv.user_data_dir == "/data/doubao_profile"


def test_empty_user_data_dir_falls_back_to_a_throwaway_profile():
    """空值的行为要钉住：**每条 job 一个全新临时 profile**。

    这是 2026-08-16 之前的默认行为，也是当时怀疑的封锁诱因。
    留这条不是因为它好，而是因为「空值等于什么」必须是明写的 ——
    否则回滚（删掉 deploy.sh 那行）时没人知道自己回滚到了什么。
    """
    import inspect

    from app.providers import doubao_web

    src = inspect.getsource(doubao_web.DoubaoWebProvider.search)
    assert "tempfile.TemporaryDirectory()" in src

    s = Settings(crawl_mode="real", doubao_storage_state="/data/doubao_storage.json")
    pv = registry.build_real_provider(
        "doubao", registry.ProviderContext(settings=s, sample_index=0, brand_names=["安踏"])
    )
    assert pv.user_data_dir is None


def test_platform_chip_no_longer_says_unimplemented():
    """接完之后前端 chip 必须变成可点 —— 忘了改注册表的话，
    平台接好了用户却选不了，而且没有任何报错。"""
    items = {p["code"]: p for p in registry.describe(crawl_mode="real")}
    assert items["doubao"]["available"] is True
    assert items["doubao"]["note"] is None


# ---------------------------------------------------------------- 失败分类


def test_doubao_login_wall_is_classified_as_login_required():
    """**和「抓取失败」排查方向完全不同**：登录墙要人去重新导出登录态，
    而 P2-16 对 `login_required` 不自动重试（重试一百次也没用）。"""
    from app.services.failure_kinds import LOGIN_REQUIRED, classify_failure, is_retryable

    exc = DoubaoLoginRequired("找不到输入框，可能在登录墙")
    assert classify_failure(exc) == LOGIN_REQUIRED
    assert not is_retryable(LOGIN_REQUIRED)


def test_credential_health_covers_doubao():
    """多一个平台就多一份会悄悄过期的凭证 —— 漏登记的话
    `GET /v1/health/credentials` 里根本不会出现豆包这一行。"""
    from app.services.credential_health import _STORAGE_SETTING

    assert _STORAGE_SETTING["doubao"] == "doubao_storage_state"


def test_doubao_issuer_region_is_unknown_and_that_is_fine():
    """豆包没有 WAF cookie（用字节自家的 ttwid/sessionid 体系）。

    `derive_status` 对 `unknown` **刻意不报 mismatch** ——
    这条设计正是在接第二个平台时兑现的：否则豆包第一天就一片红，
    然后这个端点就没人看了。
    """
    from app.services.credential_health import OK, classify_waf, derive_status

    kind, region = classify_waf(["ttwid", "sessionid", "sid_guard", "passport_csrf_token"])
    assert (kind, region) == ("none", "unknown")

    info = {"exists": True, "parse_error": None, "issuer_region": region,
            "waf_kind": kind, "earliest_expiry": None, "file_mtime": None}
    assert derive_status(info, expected_region="cn", max_age_days=0)[0] == OK


# ------------------------------------------------------------ 这一轮不做的


def test_screenshot_is_decided_by_config_not_by_code():
    """**这条 2026-08-20 反过来了，是有意的。**

    原先它断言的是 `screenshot_path=None` **在**源码里 —— 那时截图被刻意关掉
    （api 在 VPS，读不到节点的截图目录，留着只会让证据页 404），
    而关的方式是把 None 写死进 provider。

    P2-34 之后截图能随结果传回 VPS 了，那句写死就从「刻意的降级」变成了
    **一个骗人的开关**：千问那边同样一句，让回传链路整条做完之后仍然一张图都没有，
    配置说开着、代码说关着，中间没有任何地方报错。

    所以现在断言相反的事：**开关只有 `SCREENSHOT_DIR` 一个**。
    隧道模式把它置空 → 不截，降级照样是干净的。
    """
    import inspect
    from app.providers import doubao_web

    src = inspect.getsource(doubao_web.DoubaoWebProvider.search)
    assert "screenshot_path=None" not in src
    assert "capture_evidence" in src


def test_provider_does_not_touch_a_search_toggle():
    """生产要开联网已拍板，但**单列成 P2-37** —— 一次只动一个变量。
    这条守的是「别顺手把联网也接了」。"""
    import inspect
    from app.providers import doubao_web

    src = inspect.getsource(doubao_web)
    assert "citations=[]" in src


def test_l0_is_stored_raw_without_cleaning():
    """DeepSeek 那边「清洗后写库」造成过不可逆的正文破坏（BACKEND §7 第 1 行）。
    豆包不重蹈：`full_text` 只 strip，不做任何规则清洗。"""
    import inspect
    from app.providers import doubao_web

    src = inspect.getsource(doubao_web.DoubaoWebProvider.search)
    assert "full_text=text.strip()" in src


# ------------------------------------------------- 等答案：超时不能伪装成成功


class _FakeNode:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self, timeout: int | None = None) -> str:  # noqa: ARG002
        return self._text


class _FakeLocator:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    def count(self) -> int:
        return len(self._texts)

    def nth(self, i: int) -> _FakeNode:
        return _FakeNode(self._texts[i])


class _FakePage:
    """只实现 `_wait_for_answer` 真正用到的三个方法。

    **不是 Mock 库的自动替身** —— 这里要钉的是「页面上有什么」到
    「函数返回什么」的映射，用真实的数据结构表达比断言调用次数清楚得多。
    """

    def __init__(self, *, bubbles: list[str], streaming: bool) -> None:
        self.bubbles = bubbles
        self.streaming = streaming

    def wait_for_timeout(self, ms: int) -> None:
        time.sleep(ms / 1000)

    def locator(self, selector: str) -> _FakeLocator:
        if selector == f"[{STREAMING_ATTR}]":
            return _FakeLocator(["streaming"] if self.streaming else [])
        assert selector == ANSWER_SELECTOR
        return _FakeLocator(self.bubbles)


def test_timeout_raises_instead_of_returning_the_question_as_the_answer():
    """**2026-08-16 run 294 的真实故障，11/17 条就这么进的库。**

    豆包不答时 `[data-streaming]` 一直在（所以「状态位消失即写完」那条提前
    返回从不触发），而 `.md-box-root` **连用户自己那条提问气泡一起匹配** ——
    于是轮询里 `prev` 始终是提问原文，长度兜底又被 `len > 100` 挡住，
    最后 `return prev` 把**提问当成答案**返回，`search()` 只判非空就写成
    `success`。11 条的 `full_text` 就是提问本身，latency 全是 126 秒（超时打满）。

    这次靠 `answer_status=too_short` 才被发现，**但那是运气**：
    提问词长过阈值就会当成真答案入库，且没有任何地方会报错。

    超时必须抛，让 P2-16 归成 `timeout` 去退避重试。
    """
    page = _FakePage(bubbles=["打篮球穿什么牌子的鞋好？"], streaming=True)

    with pytest.raises(DoubaoAnswerTimeout):
        _wait_for_answer(page, timeout_ms=40, poll_ms=1)


def test_answer_timeout_is_classified_as_timeout_and_retried():
    """继承 `TimeoutError` 就够 —— `classify_failure` 第 3 步是类型判定。

    **不靠消息里带没带「超时」两个字**：那个模块自己写着「类型优先，
    字符串匹配是脆的」。
    """
    from app.services.failure_kinds import TIMEOUT, classify_failure, is_retryable

    assert classify_failure(DoubaoAnswerTimeout("等答案超时")) == TIMEOUT
    assert is_retryable(TIMEOUT)


def test_completed_answer_is_still_returned():
    """回归护栏：修超时不能把正常那条路弄坏。

    run 294 里有 6 条是好的（35–47 秒，1000–1700 字）——
    证明选择器与完成判定本身是对的，这次只动失败路径。
    """
    page = _FakePage(bubbles=["问题", "这是一段完整的回答正文。"], streaming=False)

    assert _wait_for_answer(page, timeout_ms=5_000, poll_ms=1) == "这是一段完整的回答正文。"


# --------------------------------------------- 截图不再写死（P2-34 / 2026-08-20）
#
# 千问那边踩过一次：`screenshot_path=None,  # 节点上截图关闭` 把一个临时的运维
# 决定焊进了代码。于是 P2-34 把回传链路整条做完之后仍然一张图都没有 ——
# **配置说开着、代码说关着，中间没有任何地方报错。**
# 豆包这句一模一样，趁现在一起改掉，别等接回豆包时再踩第二次。


def test_doubao_screenshot_follows_the_configured_dir():
    """开关只有一个：``SCREENSHOT_DIR``。空 = 不截，非空 = 截。"""
    from app.providers.browser import capture_evidence

    class _Page:
        def __init__(self): self.calls = 0
        def screenshot(self, **kw): self.calls += 1

    p = _Page()
    assert capture_evidence(p, "", platform="doubao") is None and p.calls == 0
