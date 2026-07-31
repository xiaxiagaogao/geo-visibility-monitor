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
                        viewport={"width": 1280, "height": 1600},
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






def _scroll_page_for_lazy_load(page, step: int = 400, pause_ms: int = 150) -> None:
    """Scroll through the page to trigger lazy-loaded content (doc 4.1)."""
    page.evaluate(
        """async ({ step, pause }) => {
          await new Promise((resolve) => {
            let total = 0;
            const timer = setInterval(() => {
              const sh = Math.max(
                document.body?.scrollHeight || 0,
                document.documentElement?.scrollHeight || 0
              );
              window.scrollBy(0, step);
              total += step;
              if (total >= sh - window.innerHeight - 10) {
                clearInterval(timer);
                resolve(null);
              }
            }, pause);
          });
        }""",
        {"step": step, "pause": pause_ms},
    )


def _capture_answer_evidence(page, shot_path: str, expected_text: str = "") -> None:
    """Full-page evidence shot for headless Chromium.

    Approach from project note (Playwright 全页面截图功能说明):
      1) hide non-content chrome (sidebar/composer) so the long page is the answer column
      2) scroll through page to trigger lazy load
      3) scroll back to top
      4) page.screenshot(full_page=True)  ← real full scroll-range capture

    Do NOT use viewport-only shots; do NOT rely on clip rect (height is viewport-limited).
    """
    # 1) hide left rail + bottom input so full_page is mostly the answer stream
    try:
        page.add_style_tag(
            content="""
            aside, nav,
            [class*='sidebar' i], [class*='SideBar'], [class*='sider'],
            [class*='history' i], [class*='History'] {
              display: none !important;
              width: 0 !important;
              min-width: 0 !important;
            }
            textarea {
              visibility: hidden !important;
            }
            /* reduce sticky/fixed chrome repeating in fullPage stitches */
            [style*='position: fixed'], [style*='position:fixed'],
            [class*='fixed' i], header {
              position: absolute !important;
            }
            html, body {
              height: auto !important;
              max-height: none !important;
              overflow: auto !important;
            }
            """
        )
    except Exception:
        pass

    time.sleep(0.4)

    # DeepSeek is a SPA: content often lives in an INTERNAL scroll container.
    # window scrollHeight stays ~viewport (900). Expand that container first.
    try:
        meta = page.evaluate(
            """() => {
              const answers = Array.from(document.querySelectorAll('.ds-markdown, [class*="ds-markdown"]'));
              let best = null, bestLen = 0;
              for (const n of answers) {
                const t = (n.innerText || '').trim();
                if (t.length > bestLen) { bestLen = t.length; best = n; }
              }
              if (!best) return { ok: false };

              const scrollParent = (el) => {
                let p = el.parentElement;
                while (p && p !== document.body) {
                  const st = getComputedStyle(p);
                  const oy = st.overflowY;
                  if ((oy === 'auto' || oy === 'scroll' || oy === 'overlay') && p.scrollHeight > p.clientHeight + 20) {
                    return p;
                  }
                  p = p.parentElement;
                }
                return document.scrollingElement || document.documentElement;
              };

              const sp = scrollParent(best);
              // expand ancestors so full content participates in layout height
              let cur = best;
              for (let i = 0; i < 14 && cur; i++) {
                cur.style.setProperty('overflow', 'visible', 'important');
                cur.style.setProperty('max-height', 'none', 'important');
                cur.style.setProperty('height', 'auto', 'important');
                cur = cur.parentElement;
              }
              // expand scroll parent to its full scrollHeight (key for full_page)
              if (sp && sp !== document.documentElement && sp !== document.body) {
                const sh = sp.scrollHeight;
                sp.style.setProperty('overflow', 'visible', 'important');
                sp.style.setProperty('max-height', 'none', 'important');
                sp.style.setProperty('height', sh + 'px', 'important');
              }
              // also expand document
              document.documentElement.style.setProperty('height', 'auto', 'important');
              document.body.style.setProperty('height', 'auto', 'important');
              document.documentElement.style.setProperty('overflow', 'visible', 'important');
              document.body.style.setProperty('overflow', 'visible', 'important');

              void document.body.offsetHeight;
              return {
                ok: true,
                answerLen: bestLen,
                docScrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
                spTag: sp ? sp.tagName : null,
                spScrollHeight: sp ? sp.scrollHeight : null,
              };
            }"""
        )
        logger.info("expand scroll containers: %s", meta)
    except Exception as exc:
        logger.warning("expand scroll containers failed: %s", exc)

    # 2) scroll document (and internal parents if any remaining) to trigger lazy load
    try:
        _scroll_page_for_lazy_load(page, step=500, pause_ms=100)
    except Exception as exc:
        logger.warning("lazy scroll failed: %s", exc)

    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    time.sleep(0.5)

    try:
        h = page.evaluate(
            """() => Math.max(
              document.body?.scrollHeight || 0,
              document.documentElement?.scrollHeight || 0
            )"""
        )
        logger.info("full_page capture scrollHeight=%s", h)
    except Exception:
        h = 0

    # 3) primary: full_page=True (after expanding internal scrollers)
    page.screenshot(path=shot_path, full_page=True, type="png")
    logger.info("evidence full_page screenshot saved %s", shot_path)

    # 4) if still short, element screenshot of longest answer (full element box)
    try:
        from PIL import Image

        im = Image.open(shot_path)
        w, h0 = im.size
        need_taller = (expected_text and len(expected_text) > 300 and h0 < 1500) or h0 <= 1000
        if need_taller:
            loc = page.locator(".ds-markdown")
            best_i, best_len = -1, 0
            for i in range(loc.count()):
                try:
                    txt = (loc.nth(i).inner_text(timeout=800) or "").strip()
                except Exception:
                    continue
                if len(txt) > best_len and not _is_noise_text(txt):
                    best_len = len(txt)
                    best_i = i
            if best_i >= 0:
                node = loc.nth(best_i)
                handle = node.element_handle()
                if handle:
                    page.evaluate(
                        """(el) => {
                          let cur = el;
                          for (let i = 0; i < 14 && cur; i++) {
                            cur.style.setProperty('overflow', 'visible', 'important');
                            cur.style.setProperty('max-height', 'none', 'important');
                            cur.style.setProperty('height', 'auto', 'important');
                            cur = cur.parentElement;
                          }
                        }""",
                        handle,
                    )
                time.sleep(0.3)
                alt = shot_path.replace(".png", "_elem.png")
                node.screenshot(path=alt, type="png")
                im2 = Image.open(alt)
                if im2.height > h0:
                    im2.save(shot_path)
                    logger.info(
                        "using taller element shot %s (%dx%d -> %dx%d)",
                        shot_path,
                        w,
                        h0,
                        im2.width,
                        im2.height,
                    )
    except Exception as exc:
        logger.debug("element height boost skipped: %s", exc)



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
        if last and len(last) > 120 and stable_hits >= 5:
            break
        time.sleep(0.5)
    # strip common stream glue artifacts
    last = (last or "").strip()
    for junk in ("FINISHEDSEARCH", "FINISHED", "SEARCH"):
        if last.startswith(junk) and len(last) > len(junk) + 10:
            last = last[len(junk):].lstrip(" :|-")
    return last
