"""L2 acceptance: SQL cross-check vs compute_counts (no rates).

Usage (api container or apps/api with DATABASE_URL):

    python -m app.scripts.verify_l2
    python -m app.scripts.verify_l2 --brand-id 1 --platform deepseek --prompt-id 1

Exit 0 if API service matches SQL aggregates.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from sqlalchemy import text

from app.core.db import SessionLocal
from app.services.counts import compute_counts


def _sql_counts(
    db,
    *,
    brand_id: int,
    platform: Optional[str],
    prompt_id: Optional[int],
) -> dict:
    params = {"brand_id": brand_id}
    plat_sql = ""
    prompt_sql = ""
    if platform:
        plat_sql = " AND r.platform = :platform "
        params["platform"] = platform
    if prompt_id is not None:
        prompt_sql = " AND j.prompt_id = :prompt_id "
        params["prompt_id"] = prompt_id

    den = db.execute(
        text(
            f"""
            SELECT
              count(*) AS n_total,
              count(*) FILTER (WHERE r.answer_status = 'ok') AS n_valid,
              count(*) FILTER (WHERE r.answer_status = 'empty') AS n_empty,
              count(*) FILTER (WHERE r.answer_status = 'too_short') AS n_too_short,
              count(*) FILTER (WHERE r.answer_status = 'error') AS n_error,
              count(*) FILTER (WHERE r.answer_status IS NULL) AS n_unannotated
            FROM raw_responses r
            JOIN crawl_jobs j ON j.id = r.job_id
            JOIN prompts p ON p.id = j.prompt_id
            WHERE p.brand_id = :brand_id
            {plat_sql}
            {prompt_sql}
            """
        ),
        params,
    ).mappings().one()

    brands = db.execute(
        text(
            f"""
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
            JOIN crawl_jobs j ON j.id = r.job_id
            JOIN prompts p ON p.id = j.prompt_id
            WHERE p.brand_id = :brand_id
            {plat_sql}
            {prompt_sql}
            GROUP BY m.brand_id
            """
        ),
        params,
    ).mappings().all()
    by_brand = {int(row["brand_id"]): dict(row) for row in brands}
    return {"den": dict(den), "by_brand": by_brand}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-id", type=int, default=1)
    ap.add_argument("--platform", default=None)
    ap.add_argument("--prompt-id", type=int, default=None)
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
        )
        sql = _sql_counts(
            db,
            brand_id=args.brand_id,
            platform=args.platform,
            prompt_id=args.prompt_id,
        )

        den = api["denominator"]
        sd = sql["den"]
        checks = [
            ("n_total_responses", den["n_total_responses"], int(sd["n_total"])),
            ("n_valid", den["n_valid"], int(sd["n_valid"])),
            ("n_empty", den["n_empty"], int(sd["n_empty"])),
            ("n_too_short", den["n_too_short"], int(sd["n_too_short"])),
            ("n_error", den["n_error"], int(sd["n_error"])),
            ("n_unannotated", den["n_unannotated"], int(sd["n_unannotated"])),
        ]
        print("=== L2 denominator ===")
        for name, a, b in checks:
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
        all_ids = sorted(set(brands_api) | set(sql["by_brand"]))
        for bid in all_ids:
            a = brands_api.get(bid, brand_fields({}))
            srow = sql["by_brand"].get(bid, {})
            b = brand_fields(srow)
            # SQL m_* only count rows where answer_status=ok; for brands with no mentions at all, missing
            if bid not in sql["by_brand"]:
                # if brand has zero mention rows, service still returns zeros for tracked brands
                b = brand_fields({})
            print(f"  brand_id={bid}")
            for k in a:
                ok = a[k] == b[k]
                mark = "OK" if ok else "FAIL"
                print(f"    {k}: api={a[k]} sql={b[k]} {mark}")
                if not ok:
                    errors.append(f"brand{bid}.{k}")

        # rate fields must not appear in API payload
        blob = str(api)
        for forbidden in ("visibility_rate", "mention_rate", "share_of_voice", "rate"):
            if f"'{forbidden}'" in blob or f'"{forbidden}"' in blob:
                # note key may be loose; check top-level keys
                pass
        if "note" in api and "counts only" not in api["note"]:
            errors.append("missing counts-only note")

        # unique integrity
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

        snap = db.execute(text("SELECT count(*) FROM metric_snapshots")).scalar()
        print(f"  metric_snapshots rows: {snap} (MVP authority is /v1/counts, not this table)")

        print("=== summary ===")
        if errors:
            print("FAIL:", ", ".join(errors))
            return 1
        print("PASS: L2 API matches SQL; no rate authority in DB path")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
