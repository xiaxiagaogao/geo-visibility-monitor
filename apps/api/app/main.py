from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from geo_metrics import (
    aggregate_visibility,
    composite_score,
    is_recommended,
    match_brand,
    position_bucket,
    position_score,
    score_sentiment,
)
from geo_metrics.aggregate import ResponseObservation

from app.api import brands as brands_router
from app.api import crawl_jobs as crawl_jobs_router
from app.api import health_credentials as health_credentials_router
from app.api import prompts as prompts_router
from app.api import responses as responses_router
from app.api import counts as counts_router
from app.api import auth as auth_router
from app.api import config as config_router
from app.api import qa as qa_router
from app.api import ingest as ingest_router
from app.api import tasks as tasks_router
from app.api import users as users_router
from app.core.config import get_settings
from app.core.db import check_connection
from app.core.schema import ensure_schema
from app.core.security import ApiKeyMiddleware, warn_if_open
from app.worker_loop import start_worker_loop, stop_worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    warn_if_open()
    ensure_schema()
    start_worker_loop()
    yield
    stop_worker_loop()


app = FastAPI(
    title="GEO Demo API",
    version="0.8.0",
    description="GEO learning API — B2–B7 backend ready; QA preview at /qa",
    lifespan=lifespan,
)

app.add_middleware(ApiKeyMiddleware)

# CORS 必须**后加**：Starlette 里后加的中间件在外层，先执行。
# 顺序反了的话，预检 OPTIONS 会先撞上 ApiKeyMiddleware 拿到不带 CORS 头的 401，
# 浏览器直接判定跨域失败 —— 现象是「所有请求都失败但 curl 一切正常」。
_cors_origins = get_settings().cors_origins
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        # 带 Cookie 的跨站请求不允许用 "*"，必须是具体 Origin 列表
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(brands_router.router)
app.include_router(prompts_router.router)
app.include_router(crawl_jobs_router.router)
app.include_router(responses_router.router)
app.include_router(counts_router.router)
app.include_router(config_router.router)
app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(qa_router.router)
app.include_router(ingest_router.router)
app.include_router(tasks_router.router)
app.include_router(health_credentials_router.router)


class AnalyzeRequest(BaseModel):
    body: str
    aliases: List[str] = Field(default_factory=list)
    citation_text: str = ""


class AnalyzeResponse(BaseModel):
    mentioned: bool
    mention_type: str
    matched_term: Optional[str]
    position_bucket: Optional[str]
    position_score: float
    recommended: bool
    sentiment: str
    sentiment_score: float


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/qa")


@app.get("/health")
def health():
    """公开存活探针 —— 部署脚本/容器健康检查用，故意不泄露运行配置。"""
    return {"ok": True, "service": "geo-api", "version": "0.8.0"}


@app.get("/health/config")
def health_config():
    """运行配置（需鉴权）。原先挂在 /health 上，对公网泄露 crawl_mode 等信息。"""
    from app.core.config import get_settings
    s = get_settings()
    return {
        "ok": True,
        "version": "0.8.0",
        "qa": "/qa",
        "ingest": "/v1/ingest/l0",
        "crawl_mode": s.crawl_mode,
        "worker_enabled": s.fake_worker_enabled,
        "auth_enabled": bool(s.api_key),
    }


@app.get("/health/db")
def health_db():
    try:
        info = check_connection()
        return {"ok": True, "database": info}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.post("/v1/analyze/response", response_model=AnalyzeResponse)
def analyze_response(req: AnalyzeRequest):
    m = match_brand(req.body, req.aliases, citation_text=req.citation_text)
    bucket = position_bucket(req.body, m.offset)
    sent = score_sentiment(req.body)
    rec = is_recommended(req.body, req.aliases)
    return AnalyzeResponse(
        mentioned=m.mentioned,
        mention_type=m.mention_type,
        matched_term=m.matched_term,
        position_bucket=bucket,
        position_score=position_score(bucket),
        recommended=rec,
        sentiment=sent.label,
        sentiment_score=sent.score,
    )


class BatchItem(BaseModel):
    body: str
    aliases: List[str]
    citation_text: str = ""


class BatchAnalyzeRequest(BaseModel):
    items: List[BatchItem]


@app.post("/v1/analyze/batch")
def analyze_batch(req: BatchAnalyzeRequest):
    rows: List[ResponseObservation] = []
    details = []
    for it in req.items:
        m = match_brand(it.body, it.aliases, citation_text=it.citation_text)
        bucket = position_bucket(it.body, m.offset)
        ps = position_score(bucket)
        sent = score_sentiment(it.body)
        rec = is_recommended(it.body, it.aliases)
        rows.append(
            ResponseObservation(
                mention=m,
                position_score=ps,
                recommended=rec,
                sentiment_score=sent.score,
            )
        )
        details.append(
            {
                "mentioned": m.mentioned,
                "mention_type": m.mention_type,
                "position_bucket": bucket,
                "recommended": rec,
                "sentiment": sent.label,
            }
        )
    agg = aggregate_visibility(rows)
    return {
        "aggregate": {
            "sample_size": agg.sample_size,
            "visibility_rate": agg.visibility_rate,
            "recommend_rate": agg.recommend_rate,
            "avg_position_score": agg.avg_position_score,
            "sentiment_net": agg.sentiment_net,
            "composite_score": composite_score(agg),
        },
        "items": details,
    }
