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
    platforms: Optional[List[str]] = Field(default=None, min_length=1)
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


class RunCreate(BaseModel):
    """发起一次运行时可带的口径说明。

    **为什么需要它**：`run.note` 是「这一次的口径和别的不一样」的唯一落点
    （比如「采集出口已迁至大陆」「本次未采集截图」），而在此之前**没有任何
    接口能写它** —— `/v1/runs/{id}` 只有 GET。于是 2026-08-14 迁移采集出口
    那次，基线断点就没记上。

    **在发起时带，而不是事后 PATCH**：那一刻才是最清楚这次口径的时候；
    事后补要么忘、要么补的是回忆。
    """

    note: Optional[str] = Field(default=None, max_length=500)


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
