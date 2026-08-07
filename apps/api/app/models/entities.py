from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

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
    run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=True
    )
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
    #: 出场顺位（1-based）：本条回答**正文**里，被监测品牌按首次出现位置排序的名次。
    #: 只有 mention_type=body 才有；citation_only 与未命中都是 NULL。
    #: 注意口径：**只在被监测品牌集合内排**，不是「全文第几个出现的品牌」。
    position_rank: Mapped[Optional[int]] = mapped_column(Integer)
    is_recommended: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sentiment: Mapped[Optional[str]] = mapped_column(Text)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float)
    evidence_snippet: Mapped[Optional[str]] = mapped_column(Text)
    #: 首次命中在 full_text 里的字符下标。**能直接切原文**（match_brand 用长度守恒折叠），
    #: 前端据此做命中处内联高亮。citation_only 无 offset → NULL。
    first_offset: Mapped[Optional[int]] = mapped_column(Integer)
    #: 实际命中的那个别名（如「瑞特」「ANTA」），用于展示「靠哪个别名命中的」。
    matched_term: Mapped[Optional[str]] = mapped_column(Text)

    response: Mapped[RawResponse] = relationship(back_populates="mentions")


class User(Base):
    """D2：用户与角色。

    ``workspace_id`` **只对 client 有意义** —— 它是这个客户能看到的品牌范围，
    对上 ``brands.workspace_id``。superadmin / operator 看全部，此列为 NULL。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    #: argon2 哈希。**永远不要落明文，也不要日志里打它**
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    #: superadmin | operator | client
    role: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[List["Session"]] = relationship(
        back_populates="user", cascade="all, delete", passive_deletes=True
    )


class Session(Base):
    """D2：服务端会话。

    只存 token 的 **SHA-256**，不存明文 —— 一次库备份泄露不能换成可用会话。
    这里不用 argon2：token 是 32 字节高熵随机值，本就不可爆破，
    而每个请求都要查一次，慢哈希在这里是纯负担。密码才需要慢哈希。

    登出与吊销 = **删行**，不做软删（没有审计页，软删只是多一个要处处判断的状态）。
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


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


class Task(Base):
    """命名的监测定义 —— 可反复执行，每次执行产生一个 Run。"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    platforms: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    samples: Mapped[int] = mapped_column(Integer, server_default="3")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    runs: Mapped[list["Run"]] = relationship(
        back_populates="task", cascade="all, delete", passive_deletes=True
    )


class Run(Base):
    """一次执行。**没有 status 列** —— 由其下 job 的状态派生（后续任务实现）。"""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    platforms: Mapped[Any] = mapped_column(JSONB, server_default="[]")
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="runs")
    prompts: Mapped[list["RunPrompt"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    competitors: Mapped[list["RunCompetitor"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class RunPrompt(Base):
    """提问集快照。存 text 而不只是 id —— 提问词正文可改。"""

    __tablename__ = "run_prompts"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    prompt_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[Run] = relationship(back_populates="prompts")


class RunCompetitor(Base):
    """竞品集快照。刻意不设到 brands 的外键 —— 竞品被删后，
    「当时拿它比过」这个事实仍应留在历史运行里。"""

    __tablename__ = "run_competitors"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    competitor_brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_name: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[Run] = relationship(back_populates="competitors")
