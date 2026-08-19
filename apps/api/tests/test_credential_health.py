"""登录态健康度（P2-07）。纯函数，不需要数据库。

用例里的 cookie 名**全部抄自两份真实的 storage_state**（2026-08-15 实际对比过）：

- 新加坡导出：`aws-waf-token`（`.deepseek.com`）+ `ds_session_id` / `smidV2` …
- 长沙导出：  `HWWAFSESID` / `HWWAFSESTIME` + `ds_session_id` / `smidV2` …
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.services.credential_health import (
    AGING,
    EXPIRED,
    MISSING,
    OK,
    REGION_MISMATCH,
    REGION_UNKNOWN,
    classify_waf,
    derive_status,
    inspect_storage_state,
    worse_of,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

SG_COOKIES = ["ds_session_id", "aws-waf-token", "smidV2", ".thumbcache_6b2e"]
CN_COOKIES = ["smidV2", ".thumbcache_6b2e", "HWWAFSESTIME", "HWWAFSESID", "ds_session_id"]


def _write(tmp_path, cookies, mtime=None):
    """cookies: [(name, domain, expires_ts_or_0)]"""
    p = tmp_path / "storage_state.json"
    p.write_text(
        json.dumps(
            {
                "cookies": [
                    {"name": n, "domain": d, "expires": e, "value": "SECRET-绝不该被读出来"}
                    for n, d, e in cookies
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    if mtime:
        os.utime(p, (mtime.timestamp(), mtime.timestamp()))
    return str(p)


# ----------------------------------------------------------------- WAF 识别


def test_aws_waf_means_overseas():
    """这正是 2026-08-15 那份从新加坡导出的登录态。"""
    assert classify_waf(SG_COOKIES) == ("aws", "overseas")


def test_huawei_waf_means_mainland():
    assert classify_waf(CN_COOKIES) == ("huawei", "cn")


def test_waf_detection_is_case_insensitive():
    """cookie 名的大小写不该成为判断失效的原因。"""
    assert classify_waf(["hwwafsesid"]) == ("huawei", "cn")
    assert classify_waf(["HWWAFSESID"]) == ("huawei", "cn")


def test_no_waf_cookie_is_unknown_not_a_guess():
    """认不出来就说认不出来。猜一个签发地会让后面的判级凭空产生结论。"""
    assert classify_waf(["ds_session_id", "smidV2"]) == ("none", REGION_UNKNOWN)


# --------------------------------------------------------------- 文件检查


def test_inspect_never_exposes_cookie_values(tmp_path):
    """**这条是硬规矩**：值是凭证本身，落进库或日志就等于把登录态复制了一份。"""
    path = _write(tmp_path, [("ds_session_id", "chat.deepseek.com", 0)])
    info = inspect_storage_state(path)
    assert "SECRET-绝不该被读出来" not in json.dumps(info, default=str)


def test_inspect_reads_metadata(tmp_path):
    exp = int(datetime(2027, 9, 4, tzinfo=timezone.utc).timestamp())
    path = _write(tmp_path, [("HWWAFSESID", "chat.deepseek.com", 0), ("smidV2", "chat.deepseek.com", exp)])
    info = inspect_storage_state(path)

    assert info["exists"] and info["cookie_count"] == 2
    assert info["cookie_names"] == ["HWWAFSESID", "smidV2"]
    assert info["issuer_region"] == "cn"
    assert info["earliest_expiry"].year == 2027


def test_session_cookies_do_not_count_as_earliest_expiry(tmp_path):
    """会话 cookie 随浏览器关闭失效，和「令牌到期」是两回事。
    把它们算进「最早过期」会让每份登录态都显示成 1970 年过期。"""
    path = _write(tmp_path, [("ds_session_id", "chat.deepseek.com", 0)])
    assert inspect_storage_state(path)["earliest_expiry"] is None


@pytest.mark.parametrize("bad", [None, "", "/nonexistent/nope.json"])
def test_inspect_never_raises(bad):
    """健康检查自己不能成为故障源。"""
    info = inspect_storage_state(bad)
    assert info["exists"] is False and info["parse_error"]


def test_unparseable_file_is_reported_not_raised(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ not json", encoding="utf-8")
    info = inspect_storage_state(str(p))
    assert info["exists"] and "合法 JSON" in info["parse_error"]


# ----------------------------------------------------------------- 判级


def _info(**over):
    base = {
        "exists": True,
        "parse_error": None,
        "issuer_region": "cn",
        "waf_kind": "huawei",
        "earliest_expiry": NOW + timedelta(days=300),
        "file_mtime": NOW - timedelta(days=1),
    }
    base.update(over)
    return base


def test_healthy_credential():
    assert derive_status(_info(), expected_region="cn", max_age_days=14, now=NOW) == (OK, [])


def test_the_2026_08_15_incident_is_caught(tmp_path):
    """**这条是这个模块存在的理由。**

    从新加坡导出、AWS WAF、已过期 11 天 —— 而当时「上次成功抓取」一直是几分钟前，
    任何基于「多久没成功」的告警都不会响。
    """
    info = _info(
        issuer_region="overseas",
        waf_kind="aws",
        earliest_expiry=NOW - timedelta(days=11),
    )
    status, issues = derive_status(info, expected_region="cn", max_age_days=14, now=NOW)

    assert status == REGION_MISMATCH          # 最严重的那一档
    assert len(issues) == 2                   # 但两个问题都列出来了
    assert any("签发地" in i for i in issues)
    assert any("已过期 11 天" in i for i in issues)


def test_expired_only():
    info = _info(earliest_expiry=NOW - timedelta(days=3))
    status, issues = derive_status(info, expected_region="cn", max_age_days=14, now=NOW)
    assert status == EXPIRED and "已过期 3 天" in issues[0]


def test_aging_file_is_a_nudge_not_a_failure():
    info = _info(file_mtime=NOW - timedelta(days=30))
    status, issues = derive_status(info, expected_region="cn", max_age_days=14, now=NOW)
    assert status == AGING and "30 天没更新" in issues[0]


def test_missing_file_wins_over_everything():
    status, issues = derive_status(
        {"exists": False, "parse_error": "文件不存在或为空"},
        expected_region="cn", max_age_days=14, now=NOW,
    )
    assert status == MISSING


def test_unknown_issuer_never_reports_mismatch():
    """认不出签发地时**不报不匹配** —— 宁可不报，也不要报一个我们并不确定的结论。
    否则接豆包（WAF 未知）第一天就会看到一片红。"""
    info = _info(issuer_region=REGION_UNKNOWN, waf_kind="none")
    assert derive_status(info, expected_region="cn", max_age_days=14, now=NOW)[0] == OK


def test_expected_region_unset_disables_the_check():
    """VPS 冷备切过去时出口变新加坡；不想判就把期望置空，而不是被迫看假告警。"""
    info = _info(issuer_region="overseas", waf_kind="aws")
    assert derive_status(info, expected_region="", max_age_days=14, now=NOW)[0] == OK


def test_max_age_zero_disables_the_age_check():
    info = _info(file_mtime=NOW - timedelta(days=999))
    assert derive_status(info, expected_region="cn", max_age_days=0, now=NOW)[0] == OK


def test_worse_of_picks_the_more_severe():
    assert worse_of(OK, EXPIRED) == EXPIRED
    assert worse_of(REGION_MISMATCH, EXPIRED) == REGION_MISMATCH
    assert worse_of(MISSING, REGION_MISMATCH) == MISSING
    assert worse_of(OK, OK) == OK


# ------------------------------------------------- 采集节点侧的收集（P2-34）
#
# HTTP worker 模式下，判级仍然在**节点**上算（storage_state 文件在那儿，
# api 读不到），只是结果改成 POST 上报而不是直接写库。
# 所以「读文件 + 判级」这一段必须能脱离数据库单独跑。


class _Settings:
    def __init__(self, **kw):
        self.crawl_node_label = "changsha-home"
        self.crawl_expected_credential_region = "cn"
        self.crawl_credential_max_age_days = 0
        self.deepseek_storage_state = ""
        self.doubao_storage_state = ""
        self.tongyi_storage_state = ""
        for k, v in kw.items():
            setattr(self, k, v)


def test_collect_reports_needs_no_database(tmp_path):
    """节点没有数据库 —— 这一段必须能自己跑完。"""
    import inspect

    from app.services.credential_health import collect_reports

    assert "db" not in inspect.signature(collect_reports).parameters

    path = _write(tmp_path, [("HWWAFSESID", "chat.deepseek.com", 0)])
    rows = collect_reports(_Settings(deepseek_storage_state=path))

    ds = {r["platform"]: r for r in rows}["deepseek"]
    assert ds["issuer_region"] == "cn"
    assert ds["waf_kind"] == "huawei"
    assert ds["node_label"] == "changsha-home"
    assert ds["cookie_names"] == ["HWWAFSESID"]


def test_collect_reports_covers_every_platform_even_unconfigured(tmp_path):
    """没配登录态的平台也要报 —— `missing` 是结论，漏报是沉默。"""
    from app.services.credential_health import MISSING, collect_reports

    rows = {r["platform"]: r for r in collect_reports(_Settings())}

    assert set(rows) == {"deepseek", "doubao", "tongyi"}
    assert all(r["status"] == MISSING for r in rows.values())


def test_collect_reports_never_carries_a_cookie_value(tmp_path):
    """红线：上报的东西里不能有值 —— 它接下来要走一条 HTTP 链路。"""
    from app.services.credential_health import collect_reports

    path = _write(tmp_path, [("ds_session_id", "chat.deepseek.com", 0)])
    rows = collect_reports(_Settings(deepseek_storage_state=path))

    assert "SECRET-绝不该被读出来" not in repr(rows)
