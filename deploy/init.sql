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
    position_rank INT,
    is_recommended BOOLEAN NOT NULL DEFAULT FALSE,
    sentiment TEXT,
    sentiment_score DOUBLE PRECISION,
    evidence_snippet TEXT
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
