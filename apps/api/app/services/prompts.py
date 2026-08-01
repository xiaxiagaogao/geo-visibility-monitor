from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Prompt
from app.schemas.prompt import PromptCreate, PromptUpdate
from app.services.brands import get_brand_or_404


def get_prompt_or_404(db: Session, prompt_id: int) -> Prompt:
    prompt = db.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="prompt not found")
    return prompt


def list_prompts(
    db: Session,
    brand_id: Optional[int] = None,
    active_only: bool = False,
) -> List[Prompt]:
    q = select(Prompt).order_by(Prompt.id.desc())
    if brand_id is not None:
        q = q.where(Prompt.brand_id == brand_id)
    if active_only:
        q = q.where(Prompt.is_active.is_(True))
    return list(db.scalars(q).all())


def create_prompt(db: Session, data: PromptCreate) -> Prompt:
    get_brand_or_404(db, data.brand_id)
    prompt = Prompt(
        brand_id=data.brand_id,
        text=data.text.strip(),
        category=data.category,
        tags=data.tags or [],
        is_active=data.is_active,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def update_prompt(db: Session, prompt_id: int, data: PromptUpdate) -> Prompt:
    prompt = get_prompt_or_404(db, prompt_id)
    payload = data.model_dump(exclude_unset=True)
    if "text" in payload and payload["text"] is not None:
        payload["text"] = payload["text"].strip()
    for k, v in payload.items():
        setattr(prompt, k, v)
    db.commit()
    db.refresh(prompt)
    return prompt


def delete_prompt(db: Session, prompt_id: int) -> None:
    prompt = get_prompt_or_404(db, prompt_id)
    db.delete(prompt)
    db.commit()


def count_prompts(db: Session, brand_id: Optional[int] = None) -> int:
    q = select(func.count()).select_from(Prompt)
    if brand_id is not None:
        q = q.where(Prompt.brand_id == brand_id)
    return int(db.scalar(q) or 0)
