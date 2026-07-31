"""Minimal data governance (one-shot / idempotent).

1) Delete historical fake L0 rows (source fake_* or 【假数据 prefix)
2) Re-annotate remaining responses (sidebar → answer_status=error)
3) Optionally prune crawl_jobs with zero responses

Usage:
    python -m app.scripts.data_governance_min
    python -m app.scripts.data_governance_min --dry-run
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, select, text

from app.core.db import SessionLocal
from app.models import Citation, CrawlJob, Mention, RawResponse
from app.services.annotate import annotate_response
from app.services.counts import is_fake_response


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-fake", action="store_true", help="do not delete fake rows")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(RawResponse).order_by(RawResponse.id)).all())
        fakes = [r for r in rows if is_fake_response(r)]
        print(f"total_responses={len(rows)} fake={len(fakes)} ids={[r.id for r in fakes]}")

        if fakes and not args.keep_fake:
            ids = [r.id for r in fakes]
            if args.dry_run:
                print(f"DRY-RUN would delete responses {ids}")
            else:
                # children first if no cascade in ORM path
                db.execute(delete(Mention).where(Mention.response_id.in_(ids)))
                db.execute(delete(Citation).where(Citation.response_id.in_(ids)))
                db.execute(delete(RawResponse).where(RawResponse.id.in_(ids)))
                db.commit()
                print(f"deleted fake responses {ids}")

        # re-annotate remaining
        left = list(db.scalars(select(RawResponse).order_by(RawResponse.id)).all())
        changed = []
        for r in left:
            before = r.answer_status
            if args.dry_run:
                from app.services.annotate import classify_answer_status
                after = classify_answer_status(r.full_text)
                if after != before:
                    changed.append((r.id, before, after))
            else:
                annotate_response(db, r.id, replace=True)
                db.refresh(r)
                if r.answer_status != before:
                    changed.append((r.id, before, r.answer_status))
        if not args.dry_run:
            db.commit()
        print(f"status_changes={changed}")

        # prune empty jobs
        empty_jobs = db.execute(
            text(
                """
                SELECT j.id FROM crawl_jobs j
                LEFT JOIN raw_responses r ON r.job_id = j.id
                GROUP BY j.id
                HAVING count(r.id) = 0
                """
            )
        ).fetchall()
        empty_ids = [row[0] for row in empty_jobs]
        print(f"empty_jobs={empty_ids}")
        if empty_ids and not args.dry_run:
            db.execute(delete(CrawlJob).where(CrawlJob.id.in_(empty_ids)))
            db.commit()
            print(f"deleted empty jobs {empty_ids}")

        # summary
        left = list(db.scalars(select(RawResponse)).all())
        from collections import Counter
        c = Counter((r.answer_status or "null") for r in left)
        src = Counter()
        for r in left:
            raw = r.raw_json if isinstance(r.raw_json, dict) else {}
            src[str(raw.get("source") or "?")] += 1
        print("remaining_by_status", dict(c))
        print("remaining_by_source", dict(src))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
