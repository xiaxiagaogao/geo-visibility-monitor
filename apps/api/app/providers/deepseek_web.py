"""DeepSeek Web crawl provider (B5).

Design references (study only; implementation is original):
- daijinma/geo_marketing: Playwright + network intercept for chat completion / SSE
- xxxbozzz/gitgeo core/probe: platform URL/selector config table for DeepSeek

We do NOT copy licensed/unlicensed source; we reimplement a minimal robust path:
1) open chat.deepseek.com with optional storage_state (login)
2) type prompt, wait for generation
3) prefer intercepting completion responses; fallback to DOM text
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.providers.base import BaseProvider, CitationData, CrawlResult

logger = logging.getLogger("geo.provider.deepseek")

DEEPSEEK_URL = "https://chat.deepseek.com"

# Config style similar to gitgeo probe tables
SELECTORS = {
    "input": "textarea",
    # Prefer assistant markdown bubbles; avoid broad body scrape
    "answer": ".ds-markdown",
    "login_hint": "text=登录, text=Log in, text=Sign in",
}

# Sidebar chrome phrases — if extracted text is mostly these, treat as invalid
SIDEBAR_NOISE = (
    "开启新对话",
    "深度思考",
    "智能搜索",
    "快速模式",
    "专家模式",
    "识图模式",
    "30 天内",
)

# Intercept URL fragments (pattern idea from open-source monitors)
API_HINTS = (
    "api/v0/chat/completion",
    "api/v1/chat/completion",
    "chat/completion",
    "completion",
)


class DeepSeekLoginRequired(RuntimeError):
    pass


class DeepSeekWebProvider(BaseProvider):
    platform = "deepseek"

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout_ms: int = 120_000,
        storage_state: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        screenshot_dir: Optional[str] = None,
    ):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.storage_state = storage_state
        self.user_data_dir = user_data_dir
        self.screenshot_dir = screenshot_dir

    def search(self, prompt: str) -> CrawlResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright not installed; use crawler image or pip install playwright && playwright install chromium"
            ) from exc

        t0 = time.time()
        stream_chunks: List[str] = []
        captured_json: List[Dict[str, Any]] = []
        citations: List[CitationData] = []

        with sync_playwright() as p:
            browser = None
            context = None
            try:
                if self.user_data_dir:
                    context = p.chromium.launch_persistent_context(
                        self.user_data_dir,
                        headless=self.headless,
                        viewport={"width": 1400, "height": 1200},
                        locale="zh-CN",
                    )
                    page = context.new_page()
                else:
                    browser = p.chromium.launch(headless=self.headless)
                    ctx_kwargs: Dict[str, Any] = {
                        "viewport": {"width": 1280, "height": 900},
                        "locale": "zh-CN",
                    }
                    if self.storage_state:
                        ctx_kwargs["storage_state"] = self.storage_state
                    context = browser.new_context(**ctx_kwargs)
                    page = context.new_page()

                def on_response(response):
                    try:
                        url = response.url.lower()
                        if not any(h in url for h in API_HINTS):
                            return
                        ctype = (response.headers.get("content-type") or "").lower()
                        body = response.text()
                        if not body:
                            return
                        # SSE-ish stream
                        if "event-stream" in ctype or "stream" in url or body.lstrip().startswith("data:"):
                            for line in body.splitlines():
                                line = line.strip()
                                if not line.startswith("data:"):
                                    continue
                                payload = line[5:].strip()
                                if not payload or payload in ("[DONE]", "null"):
                                    continue
                                try:
                                    data = json.loads(payload)
                                    captured_json.append(data if isinstance(data, dict) else {"v": data})
                                    text_piece = _extract_text_from_event(data)
                                    if text_piece:
                                        stream_chunks.append(text_piece)
                                except json.JSONDecodeError:
                                    if payload and not payload.startswith("{"):
                                        stream_chunks.append(payload)
                        else:
                            try:
                                data = response.json()
                                if isinstance(data, dict):
                                    captured_json.append(data)
                                    text_piece = _extract_text_from_event(data)
                                    if text_piece:
                                        stream_chunks.append(text_piece)
                                    for c in _extract_citations(data):
                                        citations.append(c)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug("response handler error: %s", e)

                page.on("response", on_response)
                page.goto(DEEPSEEK_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)

                # login wall detection
                if _looks_like_login(page):
                    raise DeepSeekLoginRequired(
                        "DeepSeek appears to require login. "
                        "Export storage_state JSON and set DEEPSEEK_STORAGE_STATE."
                    )

                box = page.wait_for_selector(SELECTORS["input"], timeout=min(30_000, self.timeout_ms))
                box.click()
                box.fill("")
                # type for slightly more human-like behavior
                page.keyboard.type(prompt, delay=15)
                page.keyboard.press("Enter")

                # wait for answer growth
                full_text = _wait_for_answer(page, stream_chunks, timeout_ms=self.timeout_ms)

                if not full_text or len(full_text.strip()) < 5:
                    # last resort DOM scrape
                    full_text = _dom_answer_text(page)

                if not full_text.strip():
                    raise RuntimeError("empty answer from DeepSeek (UI changed or blocked)")

                shot = None
                if self.screenshot_dir:
                    from pathlib import Path as P

                    P(self.screenshot_dir).mkdir(parents=True, exist_ok=True)
                    shot = str(P(self.screenshot_dir) / f"deepseek_{int(time.time())}.png")
                    _capture_answer_evidence(page, shot, expected_text=full_text)

                latency = int((time.time() - t0) * 1000)
                # dedupe citations
                seen = set()
                uniq_cites: List[CitationData] = []
                for i, c in enumerate(citations, 1):
                    key = c.url
                    if key in seen:
                        continue
                    seen.add(key)
                    if not c.domain:
                        c.domain = urlparse(c.url).netloc or "unknown"
                    if c.cite_index is None:
                        c.cite_index = i
                    uniq_cites.append(c)

                return CrawlResult(
                    platform="deepseek",
                    prompt=prompt,
                    full_text=_clean_answer_text(full_text),
                    citations=uniq_cites,
                    raw_json={
                        "source": "deepseek_web",
                        "intercept_events": len(captured_json),
                        "stream_chunks": len(stream_chunks),
                        "refs": "patterns: geo_marketing intercept + gitgeo selectors (reimplemented)",
                    },
                    latency_ms=latency,
                    screenshot_path=shot,
                )
            finally:
                try:
                    if context:
                        context.close()
                except Exception:
                    pass
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass


def _extract_text_from_event(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    # common shapes
    for key in ("v", "text", "content", "answer", "message"):
        if key in data and isinstance(data[key], str):
            return data[key]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        ch0 = choices[0] or {}
        delta = ch0.get("delta") or {}
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            return delta["content"]
        msg = ch0.get("message") or {}
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    # nested
    for k, v in data.items():
        if isinstance(v, dict):
            t = _extract_text_from_event(v)
            if t:
                return t
    return ""


def _extract_citations(data: Dict[str, Any]) -> List[CitationData]:
    out: List[CitationData] = []

    def walk(obj: Any):
        if isinstance(obj, dict):
            url = obj.get("url") or obj.get("link")
            if isinstance(url, str) and url.startswith("http"):
                out.append(
                    CitationData(
                        url=url,
                        title=obj.get("title") if isinstance(obj.get("title"), str) else None,
                        snippet=obj.get("snippet") if isinstance(obj.get("snippet"), str) else None,
                        domain=urlparse(url).netloc or None,
                    )
                )
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for it in obj:
                walk(it)

    walk(data)
    return out


def _looks_like_login(page) -> bool:
    try:
        content = page.content().lower()
        if "login" in page.url.lower():
            return True
        # weak heuristics
        if "请登录" in content or "手机号登录" in content:
            return True
        # if input missing and login button present
        if page.locator("text=登录").count() > 0 and page.locator("textarea").count() == 0:
            return True
    except Exception:
        return False
    return False



def _capture_answer_evidence(page, shot_path: str, expected_text: str = "") -> None:
    """Capture complete answer evidence: hide chrome, screenshot answer node fully.

    Viewport-only screenshots are useless for long answers. Prefer element
    screenshot of the longest assistant markdown bubble (full element height).
    """
    try:
        page.add_style_tag(
            content="""
            /* hide left conversation rail / nav chrome for cleaner evidence */
            aside, nav, [class*='sidebar'], [class*='SideBar'], [class*='sider'],
            [class*='history'], [class*='History'] {
              display: none !important;
            }
            body { overflow: auto !important; }
            """
        )
    except Exception:
        pass

    # give layout a moment after CSS
    time.sleep(0.4)

    # pick best answer element by text length / overlap with extracted text
    best = None
    best_score = -1
    for sel in (".ds-markdown", "[class*='ds-markdown']", ".message-content"):
        try:
            loc = page.locator(sel)
            n = loc.count()
        except Exception:
            continue
        for i in range(n):
            node = loc.nth(i)
            try:
                txt = (node.inner_text(timeout=1500) or "").strip()
            except Exception:
                continue
            if len(txt) < 80 or _is_noise_text(txt):
                continue
            score = len(txt)
            if expected_text:
                # bonus if shares prefix/content with extracted answer
                sample = expected_text[:80]
                if sample and sample in txt:
                    score += 10000
                elif txt[:60] in expected_text:
                    score += 5000
            if score > best_score:
                best_score = score
                best = node

    if best is not None:
        try:
            best.scroll_into_view_if_needed(timeout=5000)
            time.sleep(0.3)
            # element screenshot includes full scroll height of the node
            best.screenshot(path=shot_path, type="png")
            return
        except Exception as exc:
            logger.warning("element screenshot failed: %s", exc)

    # fallback: scroll main to top then full page
    try:
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.2)
        page.screenshot(path=shot_path, full_page=True, type="png")
    except Exception as exc:
        logger.warning("full_page screenshot failed: %s", exc)
        page.screenshot(path=shot_path, full_page=False, type="png")


def _clean_answer_text(text: str) -> str:
    text = (text or "").strip()
    import re
    # stream glue tokens at ends
    text = re.sub(r"^(FINISHEDSEARCH|FINISHED|SEARCH)+", "", text, flags=re.I).lstrip(" :|-")
    text = re.sub(r"(FINISHEDSEARCH|FINISHED|SEARCH)[\w\u4e00-\u9fff]*$", "", text, flags=re.I).strip()
    # common broken year prefix after stripping FINISHEDSEARCH2026 -> if starts with lone 6年 fix
    if re.match(r"^6年", text):
        text = "2026年" + text[len("6年"):]
    text = re.sub(r"^2026年6年", "2026年", text)
    return text.strip()


def _is_noise_text(text: str) -> bool:

    if not text or len(text.strip()) < 40:
        return True
    # pure sidebar: many short history titles, no paragraph structure
    hits = sum(1 for k in SIDEBAR_NOISE if k in text)
    if hits >= 3 and text.count("\n") > 15 and "。 " not in text and "。" not in text[:200]:
        return True
    if text.strip().startswith("开启新对话") and "2026" in text and len(text) < 800:
        # classic bad scrape of left rail
        if "请简短" not in text and "综合来看" not in text and "没有唯一" not in text:
            return True
    return False


def _dom_answer_text(page) -> str:
    """Extract the longest plausible assistant markdown, not the sidebar."""
    candidates = []
    for sel in (".ds-markdown", "[class*='ds-markdown']", ".message-content"):
        try:
            nodes = page.locator(sel)
            n = nodes.count()
            for i in range(n):
                try:
                    txt = (nodes.nth(i).inner_text(timeout=1500) or "").strip()
                except Exception:
                    continue
                if not txt or _is_noise_text(txt):
                    continue
                candidates.append(txt)
        except Exception:
            continue
    if not candidates:
        return ""
    # prefer longest non-noise
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def _wait_for_answer(page, stream_chunks: List[str], timeout_ms: int) -> str:
    deadline = time.time() + timeout_ms / 1000.0
    last = ""
    stable_hits = 0
    while time.time() < deadline:
        assembled = ""
        if stream_chunks:
            assembled = "".join(stream_chunks).strip()
        dom = _dom_answer_text(page)
        # choose better of stream vs dom
        cand = assembled if len(assembled) >= len(dom) else dom
        if cand and not _is_noise_text(cand):
            if len(cand) > len(last) + 10:
                last = cand
                stable_hits = 0
            else:
                stable_hits += 1
        else:
            stable_hits = 0
        # require substantial answer + stability ~4s
        if last and len(last) > 120 and stable_hits >= 8:
            break
        time.sleep(0.5)
    # strip common stream glue artifacts
    last = (last or "").strip()
    for junk in ("FINISHEDSEARCH", "FINISHED", "SEARCH"):
        if last.startswith(junk) and len(last) > len(junk) + 10:
            last = last[len(junk):].lstrip(" :|-")
    return last
