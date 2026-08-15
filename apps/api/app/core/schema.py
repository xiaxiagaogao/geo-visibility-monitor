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
    (
        "006_task_run",
        """
        -- 检测任务与运行。此前 35 个样本 = 35 个平铺的 crawl_jobs 行，
        -- 没有任何东西能把它们归成「一次检测」。

        CREATE TABLE IF NOT EXISTS tasks (
            id          SERIAL PRIMARY KEY,
            brand_id    INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            platforms   JSONB NOT NULL DEFAULT '[]'::jsonb,
            samples     INT NOT NULL DEFAULT 3,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_brand ON tasks(brand_id);
        ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_samples_check;
        ALTER TABLE tasks ADD CONSTRAINT tasks_samples_check
            CHECK (samples BETWEEN 1 AND 20);

        -- runs 刻意没有 status 列：由其下 crawl_jobs 的状态派生。
        -- 存一份就要有人同步，而 job 状态在 worker 里变、run 在 API 里变。
        CREATE TABLE IF NOT EXISTS runs (
            id          SERIAL PRIMARY KEY,
            task_id     INT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            platforms   JSONB NOT NULL DEFAULT '[]'::jsonb,
            note        TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_runs_task_created ON runs(task_id, created_at DESC);

        -- 快照一：提问集。连 text 一起存 —— 提问词正文可改，
        -- 只存 id 的话历史运行的问题会跟着变。
        CREATE TABLE IF NOT EXISTS run_prompts (
            run_id      INT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            prompt_id   INT NOT NULL,
            prompt_text TEXT NOT NULL,
            PRIMARY KEY (run_id, prompt_id)
        );

        -- 快照二：竞品集。不加外键到 brands —— 竞品品牌被删之后，
        -- 历史运行仍应保留「当时拿它比过」这个事实。
        CREATE TABLE IF NOT EXISTS run_competitors (
            run_id              INT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            competitor_brand_id INT NOT NULL,
            brand_name          TEXT NOT NULL,
            PRIMARY KEY (run_id, competitor_brand_id)
        );

        -- 可空：迁移前已有的 job 没有 run。非空会让这条迁移直接失败。
        ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS run_id INT
            REFERENCES runs(id) ON DELETE CASCADE;
        CREATE INDEX IF NOT EXISTS idx_crawl_jobs_run ON crawl_jobs(run_id);
        """,
    ),
    (
        "007_crawl_retry",
        """
        -- P2-16 自动退避重试 + P2-08 失败分类。

        -- 三列**全可空，这是有意的**：VPS 上那台 geo-crawler 是冷备，跑的是旧代码，
        -- 它 claim / fail 时根本不会碰这三列。可空 + 「next_attempt_at IS NULL = 立刻可领」
        -- 让它照常工作，只是不享受自动重试 —— 降级，不是损坏（PHASE2 §6 规矩 2）。
        ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS attempt INT;
        ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
        ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS failure_kind TEXT;

        -- claim 的条件从 status='pending' 变成
        --   status='pending' AND (next_attempt_at IS NULL OR next_attempt_at <= now())
        CREATE INDEX IF NOT EXISTS idx_crawl_jobs_claim
            ON crawl_jobs(status, next_attempt_at);
        """,
    ),
    (
        "008_crawl_credentials",
        """
        -- P2-07 登录态健康度。每个平台一行，由 crawler 定期上报。
        --
        -- **为什么要有这张表**：storage_state 在采集节点上，而 api 在 VPS ——
        -- api 读不到那个文件。让 crawler 把「元信息」写回来是唯一的路。
        -- P2-34 worker 化之后改成 POST 上报，这张表不用动。
        --
        -- ⚠️ **这里永远不存 cookie 的值。** 只存名字、域、过期时间。
        -- 值是凭证本身，落进数据库就等于把登录态复制到了一个没人当它是凭证的地方。
        CREATE TABLE IF NOT EXISTS crawl_credentials (
            platform        TEXT PRIMARY KEY,
            node_label      TEXT,
            status          TEXT NOT NULL,
            issuer_region   TEXT,
            waf_kind        TEXT,
            cookie_count    INT,
            cookie_names    JSONB NOT NULL DEFAULT '[]'::jsonb,
            earliest_expiry TIMESTAMPTZ,
            file_mtime      TIMESTAMPTZ,
            issues          JSONB NOT NULL DEFAULT '[]'::jsonb,
            checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """,
    ),
]


def split_statements(sql: str) -> list[str]:
    """把迁移脚本切成一条条语句。

    **不能用 ``sql.split(";")``** —— 分号不只是语句分隔符，它还会出现在：

    - 行注释里：``-- 见 issue #12; 已修``
    - 字符串字面量里：``DEFAULT 'a;b'``
    - ``$$ ... $$`` 包起来的函数体（PL/pgSQL 里每行都以分号结尾）

    裸切遇到上面任何一种都会把一条语句劈成两半，报错还离现场很远。
    这里按「引号 / 美元引用 / 行注释」状态机走一遍，只在**语句层**的分号处断开。
    """
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_line_comment = False
    quote: str | None = None  # "'" | '"' | 美元引用的完整 tag，如 $$ 或 $fn$

    while i < n:
        ch = sql[i]

        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if quote is None:
            if sql.startswith("--", i):
                in_line_comment = True
                buf.append(ch)
                i += 1
                continue
            if ch in ("'", '"'):
                quote = ch
                buf.append(ch)
                i += 1
                continue
            if ch == "$":
                end = sql.find("$", i + 1)
                if end != -1 and sql[i + 1 : end].replace("_", "").isalnum() or (
                    end == i + 1
                ):
                    quote = sql[i : end + 1]
                    buf.append(quote)
                    i = end + 1
                    continue
            if ch == ";":
                stmt = "".join(buf).strip()
                if stmt:
                    out.append(stmt)
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue

        # 引号 / 美元引用内部
        if quote in ("'", '"'):
            buf.append(ch)
            if ch == quote:
                # SQL 里连写两个引号表示转义
                if i + 1 < n and sql[i + 1] == quote:
                    buf.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if sql.startswith(quote, i):  # 美元引用结束
            buf.append(quote)
            i += len(quote)
            quote = None
            continue
        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


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
            for stmt in split_statements(sql):
                conn.execute(text(stmt))
            if not exists:
                conn.execute(
                    text("INSERT INTO schema_migrations (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                    {"id": mid},
                )
                logger.info("applied migration %s", mid)
