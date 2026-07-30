"""Verify Postgres connectivity and required MVP tables.

Usage (from apps/api, venv active):

    python -m app.scripts.verify_db

Exit codes:
  0  ok
  1  connection or schema failure
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.core.config import get_settings
from app.core.db import engine

REQUIRED_TABLES = {
    "brands",
    "brand_aliases",
    "competitor_links",
    "prompts",
    "crawl_jobs",
    "raw_responses",
    "mentions",
    "citations",
    "metric_snapshots",
    "schema_migrations",
}


def main() -> int:
    settings = get_settings()
    print(f"DATABASE_URL={settings.database_url}")
    try:
        with engine.connect() as conn:
            ver = conn.execute(text("SHOW server_version")).scalar()
            print(f"connected: PostgreSQL {ver}")
            mig = conn.execute(
                text("SELECT id FROM schema_migrations ORDER BY id")
            ).fetchall()
            print("migrations:", [r[0] for r in mig] or "(none)")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot connect: {exc}")
        print("Hint: start DB with: cd deploy && docker compose up -d postgres")
        return 1

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    missing = sorted(REQUIRED_TABLES - existing)
    extra_note = sorted(existing - REQUIRED_TABLES)
    print(f"tables found: {len(existing)}")
    if missing:
        print("MISSING tables:", ", ".join(missing))
        print("Hint: recreate volume or re-run init.sql on empty data dir")
        return 1
    print("all required tables present")
    if extra_note:
        print("other tables:", ", ".join(extra_note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
