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
from app.models import Run, Task
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
from app.services.brands import get_brand_or_404

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
    # assert_brand_visible 对 sees_all_brands 的角色（superadmin/operator/machine）
    # 直接 return，不查 Brand 表。存在性要单独校验，否则超管传个不存在的
    # brand_id 会一路走到 db.commit() 才被外键拦下，抛未捕获的 IntegrityError
    # 500 —— 而不是干净的 404。既有写法见 services/prompts.py 的 create_prompt。
    get_brand_or_404(db, body.brand_id)
    # 平台 code 必须校验，理由见 services/tasks.py 的 validate_platforms 文档
    # 字符串：不挡的话 create_run 会为打错字/未接入的平台批量建出永远跑不了的 job。
    task_svc.validate_platforms(body.platforms)
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
    if body.platforms is not None:
        # 只在这次请求真的带了 platforms 时才校验 —— body.platforms 为 None
        # 代表「没传这个字段」，沿用 task 现有的 platforms，不该拿旧值重新校验
        # （旧值建任务时已经校验过一次）。
        task_svc.validate_platforms(body.platforms)
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
