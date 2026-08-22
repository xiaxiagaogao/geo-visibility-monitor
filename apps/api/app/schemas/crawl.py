from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


#: 已知平台 = ``platform`` 列的合法取值。**注意它不等于「能跑」** ——
#: 能不能跑要问 ``registry.is_runnable``（见 registry 模块文档）。
#: 保留这个名字是为了不动既有引用；取值从注册表派生，避免两处漂移。
from app.providers.registry import known_codes as _known_codes  # noqa: E402

ALLOWED_PLATFORMS = _known_codes()


class CrawlJobCreate(BaseModel):
    prompt_id: int
    platform: str = "deepseek"
    samples: int = Field(1, ge=1, le=10)


class CrawlJobOut(BaseModel):
    id: int
    prompt_id: int
    platform: str
    status: str
    sample_index: int
    error_message: Optional[str] = None
    #: P2-08 失败分类：``timeout`` / ``rate_limited`` / ``login_required`` /
    #: ``platform_unavailable`` / ``parse_error`` / ``worker_died`` / ``unknown``。
    #: **``null`` 表示「还没失败过」**，不表示「失败了但没认出来」——
    #: 后者是 ``unknown``，两者的排查方向完全不同
    failure_kind: Optional[str] = None
    #: P2-16 已消耗的尝试次数。``attempt > 1 且 status='success'``
    #: 就是「重试之后成功的」
    attempt: Optional[int] = None
    #: P2-16 下次可被领取的时刻。**有值且在未来 = 正在退避等重试**。
    #: 退避中的 job 状态仍是 ``pending``，靠这个字段才能和「还没轮到」分开
    next_attempt_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    response_id: Optional[int] = None

    model_config = {"from_attributes": True}


class CrawlJobListOut(BaseModel):
    items: List[CrawlJobOut]
    total: int


class CrawlJobDetailOut(CrawlJobOut):
    prompt_text: Optional[str] = None
    response: Optional["RawResponseOut"] = None


class CitationOut(BaseModel):
    id: int
    cite_index: Optional[int] = None
    url: str
    domain: str
    title: Optional[str] = None
    snippet: Optional[str] = None

    model_config = {"from_attributes": True}


class MentionOut(BaseModel):
    id: int
    brand_id: int
    mentioned: bool
    mention_type: str
    position_bucket: Optional[str] = None
    #: 出场顺位（1-based，仅 body 命中有值）。**是位置事实，不是推荐名次** ——
    #: 且只在被监测品牌集合内排序，见 services/annotate.assign_position_ranks
    position_rank: Optional[int] = None
    evidence_snippet: Optional[str] = None
    #: 首次命中在 full_text 里的下标，可直接切原文 → 前端做命中处内联高亮。
    #: citation_only 命中时为 null（正文里没出现）。
    first_offset: Optional[int] = None
    #: 实际命中的别名，用于展示「靠哪个别名命中的」
    matched_term: Optional[str] = None

    model_config = {"from_attributes": True}


class RawResponseOut(BaseModel):
    id: int
    job_id: int
    platform: str
    prompt_text: str
    full_text: str
    html_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None
    latency_ms: Optional[int] = None
    answer_status: Optional[str] = None
    annotator_version: Optional[str] = None
    #: P2-37 三态：True=联网了 · False=确认没联网 · None=不知道。
    #: **前端分桶时 None 必须单独一桶**，并到 False 里就是把「没记」说成「没联网」
    search_used: Optional[bool] = None
    created_at: datetime
    citations: List[CitationOut] = Field(default_factory=list)
    mentions: List[MentionOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RawResponseListOut(BaseModel):
    items: List[RawResponseOut]
    total: int


class RawResponseSummaryOut(BaseModel):
    """列表用的轻量投影 —— **没有 full_text，也没有 raw_json**。

    单开一个模型而不是把 ``RawResponseOut.full_text`` 改成可选：
    「有时有有时没有」的字段会让类型撒谎，前端拿到 undefined 时不会报错，
    只会渲染出一片空白。这里少的字段在类型上就是不存在的。

    ``text_preview`` / ``text_length`` 由 SQL 的 substr / length 算出来，
    大列根本不进 Python —— 这是这个端点存在的全部理由。
    """

    id: int
    job_id: int
    platform: str
    prompt_text: str
    #: 正文前 N 字（N = api/responses.py::PREVIEW_CHARS），列表里给个人眼锚点
    text_preview: str
    #: 正文总字数。配合 preview 让「这条被截断了」变成可判断的事实
    text_length: int
    screenshot_path: Optional[str] = None
    latency_ms: Optional[int] = None
    answer_status: Optional[str] = None
    annotator_version: Optional[str] = None
    #: P2-37 三态：True=联网了 · False=确认没联网 · None=不知道。
    #: **前端分桶时 None 必须单独一桶**，并到 False 里就是把「没记」说成「没联网」
    search_used: Optional[bool] = None
    created_at: datetime
    #: 逐品牌标注照常给全 —— 它是列表里唯一有结论的东西，且体量比 full_text 小两个量级
    mentions: List[MentionOut] = Field(default_factory=list)


class RawResponseSummaryListOut(BaseModel):
    items: List[RawResponseSummaryOut]
    total: int


class WorkerRunOut(BaseModel):
    processed: int
    job_ids: List[int]


class WorkerLeaseItem(BaseModel):
    """一条领走的 job —— **采集节点跑完它所需的全部信息**。

    节点没有数据库，所以 ``prompt_text`` 与 ``brand_names`` 必须在这里给全。
    少给一样，节点就得自己去查库，而「节点不碰库」正是 P2-34 的全部意义。
    """

    job_id: int
    platform: str
    sample_index: int
    prompt_id: int
    prompt_text: str
    #: 中文名 · 英文名 · 全部别名（fake 模式造正文要用）
    brand_names: List[str] = Field(default_factory=list)


class WorkerCitationIn(BaseModel):
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    #: 不传就由 url 推出来（与隧道模式 persist_result 同一套口径）
    domain: Optional[str] = None
    cite_index: Optional[int] = None


class WorkerResultIn(BaseModel):
    """节点回传一次成功抓取的正文。

    **刻意没有 `prompt_text` 字段。** 我们知道自己问了什么，服务端按 `job.prompt_id`
    自己查 —— 让节点回传等于给证据页开一个可以说谎的口子。pydantic 默认忽略多余字段，
    所以节点顺手传了也不会生效（`test_result_uses_server_side_prompt_text` 钉着）。

    **也没有 `platform`。** 同理，那是建 job 时就定下的事实。
    """

    full_text: str
    citations: List[WorkerCitationIn] = Field(default_factory=list)
    raw_json: Optional[dict] = None
    latency_ms: Optional[int] = None
    #: P2-37 这次有没有联网检索。**默认 None = 不知道**，绝不能默认成 False ——
    #: 老版本节点不带这个字段时，把它记成「没联网」是凭空造一条结论
    search_used: Optional[bool] = None


class WorkerResultOut(BaseModel):
    job_id: int
    #: 重复提交时回的是**同一个** id —— 落库成功但响应没回到节点是常态，
    #: 节点重试是对的做法，不该因此多出一条样本
    response_id: int
    status: str


class WorkerFailIn(BaseModel):
    """节点回传一次失败。

    ``kind`` 由**节点**算好带上来：``classify_failure`` 的判定顺序是
    「异常类型 → 消息模式 → unknown」，而**异常类型过不了 HTTP**。
    只传字符串的话，`QianwenLoginRequired` 这类会退化成靠子串猜。
    不传（老版本节点）则退回服务端按消息文本分类。
    """

    reason: str
    kind: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: Optional[str]) -> Optional[str]:
        # 乱写的 kind 会静默毁掉重试决策（RETRYABLE_KINDS 匹配不上）与 API 契约，
        # 而它落进库之后没有任何地方会报错。宁可 422
        from app.services.failure_kinds import ALL_KINDS

        if v is not None and v not in ALL_KINDS:
            raise ValueError(f"kind must be one of {list(ALL_KINDS)}")
        return v


class WorkerEnvironmentIn(BaseModel):
    """节点自报采集环境的六个维度（P2-36）。

    **刻意没有 `fingerprint` 字段。** 指纹由服务端用 ``compute_fingerprint`` 算，
    因为它定义「什么算同一种环境」—— 让节点自己算并上报的话，节点与冷备一旦版本
    不齐，同一种环境会算出两个指纹，造出一个幻影环境，而 P2-36 的告警会据此说
    「这次 run 混了两个出口」。**告警撒谎比没有告警更糟。**
    """

    node_label: Optional[str] = None
    exit_ip: Optional[str] = None
    timezone_id: Optional[str] = None
    crawl_mode: Optional[str] = None
    credential_region: Optional[str] = None
    waf_kind: Optional[str] = None


class WorkerEnvironmentOut(BaseModel):
    #: ``null`` = 这轮记不上（落库失败）。**不阻断采集** —— 那一批 job 的
    #: ``environment_id`` 留 NULL，表示「没记」，比编一个准确
    environment_id: Optional[int] = None


class WorkerCredentialIn(BaseModel):
    """一个平台的登录态健康度快照（P2-07）。

    ⚠️ **这里永远只有 cookie 的名字，没有值。** 模型里根本没有能放值的字段，
    节点硬塞也塞不进来（pydantic 忽略多余字段）。值是凭证本身，落进数据库
    就等于把登录态复制到了一个没人当它是凭证的地方。

    **也没有 `checked_at`。** 那是「多久没听到节点动静」的信号，
    由服务端盖章 —— 用节点的时钟，钟一歪这个信号就说假话。
    """

    platform: str
    status: str
    node_label: Optional[str] = None
    issuer_region: Optional[str] = None
    waf_kind: Optional[str] = None
    cookie_count: Optional[int] = None
    cookie_names: List[str] = Field(default_factory=list)
    earliest_expiry: Optional[datetime] = None
    file_mtime: Optional[datetime] = None
    issues: List[str] = Field(default_factory=list)

    @field_validator("platform")
    @classmethod
    def _known_platform(cls, v: str) -> str:
        # platform 是主键 —— 写错一次就多一行永远清不掉的假平台，
        # 而它会直接出现在 GET /v1/health/credentials 里
        if v not in _known_codes():
            raise ValueError(f"platform must be one of {list(_known_codes())}")
        return v

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        # 乱写的 status 会直接被 worse_of 拿去算 overall，而它不在严重度表里
        # 就会被当成「比 ok 还轻」—— 一个坏掉的凭证会显示成健康
        from app.services.credential_health import _SEVERITY

        if v not in _SEVERITY:
            raise ValueError(f"status must be one of {list(_SEVERITY)}")
        return v


class WorkerCredentialsIn(BaseModel):
    items: List[WorkerCredentialIn] = Field(default_factory=list)


class WorkerCredentialsOut(BaseModel):
    accepted: int


class WorkerLeaseOut(BaseModel):
    """**空列表是正常状态**，不是错误 —— 节点每几秒来问一次，多数时候没活干。

    包一层对象而不是裸数组：将来要加 lease 时长、服务端时间这类字段时
    不必改调用方的解析形状。
    """

    jobs: List[WorkerLeaseItem] = Field(default_factory=list)
