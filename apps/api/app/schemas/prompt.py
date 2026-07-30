from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class PromptCreate(BaseModel):
    brand_id: int
    text: str = Field(..., min_length=1)
    category: Optional[str] = None
    tags: List[Any] = Field(default_factory=list)
    is_active: bool = True


class PromptUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = None
    tags: Optional[List[Any]] = None
    is_active: Optional[bool] = None


class PromptOut(BaseModel):
    id: int
    brand_id: int
    text: str
    category: Optional[str] = None
    tags: List[Any] = Field(default_factory=list)
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PromptListOut(BaseModel):
    items: List[PromptOut]
    total: int
