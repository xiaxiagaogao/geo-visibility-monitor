from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import assert_screenshot_visible, current_principal, get_db
from app.core.security import Principal
from app.core.config import get_settings
from app.core.security import (
    api_key_configured,
    clear_qa_cookie,
    set_qa_cookie,
    verify_key,
)
from app.models import Brand, CrawlJob, Mention, Prompt, RawResponse
from app.services.counts import compute_counts

router = APIRouter(tags=["qa"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/qa/login", response_class=HTMLResponse)
def qa_login_form(request: Request, bad: int = 0):
    """QA 登录页（公开）。密钥用 POST 表单提交，不走 query string —— 免得进访问日志/Referer。"""
    if not api_key_configured():
        return RedirectResponse(url="/qa", status_code=302)
    return templates.TemplateResponse(request, "qa/login.html", {"bad": bool(bad)})


@router.post("/qa/login")
def qa_login(key: str = Form(...)):
    if not verify_key(key):
        return RedirectResponse(url="/qa/login?bad=1", status_code=302)
    resp = RedirectResponse(url="/qa", status_code=302)
    s = get_settings()
    set_qa_cookie(resp, key, secure=s.api_cookie_secure, samesite=s.api_cookie_samesite)
    return resp


@router.get("/qa/logout")
def qa_logout():
    resp = RedirectResponse(url="/qa/login", status_code=302)
    clear_qa_cookie(resp)
    return resp


@router.get("/qa", response_class=HTMLResponse)
def qa_home(request: Request, db: Session = Depends(get_db)):
    job_rows = db.execute(
        select(CrawlJob.status, func.count()).group_by(CrawlJob.status)
    ).all()
    job_by_status = {s: c for s, c in job_rows}

    status_rows = db.execute(
        select(RawResponse.answer_status, func.count()).group_by(RawResponse.answer_status)
    ).all()
    answer_by_status = {(s or "null"): c for s, c in status_rows}

    n_responses = int(db.scalar(select(func.count()).select_from(RawResponse)) or 0)
    n_mentions = int(db.scalar(select(func.count()).select_from(Mention)) or 0)
    n_brands = int(db.scalar(select(func.count()).select_from(Brand)) or 0)
    n_prompts = int(db.scalar(select(func.count()).select_from(Prompt)) or 0)

    recent_jobs = list(
        db.scalars(select(CrawlJob).order_by(desc(CrawlJob.id)).limit(10)).all()
    )
    recent_responses = list(
        db.scalars(
            select(RawResponse)
            .options(selectinload(RawResponse.mentions))
            .order_by(desc(RawResponse.id))
            .limit(10)
        ).all()
    )

    # counts for brand 1 if exists
    brand1 = db.get(Brand, 1)
    counts = None
    if brand1:
        try:
            counts = compute_counts(db, brand_id=1)
        except Exception:
            counts = None

    return templates.TemplateResponse(
        request,
        "qa/home.html",
        {
            "job_by_status": job_by_status,
            "answer_by_status": answer_by_status,
            "n_responses": n_responses,
            "n_mentions": n_mentions,
            "n_brands": n_brands,
            "n_prompts": n_prompts,
            "recent_jobs": recent_jobs,
            "recent_responses": recent_responses,
            "counts": counts,
            "brand1": brand1,
        },
    )


@router.get("/qa/jobs", response_class=HTMLResponse)
def qa_jobs(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = select(CrawlJob).order_by(desc(CrawlJob.id))
    if status:
        q = q.where(CrawlJob.status == status)
    jobs = list(db.scalars(q.limit(limit)).all())
    # attach prompt text
    prompt_ids = list({j.prompt_id for j in jobs})
    prompts = {}
    if prompt_ids:
        for p in db.scalars(select(Prompt).where(Prompt.id.in_(prompt_ids))).all():
            prompts[p.id] = p
    return templates.TemplateResponse(
        request,
        "qa/jobs.html",
        {
            "jobs": jobs,
            "prompts": prompts,
            "status": status,
        },
    )


@router.get("/qa/responses", response_class=HTMLResponse)
def qa_responses(
    request: Request,
    answer_status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        select(RawResponse)
        .options(selectinload(RawResponse.mentions), selectinload(RawResponse.citations))
        .order_by(desc(RawResponse.id))
    )
    if answer_status:
        q = q.where(RawResponse.answer_status == answer_status)
    if platform:
        q = q.where(RawResponse.platform == platform)
    rows = list(db.scalars(q.limit(limit)).all())
    return templates.TemplateResponse(
        request,
        "qa/responses.html",
        {
            "rows": rows,
            "answer_status": answer_status,
            "platform": platform,
        },
    )


@router.get("/qa/responses/{response_id}", response_class=HTMLResponse)
def qa_response_detail(
    request: Request, response_id: int, db: Session = Depends(get_db)
):
    row = db.scalars(
        select(RawResponse)
        .where(RawResponse.id == response_id)
        .options(
            selectinload(RawResponse.mentions),
            selectinload(RawResponse.citations),
        )
    ).first()
    brands = {
        b.id: b for b in db.scalars(select(Brand)).all()
    }
    job = db.get(CrawlJob, row.job_id) if row else None
    prompt = db.get(Prompt, job.prompt_id) if job else None
    screenshot_url = None
    display_raw = None
    if row:
        display_raw = dict(row.raw_json or {})
        # never surface conversation URLs in QA
        for k in list(display_raw.keys()):
            if "url" in k.lower() or "chat" in k.lower():
                if isinstance(display_raw.get(k), str) and "deepseek.com" in display_raw[k]:
                    display_raw[k] = "[redacted-conversation-url]"
        if row.screenshot_path:
            name = Path(row.screenshot_path).name
            screenshot_url = f"/v1/media/screenshots/{name}"
    return templates.TemplateResponse(
        request,
        "qa/response_detail.html",
        {
            "row": row,
            "job": job,
            "prompt": prompt,
            "brands": brands,
            "screenshot_url": screenshot_url,
            "display_raw_json": display_raw,
        },
    )


@router.get("/qa/media/screenshots/{filename}")
@router.get("/v1/media/screenshots/{filename}")
def qa_screenshot(
    filename: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    """证据截图（只接受 basename）。

    两个路径指向同一处理函数：``/qa/...`` 给运维预览页，``/v1/...`` 给正式前端 ——
    前端不该依赖 ``/qa`` 这个运维工具的地盘。

    两条都是 GET，浏览器 ``<img src>`` 用 Cookie 认证即可（``<img>`` 发不了请求头）。

    **响应必须带 ``Cache-Control: private, no-store``。** 这是需要鉴权的证据文件，
    而 URL 以 ``.png`` 结尾 —— 放到 CDN（本项目走 Cloudflare）后面时，
    CDN 会按扩展名把它当静态资源缓存到边缘节点，之后任何拿到 URL 的人
    都能绕过鉴权取到图。加了这个头，共享缓存就不会存它。
    """
    import os

    safe = Path(filename).name
    if safe != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="bad filename")

    # 归属校验：这个路由只按文件名取图，与品牌毫无关联，而文件名带时间戳、可枚举。
    # 不校验的话，前面所有归属校验都白做 —— 客户照样能看到别家品牌的证据图。
    assert_screenshot_visible(db, principal, safe)

    roots = []
    env_dir = os.environ.get("SCREENSHOT_DIR")
    if env_dir:
        roots.append(Path(env_dir))
    roots.extend([
        Path("/data/screenshots"),
        Path("/app/data/screenshots"),
    ])

    for root in roots:
        path = (root / safe).resolve()
        try:
            # must stay under root
            path.relative_to(root.resolve())
        except Exception:
            continue
        if path.is_file():
            return FileResponse(
                str(path),
                media_type="image/png",
                headers={"Cache-Control": "private, no-store"},
            )
    raise HTTPException(status_code=404, detail=f"screenshot not found: {safe}")
