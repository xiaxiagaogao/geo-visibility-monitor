"""采集环境指纹（P2-36）。纯函数，不需要数据库也不需要网络。"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.crawl_env import (
    FINGERPRINT_FIELDS,
    compute_fingerprint,
    describe_environment,
    probe_exit_ip,
)

CN = {
    "node_label": "changsha-home",
    "exit_ip": "120.228.64.174",
    "timezone_id": "Asia/Shanghai",
    "crawl_mode": "real",
    "credential_region": "cn",
    "waf_kind": "huawei",
}


def test_fingerprint_is_readable_not_hashed():
    """排查时一眼要看出两种环境差在哪。一串 sha256 还得去查表。"""
    assert compute_fingerprint(CN) == (
        "changsha-home|120.228.64.174|Asia/Shanghai|real|cn|huawei"
    )


def test_same_environment_same_fingerprint():
    assert compute_fingerprint(CN) == compute_fingerprint(dict(CN))


@pytest.mark.parametrize("field", FINGERPRINT_FIELDS)
def test_any_dimension_change_makes_a_new_environment(field):
    """**每一维都要能把环境区分开。**

    2026-08-15 那次事故里变的是 `credential_region` 与 `timezone_id` ——
    只认 `node_label` 的话，那次换环境在数据上完全看不出来。
    """
    other = dict(CN, **{field: "CHANGED"})
    assert compute_fingerprint(other) != compute_fingerprint(CN)


def test_missing_dimension_is_a_dash_not_omitted():
    """「没探到 IP」和「IP 是空串」不能归成同一种环境；
    省略那一段还会让不同环境凑巧拼出同一个指纹。"""
    fp = compute_fingerprint(dict(CN, exit_ip=None))
    assert fp == "changsha-home|-|Asia/Shanghai|real|cn|huawei"
    assert compute_fingerprint(dict(CN, exit_ip="")) == fp


def test_pipe_in_a_value_cannot_forge_a_field():
    """值里带分隔符会把一段拆成两段，让两个不同环境撞成同一个指纹。"""
    fp = compute_fingerprint(dict(CN, node_label="a|b"))
    assert fp.count("|") == len(FINGERPRINT_FIELDS) - 1


def test_describe_environment_reads_settings():
    s = Settings(crawl_node_label="vps-sg", crawl_timezone_id="Asia/Singapore", crawl_mode="real")
    f = describe_environment(s, credential_region="overseas", waf_kind="aws", exit_ip="1.2.3.4")

    assert f["node_label"] == "vps-sg"
    assert f["timezone_id"] == "Asia/Singapore"
    assert f["credential_region"] == "overseas"
    assert f["fingerprint"] == "vps-sg|1.2.3.4|Asia/Singapore|real|overseas|aws"


def test_cold_standby_is_a_different_environment_than_the_node():
    """切冷备 = 换环境。这条钉的是「三样一起改」在数据上真的能被看出来。"""
    node = describe_environment(
        Settings(crawl_node_label="changsha-home", crawl_timezone_id="Asia/Shanghai"),
        credential_region="cn", waf_kind="huawei", exit_ip="120.228.64.174",
    )
    standby = describe_environment(
        Settings(crawl_node_label="vps-sg", crawl_timezone_id="Asia/Singapore"),
        credential_region="overseas", waf_kind="aws", exit_ip="96.9.213.230",
    )
    assert node["fingerprint"] != standby["fingerprint"]


def test_probe_never_raises_on_network_failure(monkeypatch):
    """健康探测自己不能成为故障源 —— 它跑在采集循环里。"""
    import urllib.request

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert probe_exit_ip(timeout=0.1) is None


def test_probe_rejects_a_non_ip_body(monkeypatch):
    """探测端点返回一页 HTML（被劫持、门户认证）时不能把它当 IP 记下来。"""
    import urllib.request

    class _Resp:
        def read(self):
            return b"<html>captive portal</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert probe_exit_ip() is None
