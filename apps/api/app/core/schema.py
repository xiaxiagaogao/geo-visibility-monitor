from __future__ import annotations

import logging

from sqlalchemy import text

from app.core.db import engine

logger = logging.getLogger("geo.schema")

_MIGRATIONS = [
    (
        "002_l1_fields",
        """
        ALTER TABLE raw_responses ADD COLUMN IF NOT EXISTS answer_status TEXT;
        ALTER TABLE raw_responses ADD COLUMN IF NOT EXISTS annotator_version TEXT;
        CREATE INDEX IF NOT EXISTS idx_raw_responses_answer_status ON raw_responses(answer_status);
        """,
    ),
]


def ensure_schema() -> None:
    """Apply lightweight migrations for existing volumes (idempotent)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        for mid, sql in _MIGRATIONS:
            exists = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE id = :id"),
                {"id": mid},
            ).scalar()
            # always run IF NOT EXISTS DDL; mark migration once
            for stmt in sql.strip().split(";"):
                s = stmt.strip()
                if s:
                    conn.execute(text(s))
            if not exists:
                conn.execute(
                    text("INSERT INTO schema_migrations (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                    {"id": mid},
                )
                logger.info("applied migration %s", mid)
