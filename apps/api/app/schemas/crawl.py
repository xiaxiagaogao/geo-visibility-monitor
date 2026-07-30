from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


ALLOWED_PLATFORMS = ("deepseek", "doubao", "kimi", "tongyi")


class CrawlJobCreate(BaseModel):
    prompt_id: int
    platform: str = "deepseek"
    samples: int = Field(1, ge=1, le=10)


class CrawlJobOut(BaseModel):
    id: int
    prompt_id: int
    platform: str
    status: str
    sample_index: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    response_id: Optional[int] = None

    model_config = {"from_attributes": True}


class CrawlJobListOut(BaseModel):
    items: List[CrawlJobOut]
    total: int


class CrawlJobDetailOut(CrawlJobOut):
    prompt_text: Optional[str] = None
    response: Optional["RawResponseOut"] = None


class CitationOut(BaseModel):
    id: int
    cite_index: Optional[int] = None
    url: str
    domain: str
    title: Optional[str] = None
    snippet: Optional[str] = None

    model_config = {"from_attributes": True}


class RawResponseOut(BaseModel):
    id: int
    job_id: int
    platform: str
    prompt_text: str
    full_text: str
    html_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    created_at: datetime
    citations: List[CitationOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RawResponseListOut(BaseModel):
    items: List[RawResponseOut]
    total: int


class WorkerRunOut(BaseModel):
    processed: int
    job_ids: List[int]
