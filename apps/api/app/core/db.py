from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def check_connection() -> dict:
    """Return connectivity + basic server info."""
    with engine.connect() as conn:
        one = conn.execute(text("SELECT 1")).scalar()
        version = conn.execute(text("SHOW server_version")).scalar()
    return {"ok": one == 1, "server_version": version}
