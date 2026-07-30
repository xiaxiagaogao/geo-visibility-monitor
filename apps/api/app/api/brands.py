from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.brand import (
    AliasReplace,
    BrandCreate,
    BrandListOut,
    BrandOut,
    BrandUpdate,
    CompetitorReplace,
)
from app.services import brands as brand_svc

router = APIRouter(prefix="/v1/brands", tags=["brands"])


@router.get("", response_model=BrandListOut)
def list_brands(
    workspace_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    items = brand_svc.list_brands(db, workspace_id=workspace_id)
    return BrandListOut(
        items=[BrandOut(**brand_svc.brand_to_dict(db, b)) for b in items],
        total=brand_svc.count_brands(db, workspace_id=workspace_id),
    )


@router.post("", response_model=BrandOut, status_code=status.HTTP_201_CREATED)
def create_brand(body: BrandCreate, db: Session = Depends(get_db)):
    b = brand_svc.create_brand(db, body)
    return BrandOut(**brand_svc.brand_to_dict(db, b))


@router.get("/{brand_id}", response_model=BrandOut)
def get_brand(brand_id: int, db: Session = Depends(get_db)):
    b = brand_svc.get_brand_or_404(db, brand_id)
    return BrandOut(**brand_svc.brand_to_dict(db, b))


@router.patch("/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: int, body: BrandUpdate, db: Session = Depends(get_db)):
    b = brand_svc.update_brand(db, brand_id, body)
    return BrandOut(**brand_svc.brand_to_dict(db, b))


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(brand_id: int, db: Session = Depends(get_db)):
    brand_svc.delete_brand(db, brand_id)
    return None


@router.put("/{brand_id}/aliases", response_model=BrandOut)
def put_aliases(brand_id: int, body: AliasReplace, db: Session = Depends(get_db)):
    b = brand_svc.replace_aliases(db, brand_id, body.aliases)
    return BrandOut(**brand_svc.brand_to_dict(db, b))


@router.put("/{brand_id}/competitors", response_model=BrandOut)
def put_competitors(
    brand_id: int, body: CompetitorReplace, db: Session = Depends(get_db)
):
    b = brand_svc.replace_competitors(db, brand_id, body.competitor_ids)
    return BrandOut(**brand_svc.brand_to_dict(db, b))
