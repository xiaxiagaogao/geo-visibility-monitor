from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CredentialHealthOut(BaseModel):
    """一个平台的登录态健康度（P2-07）。**不含任何 cookie 的值。**"""

    platform: str
    #: ``ok`` | ``aging`` | ``expired`` | ``mismatch`` | ``missing``
    status: str
    #: 哪台机器报的（P2-36 的第一块）。``null`` = 未标注
    node_label: Optional[str] = None
    #: ``cn`` | ``overseas`` | ``unknown`` —— 由 WAF cookie 的类型判定。
    #: **这是 2026-08-15 那次事故里唯一能提前发现问题的字段**
    issuer_region: Optional[str] = None
    waf_kind: Optional[str] = None
    cookie_count: Optional[int] = None
    #: 只有名字，**没有值**。接新平台时靠它看出对方用的哪家 WAF
    cookie_names: List[str] = Field(default_factory=list)
    earliest_expiry: Optional[datetime] = None
    file_mtime: Optional[datetime] = None
    #: 命中的所有问题（不只是最严重那一个）——
    #: 只报一个会让第二个问题在修完第一个之前不可见
    issues: List[str] = Field(default_factory=list)
    #: 这份快照是什么时候检查的。**太旧本身就是信号**：说明 crawler 没在跑
    checked_at: datetime
    #: 最后一次成功抓取。**只能发现「全红」，发现不了「悄悄降级」**——
    #: 保留它是因为两种故障形态都存在，不是因为它够用
    last_success_at: Optional[datetime] = None


class CredentialListOut(BaseModel):
    #: 所有平台里最严重的那一档；一条都没上报过时是 ``unreported``
    #: （**不是 ok** —— 没有数据不等于健康）
    overall: str
    items: List[CredentialHealthOut] = Field(default_factory=list)
    generated_at: datetime
