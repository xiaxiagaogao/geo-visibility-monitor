"""登录态健康度（P2-07）。纯函数：读一份 ``storage_state``，判它还能不能用。

## 为什么不是「上次成功抓取距今多久」

原计划是这么想的：``storage_state`` 过期 → 一批 job 全红 → 看最后一次成功的时间。
**2026-08-15 证明那个故障模型是错的。**

真实发生的是：登录态从新加坡导出、带着**已过期 11 天**的 `aws-waf-token`，
而 DeepSeek 境内走的是华为云 WAF。表现不是「全红」，是**悄悄降级** ——
每次 run 头一两条卡在 WAF 挑战上超时，后面照常跑完。
「上次成功抓取」一直是几分钟前，任何基于它的告警都不会响。

所以这里看的是三件「不用跑一次 run 就能知道」的事：

1. **这份登录态是从哪儿签发的** —— WAF cookie 的类型直接暴露它（见 ``WAF_SIGNATURES``）
2. **里面最早过期的 cookie 还有多久** —— 这次是已经过期 11 天
3. **文件本身多久没换了**

## 一条硬规矩：绝不读取、绝不落库 cookie 的值

这里只取**名字、域、过期时间**。值是凭证本身，一旦进了数据库或日志，
就等于把登录态复制到了一个没人当它是凭证的地方
（``BACKEND.md``：密钥 / storage_state 禁止进 Git，同一条理由）。
``inspect_storage_state`` 的返回值里没有任何一处能拿到值。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: WAF cookie 名 → (厂商, 签发地)。**这张表是这一版最有信息量的东西。**
#:
#: DeepSeek 的境内与境外流量走两套不同的基础设施，cookie 名字直接把它写在脸上：
#: 拿着 `aws-waf-token` 去大陆采集，就是「IP 切了、环境没切」。
#: 加平台时往这里加行，不要在别处散着判断。
WAF_SIGNATURES: Tuple[Tuple[str, str, str], ...] = (
    ("hwwafses", "huawei", "cn"),        # HWWAFSESID / HWWAFSESTIME
    ("aws-waf-token", "aws", "overseas"),
    ("awswaf", "aws", "overseas"),
)

REGION_UNKNOWN = "unknown"

# 状态，**按严重程度从高到低**。`status` 取最严重的那个，
# 但 `issues` 会把命中的全列出来 —— 只报一个会让第二个问题在修完第一个之前不可见。
MISSING = "missing"            # 文件不在 / 空 / 解析不了
REGION_MISMATCH = "mismatch"   # 签发地和期望的采集出口对不上 ← 2026-08-15 的形态
EXPIRED = "expired"            # 有 cookie 已经过期
AGING = "aging"                # 文件太久没更新（还没坏，但该换了）
OK = "ok"

_SEVERITY = (MISSING, REGION_MISMATCH, EXPIRED, AGING, OK)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def classify_waf(cookie_names: List[str]) -> Tuple[str, str]:
    """由 cookie 名认出 WAF 厂商与签发地。返回 ``(waf_kind, issuer_region)``。

    大小写不敏感 —— `HWWAFSESID` 与 `hwwafsesid` 是同一个东西，
    而 cookie 名的大小写不该成为判断失效的原因。
    """
    lowered = [n.lower() for n in cookie_names]
    for needle, kind, region in WAF_SIGNATURES:
        if any(needle in n for n in lowered):
            return kind, region
    return "none", REGION_UNKNOWN


def inspect_storage_state(path: Optional[str]) -> Dict[str, Any]:
    """读一份 ``storage_state``，只取元信息。**返回值里没有任何 cookie 的值。**

    读不到 / 解析不了都不抛异常 —— 这是个健康检查，它自己不能成为故障源。
    """
    out: Dict[str, Any] = {
        "path": path or None,
        "exists": False,
        "cookie_count": 0,
        "cookie_names": [],
        "domains": [],
        "waf_kind": "none",
        "issuer_region": REGION_UNKNOWN,
        "earliest_expiry": None,
        "file_mtime": None,
        "parse_error": None,
    }
    if not path:
        out["parse_error"] = "未配置 DEEPSEEK_STORAGE_STATE"
        return out

    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size == 0:
            out["parse_error"] = "文件不存在或为空"
            return out
        out["exists"] = True
        out["file_mtime"] = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        out["parse_error"] = f"读不动或不是合法 JSON: {type(exc).__name__}"
        return out

    cookies = data.get("cookies") or []
    names = [c.get("name", "") for c in cookies if c.get("name")]
    out["cookie_count"] = len(cookies)
    out["cookie_names"] = sorted(names)
    out["domains"] = sorted({c.get("domain", "") for c in cookies if c.get("domain")})
    out["waf_kind"], out["issuer_region"] = classify_waf(names)

    # 会话 cookie（expires <= 0）没有过期时间，不参与「最早过期」——
    # 它们随浏览器关闭失效，和「令牌到期」是两回事
    expiries = [c.get("expires") for c in cookies if (c.get("expires") or -1) > 0]
    if expiries:
        out["earliest_expiry"] = datetime.fromtimestamp(min(expiries), tz=timezone.utc)
    return out


def derive_status(
    info: Dict[str, Any],
    *,
    expected_region: str,
    max_age_days: int,
    now: Optional[datetime] = None,
) -> Tuple[str, List[str]]:
    """由元信息判级。返回 ``(status, issues)``；``status`` 是最严重的那一个。

    ``expected_region`` 为空或 ``unknown`` 时不做签发地判断 ——
    宁可不报，也不要报一个我们并不确定的「不匹配」。
    """
    now = now or _utcnow()
    issues: List[str] = []

    if not info.get("exists") or info.get("parse_error"):
        return MISSING, [info.get("parse_error") or "文件不存在"]

    region = info.get("issuer_region") or REGION_UNKNOWN
    if expected_region and expected_region != REGION_UNKNOWN and region != REGION_UNKNOWN:
        if region != expected_region:
            issues.append(
                f"签发地是 {region}（{info.get('waf_kind')} WAF），"
                f"而采集出口期望 {expected_region} —— IP 切了、环境没切"
            )

    exp = info.get("earliest_expiry")
    if exp and exp < now:
        days = (now - exp).days
        issues.append(f"最早过期的 cookie 已过期 {days} 天")

    mtime = info.get("file_mtime")
    if mtime and max_age_days > 0:
        age = (now - mtime).days
        if age >= max_age_days:
            issues.append(f"登录态文件 {age} 天没更新（阈值 {max_age_days} 天）")

    if not issues:
        return OK, []
    # 按严重程度取最高的那一档
    if any("签发地" in i for i in issues):
        return REGION_MISMATCH, issues
    if any("已过期" in i for i in issues):
        return EXPIRED, issues
    return AGING, issues


def worse_of(a: str, b: str) -> str:
    """两个状态取更严重的那个（多平台汇总时用）。"""
    ia = _SEVERITY.index(a) if a in _SEVERITY else len(_SEVERITY)
    ib = _SEVERITY.index(b) if b in _SEVERITY else len(_SEVERITY)
    return a if ia <= ib else b


# ─────────────────────────────────────────────────────────────────────────
# 以上全是纯函数（不碰数据库、不碰网络），以下是落库。
# 分界画在这里是为了让判级逻辑能在本机单测 —— 它是这个模块的全部价值所在。
# ─────────────────────────────────────────────────────────────────────────


#: 平台 → 该平台登录态文件的配置项名。加平台时往这里加一行。
_STORAGE_SETTING = {"deepseek": "deepseek_storage_state"}


def report_credentials(db, settings) -> List[Dict[str, Any]]:
    """检查本机上所有已知平台的登录态，写回 ``crawl_credentials``。

    **由 crawler 调用，不是 api** —— ``storage_state`` 在采集节点上，
    api 跑在 VPS，它读不到那个文件。

    整个函数不抛异常：健康检查坏掉不该把采集也带下去。
    """
    from app.models import CrawlCredential

    now = _utcnow()
    out: List[Dict[str, Any]] = []
    for platform, setting_name in _STORAGE_SETTING.items():
        try:
            info = inspect_storage_state(getattr(settings, setting_name, "") or None)
            status, issues = derive_status(
                info,
                expected_region=getattr(settings, "crawl_expected_credential_region", ""),
                max_age_days=getattr(settings, "crawl_credential_max_age_days", 0),
                now=now,
            )
            row = db.get(CrawlCredential, platform) or CrawlCredential(platform=platform)
            row.node_label = getattr(settings, "crawl_node_label", "") or None
            row.status = status
            row.issuer_region = info["issuer_region"]
            row.waf_kind = info["waf_kind"]
            row.cookie_count = info["cookie_count"]
            # 只有名字，没有值 —— 留着是为了接新平台时能看出它用的哪家 WAF
            row.cookie_names = info["cookie_names"]
            row.earliest_expiry = info["earliest_expiry"]
            row.file_mtime = info["file_mtime"]
            row.issues = issues
            row.checked_at = now
            db.add(row)
            db.commit()
            # issuer_region / waf_kind 一并返回：P2-36 的环境指纹要用它们，
            # 而它们正是这次检查刚算出来的 —— 让 worker 再读一遍文件没有意义
            out.append({
                "platform": platform,
                "status": status,
                "issues": issues,
                "issuer_region": info["issuer_region"],
                "waf_kind": info["waf_kind"],
            })
        except Exception:  # noqa: BLE001
            db.rollback()
    return out
