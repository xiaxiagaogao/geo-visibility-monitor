-- GEO demo MVP schema (docs/02-data-model.md)
-- Applied automatically on first Postgres container init.

CREATE TABLE IF NOT EXISTS brands (
    id SERIAL PRIMARY KEY,
    workspace_id INT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    name_en TEXT,
    industry TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS brand_aliases (
    id SERIAL PRIMARY KEY,
    brand_id INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    UNIQUE (brand_id, alias)
);

CREATE TABLE IF NOT EXISTS competitor_links (
    id SERIAL PRIMARY KEY,
    brand_id INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    competitor_brand_id INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    UNIQUE (brand_id, competitor_brand_id),
    CHECK (brand_id <> competitor_brand_id)
);

CREATE TABLE IF NOT EXISTS prompts (
    id SERIAL PRIMARY KEY,
    brand_id INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    category TEXT,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id SERIAL PRIMARY KEY,
    prompt_id INT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    sample_index INT NOT NULL DEFAULT 1,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_responses (
    id SERIAL PRIMARY KEY,
    job_id INT NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    full_text TEXT NOT NULL,
    html_path TEXT,
    screenshot_path TEXT,
    raw_json JSONB,
    latency_ms INT,
    answer_status TEXT,
    annotator_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mentions (
    id SERIAL PRIMARY KEY,
    response_id INT NOT NULL REFERENCES raw_responses(id) ON DELETE CASCADE,
    brand_id INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    mentioned BOOLEAN NOT NULL,
    mention_type TEXT NOT NULL,
    position_bucket TEXT,
    -- 出场顺位：正文里被监测品牌按 first_offset 升序的名次（1-based）
    position_rank INT,
    is_recommended BOOLEAN NOT NULL DEFAULT FALSE,
    sentiment TEXT,
    sentiment_score DOUBLE PRECISION,
    evidence_snippet TEXT,
    -- 首次命中在 full_text 里的下标（可直接切原文）与实际命中的别名
    first_offset INT,
    matched_term TEXT
);

CREATE TABLE IF NOT EXISTS citations (
    id SERIAL PRIMARY KEY,
    response_id INT NOT NULL REFERENCES raw_responses(id) ON DELETE CASCADE,
    cite_index INT,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    snippet TEXT
);

-- NOTE (L2 policy): metric_snapshots may hold *optional* cached rates for UI later.
-- MVP authority is GET /v1/counts (integers only). Do not treat this table as L2 source of truth.
CREATE TABLE IF NOT EXISTS metric_snapshots (
    id SERIAL PRIMARY KEY,
    brand_id INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    prompt_id INT REFERENCES prompts(id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    visibility_rate DOUBLE PRECISION NOT NULL,
    recommend_rate DOUBLE PRECISION NOT NULL,
    avg_position_score DOUBLE PRECISION NOT NULL,
    sentiment_net DOUBLE PRECISION NOT NULL,
    share_of_voice DOUBLE PRECISION,
    sample_size INT NOT NULL,
    extras JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brand_aliases_brand ON brand_aliases(brand_id);
CREATE INDEX IF NOT EXISTS idx_prompts_brand ON prompts(brand_id);
CREATE INDEX IF NOT EXISTS idx_raw_responses_created ON raw_responses(created_at);
CREATE INDEX IF NOT EXISTS idx_mentions_brand ON mentions(brand_id, response_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mentions_response_brand ON mentions(response_id, brand_id);
CREATE INDEX IF NOT EXISTS idx_mentions_response ON mentions(response_id);
CREATE INDEX IF NOT EXISTS idx_raw_responses_platform_created ON raw_responses(platform, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON crawl_jobs(status, platform);
CREATE INDEX IF NOT EXISTS idx_metrics_brand_window ON metric_snapshots(brand_id, platform, window_end);

-- schema version marker for verify_db
CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (id) VALUES ('001_mvp_init')
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_migrations (id) VALUES ('002_l1_fields')
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_migrations (id) VALUES ('003_l2_mentions_unique')
ON CONFLICT (id) DO NOTHING;

-- ── D2：用户体系与三角色 ──
-- workspace_id 只对 client 有意义（= 他能看到的品牌范围，对上 brands.workspace_id）；
-- superadmin / operator 看全部，此列为 NULL。
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('superadmin','operator','client')),
    workspace_id  INT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

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
