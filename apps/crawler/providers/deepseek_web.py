"""DeepSeek Web provider — stub for POC.

Next step: implement Playwright flow (open chat, type prompt, capture answer).
Study patterns from open-source (network intercept + DOM fallback); write our own code.
"""

from __future__ import annotations

from .base import BaseProvider, CrawlResult


class DeepSeekWebProvider(BaseProvider):
    platform = "deepseek"

    def __init__(self, headless: bool = True, timeout_ms: int = 60000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def search(self, prompt: str) -> CrawlResult:
        raise NotImplementedError(
            "DeepSeek Web crawl not implemented yet — see apps/crawler/README.md"
        )
