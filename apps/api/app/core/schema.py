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
    (
        "003_l2_mentions_unique",
        """
        -- L2 integrity: one mention row per (response, brand)
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mentions_response_brand
            ON mentions(response_id, brand_id);
        CREATE INDEX IF NOT EXISTS idx_raw_responses_platform_created
            ON raw_responses(platform, created_at);
        CREATE INDEX IF NOT EXISTS idx_mentions_response ON mentions(response_id);
        """,
    ),
    (
        "004_l1_offset_rank",
        """
        -- match_brand 一直在算 offset 与 matched_term，annotate 却切完
        -- evidence_snippet 就丢掉。落库后解锁：原文命中处内联高亮、别名命中展示，
        -- 以及按 offset 升序派生 position_rank（此前恒 NULL）。
        ALTER TABLE mentions ADD COLUMN IF NOT EXISTS first_offset INT;
        ALTER TABLE mentions ADD COLUMN IF NOT EXISTS matched_term TEXT;
        """,
    ),
    (
        "005_auth",
        """
        -- D2：用户体系与三角色。纯新增，不动既有表。
        -- workspace_id 只对 client 有意义（= 他能看到的品牌范围，对上 brands.workspace_id）；
        -- superadmin / operator 看全部，此列为 NULL。
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL,
            workspace_id  INT,
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ
        );
        -- 角色取值收在数据库层，免得应用层写错一个字符串就静默产生越权账号
        ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
        ALTER TABLE users ADD CONSTRAINT users_role_check
            CHECK (role IN ('superadmin','operator','client'));

        -- 只存 token 的 SHA-256；登出/吊销 = 删行，不做软删
        CREATE TABLE IF NOT EXISTS sessions (
            id         SERIAL PRIMARY KEY,
            user_id    INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
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
