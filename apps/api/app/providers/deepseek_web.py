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
                    _capture_answer_evidence(page, shot, expected_text=full_text, question=prompt)

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

                # L0 = 原始回答（docs/10）：full_text 存抓到什么就是什么，
                # 清洗只做派生字段，且仅在确实改动了内容时才记录
                raw_text = (full_text or "").strip()
                cleaned = _clean_answer_text(raw_text)
                raw_json: Dict[str, Any] = {
                    "source": "deepseek_web",
                    "intercept_events": len(captured_json),
                    "stream_chunks": len(stream_chunks),
                    "refs": "patterns: geo_marketing intercept + gitgeo selectors (reimplemented)",
                }
                if cleaned != raw_text:
                    raw_json["cleaned_text"] = cleaned

                return CrawlResult(
                    platform="deepseek",
                    prompt=prompt,
                    full_text=raw_text,
                    citations=uniq_cites,
                    raw_json=raw_json,
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



def _sanitize_answer_html(html: str) -> str:
    """粗筛第三方页面片段 —— 只是纵深防御的第二层，真正兜底的是文档里的 CSP。

    这段 HTML 来自 chat.deepseek.com 的回答气泡，会被 set_content 到同一个
    browser context（带着登录态）的新页面里渲染截图。原实现只用
    ``\\son\\w+=(["']).*?\\1`` 剥事件处理器，匹配不到**无引号**写法，
    ``<img src=x onerror=alert(1)>`` 能整条活下来。
    """
    out = html
    # 会执行脚本或发起外部请求的元素，整块删掉
    for tag in ("script", "iframe", "object", "embed", "link", "meta", "base", "svg"):
        out = re.sub(rf"<{tag}[\s\S]*?</{tag}\s*>", "", out, flags=re.I)
        out = re.sub(rf"<{tag}\b[^>]*/?>", "", out, flags=re.I)
    # 事件处理器：带引号、无引号、JSX 花括号三种写法
    out = re.sub(r"""\son\w+\s*=\s*(["']).*?\1""", " ", out, flags=re.I | re.S)
    out = re.sub(r"\son\w+\s*=\s*\{[^}]*\}", " ", out, flags=re.I)
    out = re.sub(r"\son\w+\s*=\s*[^\s>]+", " ", out, flags=re.I)
    # javascript: / data: 伪协议
    out = re.sub(
        r"""\s(?:href|src|xlink:href)\s*=\s*(["'])\s*(?:javascript|data|vbscript):[^"']*\1""",
        " ",
        out,
        flags=re.I,
    )
    return out


def _capture_answer_evidence(
    page,
    shot_path: str,
    expected_text: str = "",
    question: str = "",
) -> None:
    """Clean complete-answer evidence screenshot.

    Where: VPS crawler container (Playwright headless Chromium), NOT Mac Chrome.
    How:
      1) Extract answer HTML via Playwright locators (avoid fragile page.evaluate)
      2) Open a blank page, set_content a dark card document with Q + full answer
      3) screenshot(full_page=True) so tables/lists are fully visible
    Fallback: hide chrome on live page + expand scroll parents + full_page
    """
    import html as html_lib
    import re as _re

    sample = (expected_text or "").strip()[:80]
    answer_html = ""
    answer_text = ""
    best_score = -1

    # Prefer Playwright locator API over complex evaluate (avoids SyntaxError edge cases)
    for sel in (".ds-markdown", "[class*='ds-markdown']", ".message-content"):
        try:
            nodes = page.locator(sel)
            n = nodes.count()
        except Exception:
            continue
        for i in range(min(n, 40)):
            try:
                node = nodes.nth(i)
                txt = (node.inner_text(timeout=2000) or "").strip()
                if not txt or len(txt) < 40:
                    continue
                if txt.startswith("开启新对话") and len(txt) < 900:
                    continue
                score = len(txt)
                try:
                    if node.locator("table").count() > 0:
                        score += 4000
                    if node.locator("li").count() > 0:
                        score += 400
                except Exception:
                    pass
                if sample and sample[:24] in txt:
                    score += 100000
                if score > best_score:
                    best_score = score
                    answer_text = txt
                    answer_html = node.inner_html(timeout=2000) or ""
            except Exception:
                continue
        if answer_html:
            break

    if not answer_html and answer_text:
        answer_html = f"<pre style='white-space:pre-wrap;font:inherit'>{html_lib.escape(answer_text)}</pre>"

    q = (question or "").strip()
    if not q:
        # best-effort: short line ending with ? from page text
        try:
            body = page.locator("body").inner_text(timeout=2000) or ""
            for line in reversed(body.splitlines()):
                t = line.strip()
                if 4 < len(t) < 120 and ("？" in t or "?" in t):
                    q = t
                    break
        except Exception:
            q = ""

    status = ""
    try:
        body = page.locator("body").inner_text(timeout=2000) or ""
        m = _re.search(r"已阅读\s*\d+\s*个网页", body)
        if m:
            status = m.group(0)
    except Exception:
        pass

    if answer_html:
        answer_html = _sanitize_answer_html(answer_html)

        q_html = (
            f'<div class="q">{html_lib.escape(q)}</div>' if q else ""
        )
        status_html = (
            f'<div class="meta">{html_lib.escape(status)}</div>' if status else ""
        )
        # CSP 才是真正的防线：正则消毒永远有绕过，而这份文档只需要文字+样式，
        # 直接禁掉脚本与一切外部请求（图片只允许内联 data:）。
        doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8" />
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src 'none'; script-src 'none'; frame-src 'none'; connect-src 'none'" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:#0f1115;color:#e8eaed}}
body{{padding:28px 36px 56px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;line-height:1.7;font-size:15px}}
.wrap{{max-width:920px;margin:0 auto}}
.q{{display:block;margin:0 0 16px auto;padding:10px 16px;border-radius:18px;background:#2a2f3a;color:#f3f4f6;max-width:88%;width:fit-content;margin-left:auto;white-space:pre-wrap}}
.meta{{color:#9aa3b2;font-size:13px;margin:0 0 14px}}
.answer{{background:#161b22;border:1px solid #2a3344;border-radius:14px;padding:22px 24px}}
.answer p{{margin:0 0 0.85em}}
.answer h1,.answer h2,.answer h3,.answer h4{{margin:1em 0 0.5em;line-height:1.35}}
.answer table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px}}
.answer th,.answer td{{border:1px solid #3a455a;padding:8px 10px;vertical-align:top}}
.answer th{{background:#1e2633;text-align:left}}
.answer a{{color:#8ab4ff;text-decoration:none}}
.answer ul,.answer ol{{padding-left:1.35em;margin:0.4em 0 0.9em}}
.answer li{{margin:0.25em 0}}
.answer code{{background:#1e2633;padding:0.1em 0.35em;border-radius:4px;font-size:0.92em}}
.answer pre{{background:#1e2633;padding:12px;border-radius:8px;overflow:auto}}
.answer strong{{font-weight:600}}
</style></head><body><div class="wrap">
{q_html}{status_html}<div class="answer">{answer_html}</div>
</div></body></html>"""
        evidence = None
        try:
            evidence = page.context.new_page()
            evidence.set_viewport_size({"width": 1100, "height": 900})
            evidence.set_content(doc, wait_until="load")
            evidence.wait_for_timeout(400)
            # ensure full document height is measured after fonts/layout
            try:
                evidence.evaluate(
                    """async () => {
                      window.scrollTo(0, document.body.scrollHeight);
                      await new Promise(r => setTimeout(r, 120));
                      window.scrollTo(0, 0);
                    }"""
                )
                evidence.wait_for_timeout(150)
            except Exception:
                pass
            evidence.screenshot(path=shot_path, full_page=True, type="png")
            logger.info(
                "evidence clean-render full_page saved %s html_len=%s text_len=%s",
                shot_path,
                len(answer_html),
                len(answer_text),
            )
            return
        except Exception as exc:
            logger.warning("clean-render screenshot failed: %s", exc)
        finally:
            if evidence is not None:
                try:
                    evidence.close()
                except Exception:
                    pass

    # Fallback: live page full_page after hiding chrome / expanding scrollers
    try:
        page.add_style_tag(
            content=(
                "aside,nav,[class*='sidebar' i],[class*='history' i],"
                "[class*='side-bar' i]{display:none!important}"
                "textarea,[contenteditable='true'],[class*='composer' i],"
                "[class*='input-area' i]{visibility:hidden!important;height:0!important;overflow:hidden!important}"
            )
        )
        page.evaluate(
            """() => {
              const answers = Array.from(document.querySelectorAll('.ds-markdown'));
              let best = null, n = 0;
              for (const a of answers) {
                const t = (a.innerText || '').trim();
                if (t.length > n) { n = t.length; best = a; }
              }
              if (!best) return false;
              let p = best;
              while (p && p !== document.body) {
                const st = getComputedStyle(p);
                if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && p.scrollHeight > p.clientHeight + 20) {
                  p.style.setProperty('height', p.scrollHeight + 'px', 'important');
                  p.style.setProperty('max-height', 'none', 'important');
                  p.style.setProperty('overflow', 'visible', 'important');
                }
                p.style.setProperty('max-height', 'none', 'important');
                p = p.parentElement;
              }
              document.documentElement.style.overflow = 'visible';
              document.body.style.overflow = 'visible';
              return true;
            }"""
        )
        _scroll_page_for_lazy_load(page, step=500, pause_ms=80)
        page.evaluate("window.scrollTo(0,0)")
        time.sleep(0.3)
        page.screenshot(path=shot_path, full_page=True, type="png")
        logger.info("evidence live full_page fallback saved %s", shot_path)
    except Exception as exc:
        logger.warning("live full_page failed: %s", exc)
        page.screenshot(path=shot_path, full_page=False, type="png")


def _clean_answer_text(text: str) -> str:
    """剥掉流式拼接残留的胶水 token —— 仅用于派生字段。

    结果写进 raw_json.cleaned_text，绝不覆盖 full_text：docs/10 定义 L0 = 原始回答，
    证据必须可审计、可复核。

    只剥开头独立成词的 FINISHED/SEARCH（后面不能紧跟字母数字）。
    原实现有三条会破坏正文的规则，已删除：

    1. 开头 ``(FINISHEDSEARCH|FINISHED|SEARCH)+`` 无边界条件 —— 把
       「SEARCH引擎优化…」开头的正文砍成「引擎优化…」。本项目做的就是 GEO/SEO，
       这种开头完全可能出现。
    2. 结尾 ``(...)[\\w\\u4e00-\\u9fff]*$`` —— ``\\w`` 在 Python 下匹配中文，
       结尾只要出现 search 字样就把后面整串吞掉。
       实测「…目前主营业务为家装SEARCH」被截断成「…目前主营业务为家装」。
    3. ``^6年`` → ``2026年`` —— 硬编码年份猜测，直接改写模型答案：
       正常的「6年内…」被写成「2026年内…」，而且过了 2026 必错。
    """
    text = (text or "").strip()
    # FINISHEDSEARCH / FINISHED 是无歧义的控制 token，正常回答不会这样开头 → 无条件剥。
    # 裸 SEARCH 有歧义（"SEARCH引擎优化…" 是正文），必须后接 串尾/空白/分隔符 才剥。
    text = re.sub(r"^(?:FINISHEDSEARCH|FINISHED)", "", text, flags=re.I)
    text = re.sub(r"^SEARCH(?=$|[\s:|-])", "", text, flags=re.I)
    return text.lstrip(" :|-").strip()


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


# 流式拼接产生的控制 token。正常中文回答不会以这些 ASCII 串开头，
# 出现即说明首块被它顶替了。
STREAM_GLUE_PREFIXES = ("FINISHEDSEARCH", "FINISHED")


def _pick_answer_text(assembled: str, dom: str) -> str:
    """在「流式拼接」与「DOM 渲染」之间选 L0 正文。

    优先 DOM。VPS 实测（job 37 / response 22）：

        DOM    挑选一家靠谱的装修公司是件耗时又重要的事，…
        stream FINISHEDSEARCH一家靠谱的装修公司是件耗时又重要的事，…

    SSE 拼接会丢掉**首块**，位置上被 FINISHEDSEARCH 顶替。原实现「谁长选谁」，
    而带着胶水 token 的 stream 往往更长，于是每次都选中缺头的那份 ——
    历史样本 id=10/12/13/14/16 开头缺字都是这么来的。

    首字直接决定 position_bucket 的 head/middle/tail，不能将就。
    """
    assembled = (assembled or "").strip()
    dom = (dom or "").strip()
    if not dom:
        return assembled
    if not assembled:
        return dom
    # 侧栏误抓的 DOM 一律不参与竞争（含最后的比长度兜底）
    if _is_noise_text(dom):
        return assembled
    # stream 带胶水前缀 = 首块已丢，直接用 DOM
    if assembled.upper().startswith(STREAM_GLUE_PREFIXES):
        return dom
    # DOM 基本完整时同样优先它（渲染结果才是真值）
    if len(dom) >= len(assembled) * 0.9:
        return dom
    # DOM 明显更短 = 还在生成中，退回 stream
    return assembled


def _wait_for_answer(page, stream_chunks: List[str], timeout_ms: int) -> str:
    deadline = time.time() + timeout_ms / 1000.0
    last = ""
    stable_hits = 0
    while time.time() < deadline:
        assembled = ""
        if stream_chunks:
            assembled = "".join(stream_chunks).strip()
        dom = _dom_answer_text(page)
        cand = _pick_answer_text(assembled, dom)
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
    # 原样返回：胶水 token 的剥离交给 _clean_answer_text 写进派生字段，
    # 这里若动手就等于污染了 L0（docs/10）
    return (last or "").strip()
