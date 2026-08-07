from __future__ import annotations

from collections.abc import Generator
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import ROLE_SUPERADMIN
from app.core.db import SessionLocal
from app.core.security import ANONYMOUS, Principal
from app.models import Brand, CrawlJob, Prompt, RawResponse, Run, Task


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- 身份 ----------


def current_principal(request: Request) -> Principal:
    """中间件解析好的身份。能走到这里的请求都已认证（PUBLIC_PATHS 除外）。"""
    return getattr(request.state, "principal", ANONYMOUS)


# ---------- 授权 ----------
#
# 权限判断放依赖、不放中间件：中间件看不到路径与查询参数，做不了归属校验；
# 放依赖里既拿得到 brand_id，又让「这个接口要什么权限」在函数签名上一眼可见。


def require_write(principal: Principal = Depends(current_principal)) -> Principal:
    """能改配置 / 发起抓取的角色。客户是纯只读。"""
    if not principal.can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this action requires operator or superadmin role",
        )
    return principal


def require_superadmin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.effective_role != ROLE_SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this action requires superadmin role",
        )
    return principal


# ---------- 归属校验 ----------


def visible_workspace_id(principal: Principal) -> Optional[int]:
    """None = 看全部；否则只能看这个 workspace 下的品牌。

    **这里必须 fail-closed。** ``None`` 同时是「看全部」的含义，所以任何
    「本该受限却拿不到 workspace」的情况都不能落到 None 上，否则就是放行全部：

    - 匿名身份：正常走不到这里（中间件先挡），但不能靠「正常情况」
    - 角色是 client 却没有 workspace_id：接口层建号时校验过，
      但直接改库能造出这种行，那时它会变成一个能看全部数据的客户
    """
    if not principal.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    if principal.sees_all_brands:
        return None
    if principal.workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account has no workspace assigned",
        )
    return principal.workspace_id


def _not_found(what: str) -> HTTPException:
    """**不可见一律 404，不是 403。**

    403 等于确认「这个 id 存在但不属于你」，客户据此能枚举出别家有多少品牌、
    多少样本。404 让「不存在」与「不属于你」在外部看起来完全一样。
    """
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def assert_brand_visible(db: Session, principal: Principal, brand_id: int) -> None:
    ws = visible_workspace_id(principal)
    if ws is None:
        return
    brand = db.get(Brand, brand_id)
    if brand is None or brand.workspace_id != ws:
        raise _not_found("brand")


def assert_prompt_visible(db: Session, principal: Principal, prompt_id: int) -> None:
    ws = visible_workspace_id(principal)
    if ws is None:
        return
    brand_id = db.scalar(select(Prompt.brand_id).where(Prompt.id == prompt_id))
    if brand_id is None:
        raise _not_found("prompt")
    assert_brand_visible(db, principal, brand_id)


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


def assert_response_visible(db: Session, principal: Principal, response_id: int) -> None:
    """样本可见性：response → job → prompt → brand → workspace。"""
    ws = visible_workspace_id(principal)
    if ws is None:
        return
    brand_id = db.scalar(
        select(Prompt.brand_id)
        .select_from(RawResponse)
        .join(CrawlJob, CrawlJob.id == RawResponse.job_id)
        .join(Prompt, Prompt.id == CrawlJob.prompt_id)
        .where(RawResponse.id == response_id)
    )
    if brand_id is None:
        raise _not_found("response")
    assert_brand_visible(db, principal, brand_id)


def assert_screenshot_visible(db: Session, principal: Principal, basename: str) -> None:
    """截图可见性 —— 这条最容易被漏掉。

    路由只按文件名取图，与品牌毫无关联，而文件名带时间戳、可枚举。
    不校验的话，前面所有归属校验都白做：客户照样能看到别家品牌的证据图。
    """
    ws = visible_workspace_id(principal)
    if ws is None:
        return
    brand_id = db.scalar(
        select(Prompt.brand_id)
        .select_from(RawResponse)
        .join(CrawlJob, CrawlJob.id == RawResponse.job_id)
        .join(Prompt, Prompt.id == CrawlJob.prompt_id)
        .where(RawResponse.screenshot_path == basename)
    )
    if brand_id is None:
        raise _not_found("screenshot")
    assert_brand_visible(db, principal, brand_id)


def visible_brand_ids(db: Session, principal: Principal) -> Optional[List[int]]:
    """该身份能看到的全部 brand_id；None = 不限。列表接口用它注入过滤。"""
    ws = visible_workspace_id(principal)
    if ws is None:
        return None
    return list(db.scalars(select(Brand.id).where(Brand.workspace_id == ws)).all())
