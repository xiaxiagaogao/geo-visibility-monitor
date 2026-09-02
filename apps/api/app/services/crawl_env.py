"""采集环境指纹（P2-36）。

## 为什么要有它

run 215 / 292 / 293 之间，**出口 IP、浏览器时区、登录态签发地、WAF 类型全都不一样**，
而数据里唯一记得住这些的是 ``run.note`` —— 一个自由文本，靠人当时记得写。

没有它，两件事做不了：

1. **跨 run 对比不可信。** 「这次比上次差了 10 个点」到底是表现变了还是环境变了，
   事后没有任何办法分辨。
2. **无法证明一次 run 没有混着两个出口采。** 冷备「只接替不并行」是一条纪律，
   而纪律需要证据 —— 2026-08-14 那次部署把冷备静默拉起来，正是这类事故。

## 一行 = 一种环境，不是一行一次抓取

环境很少变，job 每天几十条。所以 ``crawl_environments`` 按指纹去重，
``crawl_jobs.environment_id`` 指过去。于是：

```sql
SELECT DISTINCT environment_id FROM crawl_jobs WHERE run_id = 293;
```

**多于一行就是混了。** 这是一次查询就能得到的事实，不是回忆。
"""
from __future__ import annotations

import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("geo.crawl_env")

#: 出口 IP 探测。ipinfo 的纯文本端点，返回体就一个 IP
_EXIT_IP_URL = "https://ipinfo.io/ip"
_IP_RE = re.compile(r"^[0-9a-fA-F.:]{7,45}$")

#: 指纹里包含哪些维度。**改这里等于改「什么算同一种环境」**，
#: 加维度会让历史环境行全部变成「另一种」——加之前想清楚值不值。
FINGERPRINT_FIELDS = (
    "node_label",
    "exit_ip",
    "timezone_id",
    "crawl_mode",
    "credential_region",
    "waf_kind",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_fingerprint(fields: Dict[str, Any]) -> str:
    """把一组环境维度归一成一个可读的指纹。

    **刻意不做哈希。** 排查时一眼要能看出两种环境差在哪 ——
    `changsha-home|203.0.113.10|Asia/Shanghai|real|cn|huawei` 自己就是答案，
    而一串 sha256 还得去查表。

    缺失的维度写成 ``-``，不是省略 —— 否则「没探到 IP」和「IP 是空字符串」
    会归成同一种环境。
    """
    parts = []
    for k in FINGERPRINT_FIELDS:
        v = fields.get(k)
        v = str(v).strip() if v not in (None, "") else "-"
        parts.append(v.replace("|", "/"))  # 分隔符不能出现在值里
    return "|".join(parts)


def probe_exit_ip(
    timeout: float = 8.0, attempts: int = 3, retry_sleep: float = 2.0
) -> Optional[str]:
    """探容器的出口 IP。失败返回 ``None``，**绝不抛异常**。

    **刻意不禁用代理。** 我们要记的是这个环境**实际**从哪儿出去的 ——
    如果有人给容器设了 proxy 环境变量，那出口就真的变成了代理的落地，
    该被如实记下来。（`deploy.sh verify` 另有一条硬检查会直接拦住这种情况，
    见 `scripts/crawl-node/README.md`。）

    **重试是 P2-39 加的。** 探测失败的代价不再是「指纹缺一维」（那会造出幻影
    环境，见 ``upsert_environment``），而是「这一轮整个不记」—— 代价变大了，
    所以值得为一次网络抖动多试两下。家宽本来就会抖。
    """
    for i in range(max(1, attempts)):
        try:
            with urllib.request.urlopen(_EXIT_IP_URL, timeout=timeout) as resp:
                ip = (resp.read().decode("utf-8") or "").strip()
            if _IP_RE.match(ip):
                return ip
            logger.warning("出口 IP 探测返回了不像 IP 的内容，重试")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "探出口 IP 失败（第 %s/%s 次）: %s", i + 1, attempts, type(exc).__name__
            )
        if i + 1 < attempts and retry_sleep > 0:
            time.sleep(retry_sleep)
    logger.warning("出口 IP 探不到，本轮不记录采集环境（那批 job 会留 NULL）")
    return None


def describe_environment(
    settings,
    *,
    credential_region: Optional[str] = None,
    waf_kind: Optional[str] = None,
    exit_ip: Optional[str] = None,
) -> Dict[str, Any]:
    """收集当前环境的各维度。纯函数（``exit_ip`` 由调用方探好传进来）。

    ``credential_region`` / ``waf_kind`` 来自 P2-07 的登录态检查 ——
    两者在 worker 循环里是同一轮算出来的，不重复读文件。
    """
    fields = {
        "node_label": getattr(settings, "crawl_node_label", "") or None,
        "exit_ip": exit_ip,
        "timezone_id": getattr(settings, "crawl_timezone_id", "") or None,
        "crawl_mode": getattr(settings, "crawl_mode", "") or None,
        "credential_region": credential_region,
        "waf_kind": waf_kind,
    }
    fields["fingerprint"] = compute_fingerprint(fields)
    return fields


# ─────────────────────────────────────────────────────────────────────────
# 以上纯函数，以下落库
# ─────────────────────────────────────────────────────────────────────────


def upsert_environment(db, fields: Dict[str, Any]) -> Optional[int]:
    """按指纹取回环境 id，没有就建一行。返回 ``None`` 表示这轮记不上（不阻断采集）。

    **``exit_ip`` 探不到时直接不记（P2-39）。** 这是本模块 docstring 那条
    「探不到就留 NULL，不编默认值」的兑现 —— 而在此之前实现是自相矛盾的：
    探测失败会让指纹里那一维变成 ``-``，于是 upsert 出**一行新环境**，于是
    ``SELECT DISTINCT environment_id`` 大于 1，于是告警说
    「这次 run 混了两个出口」。**而出口根本没混，只是那一次探测失败了。**
    （run 298 实际发生过；库里 fingerprint 带 ``|-|`` 的那行就是那次留下的。）

    宁可这批 job 标成「没记」，也不要记成「另一种环境」：
    **前者是事实，后者是一句会触发告警的假话。**

    ⚠️ 只有 ``exit_ip`` 享受这个待遇，因为只有它会**间歇性**失败。
    别的维度缺失（比如没配 ``CRAWL_NODE_LABEL``）是稳定的配置状态，
    不会一会儿有一会儿没有，也就造不出幻影。
    """
    from app.models import CrawlEnvironment

    fp = fields.get("fingerprint")
    if not fp:
        return None
    if not fields.get("exit_ip"):
        logger.warning("出口 IP 未知，本轮不记录采集环境（避免造出幻影环境）")
        return None
    try:
        from sqlalchemy import func, select

        now = _utcnow()
        row = db.scalars(
            select(CrawlEnvironment).where(CrawlEnvironment.fingerprint == fp)
        ).first()
        if row is None:
            # **新环境要吼一声。** 出口/时区/登录态任何一维变了都会走到这里，
            # 而那正是「跨 run 对比要小心」的时刻。
            #
            # 但第一行要说「首次记录」而不是「变了」—— 表是空的时候什么都没变，
            # 说「变了」是句假话，而假日志比没日志更坏：它会让人去找一个不存在的变更
            is_first = db.scalar(select(func.count(CrawlEnvironment.id))) == 0
            row = CrawlEnvironment(fingerprint=fp, first_seen_at=now)
            if is_first:
                logger.info("首次记录采集环境: %s", fp)
            else:
                logger.warning("采集环境变了，新指纹: %s", fp)
        for k in FINGERPRINT_FIELDS:
            setattr(row, k, fields.get(k))
        row.last_seen_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("环境指纹落库失败（本轮 job 将不带环境标记）")
        return None
