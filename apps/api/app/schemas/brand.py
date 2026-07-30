from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BrandCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    name_en: Optional[str] = None
    industry: Optional[str] = None
    workspace_id: int = 1
    aliases: List[str] = Field(default_factory=list)


class BrandUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    name_en: Optional[str] = None
    industry: Optional[str] = None


class BrandOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    name_en: Optional[str] = None
    industry: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    competitor_ids: List[int] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class BrandListOut(BaseModel):
    items: List[BrandOut]
    total: int


class AliasReplace(BaseModel):
    aliases: List[str] = Field(default_factory=list)


class CompetitorReplace(BaseModel):
    competitor_ids: List[int] = Field(default_factory=list)
