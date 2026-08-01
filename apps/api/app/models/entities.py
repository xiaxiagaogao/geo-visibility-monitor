from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[Optional[str]] = mapped_column(Text)
    industry: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # passive_deletes=True：交给数据库的 ON DELETE CASCADE。
    # 不加的话 SQLAlchemy 删父行前会先 UPDATE 子表把外键置 NULL，
    # 而这些外键列都是 NOT NULL → IntegrityError（见 test_cascade_delete.py）
    aliases: Mapped[list["BrandAlias"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan", passive_deletes=True
    )
    prompts: Mapped[list["Prompt"]] = relationship(
        back_populates="brand", cascade="all, delete", passive_deletes=True
    )


class BrandAlias(Base):
    __tablename__ = "brand_aliases"
    __table_args__ = (UniqueConstraint("brand_id", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(Text, nullable=False)

    brand: Mapped[Brand] = relationship(back_populates="aliases")


class CompetitorLink(Base):
    __tablename__ = "competitor_links"
    __table_args__ = (
        UniqueConstraint("brand_id", "competitor_brand_id"),
        CheckConstraint("brand_id <> competitor_brand_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    competitor_brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE")
    )


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    brand: Mapped[Brand] = relationship(back_populates="prompts")
    jobs: Mapped[list["CrawlJob"]] = relationship(
        back_populates="prompt", cascade="all, delete", passive_deletes=True
    )


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    sample_index: Mapped[int] = mapped_column(Integer, server_default="1")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    prompt: Mapped[Prompt] = relationship(back_populates="jobs")
    responses: Mapped[list["RawResponse"]] = relationship(
        back_populates="job", cascade="all, delete", passive_deletes=True
    )


class RawResponse(Base):
    __tablename__ = "raw_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    html_path: Mapped[Optional[str]] = mapped_column(Text)
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text)
    raw_json: Mapped[Optional[Any]] = mapped_column(JSONB)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    answer_status: Mapped[Optional[str]] = mapped_column(Text)  # ok|empty|too_short|error
    annotator_version: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped[CrawlJob] = relationship(back_populates="responses")
    mentions: Mapped[list["Mention"]] = relationship(
        back_populates="response", cascade="all, delete", passive_deletes=True
    )
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="response", cascade="all, delete", passive_deletes=True
    )


class Mention(Base):
    __tablename__ = "mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    response_id: Mapped[int] = mapped_column(
        ForeignKey("raw_responses.id", ondelete="CASCADE")
    )
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    mentioned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mention_type: Mapped[str] = mapped_column(Text, nullable=False)
    position_bucket: Mapped[Optional[str]] = mapped_column(Text)
    position_rank: Mapped[Optional[int]] = mapped_column(Integer)
    is_recommended: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sentiment: Mapped[Optional[str]] = mapped_column(Text)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)
    evidence_snippet: Mapped[Optional[str]] = mapped_column(Text)

    response: Mapped[RawResponse] = relationship(back_populates="mentions")


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    response_id: Mapped[int] = mapped_column(
        ForeignKey("raw_responses.id", ondelete="CASCADE")
    )
    cite_index: Mapped[Optional[int]] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    snippet: Mapped[Optional[str]] = mapped_column(Text)

    response: Mapped[RawResponse] = relationship(back_populates="citations")


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    prompt_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL")
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visibility_rate: Mapped[float] = mapped_column(Float, nullable=False)
    recommend_rate: Mapped[float] = mapped_column(Float, nullable=False)
    avg_position_score: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_net: Mapped[float] = mapped_column(Float, nullable=False)
    share_of_voice: Mapped[Optional[float]] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    extras: Mapped[Any] = mapped_column(JSONB, server_default="{}")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
