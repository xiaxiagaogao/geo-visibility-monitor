from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.prompt import PromptCreate, PromptListOut, PromptOut, PromptUpdate
from app.services import prompts as prompt_svc

router = APIRouter(prefix="/v1/prompts", tags=["prompts"])


@router.get("", response_model=PromptListOut)
def list_prompts(
    brand_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    items = prompt_svc.list_prompts(db, brand_id=brand_id, active_only=active_only)
    return PromptListOut(
        items=[PromptOut.model_validate(p) for p in items],
        total=prompt_svc.count_prompts(db, brand_id=brand_id),
    )


@router.post("", response_model=PromptOut, status_code=status.HTTP_201_CREATED)
def create_prompt(body: PromptCreate, db: Session = Depends(get_db)):
    p = prompt_svc.create_prompt(db, body)
    return PromptOut.model_validate(p)


@router.get("/{prompt_id}", response_model=PromptOut)
def get_prompt(prompt_id: int, db: Session = Depends(get_db)):
    p = prompt_svc.get_prompt_or_404(db, prompt_id)
    return PromptOut.model_validate(p)


@router.patch("/{prompt_id}", response_model=PromptOut)
def update_prompt(prompt_id: int, body: PromptUpdate, db: Session = Depends(get_db)):
    p = prompt_svc.update_prompt(db, prompt_id, body)
    return PromptOut.model_validate(p)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(prompt_id: int, db: Session = Depends(get_db)):
    prompt_svc.delete_prompt(db, prompt_id)
    return None
