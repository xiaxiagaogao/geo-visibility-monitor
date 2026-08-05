"""``/v1/config/*`` —— 下发口径与能力，让前端不必硬编码。

``/v1/config/metrics`` 原本挂在 counts 路由里，随本次新增 ``platforms`` 一起收到这里；
URL 未变，前端无需改动。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.providers import registry
from app.schemas.config import MetricsConfigOut, PlatformListOut, PlatformOut
from app.services import counts as counts_svc

router = APIRouter(prefix="/v1/config", tags=["config"])


@router.get("/metrics", response_model=MetricsConfigOut)
def get_metrics_config():
    """口径下发：answer_status 枚举、mention 类型、位置桶、默认权重、标注版本。"""
    return MetricsConfigOut(**counts_svc.metrics_config())


@router.get("/platforms", response_model=PlatformListOut)
def get_platforms():
    """平台可用性下发。

    在此之前前端没有任何办法知道「哪些平台已接入」，只能硬编码；
    而 ``ALLOWED_PLATFORMS`` 又包含没有 Provider 的平台，照它渲染会给出假选项。
    """
    crawl_mode = (get_settings().crawl_mode or "fake").lower()
    return PlatformListOut(
        items=[PlatformOut(**p) for p in registry.describe(crawl_mode=crawl_mode)],
        crawl_mode=crawl_mode,
    )
