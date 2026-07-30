"""Backward-compatible entry: real implementation is crawl_runner (B5)."""
from __future__ import annotations

from app.services.crawl_runner import process_job, run_once

__all__ = ["run_once", "process_job"]
