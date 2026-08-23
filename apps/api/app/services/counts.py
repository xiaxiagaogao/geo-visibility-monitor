from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import (
    Citation,
    CompetitorLink,
    CrawlJob,
    Mention,
    Prompt,
    RawResponse,
    Run,
    RunCompetitor,
    Task,
)
from app.services.annotate import ANNOTATOR_VERSION
from app.services.brands import get_brand_or_404


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_dt(value: Optional[str], *, end: bool = False) -> Optional[datetime]:
    """解析 ISO 时间；``end=True`` 时纯日期补到当天最后一刻。

    区间是闭区间（created_at <= to）。若 ``to=2026-08-01`` 按 00:00:00 处理，
    整个 8/1 都会被排除 —— 前端传日期而非时间戳时必踩。
    """
    if not value:
        return None
    v = value.strip()
    date_only = bool(_DATE_ONLY.match(v))
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid datetime: {value}",
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if end and date_only:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def _empty_brand_counts(brand_id: int) -> Dict[str, int]:
    return {
        "brand_id": brand_id,
        "m_mentioned": 0,
        "m_body": 0,
        "m_citation_only": 0,
        "m_none": 0,
        "m_head": 0,
        "m_middle": 0,
        "m_tail": 0,
        "m_first": 0,
    }


def _empty_den() -> Dict[str, int]:
    return {
        "n_valid": 0,
        "n_total_responses": 0,
        "n_empty": 0,
        "n_too_short": 0,
        "n_error": 0,
        "n_unannotated": 0,
    }



FAKE_SOURCES = frozenset({"fake_worker", "fake_provider", "fake", "fake_provider_v1"})


def is_fake_response(resp: RawResponse) -> bool:
    """Historical B3 fake L0 rows — excluded from L2 by default."""
    raw = resp.raw_json if isinstance(resp.raw_json, dict) else {}
    src = str(raw.get("source") or "").strip().lower()
    if src.startswith("fake") or src in FAKE_SOURCES:
        return True
    text = (resp.full_text or "").lstrip()
    if text.startswith("【假数据"):
        return True
    return False


def _assert_run_belongs_to_brand(db: Session, run_id: int, brand_id: int) -> None:
    """校验这个 run 确实属于这个 brand（沿 Run → Task → Task.brand_id 查一次）。

    放在这里而不是只在路由层做，理由是下面 ``competitor_ids`` 的快照分支
    完全信任「run 与 brand 匹配」这个前提 —— 不匹配时它会把另一个租户
    run 快照里的 competitor_brand_id 原样吐出去。两者必须在同一层保证。

    不可见/不匹配一律 404，不是 403 —— 见 deps.py 的 ``_not_found``。
    """
    task_brand_id = db.scalar(
        select(Task.brand_id)
        .select_from(Run)
        .join(Task, Task.id == Run.task_id)
        .where(Run.id == run_id)
    )
    if task_brand_id is None or task_brand_id != brand_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")


def competitor_ids(
    db: Session, brand_id: int, run_id: Optional[int] = None
) -> List[int]:
    """竞品集。

    **带 run_id 时必须读 RunCompetitor 快照,不能查当前的 CompetitorLink。**
    否则「建 job 时用冻结快照、统计时查当前配置」自相矛盾 ——
    八月给品牌加一个竞品,七月那次 run 的缺口清单和竞品列会被当场重算,
    而这正是 RunCompetitor 存在的全部理由。

    不带 run_id 是品牌级累计口径(跨 run),此时没有「当时」可言,
    只能用当前配置。
    """
    if run_id is not None:
        return list(
            db.scalars(
                select(RunCompetitor.competitor_brand_id).where(
                    RunCompetitor.run_id == run_id
                )
            ).all()
        )
    return list(
        db.scalars(
            select(CompetitorLink.competitor_brand_id).where(
                CompetitorLink.brand_id == brand_id
            )
        ).all()
    )


def _base_response_query(
    db: Session,
    *,
    brand_id: int,
    platform: Optional[str],
    prompt_id: Optional[int],
    run_id: Optional[int],
    dt_from: Optional[datetime],
    dt_to: Optional[datetime],
):
    """Responses tied to prompts of this brand (owner brand's monitoring set)."""
    q = (
        select(RawResponse)
        .join(CrawlJob, CrawlJob.id == RawResponse.job_id)
        .join(Prompt, Prompt.id == CrawlJob.prompt_id)
        .where(Prompt.brand_id == brand_id)
    )
    if platform:
        q = q.where(RawResponse.platform == platform)
    if prompt_id is not None:
        q = q.where(CrawlJob.prompt_id == prompt_id)
    if run_id is not None:
        q = q.where(CrawlJob.run_id == run_id)
    if dt_from is not None:
        q = q.where(RawResponse.created_at >= dt_from)
    if dt_to is not None:
        q = q.where(RawResponse.created_at <= dt_to)
    return q


def domain_counts(
    db: Session,
    *,
    brand_id: int,
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    run_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """引用域名聚合 —— **哪些站正在被 AI 引用**（P2-37 之后的新需求）。

    ## 口径（2026-08-22 用户拍板）

    **按引用次数累加**：一个域名在一条回答里被引 3 次就计 3。

    ⚠️ **这个口径有已知偏向**：聚合型站点会把榜单刷高（实测 job 638 的 7 条引用里
    ``bitauto.com`` 独占 5 条）。所以每行**另给一个 ``n_samples``**
    （出现在几条不同样本里）作为诊断 —— 它不参与排序，
    只是让「23 次里 20 次来自同一条样本」这种情况暴露出来，
    而不是藏在一个大数字后面。

    ## 只数有效样本

    与 ``compute_counts`` **共用同一个分母定义**（``answer_status='ok'``）。
    这个项目只允许有一个分母口径 —— 让引用榜单跑在另一套样本集合上，
    就等于同一个页面上两个数字来自两个宇宙，而没人看得出来。

    过滤条件复用 ``_base_response_query``，不另写一套：那正是
    「同一份约束不许有两处实现」。
    """
    dt_from = _parse_dt(date_from)
    dt_to = _parse_dt(date_to, end=True)

    valid_ids = (
        _base_response_query(
            db, brand_id=brand_id, platform=platform, prompt_id=prompt_id,
            run_id=run_id, dt_from=dt_from, dt_to=dt_to,
        )
        .where(RawResponse.answer_status == "ok")
        .with_only_columns(RawResponse.id)
    )

    rows = db.execute(
        select(
            Citation.domain,
            func.count().label("n_citations"),
            func.count(distinct(Citation.response_id)).label("n_samples"),
        )
        .where(Citation.response_id.in_(valid_ids))
        .group_by(Citation.domain)
        # 次数降序；**同次数按域名升序兜底** —— 不定序的话同分的行每次刷新
        # 都在跳，用户会以为数据变了（同 platforms.ts 那条纪律）
        .order_by(func.count().desc(), Citation.domain.asc())
        # **不在 SQL 里 limit。** 见下面对总数的说明 —— 截断要发生在算完总数之后
    ).all()

    every = [
        {"domain": d or "unknown", "n_citations": int(n), "n_samples": int(m)}
        for d, n, m in rows
    ]
    return {
        "filters": {
            "brand_id": brand_id, "platform": platform, "prompt_id": prompt_id,
            "run_id": run_id, "from": date_from, "to": date_to,
        },
        # ⚠️ **两个总数描述的是全集，不是返回的那几行。**
        #
        # 第一版是「先 SQL limit，再把返回行加起来」，于是 limit=3 时
        # n_citations 变成了前三行的和 —— 而界面上那个数字看起来就是
        # 「一共多少条引用」。拿它当百分比的分母会算出偏大的占比，
        # 且永远不报错（2026-08-23 在生产上一查才露馅：run 300 单独 85 条，
        # 而带 limit 的全历史查询回 33）。
        #
        # 现在先算全量再切片。**仍然只有一个查询** —— 域名数是几十的量级，
        # 全取回来再切比跑第二个 count(*) 更省，也不会让两个查询在某个
        # 过滤条件上分叉。
        "n_citations": sum(i["n_citations"] for i in every),
        "n_domains": len(every),
        "items": every[:limit],
    }


def _accumulate_denominator(den: Dict[str, int], status: Optional[str]) -> None:
    den["n_total_responses"] += 1
    if status == "ok":
        den["n_valid"] += 1
    elif status == "empty":
        den["n_empty"] += 1
    elif status == "too_short":
        den["n_too_short"] += 1
    elif status == "error":
        den["n_error"] += 1
    elif status is None:
        den["n_unannotated"] += 1


def _accumulate_mention(bc: Dict[str, int], m: Mention) -> None:
    if m.mentioned:
        bc["m_mentioned"] += 1
    mt = m.mention_type or "none"
    if mt == "body":
        bc["m_body"] += 1
    elif mt == "citation_only":
        bc["m_citation_only"] += 1
    else:
        bc["m_none"] += 1
    pb = m.position_bucket
    if pb == "head":
        bc["m_head"] += 1
    elif pb == "middle":
        bc["m_middle"] += 1
    elif pb == "tail":
        bc["m_tail"] += 1
    # 出场顺位第一。**必须是 `== 1` 而不是真值判断** —— rank 是 1-based，
    # 但 citation_only 与未命中都是 None，`if m.position_rank:` 看着等价，
    # 将来 rank 若改成 0-based 就会静默把第一名漏掉。
    if m.position_rank == 1:
        bc["m_first"] += 1


#: `group_by` 的合法取值。**只有这一处** ——
#:
#: 加 search_used 时才发现这个文件里原本有两份清单：一份在 compute_counts 的
#: 入口校验，一份在 _bucket_key 的兜底 raise。改了后者、忘了前者，表现是
#: 「新取值一律 400，而报错信息里还列着旧清单」。收成一个元组，两处都引它。
GROUP_BY_VALUES = ("none", "day", "platform", "prompt", "search_used")

_GROUP_BY_ERROR = f"group_by must be one of: {', '.join(GROUP_BY_VALUES)}"


def _bucket_key(resp: RawResponse, group_by: str, prompt_id_by_job: Dict[int, int]) -> str:
    if group_by == "none":
        return "all"
    if group_by == "day":
        # UTC day
        dt = resp.created_at
        if dt is None:
            return "unknown"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()
    if group_by == "platform":
        return resp.platform or "unknown"
    if group_by == "prompt":
        return str(prompt_id_by_job.get(resp.job_id, "unknown"))
    if group_by == "search_used":
        # P2-37 §4.0.1：「记录 search 是否激活；无搜索输出是结果，不是废样本」。
        # **三桶，不是两桶。** `None` 是「我们不知道」——库里那 55 条 P2-37 之前的
        # 样本全在这一桶，把它们并进 "false" 就是在报告里凭空断言「确认没联网」。
        # 桶名用 "unknown" 而不是 "no_search"，是为了让口径写在 key 上。
        if resp.search_used is None:
            return "unknown"
        return "true" if resp.search_used else "false"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=_GROUP_BY_ERROR,
    )


def compute_counts(
    db: Session,
    *,
    brand_id: int,
    platform: Optional[str] = None,
    prompt_id: Optional[int] = None,
    run_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "none",
    include_fake: bool = False,
    source: Optional[str] = None,
) -> dict:
    get_brand_or_404(db, brand_id)
    if run_id is not None:
        _assert_run_belongs_to_brand(db, run_id, brand_id)
    group_by = (group_by or "none").lower()
    if group_by not in GROUP_BY_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GROUP_BY_ERROR,
        )

    dt_from = _parse_dt(date_from)
    dt_to = _parse_dt(date_to, end=True)
    comp_ids = competitor_ids(db, brand_id, run_id)
    track_ids = [brand_id] + [c for c in comp_ids if c != brand_id]

    responses = list(
        db.scalars(
            _base_response_query(
                db,
                brand_id=brand_id,
                platform=platform,
                prompt_id=prompt_id,
                run_id=run_id,
                dt_from=dt_from,
                dt_to=dt_to,
            ).order_by(RawResponse.id.asc())
        ).all()
    )
    if not include_fake:
        responses = [r for r in responses if not is_fake_response(r)]
    if source:
        src_l = source.strip().lower()
        def _src(r: RawResponse) -> str:
            raw = r.raw_json if isinstance(r.raw_json, dict) else {}
            return str(raw.get("source") or "").strip().lower()
        responses = [r for r in responses if _src(r) == src_l]
    resp_ids = [r.id for r in responses]
    job_ids = list({r.job_id for r in responses})
    prompt_id_by_job: Dict[int, int] = {}
    if job_ids:
        rows = db.execute(
            select(CrawlJob.id, CrawlJob.prompt_id).where(CrawlJob.id.in_(job_ids))
        ).all()
        prompt_id_by_job = {jid: pid for jid, pid in rows}

    mentions_by_resp: Dict[int, List[Mention]] = defaultdict(list)
    if resp_ids:
        ments = list(
            db.scalars(
                select(Mention).where(
                    Mention.response_id.in_(resp_ids),
                    Mention.brand_id.in_(track_ids),
                )
            ).all()
        )
        for m in ments:
            mentions_by_resp[m.response_id].append(m)

    # overall
    overall_den = _empty_den()
    overall_brand = {bid: _empty_brand_counts(bid) for bid in track_ids}

    # series buckets
    series_den: Dict[str, Dict[str, int]] = defaultdict(_empty_den)
    series_brand: Dict[str, Dict[int, Dict[str, int]]] = defaultdict(
        lambda: {bid: _empty_brand_counts(bid) for bid in track_ids}
    )

    for resp in responses:
        key = _bucket_key(resp, group_by, prompt_id_by_job)
        _accumulate_denominator(overall_den, resp.answer_status)
        if group_by != "none":
            _accumulate_denominator(series_den[key], resp.answer_status)

        # only count mentions toward brand metrics when sample is valid
        if resp.answer_status != "ok":
            continue

        for m in mentions_by_resp.get(resp.id, []):
            if m.brand_id not in overall_brand:
                continue
            _accumulate_mention(overall_brand[m.brand_id], m)
            if group_by != "none":
                _accumulate_mention(series_brand[key][m.brand_id], m)

    def pack_den(d: Dict[str, int]) -> dict:
        return {
            "definition": "answer_status=ok",
            **d,
        }

    def pack_brand(bc: Dict[str, int]) -> dict:
        return dict(bc)

    series = []
    if group_by != "none":
        for key in sorted(series_den.keys()):
            series.append(
                {
                    "key": key,
                    "denominator": pack_den(series_den[key]),
                    "brand": pack_brand(series_brand[key][brand_id]),
                    "competitors": [
                        pack_brand(series_brand[key][cid]) for cid in comp_ids
                    ],
                }
            )

    return {
        "brand_id": brand_id,
        "filters": {
            "platform": platform,
            "prompt_id": prompt_id,
            "run_id": run_id,
            "from": date_from,
            "to": date_to,
            "include_fake": include_fake,
            "source": source,
        },
        "group_by": group_by,
        "denominator": pack_den(overall_den),
        "brand": pack_brand(overall_brand[brand_id]),
        "competitors": [pack_brand(overall_brand[cid]) for cid in comp_ids],
        "series": series,
        "note": "counts only; compute rates on client (L3); fake L0 excluded unless include_fake=true",
    }


def metrics_config() -> dict:
    return {
        "answer_status_values": ["ok", "empty", "too_short", "error"],
        "valid_denominator": "answer_status=ok",
        "mention_types": ["body", "citation_only", "none"],
        "position_buckets": ["head", "middle", "tail"],
        "default_composite_weights": {
            "mention": 0.4,
            "position": 0.3,
            "sentiment": 0.3,
        },
        "annotator_version": ANNOTATOR_VERSION,
        "crawl_mode_default_hint": "fake|real",
    }
