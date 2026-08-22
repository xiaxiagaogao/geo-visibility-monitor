from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CitationData:
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    domain: Optional[str] = None
    cite_index: Optional[int] = None


@dataclass
class CrawlResult:
    platform: str
    prompt: str
    full_text: str
    citations: List[CitationData] = field(default_factory=list)
    raw_json: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    screenshot_path: Optional[str] = None
    #: P2-37 这次有没有联网检索。**None = 不知道**，不是「没联网」
    search_used: Optional[bool] = None


class BaseProvider(ABC):
    platform: str

    @abstractmethod
    def search(self, prompt: str) -> CrawlResult:
        """Run one prompt; raise on hard failure (caller marks job failed)."""
