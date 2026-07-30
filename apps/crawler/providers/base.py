from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Citation:
    url: str
    title: str | None = None
    snippet: str | None = None
    domain: str | None = None


@dataclass
class CrawlResult:
    platform: str
    prompt: str
    full_text: str
    citations: list[Citation] = field(default_factory=list)
    raw_json: dict[str, Any] | None = None
    latency_ms: int | None = None
    screenshot_path: str | None = None


class BaseProvider(ABC):
    platform: str

    @abstractmethod
    def search(self, prompt: str) -> CrawlResult:
        """Run one prompt against the platform UI or API."""
