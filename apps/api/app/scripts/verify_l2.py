"""L2 acceptance: SQL cross-check vs compute_counts (no rates).

Usage:
    python -m app.scripts.verify_l2
    python -m app.scripts.verify_l2 --brand-id 1 --platform deepseek --prompt-id 1
    python -m app.scripts.verify_l2 --include-fake
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from sqlalchemy import text

from app.core.db import SessionLocal
from app.services.counts import compute_counts, is_fake_response
from app.models import RawResponse
from sqlalchemy import select
from app.models import CrawlJob, Prompt


def _sql_counts(db, *, brand_id: int, platform: Optional[str], prompt_id: Optional[int], include_fake: bool) -> dict:
    params = {"brand_id": brand_id}
    plat_sql = ""
    prompt_sql = ""
    if platform:
        plat_sql = " AND r.platform = :platform "
        params["platform"] = platform
    if prompt_id is not None:
        prompt_sql = " AND j.prompt_id = :prompt_id "
        params["prompt_id"] = prompt_id

    # Load candidate ids then filter fake in Python (same as service)
    rows = db.execute(
        text(
            f"""
            SELECT r.id, r.answer_status, r.full_text, r.raw_json
            FROM raw_responses r
            JOIN crawl_jobs j ON j.id = r.job_id
            JOIN prompts p ON p.id = j.prompt_id
            WHERE p.brand_id = :brand_id
            {plat_sql}
            {prompt_sql}
            ORDER BY r.id
            """
        ),
        params,
    ).mappings().all()

    # Use ORM is_fake_response
    orm_by_id = {
        r.id: r
        for r in db.scalars(select(RawResponse).where(RawResponse.id.in_([row["id"] for row in rows] or [0]))).all()
    }
    kept = []
    for row in rows:
        resp = orm_by_id.get(row["id"])
        if resp is None:
            continue
        if not include_fake and is_fake_response(resp):
            continue
        kept.append(resp)

    den = {
        "n_total": 0,
        "n_valid": 0,
        "n_empty": 0,
        "n_too_short": 0,
        "n_error": 0,
        "n_unannotated": 0,
    }
    for r in kept:
        den["n_total"] += 1
        st = r.answer_status
        if st == "ok":
            den["n_valid"] += 1
        elif st == "empty":
            den["n_empty"] += 1
        elif st == "too_short":
            den["n_too_short"] += 1
        elif st == "error":
            den["n_error"] += 1
        elif st is None:
            den["n_unannotated"] += 1

    kept_ids = [r.id for r in kept]
    by_brand = {}
    if kept_ids:
        brands = db.execute(
            text(
                """
                SELECT m.brand_id,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND m.mentioned) AS m_mentioned,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND m.mention_type = 'body') AS m_body,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND m.mention_type = 'citation_only') AS m_citation_only,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND coalesce(m.mention_type,'none') = 'none') AS m_none,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND m.position_bucket = 'head') AS m_head,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND m.position_bucket = 'middle') AS m_middle,
                  count(*) FILTER (WHERE r.answer_status = 'ok' AND m.position_bucket = 'tail') AS m_tail
                FROM mentions m
                JOIN raw_responses r ON r.id = m.response_id
                WHERE m.response_id = ANY(:ids)
                GROUP BY m.brand_id
                """
            ),
            {"ids": kept_ids},
        ).mappings().all()
        by_brand = {int(row["brand_id"]): dict(row) for row in brands}
    return {"den": den, "by_brand": by_brand}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-id", type=int, default=1)
    ap.add_argument("--platform", default=None)
    ap.add_argument("--prompt-id", type=int, default=None)
    ap.add_argument("--include-fake", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    errors: list[str] = []
    try:
        api = compute_counts(
            db,
            brand_id=args.brand_id,
            platform=args.platform,
            prompt_id=args.prompt_id,
            group_by="none",
            include_fake=args.include_fake,
        )
        sql = _sql_counts(
            db,
            brand_id=args.brand_id,
            platform=args.platform,
            prompt_id=args.prompt_id,
            include_fake=args.include_fake,
        )

        den = api["denominator"]
        sd = sql["den"]
        print(f"=== L2 denominator (include_fake={args.include_fake}) ===")
        for name, a, b in [
            ("n_total_responses", den["n_total_responses"], int(sd["n_total"])),
            ("n_valid", den["n_valid"], int(sd["n_valid"])),
            ("n_empty", den["n_empty"], int(sd["n_empty"])),
            ("n_too_short", den["n_too_short"], int(sd["n_too_short"])),
            ("n_error", den["n_error"], int(sd["n_error"])),
            ("n_unannotated", den["n_unannotated"], int(sd["n_unannotated"])),
        ]:
            ok = a == b
            print(f"  {name}: api={a} sql={b} {'OK' if ok else 'FAIL'}")
            if not ok:
                errors.append(name)

        def brand_fields(src: dict) -> dict:
            return {
                k: int(src.get(k, 0) or 0)
                for k in (
                    "m_mentioned",
                    "m_body",
                    "m_citation_only",
                    "m_none",
                    "m_head",
                    "m_middle",
                    "m_tail",
                )
            }

        brands_api = {api["brand"]["brand_id"]: brand_fields(api["brand"])}
        for c in api["competitors"]:
            brands_api[c["brand_id"]] = brand_fields(c)

        print("=== L2 brand counts (valid samples only) ===")
        for bid in sorted(set(brands_api) | set(sql["by_brand"])):
            a = brands_api.get(bid, brand_fields({}))
            b = brand_fields(sql["by_brand"].get(bid, {}))
            print(f"  brand_id={bid}")
            for k in a:
                ok = a[k] == b[k]
                print(f"    {k}: api={a[k]} sql={b[k]} {'OK' if ok else 'FAIL'}")
                if not ok:
                    errors.append(f"brand{bid}.{k}")

        dup = db.execute(
            text(
                """
                SELECT response_id, brand_id, count(*) AS c
                FROM mentions
                GROUP BY response_id, brand_id
                HAVING count(*) > 1
                """
            )
        ).fetchall()
        print("=== integrity ===")
        print(f"  duplicate mention pairs: {len(dup)} {'OK' if not dup else 'FAIL'}")
        if dup:
            errors.append("duplicate_mentions")

        print("=== summary ===")
        if errors:
            print("FAIL:", ", ".join(errors))
            return 1
        print("PASS: L2 API matches reference aggregates")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
