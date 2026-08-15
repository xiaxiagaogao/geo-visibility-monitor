"""豆包 Web Provider（P2-06a）。

选择器与判定全部来自 2026-08-15 在采集节点上的实测，**不是照抄 DeepSeek**。
接之前踩过的坑见 `docs/PHASE2.md`「豆包这条路可能不成立」。

## 与 DeepSeek 的四处关键差异

===============  =============================  ==================================
                 DeepSeek                        豆包
===============  =============================  ==================================
反自动化          一年没遇到                      **未加固时发一条就登出**
输入框            ``textarea``                   ``textarea`` **有两个**，
                                                 第二个是 ``aria-hidden`` 的替身
答案气泡          ``.ds-markdown``               ``.md-box-root``
完成判定          长度连续不变轮询                 **``[data-streaming]`` 状态位**
===============  =============================  ==================================

**最后一条是豆包比 DeepSeek 好的地方**：DS 只能靠「长度连续 N 次不变」猜写完没有，
豆包直接给状态位。这里仍保留长度稳定作为兜底 —— 状态位是它自己的实现细节，
改版时会先于选择器失效，而那时长度轮询还能撑住。

## 这一轮刻意不做的两件

- **不截图。** 采集节点上 ``SCREENSHOT_DIR`` 是空的（api 在 VPS，读不到节点上的
  截图目录，留着只会让证据页 404）。`CrawlResult.screenshot_path` 契约保留，
  P2-34 worker 化之后随结果传回即可恢复。
- **不碰联网搜索。** 实测输入区没有联网开关（工具栏全是技能，「快速」是模型
  选择器），大概率豆包自动判断。生产要开联网这件事已拍板，但**单列成 P2-37** ——
  一次只动一个变量。见 `PHASE2` §4.0.1。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.providers.base import BaseProvider, CitationData, CrawlResult
from app.providers.browser import launch_persistent, seed_storage_state

logger = logging.getLogger("geo.doubao_web")

DOUBAO_URL = "https://www.doubao.com/chat/"

#: **必须按 placeholder 认输入框。** 页面上有两个 ``textarea``，
#: 第二个是 ``aria-hidden="true"`` 的隐藏替身 —— 照抄 DeepSeek 的裸 ``textarea``
#: 会点到假的（2026-08-15 实测踩过）。
INPUT_SELECTOR = 'textarea[placeholder="发消息或按住空格说话..."]'

#: 答案气泡。``md-box-root`` 是稳定语义类；同元素上那个 ``container-xxxxxx``
#: 是 CSS Modules 生成的哈希，**不能用**。
ANSWER_SELECTOR = ".md-box-root"

#: 还在生成时这个属性在。比长度轮询准，但它是实现细节，所以下面仍留长度兜底。
STREAMING_ATTR = "data-streaming"

#: 拦截用：豆包的流式接口（实测 ``POST /chat/completion`` → ``text/event-stream``）
COMPLETION_HINT = "/chat/completion"

#: 侧栏条目里那个 hover 才出现的「更多」按钮 → 菜单项「删除」（实测菜单为
#: 置顶 / 分享 / 重命名 / 移动到项目 / 删除）
DELETE_MENU_TEXT = "删除"


class DoubaoWebProvider(BaseProvider):
    platform = "doubao"

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
        #: persistent context 的 profile 目录。为空时用临时目录 ——
        #: 每次都是干净的，代价是每次都要重灌 storage_state
        self.user_data_dir = user_data_dir
        self.screenshot_dir = screenshot_dir
        self.delete_session_after = delete_session_after
        self.timezone_id = timezone_id

    # ------------------------------------------------------------------

    def search(self, prompt: str) -> CrawlResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright not installed; use crawler image"
            ) from exc

        import tempfile

        t0 = time.time()
        captured: List[Dict[str, Any]] = []

        tmp = None
        profile = self.user_data_dir
        if not profile:
            tmp = tempfile.TemporaryDirectory()
            profile = tmp.name

        try:
            with sync_playwright() as p:
                context = launch_persistent(
                    p,
                    user_data_dir=profile,
                    headless=self.headless,
                    timezone_id=self.timezone_id,
                )
                try:
                    if self.storage_state:
                        seed_storage_state(context, self.storage_state)

                    page = context.pages[0] if context.pages else context.new_page()
                    page.on("response", lambda r: _collect(r, captured))

                    page.goto(DOUBAO_URL, wait_until="domcontentloaded",
                              timeout=self.timeout_ms)

                    box = page.wait_for_selector(
                        INPUT_SELECTOR, timeout=min(30_000, self.timeout_ms)
                    )
                    if box is None:
                        raise DoubaoLoginRequired(
                            "找不到输入框，可能在登录墙。重新导出 storage_state："
                            "scripts/export_storage_state.py --platform doubao"
                        )
                    box.click()
                    page.keyboard.type(prompt, delay=25)
                    page.keyboard.press("Enter")

                    text = _wait_for_answer(page, timeout_ms=self.timeout_ms)
                    if not text.strip():
                        raise RuntimeError("empty answer from 豆包 (UI changed or blocked)")

                    latency = int((time.time() - t0) * 1000)
                    raw_json: Dict[str, Any] = {
                        "source": "doubao_web",
                        "sse_events": len(captured),
                        "conversation_url": None,   # 会话 URL 不落库，见 BACKEND §7
                    }

                    if self.delete_session_after:
                        raw_json["session_deleted"] = _delete_current_session(page)

                    # **L0 存原文。** 不做任何清洗 —— DeepSeek 那边
                    # 「清洗后写库」造成过不可逆的正文破坏（BACKEND §7 第 1 行）
                    return CrawlResult(
                        platform="doubao",
                        prompt=prompt,
                        full_text=text.strip(),
                        citations=[],          # 未开联网，见模块 docstring 与 P2-37
                        raw_json=raw_json,
                        latency_ms=latency,
                        screenshot_path=None,  # 节点上截图关闭
                    )
                finally:
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            if tmp is not None:
                tmp.cleanup()


class DoubaoLoginRequired(RuntimeError):
    """登录态失效。**和「抓取失败」排查方向完全不同**，所以单独一个类型 ——
    `services/failure_kinds.py` 靠它归成 `login_required`（不自动重试）。"""


# ---------------------------------------------------------------- helpers


def _collect(response, sink: List[Dict[str, Any]]) -> None:
    """只记流式接口的元信息，**不存响应体**（与 DeepSeek 同一条纪律）。"""
    try:
        if COMPLETION_HINT in response.url:
            sink.append({"status": response.status,
                         "ct": (response.headers.get("content-type") or "")[:40]})
    except Exception:  # noqa: BLE001
        pass


def _answer_text(page) -> str:
    """取最长的一条答案气泡正文。

    取最长而不是取最后一条：页面上同时有用户提问和答案，
    而 `.md-box-root` 只包答案 —— 但一次会话里可能有多轮，取最长的那条
    是「本次提问的回答」的稳妥近似（本 provider 每次都开新会话）。
    """
    try:
        nodes = page.locator(ANSWER_SELECTOR)
        best = ""
        for i in range(min(nodes.count(), 20)):
            try:
                t = (nodes.nth(i).inner_text(timeout=2000) or "").strip()
            except Exception:  # noqa: BLE001
                continue
            if len(t) > len(best):
                best = t
        return best
    except Exception:  # noqa: BLE001
        return ""


def is_streaming(page) -> bool:
    """回答还在生成吗。豆包给了状态位，比 DeepSeek 的长度轮询准。"""
    try:
        return page.locator(f"[{STREAMING_ATTR}]").count() > 0
    except Exception:  # noqa: BLE001
        return False


def _wait_for_answer(page, *, timeout_ms: int, poll_ms: int = 1500) -> str:
    """等回答写完。

    **两条判据，状态位优先、长度稳定兜底。** 状态位是豆包自己的实现细节，
    改版时会先于选择器失效；那时长度轮询还能撑住，不至于当场全线崩。
    """
    deadline = time.time() + timeout_ms / 1000
    prev, stable = "", 0
    while time.time() < deadline:
        page.wait_for_timeout(poll_ms)
        cur = _answer_text(page)
        if cur and not is_streaming(page):
            return cur
        stable = stable + 1 if cur == prev and cur else 0
        prev = cur
        if stable >= 3 and len(cur) > 100:
            logger.info("按长度稳定判定写完（%s 属性没出现）", STREAMING_ATTR)
            return cur
    return prev


def _delete_current_session(page) -> bool:
    """删掉刚抓完的会话，走侧栏 UI。

    **按 URL 里的会话 id 精确定位，绝不按标题模糊匹配** ——
    这个账号里绝大多数是用户私人对话，误删不可接受（DeepSeek 那边同样的纪律，
    见 `providers/deepseek_web.py` 的 `_delete_session`）。

    失败只记日志返回 False，**绝不让整次抓取失败**：正文已经拿到了。
    """
    try:
        conv_id = (page.url.rstrip("/").rsplit("/", 1) or [""])[-1]
        if not conv_id or not conv_id.isdigit():
            logger.warning("拿不到会话 id，跳过删除 url=%s", page.url)
            return False
        item = page.locator(f'a[href*="{conv_id}"]')
        if item.count() == 0:
            logger.warning("侧栏找不到会话 %s", conv_id)
            return False
        item.first.hover(timeout=5000)
        page.wait_for_timeout(500)
        btn = item.first.locator("button")
        if btn.count() == 0:
            logger.warning("会话条目里没有「更多」按钮")
            return False
        btn.first.click(timeout=5000)
        page.wait_for_timeout(800)
        page.locator(f'[role="menuitem"]:has-text("{DELETE_MENU_TEXT}")').first.click(timeout=5000)
        page.wait_for_timeout(1200)
        # **必须复核条目真的消失**——DeepSeek 第一版正是败在没复核（commit 1ca55b7）
        gone = page.locator(f'a[href*="{conv_id}"]').count() == 0
        if not gone:
            logger.warning("点了删除但条目还在 conv=%s（可能有二次确认）", conv_id)
        return gone
    except Exception:  # noqa: BLE001
        logger.warning("删除会话失败（不影响本次抓取）", exc_info=True)
        return False
