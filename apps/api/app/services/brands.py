from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Brand, BrandAlias, CompetitorLink
from app.schemas.brand import BrandCreate, BrandUpdate


def _normalize_aliases(aliases: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for a in aliases:
        s = (a or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def brand_to_dict(db: Session, brand: Brand) -> dict:
    aliases = [a.alias for a in brand.aliases]
    comp_ids = db.scalars(
        select(CompetitorLink.competitor_brand_id).where(
            CompetitorLink.brand_id == brand.id
        )
    ).all()
    return {
        "id": brand.id,
        "workspace_id": brand.workspace_id,
        "name": brand.name,
        "name_en": brand.name_en,
        "industry": brand.industry,
        "aliases": aliases,
        "competitor_ids": list(comp_ids),
        "created_at": brand.created_at,
    }


def get_brand_or_404(db: Session, brand_id: int) -> Brand:
    brand = db.scalars(
        select(Brand)
        .where(Brand.id == brand_id)
        .options(selectinload(Brand.aliases))
    ).first()
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="brand not found")
    return brand


def list_brands(db: Session, workspace_id: Optional[int] = None) -> List[Brand]:
    q = select(Brand).options(selectinload(Brand.aliases)).order_by(Brand.id.desc())
    if workspace_id is not None:
        q = q.where(Brand.workspace_id == workspace_id)
    return list(db.scalars(q).all())


def create_brand(db: Session, data: BrandCreate) -> Brand:
    brand = Brand(
        name=data.name.strip(),
        name_en=data.name_en,
        industry=data.industry,
        workspace_id=data.workspace_id,
    )
    db.add(brand)
    db.flush()
    for alias in _normalize_aliases(data.aliases):
        db.add(BrandAlias(brand_id=brand.id, alias=alias))
    # also ensure canonical name is matchable later via alias list optionally
    db.commit()
    return get_brand_or_404(db, brand.id)


def update_brand(db: Session, brand_id: int, data: BrandUpdate) -> Brand:
    brand = get_brand_or_404(db, brand_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        payload["name"] = payload["name"].strip()
    for k, v in payload.items():
        setattr(brand, k, v)
    db.commit()
    return get_brand_or_404(db, brand.id)


def delete_brand(db: Session, brand_id: int) -> None:
    brand = get_brand_or_404(db, brand_id)
    # clean competitor links either side
    db.execute(
        delete(CompetitorLink).where(
            (CompetitorLink.brand_id == brand_id)
            | (CompetitorLink.competitor_brand_id == brand_id)
        )
    )
    db.delete(brand)
    db.commit()


def replace_aliases(db: Session, brand_id: int, aliases: List[str]) -> Brand:
    brand = get_brand_or_404(db, brand_id)
    db.execute(delete(BrandAlias).where(BrandAlias.brand_id == brand_id))
    for alias in _normalize_aliases(aliases):
        db.add(BrandAlias(brand_id=brand_id, alias=alias))
    db.commit()
    return get_brand_or_404(db, brand.id)


def replace_competitors(db: Session, brand_id: int, competitor_ids: List[int]) -> Brand:
    brand = get_brand_or_404(db, brand_id)
    # unique, no self
    cleaned = []
    seen = set()
    for cid in competitor_ids:
        if cid == brand_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="competitor cannot be self",
            )
        if cid in seen:
            continue
        seen.add(cid)
        cleaned.append(cid)

    if cleaned:
        existing = set(
            db.scalars(select(Brand.id).where(Brand.id.in_(cleaned))).all()
        )
        missing = [c for c in cleaned if c not in existing]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown competitor brand ids: {missing}",
            )

    db.execute(delete(CompetitorLink).where(CompetitorLink.brand_id == brand_id))
    for cid in cleaned:
        db.add(CompetitorLink(brand_id=brand_id, competitor_brand_id=cid))
    db.commit()
    return get_brand_or_404(db, brand.id)


def count_brands(db: Session, workspace_id: Optional[int] = None) -> int:
    q = select(func.count()).select_from(Brand)
    if workspace_id is not None:
        q = q.where(Brand.workspace_id == workspace_id)
    return int(db.scalar(q) or 0)
