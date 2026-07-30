from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from geo_metrics import (
    is_recommended,
    match_brand,
    position_bucket,
    position_score,
    score_sentiment,
    aggregate_visibility,
    composite_score,
)
from geo_metrics.aggregate import ResponseObservation

from app.core.db import check_connection

app = FastAPI(title="GEO Demo API", version="0.1.0")


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


@app.get("/health")
def health():
    return {"ok": True, "service": "geo-api"}


@app.get("/health/db")
def health_db():
    """B1: probe database. Returns 200 only if DB is reachable."""
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
