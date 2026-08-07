"""Task / Run 建表与外键 —— 需要真实 Postgres。

在 VPS 的 api 容器里跑：

    docker exec -w /app/apps/api -e PYTHONPATH=. \
      -e GEO_TEST_DATABASE_URL="$DATABASE_URL" geo-api python -m pytest tests/ -q
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect as sa_inspect

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


@pytest.fixture
def conn():
    from app.core.db import engine

    with engine.connect() as c:
        yield c


def test_tables_exist(conn):
    names = set(sa_inspect(conn).get_table_names())
    for t in ("tasks", "runs", "run_prompts", "run_competitors"):
        assert t in names, f"缺表 {t}"


def test_crawl_jobs_has_nullable_run_id(conn):
    cols = {c["name"]: c for c in sa_inspect(conn).get_columns("crawl_jobs")}
    assert "run_id" in cols, "crawl_jobs 必须能指回它属于哪次运行"
    assert cols["run_id"]["nullable"] is True, (
        "必须可空 —— 迁移前已有的 job 没有 run，非空会让迁移直接失败"
    )


def test_run_has_no_status_column(conn):
    """状态由 job 派生，不落列。

    落了列就要有人维护它，而 job 状态在 worker 里变、run 状态在别处变，
    两者迟早不一致。不一致的状态列比没有更糟：它看起来权威。
    """
    cols = {c["name"] for c in sa_inspect(conn).get_columns("runs")}
    assert "status" not in cols
