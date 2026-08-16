"""通义千问 Provider 的接线与常量（P2-06b）。不需要 playwright，本机可跑。

选择器与判定**全部来自 2026-08-16 在采集节点上的实测**（PHASE2「P2-06b 第 0 步」），
不是照抄 DeepSeek 或豆包 —— 三家的 DOM 没有一处是通用的。

平台代码是 `tongyi`、站点是 `qianwen.com`：阿里把产品改名叫「千问」，
但代码已经在 `ALLOWED_PLATFORMS` 与历史数据里，改它等于一次数据迁移，
收益只是名字好看。**这个不一致是有意保留的。**
"""
from __future__ import annotations

import pytest

from app.core.config import Settings


# ------------------------------------------------------- 完成判定（纯函数）
#
# 千问**没有 data-streaming 那样的状态位** —— 2026-08-16 在节点上逐秒记录 60 秒，
# 页面上唯一带 stream/generat/loading 字样的属性是图片的 `loading=lazy`。
# 所以只能靠长度稳定，和 DeepSeek 同级、比豆包弱。这是实测结论，不是偷懒。
#
# 唯一能加强它的是「停止回答」按钮，但**只能当正向信号用**：实测它在第 8 秒
# 就消失，而正文一直长到第 15 秒 —— 按钮消失比写完早了 7 秒，
# 只认它会把答案截掉一半。


def test_stop_button_present_means_definitely_not_done():
    """按钮在 = 一定还在生成。这是它唯一可靠的用法。"""
    from app.providers.qianwen_web import is_answer_complete

    assert not is_answer_complete(text="已经写了很长一段" * 20, stable_ticks=99,
                                  stop_button_present=True)


def test_length_stable_without_stop_button_means_done():
    from app.providers.qianwen_web import STABLE_TICKS_REQUIRED, is_answer_complete

    assert is_answer_complete(text="正文" * 60, stable_ticks=STABLE_TICKS_REQUIRED,
                              stop_button_present=False)


def test_not_done_while_still_growing():
    from app.providers.qianwen_web import is_answer_complete

    assert not is_answer_complete(text="正文" * 60, stable_ticks=0,
                                  stop_button_present=False)


def test_empty_text_is_never_complete_however_stable():
    """**空且稳定不能判成写完。**

    实测 2–4 秒时长度走的是 `10 → 0 → 50`（元素被替换重渲染）——
    答案容器会短暂变空。把「空 + 稳定」判成写完，就会返回空正文，
    而 `search()` 只判非空的话就成了豆包那个 bug 的翻版。
    """
    from app.providers.qianwen_web import is_answer_complete

    assert not is_answer_complete(text="", stable_ticks=999, stop_button_present=False)
    assert not is_answer_complete(text="   ", stable_ticks=999, stop_button_present=False)


def test_too_short_text_needs_more_patience_than_a_long_one():
    """十几个字就稳定下来，更可能是渲染中途，不是真写完。

    豆包那边正是「12 字符的提问原文」被当成答案写库的（PHASE2 bug A）。
    千问这里提前设一道下限，宁可多等几秒。
    """
    from app.providers.qianwen_web import MIN_ANSWER_CHARS, is_answer_complete

    assert not is_answer_complete(text="好的" * 3, stable_ticks=4, stop_button_present=False)
    assert len("好的" * 3) < MIN_ANSWER_CHARS


# ---------------------------------------------------------------- 凭证接线


def test_login_wall_is_classified_by_type_not_by_message():
    """**和「抓取失败」排查方向完全不同**：登录墙要人去重新导出登录态，
    而 P2-16 对 `login_required` 不自动重试（重试一百次也没用）。

    ⚠️ **消息刻意不含「登录」「storage_state」这类词。** 带上它们的话，
    `classify_message` 的字符串兜底会让这条测试**假绿** —— 类型没登记也照样通过，
    而真实故障的报错文案一变就当场失效。`failure_kinds` 的模块 docstring
    写着「类型优先，字符串匹配是脆的」，这条测试就是钉住那个顺序的。
    """
    from app.providers.qianwen_web import QianwenLoginRequired
    from app.services.failure_kinds import (
        LOGIN_REQUIRED,
        classify_failure,
        classify_message,
        is_retryable,
    )

    exc = QianwenLoginRequired("凭证不可用")
    assert classify_message(str(exc)) != LOGIN_REQUIRED   # 字符串兜底认不出来
    assert classify_failure(exc) == LOGIN_REQUIRED        # 只能靠类型
    assert not is_retryable(LOGIN_REQUIRED)


def test_answer_timeout_is_classified_as_timeout_and_retried():
    """继承 `TimeoutError` 就够 —— `classify_failure` 第 3 步是类型判定，
    不靠消息里带没带「超时」两个字。"""
    from app.providers.qianwen_web import QianwenAnswerTimeout
    from app.services.failure_kinds import TIMEOUT, classify_failure, is_retryable

    assert classify_failure(QianwenAnswerTimeout("等答案超时")) == TIMEOUT
    assert is_retryable(TIMEOUT)


def test_timeout_never_returns_partial_text():
    """**豆包 bug A 的防线**：超时那条路径必须 raise，不能 return。

    豆包 `_wait_for_answer` 超时后 `return prev`，而页面上最后一条气泡是
    用户自己的提问 —— 11/17 条以「成功，答案 = 提问原文」入库，
    且没有任何地方报错。千问从第一天就不留这个口子。
    """
    import ast
    import inspect

    from app.providers import qianwen_web

    fn = ast.parse(inspect.getsource(qianwen_web._wait_for_answer).lstrip()).body[0]
    returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    # 唯一的 return 是「判定写完」那条；函数体最后一句必须是 raise
    assert len(returns) == 1
    assert len(raises) == 1
    assert isinstance(fn.body[-1], ast.Raise)


def test_session_deletion_is_honestly_reported_as_not_done():
    """删会话**没实现**（侧栏找不到 conv_id，见模块 docstring）。

    没实现就如实报 `False`，**不写 True 骗自己** ——
    「以为删了其实没删」比「知道没删」难查得多。
    """
    import inspect

    from app.providers import qianwen_web

    src = inspect.getsource(qianwen_web.QianwenWebProvider.search)
    assert '"session_deleted": False' in src


def test_tongyi_is_registered_and_runnable_in_real_mode():
    from app.providers import registry

    assert registry.is_known("tongyi")
    assert registry.is_implemented("tongyi")
    assert registry.is_runnable("tongyi", crawl_mode="real")


def test_registry_builds_a_tongyi_provider_with_settings_wired():
    """**接线漏一项不会报错，只会让那个设置永远是默认值。**

    `user_data_dir` 尤其要钉住：豆包就是因为 deploy.sh 没设它、每条 job 开一个
    临时 profile，才有了「老会话 + 空白设备」那个自相矛盾的组合（PHASE2 现象 C）。
    """
    from app.providers import registry
    from app.providers.qianwen_web import QianwenWebProvider

    s = Settings(
        crawl_mode="real",
        tongyi_storage_state="/data/tongyi_storage.json",
        tongyi_user_data_dir="/data/tongyi_profile",
        crawl_timezone_id="Asia/Shanghai",
        crawl_timeout_ms=99_000,
        tongyi_delete_session=False,
    )
    pv = registry.build_real_provider(
        "tongyi", registry.ProviderContext(settings=s, sample_index=1, brand_names=["安踏"])
    )

    assert isinstance(pv, QianwenWebProvider)
    assert pv.platform == "tongyi"
    assert pv.storage_state == "/data/tongyi_storage.json"
    assert pv.user_data_dir == "/data/tongyi_profile"
    assert pv.timezone_id == "Asia/Shanghai"
    assert pv.timeout_ms == 99_000
    assert pv.delete_session_after is False


def test_platform_chip_no_longer_says_unimplemented():
    """接完之后前端 chip 必须变成可点 —— 忘了改注册表的话，
    平台接好了用户却选不了，而且没有任何报错。"""
    from app.providers import registry

    items = {p["code"]: p for p in registry.describe(crawl_mode="real")}
    assert items["tongyi"]["available"] is True
    assert items["tongyi"]["note"] is None


def test_settings_have_a_tongyi_storage_state():
    """多一个平台就多一份会悄悄过期的凭证。

    漏了这个字段的话，登录态根本没有地方可以配，
    而表现是「每一条抓取都失败在登录页」—— 排查方向完全跑偏。
    """
    s = Settings()
    assert hasattr(s, "tongyi_storage_state")


def test_settings_have_a_tongyi_user_data_dir():
    """**持久 profile 从第一天就要有。**

    豆包是先用临时 profile 上线、抓了两轮才发现「老会话 + 空白设备」
    这个自相矛盾的组合可能正是被封的诱因（PHASE2 现象 C）。
    千问不重蹈：这个字段一开始就在，deploy.sh 一开始就设。
    """
    s = Settings()
    assert hasattr(s, "tongyi_user_data_dir")


def test_credential_health_covers_tongyi():
    """漏登记的话 `GET /v1/health/credentials` 里根本不会出现千问这一行 ——
    而「少一行」比「报红」更难发现。"""
    from app.services.credential_health import _STORAGE_SETTING

    assert _STORAGE_SETTING["tongyi"] == "tongyi_storage_state"


def test_export_script_knows_tongyi():
    """`scripts/export_storage_state.py` 的 PLATFORMS 是「加平台只改这里」的那个表。

    漏了它，登录态**没有任何办法导出** —— provider 写得再对也跑不起来。
    入口用 `qianwen.com`：`tongyi.com` 只是 302 跳过来（实测 `?ch=tongyi_redirect`）。

    ⚠️ **用 ast 静态解析，绝不 import 那个脚本。** 它顶层
    `from playwright.sync_api import sync_playwright`，而 **api 容器里没装
    playwright**（它不跑抓取）—— import 一下整条测试就挂。
    这条约束 `services/failure_kinds._has_type` 的 docstring 已经写过一次，
    2026-08-16 我在这里又踩了一遍：本机 venv 有 playwright 所以本机是绿的，
    只有 VPS 真环境跑全量才抓得到。**这就是为什么真库档不能只在本机跑。**
    """
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[3]
           / "scripts" / "export_storage_state.py").read_text(encoding="utf-8")
    table = next(
        node.value
        for node in ast.parse(src).body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "PLATFORMS" for t in node.targets)
    )
    platforms = ast.literal_eval(table)

    cfg = platforms["tongyi"]
    assert cfg["url"].startswith("https://www.qianwen.com")
    assert cfg["out"] == "tongyi_storage.json"
    # **不为新平台瞎写登录检测器**（同豆包）：检测错了会在你还没登完时
    # 就导出一份空会话，而空会话拿去采集的表现是「一批 job 全 failed」
    assert cfg["detect"] is None
