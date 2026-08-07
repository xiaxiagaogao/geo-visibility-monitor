# 后端 Task / Run 实体 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **这份文件是临时工作产物**，实施完就删。长期文档只有 `docs/BACKEND.md`、`docs/API.md`、`apps/web/README.md` 三份。

**Goal:** 给后端加「检测任务」与「运行」两级实体，让一批 `crawl_jobs` 能被归成一次命名的检测，并把当次的口径（提问集 / 竞品集 / 平台）冻结在运行上。

**Architecture:** `Task` 是可反复执行的监测定义（一个主品牌 + 平台 + 采样数）；`Run` 是一次执行。发起 run 时**先冻结口径再建 job**，快照写进 `run_prompts` / `run_competitors` 与 `runs.platforms`。`crawl_jobs` 加 `run_id` 外键。Run 的状态**不落列**，由其下 job 的状态派生——状态列迟早会和实际漂移。

**Tech Stack:** FastAPI · SQLAlchemy 2.0（`Mapped` / `mapped_column`）· Postgres 16 · pytest

---

## 前置：怎么跑测试

**本机跑，不要为了跑测试去 push 生产。** 仓库根目录有个 `.venv`（已 gitignore）装好了后端依赖：

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q
```

**当前基线：155 passed, 7 skipped。** 那 7 条 skip 是需要真实 Postgres 的用例
（靠 `GEO_TEST_DATABASE_URL` 是否设置来跳过）。每个任务做完都要跑这条命令，
且**通过数只能增不能减**。

venv 坏了就重建：

```bash
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip setuptools wheel
.venv/bin/pip install -q -e ./packages/metrics -e ./apps/api pytest httpx
```

### 需要真库的用例（Task 1 / 3 / 7）

本机没有 Postgres，这三个任务的 DB 用例会 skip —— **skip 不等于通过**。
它们统一攒到最后，在 VPS 上一次性验（见「完成判据」）。

子代理该做的是：**把 DB 用例写好、确认本机是 skip 而不是 error、提交**，
然后在报告里注明「DB 用例待 VPS 验证」。

> ⚠️ **子代理不许执行 `git push vps main`。** 那会触发 post-receive
> 直接部署到生产（`docker compose up -d --build`）。推生产由主控会话在
> 拿到明确许可后统一做。

**迁移怎么加：** 不写 `deploy/migrations/*.sql`（那是遗留副本）。往
`apps/api/app/core/schema.py` 的 `_MIGRATIONS` 列表尾部追加一个 `(id, sql)` 元组，
API 启动时 `ensure_schema()` 幂等执行。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `apps/api/app/core/schema.py` | **改**：追加 `006_task_run` 迁移 |
| `apps/api/app/models/entities.py` | **改**：加 `Task` `Run` `RunPrompt` `RunCompetitor`；`CrawlJob` 加 `run_id` |
| `apps/api/app/models/__init__.py` | **改**：导出四个新模型 |
| `apps/api/app/schemas/task.py` | **建**：`TaskCreate` `TaskOut` `TaskListOut` `RunOut` `RunDetailOut` `RunListOut` |
| `apps/api/app/services/tasks.py` | **建**：建任务、发起 run（快照 + 建 job）、派生 run 状态 |
| `apps/api/app/api/tasks.py` | **建**：`/v1/tasks` 与 `/v1/runs` 路由 + 归属校验 |
| `apps/api/app/api/deps.py` | **改**：加 `assert_task_visible` / `assert_run_visible` |
| `apps/api/app/services/counts.py` | **改**：`run_id` 过滤 |
| `apps/api/app/api/counts.py` | **改**：透传 `run_id` |
| `apps/api/app/main.py` | **改**：挂 tasks 路由 |
| `apps/api/app/scripts/backfill_run.py` | **建**：把现有无主 job 归到一个「历史」run |
| `apps/api/tests/test_task_run_snapshot.py` | **建**：快照与建 job 顺序（需真库） |
| `apps/api/tests/test_task_rbac.py` | **建**：归属校验（`inspect` 断言，不需库） |
| `apps/api/tests/test_run_status.py` | **建**：派生状态纯函数 |

---

## Task 1: 迁移与模型

**Files:**
- Modify: `apps/api/app/core/schema.py`（`_MIGRATIONS` 尾部）
- Modify: `apps/api/app/models/entities.py`
- Modify: `apps/api/app/models/__init__.py`
- Test: `apps/api/tests/test_task_run_schema.py`

- [ ] **Step 1: 写失败的测试**

建 `apps/api/tests/test_task_run_schema.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_run_schema.py -q
```

本机没有 Postgres，**预期是 skipped，不是 error**。

skip 说明用例能被收集、import 没报错 —— 这是本机能验到的全部。
「跑起来看它红」这一步在真库上才有意义，攒到最后由主控会话在 VPS 上做，
届时预期 `test_tables_exist` FAIL，报 `缺表 tasks`。

**别为了让它在本机变红而去掉 skipif。** 那会让这个用例在没有库的环境里
变成 error，CI 与本机都跑不过。

- [ ] **Step 3: 加迁移**

在 `apps/api/app/core/schema.py` 的 `_MIGRATIONS` 列表**末尾**追加：

```python
    (
        "006_task_run",
        """
        -- 检测任务与运行。此前 35 个样本 = 35 个平铺的 crawl_jobs 行，
        -- 没有任何东西能把它们归成「一次检测」。

        CREATE TABLE IF NOT EXISTS tasks (
            id          SERIAL PRIMARY KEY,
            brand_id    INT NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            platforms   JSONB NOT NULL DEFAULT '[]',
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
            platforms   JSONB NOT NULL DEFAULT '[]',
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
```

- [ ] **Step 4: 加模型**

在 `apps/api/app/models/entities.py` 末尾追加（`CrawlJob` 之后即可，位置不影响）：

```python
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
    """一次执行。**没有 status 列** —— 见 services/tasks.py:derive_run_status。"""

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
```

在同文件的 `CrawlJob` 类里，`prompt_id` 那行下面加一行：

```python
    run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=True
    )
```

- [ ] **Step 5: 导出模型**

`apps/api/app/models/__init__.py` 的 import 与 `__all__` 各加四项：`Run`、`RunCompetitor`、`RunPrompt`、`Task`（按字母序插入既有列表）。

- [ ] **Step 6: 部署并跑测试**

```bash
git add apps/api/app/core/schema.py apps/api/app/models/ apps/api/tests/test_task_run_schema.py
git commit -m "feat(api): Task/Run 实体建表 —— 一批 job 终于能归成一次检测"
# 不 push —— 推生产由主控会话统一做
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_run_schema.py -q
```

本机没有 Postgres，预期是 **skipped**（不是 error）。skip 说明用例本身能被收集、import 不报错。真正的验证在 VPS，攒到最后一起做。

```bash
# 留给主控会话：
# docker exec -w /app/apps/api -e PYTHONPATH=. \
#   -e GEO_TEST_DATABASE_URL="$DATABASE_URL" geo-api python -m pytest tests/test_task_run_schema.py -q
```

预期：3 passed。

- [ ] **Step 7: 确认既有测试没被打断**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q
```

预期：全绿。特别注意 `test_cascade_delete.py` —— 新加的外键可能影响删品牌的级联。

---

## Task 2: 派生 run 状态（纯函数，先做因为后面都要用）

**Files:**
- Create: `apps/api/app/services/tasks.py`
- Test: `apps/api/tests/test_run_status.py`

- [ ] **Step 1: 写失败的测试**

建 `apps/api/tests/test_run_status.py`：

```python
"""run 状态由其下 job 派生 —— 纯函数，不需要数据库。"""
from __future__ import annotations

from app.services.tasks import derive_run_status


def test_all_success():
    assert derive_run_status({"success": 35}) == "success"


def test_any_pending_is_pending():
    assert derive_run_status({"success": 30, "pending": 5}) == "pending"


def test_any_running_beats_pending():
    """running 优先于 pending —— 用户关心「正在跑」，不关心队列里还剩几个。"""
    assert derive_run_status({"pending": 3, "running": 1, "success": 10}) == "running"


def test_all_failed():
    assert derive_run_status({"failed": 12}) == "failed"


def test_partial_is_its_own_state():
    """部分成功不能报成 success —— 分母少了一截，比率会静默偏高。"""
    assert derive_run_status({"success": 30, "failed": 5}) == "partial"


def test_no_jobs_is_empty():
    """建了 run 却一个 job 都没有 —— 是配置问题（提问集为空），不是成功。"""
    assert derive_run_status({}) == "empty"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_run_status.py -q
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.services.tasks'`。

- [ ] **Step 3: 实现**

建 `apps/api/app/services/tasks.py`：

```python
from __future__ import annotations

from typing import Dict

# job 状态优先级：只要还有没跑完的，run 就没跑完
_UNFINISHED = ("running", "pending")


def derive_run_status(counts: Dict[str, int]) -> str:
    """由 job 状态计数派生 run 状态。

    **不落库。** 存一份就要有人同步，而 job 状态在 worker 里变、
    run 在 API 里变，两者迟早不一致 —— 而一个不一致的状态列
    比没有状态列更糟，因为它看起来权威。

    ``partial`` 是独立一档：部分成功报成 success 会让人以为
    35 条都在，实际分母少了一截，所有比率静默偏高。
    """
    total = sum(counts.values())
    if total == 0:
        return "empty"
    for st in _UNFINISHED:
        if counts.get(st, 0) > 0:
            return st
    ok = counts.get("success", 0)
    if ok == total:
        return "success"
    if ok == 0:
        return "failed"
    return "partial"
```

- [ ] **Step 4: 跑测试确认通过**

```bash
git add apps/api/app/services/tasks.py apps/api/tests/test_run_status.py
git commit -m "feat(api): run 状态由 job 派生，不落列"
# 不 push —— 推生产由主控会话统一做
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_run_status.py -q
```

预期：6 passed。

---

## Task 3: 发起 run —— 先冻结口径再建 job

**Files:**
- Modify: `apps/api/app/services/tasks.py`
- Test: `apps/api/tests/test_task_run_snapshot.py`

- [ ] **Step 1: 写失败的测试**

建 `apps/api/tests/test_task_run_snapshot.py`：

```python
"""发起 run 时的口径冻结 —— 需要真实 Postgres。

守的是这个产品最核心的一条：两次 run 之间的差异必须是**表现变化**，
不能是**口径变化**。提问集决定分母，竞品集决定缺口清单与失分量，
两者都可改；不冻结的话，八月加一个竞品会重算七月的结论。
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import func, select

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)

PROBE = "__pytest_task_run__"


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def fixture_brand(db):
    """一个主品牌 + 一个竞品 + 两条启用提问 + 一条停用提问。"""
    from app.models import Brand, CompetitorLink, Prompt

    own = Brand(name=f"{PROBE}_own", workspace_id=1)
    rival = Brand(name=f"{PROBE}_rival", workspace_id=1)
    db.add_all([own, rival])
    db.flush()
    db.add(CompetitorLink(brand_id=own.id, competitor_brand_id=rival.id))
    db.add_all([
        Prompt(brand_id=own.id, text=f"{PROBE} q1", is_active=True),
        Prompt(brand_id=own.id, text=f"{PROBE} q2", is_active=True),
        Prompt(brand_id=own.id, text=f"{PROBE} q3", is_active=False),
    ])
    db.commit()
    yield own, rival
    for b in (own, rival):
        db.delete(db.get(Brand, b.id))
    db.commit()


def test_snapshot_freezes_prompts_and_competitors(db, fixture_brand):
    from app.models import Run, RunCompetitor, RunPrompt, Task
    from app.services.tasks import create_run

    own, rival = fixture_brand
    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=2)
    db.add(task)
    db.commit()

    run = create_run(db, task)

    prompts = db.scalars(select(RunPrompt).where(RunPrompt.run_id == run.id)).all()
    assert len(prompts) == 2, "只快照启用的提问词"
    assert all(p.prompt_text.startswith(PROBE) for p in prompts), "正文要一起存下来"

    rivals = db.scalars(
        select(RunCompetitor).where(RunCompetitor.run_id == run.id)
    ).all()
    assert [r.competitor_brand_id for r in rivals] == [rival.id]
    assert rivals[0].brand_name == f"{PROBE}_rival"

    assert db.get(Run, run.id).platforms == ["deepseek"]


def test_snapshot_survives_later_config_change(db, fixture_brand):
    """改配置不许改写历史 —— 这条是整个模型存在的理由。"""
    from app.models import CompetitorLink, Prompt, RunCompetitor, RunPrompt, Task
    from app.services.tasks import create_run

    own, rival = fixture_brand
    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=1)
    db.add(task)
    db.commit()
    run = create_run(db, task)

    # run 之后：加一条提问、加一个竞品、改一条提问的正文
    newcomer = db.scalars(
        select(Prompt).where(Prompt.brand_id == own.id, Prompt.is_active.is_(True))
    ).first()
    newcomer.text = f"{PROBE} 改过的正文"
    db.add(Prompt(brand_id=own.id, text=f"{PROBE} q4", is_active=True))
    db.commit()

    assert db.scalar(
        select(func.count()).select_from(RunPrompt).where(RunPrompt.run_id == run.id)
    ) == 2, "新增提问不许进历史 run"
    texts = db.scalars(
        select(RunPrompt.prompt_text).where(RunPrompt.run_id == run.id)
    ).all()
    assert f"{PROBE} 改过的正文" not in texts, "改正文不许改写历史 run"


def test_jobs_are_attached_to_run(db, fixture_brand):
    from app.models import CrawlJob, Task
    from app.services.tasks import create_run

    own, _ = fixture_brand
    task = Task(brand_id=own.id, name=f"{PROBE} 周检", platforms=["deepseek"], samples=3)
    db.add(task)
    db.commit()
    run = create_run(db, task)

    jobs = db.scalars(select(CrawlJob).where(CrawlJob.run_id == run.id)).all()
    assert len(jobs) == 2 * 1 * 3, "2 条启用提问 × 1 平台 × 3 采样"
    assert {j.sample_index for j in jobs} == {1, 2, 3}


def test_empty_prompt_set_creates_no_jobs(db, fixture_brand):
    """提问集为空时不能静默建一个空 run 就报成功 —— derive_run_status 会给 empty。"""
    from app.models import CrawlJob, Prompt, Task
    from app.services.tasks import create_run

    own, _ = fixture_brand
    db.query(Prompt).filter(Prompt.brand_id == own.id).update({"is_active": False})
    db.commit()

    task = Task(brand_id=own.id, name=f"{PROBE} 空集", platforms=["deepseek"], samples=2)
    db.add(task)
    db.commit()
    run = create_run(db, task)

    assert db.scalars(select(CrawlJob).where(CrawlJob.run_id == run.id)).all() == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_run_snapshot.py -q
```

本机没有 Postgres，**预期是 skipped，不是 error**。

skip 说明用例能被收集、import 没报错 —— 这是本机能验到的全部。
「跑起来看它红」这一步在真库上才有意义，攒到最后由主控会话在 VPS 上做，
届时预期 FAIL，`ImportError: cannot import name 'create_run'`。

**别为了让它在本机变红而去掉 skipif。** 那会让这个用例在没有库的环境里
变成 error，CI 与本机都跑不过。

- [ ] **Step 3: 实现**

在 `apps/api/app/services/tasks.py` 顶部补 import，并追加函数：

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Brand,
    CompetitorLink,
    CrawlJob,
    Prompt,
    Run,
    RunCompetitor,
    RunPrompt,
    Task,
)


def create_run(db: Session, task: Task) -> Run:
    """发起一次运行。

    **顺序不能反：先冻结口径，再建 job。** 反过来的话，两步之间任何一次
    配置修改都会让 job 用新口径跑、快照记旧口径 —— 而这种错不会报错，
    只会让某次 run 的数字对不上它自己的快照。
    """
    run = Run(task_id=task.id, platforms=list(task.platforms or []))
    db.add(run)
    db.flush()  # 拿 run.id

    prompts = list(
        db.scalars(
            select(Prompt)
            .where(Prompt.brand_id == task.brand_id, Prompt.is_active.is_(True))
            .order_by(Prompt.id)
        )
    )
    for p in prompts:
        db.add(RunPrompt(run_id=run.id, prompt_id=p.id, prompt_text=p.text))

    rivals = list(
        db.execute(
            select(CompetitorLink.competitor_brand_id, Brand.name)
            .join(Brand, Brand.id == CompetitorLink.competitor_brand_id)
            .where(CompetitorLink.brand_id == task.brand_id)
            .order_by(CompetitorLink.competitor_brand_id)
        )
    )
    for rival_id, rival_name in rivals:
        db.add(
            RunCompetitor(
                run_id=run.id, competitor_brand_id=rival_id, brand_name=rival_name
            )
        )

    for p in prompts:
        for platform in run.platforms:
            for i in range(1, (task.samples or 1) + 1):
                db.add(
                    CrawlJob(
                        run_id=run.id,
                        prompt_id=p.id,
                        platform=platform,
                        sample_index=i,
                    )
                )

    db.commit()
    db.refresh(run)
    return run


def run_job_status_counts(db: Session, run_id: int) -> dict:
    """该 run 下 job 的状态计数，喂给 derive_run_status。"""
    rows = db.execute(
        select(CrawlJob.status, func.count())
        .where(CrawlJob.run_id == run_id)
        .group_by(CrawlJob.status)
    )
    return {status: n for status, n in rows}
```

同时把 `func` 加进 sqlalchemy 的 import：`from sqlalchemy import func, select`。

- [ ] **Step 4: 跑测试确认通过**

```bash
git add apps/api/app/services/tasks.py apps/api/tests/test_task_run_snapshot.py
git commit -m "feat(api): 发起 run 先冻结口径再建 job —— 顺序反了会静默错"
# 不 push —— 推生产由主控会话统一做
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_run_snapshot.py -q
```

本机没有 Postgres，预期是 **skipped**（不是 error）。skip 说明用例本身能被收集、import 不报错。真正的验证在 VPS，攒到最后一起做。

```bash
# 留给主控会话：
# docker exec -w /app/apps/api -e PYTHONPATH=. \
#   -e GEO_TEST_DATABASE_URL="$DATABASE_URL" geo-api python -m pytest tests/test_task_run_snapshot.py -q
```

预期：4 passed。

---

## Task 4: 归属校验

**Files:**
- Modify: `apps/api/app/api/deps.py`
- Test: `apps/api/tests/test_task_rbac.py`

- [ ] **Step 1: 写失败的测试**

建 `apps/api/tests/test_task_rbac.py`：

```python
"""任务 / 运行的归属校验 —— 不需要数据库，只验代码结构。

守的是 D2 那条最容易漏的：新加的路由必须挂上归属校验，
否则客户能通过 task_id 枚举到别家在监测什么。
"""
from __future__ import annotations

import inspect

from app.api import deps


def test_assert_task_visible_exists():
    assert hasattr(deps, "assert_task_visible")


def test_assert_run_visible_exists():
    assert hasattr(deps, "assert_run_visible")


def test_task_visibility_goes_through_brand():
    """可见性必须走 task → brand → workspace，不能自己造一套判断。"""
    src = inspect.getsource(deps.assert_task_visible)
    assert "assert_brand_visible" in src, "复用既有的品牌可见性，别重造"


def test_run_visibility_goes_through_task():
    src = inspect.getsource(deps.assert_run_visible)
    assert "assert_task_visible" in src


def test_invisible_is_404_not_403():
    """403 等于确认「这个 id 存在但不属于你」，客户据此能枚举出别家有多少任务。"""
    src = inspect.getsource(deps.assert_task_visible)
    assert "_not_found" in src
    assert "403" not in src and "FORBIDDEN" not in src
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_rbac.py -q
```

预期：FAIL，`assert hasattr(deps, "assert_task_visible")`。

- [ ] **Step 3: 实现**

在 `apps/api/app/api/deps.py` 的 `assert_prompt_visible` 之后追加，并把 `Run`、`Task` 加进顶部的 `from app.models import ...`：

```python
def assert_task_visible(db: Session, principal: Principal, task_id: int) -> None:
    """任务可见性：task → brand → workspace。"""
    ws = visible_workspace_id(principal)
    if ws is None:
        return
    brand_id = db.scalar(select(Task.brand_id).where(Task.id == task_id))
    if brand_id is None:
        raise _not_found("task")
    assert_brand_visible(db, principal, brand_id)


def assert_run_visible(db: Session, principal: Principal, run_id: int) -> None:
    """运行可见性：run → task → brand → workspace。"""
    ws = visible_workspace_id(principal)
    if ws is None:
        return
    task_id = db.scalar(select(Run.task_id).where(Run.id == run_id))
    if task_id is None:
        raise _not_found("run")
    assert_task_visible(db, principal, task_id)


def visible_task_ids(db: Session, principal: Principal) -> Optional[List[int]]:
    """该身份能看到的全部 task_id；None = 不限。列表接口用它注入过滤。"""
    brand_ids = visible_brand_ids(db, principal)
    if brand_ids is None:
        return None
    return list(db.scalars(select(Task.id).where(Task.brand_id.in_(brand_ids))).all())
```

- [ ] **Step 4: 跑测试确认通过**

```bash
git add apps/api/app/api/deps.py apps/api/tests/test_task_rbac.py
git commit -m "feat(api): 任务/运行归属校验 —— 不可见一律 404"
# 不 push —— 推生产由主控会话统一做
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_rbac.py -q
```

预期：5 passed。

---

## Task 5: Schemas 与路由

**Files:**
- Create: `apps/api/app/schemas/task.py`
- Create: `apps/api/app/api/tasks.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_task_routes.py`

- [ ] **Step 1: 写失败的测试**

建 `apps/api/tests/test_task_routes.py`：

```python
"""任务路由的形状 —— 不需要数据库。"""
from __future__ import annotations

import inspect

from app.api import tasks as tasks_api


def test_list_tasks_supports_paging():
    sig = inspect.signature(tasks_api.list_tasks)
    assert "limit" in sig.parameters and "offset" in sig.parameters


def test_create_task_requires_write():
    """建任务是写操作，客户不许碰。"""
    src = inspect.getsource(tasks_api.create_task)
    assert "require_write" in src


def test_start_run_requires_write():
    src = inspect.getsource(tasks_api.start_run)
    assert "require_write" in src


def test_get_task_checks_visibility():
    src = inspect.getsource(tasks_api.get_task)
    assert "assert_task_visible" in src


def test_list_tasks_scopes_to_visible():
    """列表必须服务端收敛，不能靠前端自己过滤。"""
    src = inspect.getsource(tasks_api.list_tasks)
    assert "visible_task_ids" in src or "visible_brand_ids" in src


def test_latest_run_endpoint_exists():
    """客户首页分流要用：我这个 workspace 下最新一次运行是哪个。"""
    assert hasattr(tasks_api, "latest_run")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_routes.py -q
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.api.tasks'`。

- [ ] **Step 3: 写 schemas**

建 `apps/api/app/schemas/task.py`：

```python
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    brand_id: int
    name: str = Field(min_length=1, max_length=120)
    platforms: List[str] = Field(min_length=1)
    samples: int = Field(default=3, ge=1, le=20)


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    platforms: Optional[List[str]] = None
    samples: Optional[int] = Field(default=None, ge=1, le=20)
    is_active: Optional[bool] = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    name: str
    platforms: List[str]
    samples: int
    is_active: bool
    created_at: datetime
    # 列表页要显示「最近一次运行」，避免前端逐个再打一次
    latest_run_id: Optional[int] = None
    latest_run_at: Optional[datetime] = None
    latest_run_status: Optional[str] = None


class TaskListOut(BaseModel):
    items: List[TaskOut]
    total: int


class RunPromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prompt_id: int
    prompt_text: str


class RunCompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    competitor_brand_id: int
    brand_name: str


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    platforms: List[str]
    note: Optional[str] = None
    created_at: datetime
    status: str
    n_jobs: int


class RunDetailOut(RunOut):
    """带快照 —— 前端据此显示「这次跑的是哪些提问、比的是哪些竞品」。"""

    prompts: List[RunPromptOut]
    competitors: List[RunCompetitorOut]


class RunListOut(BaseModel):
    items: List[RunOut]
    total: int
```

- [ ] **Step 4: 写路由**

建 `apps/api/app/api/tasks.py`：

```python
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    assert_brand_visible,
    assert_run_visible,
    assert_task_visible,
    current_principal,
    get_db,
    require_write,
    visible_task_ids,
)
from app.core.security import Principal
from app.models import CrawlJob, Run, Task
from app.schemas.task import (
    RunDetailOut,
    RunListOut,
    RunOut,
    TaskCreate,
    TaskListOut,
    TaskOut,
    TaskUpdate,
)
from app.services import tasks as task_svc

router = APIRouter(prefix="/v1", tags=["tasks"])


def _run_out(db: Session, run: Run) -> dict:
    counts = task_svc.run_job_status_counts(db, run.id)
    return {
        "id": run.id,
        "task_id": run.task_id,
        "platforms": list(run.platforms or []),
        "note": run.note,
        "created_at": run.created_at,
        "status": task_svc.derive_run_status(counts),
        "n_jobs": sum(counts.values()),
    }


def _task_out(db: Session, task: Task) -> dict:
    latest = db.scalars(
        select(Run).where(Run.task_id == task.id).order_by(Run.created_at.desc()).limit(1)
    ).first()
    base = {
        "id": task.id,
        "brand_id": task.brand_id,
        "name": task.name,
        "platforms": list(task.platforms or []),
        "samples": task.samples,
        "is_active": task.is_active,
        "created_at": task.created_at,
    }
    if latest is not None:
        r = _run_out(db, latest)
        base.update(
            latest_run_id=r["id"],
            latest_run_at=r["created_at"],
            latest_run_status=r["status"],
        )
    return base


@router.get("/tasks", response_model=TaskListOut)
def list_tasks(
    brand_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    stmt = select(Task)
    count_stmt = select(func.count()).select_from(Task)
    if brand_id is not None:
        assert_brand_visible(db, principal, brand_id)
        stmt = stmt.where(Task.brand_id == brand_id)
        count_stmt = count_stmt.where(Task.brand_id == brand_id)
    else:
        ids = visible_task_ids(db, principal)
        if ids is not None:
            stmt = stmt.where(Task.id.in_(ids))
            count_stmt = count_stmt.where(Task.id.in_(ids))
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Task.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return TaskListOut(items=[TaskOut(**_task_out(db, t)) for t in rows], total=total)


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    assert_brand_visible(db, principal, body.brand_id)
    task = Task(
        brand_id=body.brand_id,
        name=body.name,
        platforms=body.platforms,
        samples=body.samples,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskOut(**_task_out(db, task))


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    assert_task_visible(db, principal, task_id)
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskOut(**_task_out(db, task))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    assert_task_visible(db, principal, task_id)
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return TaskOut(**_task_out(db, task))


@router.get("/tasks/{task_id}/runs", response_model=RunListOut)
def list_runs(
    task_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    assert_task_visible(db, principal, task_id)
    total = db.scalar(
        select(func.count()).select_from(Run).where(Run.task_id == task_id)
    ) or 0
    rows = db.scalars(
        select(Run)
        .where(Run.task_id == task_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return RunListOut(items=[RunOut(**_run_out(db, r)) for r in rows], total=total)


@router.post(
    "/tasks/{task_id}/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED
)
def start_run(
    task_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    assert_task_visible(db, principal, task_id)
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    run = task_svc.create_run(db, task)
    return RunOut(**_run_out(db, run))


@router.get("/runs/latest", response_model=RunDetailOut)
def latest_run(
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    """我能看到的最新一次运行 —— 客户首页分流用。

    没有任何可见运行时返回 404，前端据此显示「还没有检测记录」。
    """
    stmt = select(Run).order_by(Run.created_at.desc())
    ids = visible_task_ids(db, principal)
    if ids is not None:
        stmt = stmt.where(Run.task_id.in_(ids))
    run = db.scalars(stmt.limit(1)).first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no run yet")
    return _run_detail(db, run)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    assert_run_visible(db, principal, run_id)
    run = db.scalars(
        select(Run)
        .where(Run.id == run_id)
        .options(selectinload(Run.prompts), selectinload(Run.competitors))
    ).first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return _run_detail(db, run)


def _run_detail(db: Session, run: Run) -> RunDetailOut:
    return RunDetailOut(
        **_run_out(db, run),
        prompts=list(run.prompts),
        competitors=list(run.competitors),
    )
```

> **注意路由顺序：** `/runs/latest` 必须写在 `/runs/{run_id}` **之前**，
> 否则 FastAPI 会把 `latest` 当成 `run_id` 去解析，返回 422。

- [ ] **Step 5: 挂路由**

在 `apps/api/app/main.py` 里，参照既有 `include_router` 的写法加一行：

```python
from app.api import tasks as tasks_api
...
app.include_router(tasks_api.router)
```

- [ ] **Step 6: 跑测试并手工验一遍**

```bash
git add apps/api/app/schemas/task.py apps/api/app/api/tasks.py apps/api/app/main.py \
        apps/api/tests/test_task_routes.py
git commit -m "feat(api): /v1/tasks 与 /v1/runs 路由"
# 不 push —— 推生产由主控会话统一做
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_task_routes.py -q
```

预期：6 passed。然后手工验一次（`$KEY` 是 `deploy/.env` 里的 `API_KEY`）：

```bash
ssh -i <pem> root@96.9.213.230 \
  'curl -s -X POST http://127.0.0.1:8200/v1/tasks -H "X-API-Key: $KEY" \
   -H "Content-Type: application/json" \
   -d "{\"brand_id\":34,\"name\":\"安踏周检\",\"platforms\":[\"deepseek\"],\"samples\":3}"'
```

预期：201，返回体带 `id` 与 `latest_run_id: null`。

---

## Task 6: counts 支持按 run 过滤

**Files:**
- Modify: `apps/api/app/services/counts.py`
- Modify: `apps/api/app/api/counts.py`
- Test: `apps/api/tests/test_counts_run_filter.py`

- [ ] **Step 1: 写失败的测试**

建 `apps/api/tests/test_counts_run_filter.py`：

```python
"""counts 必须能按 run 过滤 —— 任务详情的 KPI 是「这一次运行」的数，
不是这个品牌历史所有样本的数。不需要数据库。
"""
from __future__ import annotations

import inspect

from app.api import counts as counts_api
from app.services import counts as counts_svc


def test_endpoint_accepts_run_id():
    sig = inspect.signature(counts_api.get_counts)
    assert "run_id" in sig.parameters


def test_service_applies_run_filter():
    """收下参数不算数，必须真的进 SQL。"""
    src = inspect.getsource(counts_svc)
    assert "run_id" in src, "counts 服务层必须用上 run_id"
    assert "CrawlJob.run_id" in src, "过滤要走 crawl_jobs.run_id"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_counts_run_filter.py -q
```

预期：FAIL，`assert "run_id" in sig.parameters`。

- [ ] **Step 3: 实现**

`_base_response_query`（`counts.py:96`）**已经** join 了 `CrawlJob`，所以只是加一个 where。

改 `apps/api/app/services/counts.py:96` 的签名，在 `prompt_id` 之后加一个参数：

```python
def _base_response_query(
    db: Session,
    *,
    brand_id: int,
    platform: Optional[str],
    prompt_id: Optional[int],
    run_id: Optional[int],
    dt_from: Optional[datetime],
    dt_to: Optional[datetime],
):
```

在 `counts.py:115` 的 `prompt_id` 过滤之后加两行：

```python
    if run_id is not None:
        q = q.where(CrawlJob.run_id == run_id)
```

改 `compute_counts`（`counts.py:177`）的签名，在 `prompt_id` 之后加
`run_id: Optional[int] = None,`，并在 `counts.py:204` 调用 `_base_response_query`
的地方把 `run_id=run_id` 传进去。

`apps/api/app/api/counts.py` 的 `get_counts` 签名加 `run_id: Optional[int] = None`，
透传给 `compute_counts`，并加进响应的 `filters` 回显（照既有 `platform` 的写法）。

- [ ] **Step 4: 跑全套并对数**

```bash
git add apps/api/app/services/counts.py apps/api/app/api/counts.py \
        apps/api/tests/test_counts_run_filter.py
git commit -m "feat(api): counts 支持 run_id 过滤 —— 任务详情 KPI 要按次算"
# 不 push —— 推生产由主控会话统一做
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q
```

预期：全绿。**特别验一条回归**：不带 `run_id` 时结果必须和改动前一致——

```bash
ssh -i <pem> root@96.9.213.230 \
  'curl -s -H "X-API-Key: $KEY" "http://127.0.0.1:8200/v1/counts?brand_id=34"'
```

预期：`n_valid=35`、`m_mentioned=21`（`docs/API.md` §10 的基线）。

---

## Task 7: 回填历史数据

**Files:**
- Create: `apps/api/app/scripts/backfill_run.py`

现有 35 个 job 的 `run_id` 是 NULL，在任务式 IA 里会**完全不可见**——而它是目前唯一的真实数据。

- [ ] **Step 1: 写脚本**

建 `apps/api/app/scripts/backfill_run.py`：

```python
"""把 run_id 为空的历史 job 归到一个补建的 run 下。

现有 35 条安踏样本是在 Task/Run 存在之前跑的，run_id 为 NULL，
在任务式 IA 里会完全不可见 —— 而它是目前唯一的真实数据。

快照按**当前**配置补：这是没办法的事，当时的提问集与竞品集没有记录。
所以补出来的 run 带 note 说明这一点，不要当成和后续 run 同等可比。

    docker exec geo-api python -m app.scripts.backfill_run --brand-id 34 --dry-run
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import (
    Brand,
    CompetitorLink,
    CrawlJob,
    Prompt,
    Run,
    RunCompetitor,
    RunPrompt,
    Task,
)

# 刻意不 import create_run —— 它会再建一批新 job，而回填要的是把旧 job 挂上去

NOTE = "历史回填：Task/Run 引入前的样本。快照按回填时的配置补，与后续运行不完全可比。"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-id", type=int, required=True)
    ap.add_argument("--task-name", default="历史监测集")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        orphan_ids = list(
            db.scalars(
                select(CrawlJob.id)
                .join(Prompt, Prompt.id == CrawlJob.prompt_id)
                .where(Prompt.brand_id == args.brand_id, CrawlJob.run_id.is_(None))
            )
        )
        brand = db.get(Brand, args.brand_id)
        print(f"品牌 {args.brand_id} {brand.name if brand else '(不存在)'}")
        print(f"无主 job：{len(orphan_ids)} 条")
        if args.dry_run:
            print("dry-run，未写入")
            return
        if not orphan_ids:
            print("没有要回填的")
            return

        platforms = sorted(
            set(
                db.scalars(
                    select(CrawlJob.platform).where(CrawlJob.id.in_(orphan_ids))
                )
            )
        )
        task = Task(
            brand_id=args.brand_id,
            name=args.task_name,
            platforms=platforms,
            samples=1,  # 回填不再建 job，采样数只作展示
        )
        db.add(task)
        db.flush()

        # create_run 会建 job，这里不要 —— 手工建空 run 再挂旧 job
        run = Run(task_id=task.id, platforms=platforms, note=NOTE)
        db.add(run)
        db.flush()
        for p in db.scalars(
            select(Prompt).where(Prompt.brand_id == args.brand_id)
        ):
            db.add(RunPrompt(run_id=run.id, prompt_id=p.id, prompt_text=p.text))

        for rid, rname in db.execute(
            select(CompetitorLink.competitor_brand_id, Brand.name)
            .join(Brand, Brand.id == CompetitorLink.competitor_brand_id)
            .where(CompetitorLink.brand_id == args.brand_id)
        ):
            db.add(RunCompetitor(run_id=run.id, competitor_brand_id=rid, brand_name=rname))

        db.query(CrawlJob).filter(CrawlJob.id.in_(orphan_ids)).update(
            {"run_id": run.id}, synchronize_session=False
        )
        db.commit()
        print(f"回填完成：task={task.id} run={run.id} 挂上 {len(orphan_ids)} 条 job")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

> `create_run` 在这里**不能用** —— 它会再建一批新 job。回填要的是把旧 job 挂上去，
> 所以手工建空 run。这个区别写在脚本注释里，别让下一个人踩。

- [ ] **Step 2: 先 dry-run**

```bash
git add apps/api/app/scripts/backfill_run.py
git commit -m "feat(api): 历史 job 回填脚本 —— 否则唯一的真实数据在新 IA 里不可见"
# 不 push —— 推生产由主控会话统一做
ssh -i <pem> root@96.9.213.230 \
  'docker exec geo-api python -m app.scripts.backfill_run --brand-id 34 --dry-run'
```

预期：打印「无主 job：35 条」，不写库。

- [ ] **Step 3: 确认后执行并对数**

```bash
ssh -i <pem> root@96.9.213.230 \
  'docker exec geo-api python -m app.scripts.backfill_run --brand-id 34'
```

记下输出里的 `run=<id>`，然后验按 run 过滤的 counts 与全量一致：

```bash
ssh -i <pem> root@96.9.213.230 \
  'curl -s -H "X-API-Key: $KEY" "http://127.0.0.1:8200/v1/counts?brand_id=34&run_id=<id>"'
```

预期：`n_valid=35`、`m_mentioned=21` —— 与不带 `run_id` 时相同（因为该品牌所有样本都归了这一个 run）。

---

## Task 8: 回填文档

**Files:**
- Modify: `docs/BACKEND.md`
- Modify: `docs/API.md`

BACKEND.md §13 规定「先改代码与测试，再改本文」，所以文档放在最后。

- [ ] **Step 1: 改 BACKEND.md**

1. §3 域模型的关系图加两行：

```text
Brand ──< Task ──< Run ──< CrawlJob
Run ──< RunPrompt · RunCompetitor（口径快照）
```

2. §3 的表格加四行（tasks / runs / run_prompts / run_competitors），
   要点写「run 没有 status 列，由 job 派生」与「快照表刻意不设到 brands 的外键」。
3. §3 那句「**没有「批次 / 检测」实体。**」整段删掉——它不再成立。
4. §4 API 地图加 `/v1/tasks`、`/v1/tasks/{id}/runs`、`/v1/runs/{id}`、`/v1/runs/latest`。
5. §11 已知债务删掉「**无批次 / 提问集实体**」那一行。

- [ ] **Step 2: 改 API.md**

1. §9「后端现在给不了的」删掉「无「批次 / 检测」实体」那一行。
2. 新增一节写 Task / Run 的字段与 `/v1/counts?run_id=`，并强调
   **run 的三份快照是历史可比性的唯一保证**。

- [ ] **Step 3: 提交**

```bash
git add docs/BACKEND.md docs/API.md
git commit -m "docs: 回填 Task/Run —— 删掉「无批次实体」这条已不成立的说法"
# 不 push —— 推生产由主控会话统一做
```

- [ ] **Step 4: 全套回归**

```bash
cd apps/api && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q
ssh -i <pem> root@96.9.213.230 'docker exec geo-api python -m app.scripts.verify_l2 --brand-id 34'
```

预期：pytest 全绿；`verify_l2` 不报 FAIL。

---

## 完成判据

1. `POST /v1/tasks` → `POST /v1/tasks/{id}/runs` → `GET /v1/runs/{id}` 能跑通，返回体带快照
2. `GET /v1/counts?brand_id=34&run_id=<回填的 run>` 给出 `n_valid=35`、`m_mentioned=21`
3. 客户角色调 `GET /v1/tasks` 只看到自己 workspace 的任务；调别家 task_id 得 404 不是 403
4. `GET /v1/runs/latest` 对客户返回他自己的最新 run
5. 全套 pytest 绿，`verify_l2` 不报 FAIL

## 明确不在这个计划里

| 项 | 为什么 |
|----|-------|
| 定时执行（cron / 调度） | 先把手动发起跑通。定时是另一套（调度器、失败重试、并发控制），塞进来会让这个计划失焦 |
| 删除 run / task 的接口 | 删 run 会级联掉证据。先不给这个口子，需要时再单独设计（大概率是软删或归档） |
| run 之间的 diff 接口 | 前端本轮不做趋势，没有消费者 |
| `Task.prompt_selection`（显式选提问子集） | 当前一律取品牌下全部启用提问。真出现「只跑一部分」的需求再加，YAGNI |
