"""通义千问 Web Provider（P2-06b）。

选择器与判定**全部来自 2026-08-16 在采集节点上的实测**，不是照抄 DeepSeek 或豆包。

平台代码是 ``tongyi``、站点是 ``qianwen.com``：阿里把产品改名叫「千问」，
但代码已在 ``ALLOWED_PLATFORMS`` 与历史数据里，改它等于一次数据迁移。
**这个不一致是有意保留的。**

## 与豆包/DeepSeek 的三处关键差异（全部实测）

===========  ==========================  ==============================
             豆包                         千问
===========  ==========================  ==============================
输入框        ``textarea``（两个）          ``contenteditable``（Slate），
                                          **click() 会被首屏大图挡住**
完成判定      ``[data-streaming]`` 状态位   **没有状态位**，只能长度稳定
答案气泡      ``.md-box-root``             ``.answer-common-card``
===========  ==========================  ==============================

**完成判定这条是退步，要认。** 逐秒记录 60 秒确认过：页面上唯一带
stream/generat/loading 字样的属性是图片的 ``loading=lazy``。
「停止回答」按钮只能当正向信号 —— 它在第 8 秒消失而正文长到第 15 秒。

## 这一轮刻意不做的两件

- **不删会话。** 豆包那套（按 URL 里的会话 id 到侧栏精确定位）在这里**不成立**：
  实测发出提问后 ``conv_id`` 在侧栏 DOM 里找不到（``侧栏命中 0``）。
  本仓规矩是选择器必须实测，**没验过的删除逻辑绝不能写** ——
  误删的是用户的私人对话，代价不可逆。所以 ``session_deleted`` 如实报
  ``False``，不写 True 骗自己。**代价是会话会堆积**（豆包 bug B 的同款），
  已记进 PHASE2 待办。
- ~~**不碰联网/引用。**~~ **P2-37 已接（2026-08-21）**：引用从 SSE 流里抽
  （``qianwen_sse.parse_stream``），同时记录 ``search_used``。
  **不强制开联网** —— 千问根本没有联网开关（枚举过输入区全部 24 个按钮），
  且联网是按 query 触发的：时效性问题触发，而监测集全是品牌对比类，实测不触发。
  §4.0.1 的口径是「**记录 search 是否激活；无搜索输出是结果，不是废样本**」。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.providers.base import BaseProvider, CrawlResult
from app.providers.browser import capture_evidence, launch_persistent, seed_storage_state
from app.providers.qianwen_sse import parse_stream

logger = logging.getLogger("geo.qianwen_web")

QIANWEN_URL = "https://www.qianwen.com/"

#: 流式对话接口（P2-37）。**引用只在这条流里，DOM 里一条外链都没有** ——
#: 2026-08-17 节点实测，见 `PHASE2.md` §4.0.1 第五节与 `qianwen_sse.py`。
CHAT_API_HINT = "/api/v2/chat"

#: 输入框是 Slate 编辑器的 contenteditable，**页面上没有 textarea**。
INPUT_SELECTOR = "[contenteditable='true']"

#: 答案气泡。``.chat-answers-card-wrap`` 会把「N 篇来源」一起带进来，所以用这个。
ANSWER_SELECTOR = ".answer-common-card"

#: 「停止回答」按钮 —— 只能当**正向**信号用，见 ``is_answer_complete``。
STOP_BUTTON_TEXT = "停止回答"

#: 长度连续多少次不变算写完。
STABLE_TICKS_REQUIRED = 4

#: 低于这个长度就算稳定也不认。
MIN_ANSWER_CHARS = 24


def is_answer_complete(*, text: str, stable_ticks: int,
                       stop_button_present: bool) -> bool:
    """回答写完了吗。**纯函数，判定规则集中在这里。**

    千问**没有 `data-streaming` 那样的状态位** —— 2026-08-16 在节点上逐秒
    记录 60 秒，页面上唯一带 stream/generat/loading 字样的属性是图片的
    `loading=lazy`。所以只能靠长度稳定，和 DeepSeek 同级、比豆包弱。
    这是实测结论，不是偷懒。

    三道闸，缺一不可：

    1. **「停止回答」按钮在 → 一定没写完。** 它只能当正向信号用：实测它在
       第 8 秒就消失，而正文一直长到第 15 秒 —— 按钮消失比写完早 7 秒，
       只认它会把答案截掉一半。
    2. **空的永远不算写完。** 实测 2–4 秒时长度走的是 `10 → 0 → 50`
       （答案容器被替换重渲染），会短暂变空。把「空 + 稳定」判成写完，
       就会返回空正文 —— 那是豆包 bug A 的翻版。
    3. **太短的要多等。** 十几个字就稳定下来，更可能是渲染中途。
       豆包正是把「12 字符的提问原文」当答案写进了库。
    """
    if stop_button_present:
        return False
    body = (text or "").strip()
    if len(body) < MIN_ANSWER_CHARS:
        return False
    return stable_ticks >= STABLE_TICKS_REQUIRED


class QianwenLoginRequired(RuntimeError):
    """登录态失效。单独一个类型 —— `failure_kinds` 靠它归成 `login_required`
    （不自动重试：重试一百次也没用，要人去重新导出）。"""


class QianwenAnswerTimeout(TimeoutError):
    """等答案等到超时。

    **继承 `TimeoutError` 是为了走类型判定**（`classify_failure` 第 3 步）→
    `timeout` → P2-16 退避重试。

    ⚠️ **超时必须抛，绝不能把手上那点文本返回出去。** 豆包正是在这里栽过：
    `_wait_for_answer` 超时后 `return prev`，而页面上最后一条气泡是**用户自己
    的提问**，于是 11/17 条以「成功，答案 = 提问原文」入库（PHASE2 bug A）。
    千问从第一天就不留这个口子。
    """


def _answer_text(page) -> str:
    """取答案气泡正文。

    每条 job 都开新会话，所以正常情况下只有一条 `.answer-common-card`；
    取 `.last` 是为了万一有多轮时拿最新那条。**提问在
    `.message-card-wrap.question` 里，不在这个选择器下** —— 实测确认过，
    所以不会重蹈豆包「把提问当答案」的覆辙。
    """
    try:
        nodes = page.locator(ANSWER_SELECTOR)
        if not nodes.count():
            return ""
        return (nodes.last.inner_text(timeout=3000) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _stop_button_present(page) -> bool:
    """「停止回答」按钮在不在 —— 在 = 一定还在生成。"""
    try:
        return page.get_by_role(
            "button", name=STOP_BUTTON_TEXT
        ).count() > 0
    except Exception:  # noqa: BLE001
        return False


def _looks_like_login_wall(page) -> bool:
    """登录态没认。

    实测已登录时顶栏没有「登录」、也没有「登录可同步历史对话」这句提示；
    未登录时两者都在。用后者更稳 —— 前者在已登录页面上也可能作为
    某些入口文案出现。
    """
    try:
        body = (page.inner_text("body") or "")
        return "登录可同步历史对话" in body
    except Exception:  # noqa: BLE001
        return False


def _wait_for_answer(page, *, timeout_ms: int, poll_ms: int = 1000) -> str:
    """等回答写完。判定规则在 `is_answer_complete`（纯函数、有单测）。"""
    deadline = time.time() + timeout_ms / 1000
    prev, stable = "", 0
    while time.time() < deadline:
        page.wait_for_timeout(poll_ms)
        cur = _answer_text(page)
        stable = stable + 1 if cur == prev and cur else 0
        prev = cur
        if is_answer_complete(text=cur, stable_ticks=stable,
                              stop_button_present=_stop_button_present(page)):
            return cur

    raise QianwenAnswerTimeout(
        f"等答案超过 {timeout_ms}ms；当前正文 {len(prev)} 字符"
        f"（停止回答按钮={_stop_button_present(page)}）"
    )


class QianwenWebProvider(BaseProvider):
    platform = "tongyi"

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 120_000,
        storage_state: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        screenshot_dir: Optional[str] = None,
        delete_session_after: bool = True,
        timezone_id: str = "Asia/Shanghai",
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.storage_state = storage_state
        self.user_data_dir = user_data_dir
        self.screenshot_dir = screenshot_dir
        self.delete_session_after = delete_session_after
        self.timezone_id = timezone_id

    def search(self, prompt: str) -> CrawlResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("playwright not installed; use crawler image") from exc

        import tempfile

        t0 = time.time()
        tmp = None
        profile = self.user_data_dir
        if not profile:
            tmp = tempfile.TemporaryDirectory()
            profile = tmp.name

        try:
            with sync_playwright() as p:
                context = launch_persistent(
                    p, user_data_dir=profile, headless=self.headless,
                    timezone_id=self.timezone_id,
                )
                try:
                    if self.storage_state:
                        seed_storage_state(context, self.storage_state)

                    page = context.pages[0] if context.pages else context.new_page()

                    # P2-37：引用只在流里，DOM 里一条外链都没有（§4.0.1 第五节）。
                    # 只在内存里攒着解析，**不落库** —— 与 DeepSeek/豆包同一条纪律
                    sse_bodies: List[str] = []

                    def _on_response(response):
                        try:
                            if CHAT_API_HINT not in response.url:
                                return
                            body = response.text()
                            if body:
                                sse_bodies.append(body)
                        except Exception:  # noqa: BLE001
                            # 取不到流不该让一条已经拿到答案的 job 失败
                            logger.debug("千问 SSE 取不到正文（引用会缺）")

                    page.on("response", _on_response)
                    page.goto(QIANWEN_URL, wait_until="domcontentloaded",
                              timeout=self.timeout_ms)
                    page.wait_for_timeout(4000)

                    if _looks_like_login_wall(page):
                        raise QianwenLoginRequired(
                            "千问未登录。重新导出 storage_state："
                            "scripts/export_storage_state.py --platform tongyi"
                        )

                    box = page.locator(INPUT_SELECTOR).first
                    # ⚠️ **必须 focus()，不能 click()。** 首屏那张大图
                    # （`absolute inset-0 h-[266px]`）盖在输入框中心点上，
                    # 另有一个 z-[1001] 的浮层 —— `click()` 会超时。
                    # 2026-08-16 实测；和豆包「两个 textarea」是同类坑。
                    box.evaluate("e => e.focus()")
                    page.wait_for_timeout(300)
                    page.keyboard.type(prompt, delay=30)
                    page.wait_for_timeout(400)
                    page.keyboard.press("Enter")

                    text = _wait_for_answer(page, timeout_ms=self.timeout_ms)

                    latency = int((time.time() - t0) * 1000)
                    raw_json: Dict[str, Any] = {
                        "source": "qianwen_web",
                        "conversation_url": None,   # 会话 URL 不落库
                        # **删会话还没实现**，见下面 docstring。如实上报，
                        # 不写 True 骗自己
                        "session_deleted": False,
                    }

                    # **L0 存原文**，只 strip，不做任何规则清洗
                    # P2-37：从流里抽引用与「有没有联网」。解析器绝不抛异常
                    trace = parse_stream("\n".join(sse_bodies))
                    raw_json["match_num"] = trace.match_num
                    # 站点名与发布时间在 Citation 表里没有列，原样留在 raw_json 里 ——
                    # 那是实测多拿到的东西，丢掉等于把一次真机产出扔了
                    raw_json["sources"] = trace.raw

                    return CrawlResult(
                        platform="tongyi",
                        prompt=prompt,
                        full_text=text.strip(),
                        citations=trace.citations,
                        search_used=trace.search_used,
                        raw_json=raw_json,
                        latency_ms=latency,
                        # P2-34：截图回来了。**这里原先写死 None**（注释是
                        # 「节点上截图关闭」）—— 那是把一个临时的运维决定
                        # 焊进了代码，结果 worker 化之后配置说开着、代码说关着，
                        # 而没有任何地方报错。现在只认 screenshot_dir
                        screenshot_path=capture_evidence(
                            page, self.screenshot_dir, platform="tongyi"
                        ),
                    )
                finally:
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            if tmp is not None:
                tmp.cleanup()
