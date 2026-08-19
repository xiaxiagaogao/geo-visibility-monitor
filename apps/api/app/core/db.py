from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import Settings, get_settings

logger = logging.getLogger("geo.db")


class Base(DeclarativeBase):
    pass


def _make_engine():
    """建 engine。**注意这行在 import 期就会跑**（见文件末尾）。

    ``DATABASE_URL`` 是空串时回落到默认值，而不是让 ``create_engine("")``
    抛 ``ArgumentError``。理由是 P2-34 的 HTTP worker 模式：

    采集节点在那个模式下**根本没有数据库**，而「把 DATABASE_URL 设成空」
    是最直觉的删法。engine 建在 import 期，于是容器起不来，
    traceback 里只有一句「Could not parse SQLAlchemy URL」——
    一个字都不提 worker 模式，排查会往完全错误的方向走
    （2026-08-19 在 VPS 上预检镜像时实际撞到）。

    **回落不是掩盖**：HTTP 模式下没有任何代码会去连它；隧道模式下配空了，
    照样会在第一次连接时明确报「连不上 127.0.0.1:5432」，那句话是准的。
    另外这里会 WARNING 一声，让「没配」这件事本身留下痕迹。
    """
    settings = get_settings()
    url = (settings.database_url or "").strip()
    if not url:
        url = Settings.model_fields["database_url"].default
        logger.warning(
            "DATABASE_URL 未设置或为空，回落到默认值。"
            "HTTP worker 模式（WORKER_API_BASE）下这是正常的 —— 那个模式不碰数据库。"
        )
    return create_engine(url, pool_pre_ping=True, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def check_connection() -> dict:
    """Return connectivity + basic server info."""
    with engine.connect() as conn:
        one = conn.execute(text("SELECT 1")).scalar()
        version = conn.execute(text("SHOW server_version")).scalar()
    return {"ok": one == 1, "server_version": version}
