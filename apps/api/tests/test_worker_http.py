"""采集节点侧的 HTTP 模式（P2-34 第 5 步）。**不需要数据库，也不需要网络。**

节点侧的代码在本仓里最难验 —— 它跑在别人家的机器上、要拉起 Chromium、
还要打网络。所以这一档刻意把三件事拆开，只留能在本机跑的那部分：

| 能在这儿验 | 怎么验 |
|---|---|
| 请求怎么拼（multipart / JSON 序列化） | 纯函数，直接比字节 |
| 一条 job 的成功/失败流程 | `crawl_mode=fake` 走 FakeProvider（不拉 Chromium）+ 一个假的 client |
| **失败分类在节点侧算** | 真的抛一个异常，看上报的 `kind` 对不对 |

| 不在这儿验 | 在哪儿 |
|---|---|
| 端点行为 | `test_worker_{lease,result,selfreport}.py`（VPS 真库） |
| 真的能不能抓到答案 | 只能在采集节点上跑真 run |

⚠️ **本文件绝不能 import 会拉起 playwright 的东西** —— 本机 venv 有它，
api 容器没有，那样会「本机全绿、VPS 挂掉」。走 fake 模式就绕开了。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.worker_http import WorkerClient, build_multipart, process_leased_job


class _Settings:
    """够 build_provider + run_with_timeout 用的最小 settings。"""

    def __init__(self, crawl_mode="fake"):
        self.crawl_mode = crawl_mode
        self.crawl_timeout_ms = 1000
        self.playwright_headless = True
        self.crawl_timezone_id = "Asia/Shanghai"
        self.screenshot_dir = ""
        for p in ("deepseek", "doubao", "tongyi"):
            setattr(self, f"{p}_storage_state", "")
            setattr(self, f"{p}_user_data_dir", "")
            setattr(self, f"{p}_delete_session", True)


class FakeClient:
    """记下节点「说了什么」，不发任何请求。

    用一个真对象而不是 mock 库：断言的是**上报的内容**，
    不是「某个方法被调了几次」。
    """

    def __init__(self):
        self.results = []
        self.failures = []

    def report_result(self, job_id, result, screenshot=None):
        self.results.append((job_id, result, screenshot))
        return {"job_id": job_id, "response_id": 1, "status": "success"}

    def report_failure(self, job_id, reason, kind):
        self.failures.append((job_id, reason, kind))
        return {"id": job_id, "status": "failed"}


JOB = {
    "job_id": 3512,
    "platform": "tongyi",
    "sample_index": 1,
    "prompt_id": 88,
    "prompt_text": "国产运动鞋品牌有哪些值得买的？",
    "brand_names": ["安踏", "ANTA"],
}


# ─────────────────────────────────────────────────────────────────────────
# 一、跑一条 job
# ─────────────────────────────────────────────────────────────────────────


def test_a_successful_job_is_reported_as_a_result():
    client = FakeClient()

    outcome = process_leased_job(client, _Settings(), JOB)

    assert outcome == "success"
    assert client.failures == []
    job_id, result, _ = client.results[0]
    assert job_id == 3512
    assert result.full_text  # FakeProvider 造的正文
    assert result.platform == "tongyi"


def test_the_prompt_that_gets_asked_is_the_one_that_was_leased():
    """节点只有 lease 回来的那段文字 —— 它必须就是真正被问出去的那句。"""
    client = FakeClient()

    process_leased_job(client, _Settings(), JOB)

    assert client.results[0][1].prompt == JOB["prompt_text"]


def test_a_failing_job_is_reported_with_a_kind_computed_on_the_node():
    """**这条是节点侧存在的理由之一。**

    `classify_failure` 的判定顺序是「异常类型 → 消息模式 → unknown」，
    而**异常类型过不了 HTTP**。所以分类必须在这儿算 —— 这里手里还有异常对象。

    用 kimi 触发：real 模式下它没有 Provider，`build_provider` 抛 RuntimeError，
    分类应落在 `platform_unavailable` 而不是 `unknown`。
    """
    client = FakeClient()

    outcome = process_leased_job(client, _Settings(crawl_mode="real"), dict(JOB, platform="kimi"))

    assert outcome == "failed"
    assert client.results == []
    job_id, reason, kind = client.failures[0]
    assert job_id == 3512
    assert kind == "platform_unavailable"
    assert "kimi" in reason


def test_one_bad_job_does_not_take_down_the_loop():
    """一条 job 炸了不能让整轮挂掉 —— 后面那些还等着跑。"""
    client = FakeClient()

    process_leased_job(client, _Settings(crawl_mode="real"), dict(JOB, platform="kimi"))
    process_leased_job(client, _Settings(), JOB)

    assert len(client.failures) == 1 and len(client.results) == 1


# ─────────────────────────────────────────────────────────────────────────
# 二、请求怎么拼
# ─────────────────────────────────────────────────────────────────────────


def test_multipart_carries_payload_and_screenshot():
    body, ctype = build_multipart({"full_text": "答案"}, b"\x89PNG\r\n\x1a\nDATA")

    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="payload"' in body
    assert b'name="screenshot"' in body
    assert b"\x89PNG\r\n\x1a\nDATA" in body
    assert "答案".encode() in body


def test_multipart_omits_the_screenshot_part_when_there_is_none():
    """截图关着时不能带一个空 part —— 服务端会把它当成一个 0 字节的文件，
    按魔数判定直接 415，整条结果跟着丢。"""
    body, _ = build_multipart({"full_text": "答案"}, None)

    assert b'name="payload"' in body
    assert b'name="screenshot"' not in body


def test_boundary_does_not_collide_with_the_payload():
    """分隔符要是恰好出现在正文里，整个 body 就被解析错了。"""
    body, ctype = build_multipart({"full_text": "----geo234 边界"}, None)

    boundary = ctype.split("boundary=")[1]
    assert body.count(boundary.encode()) == 2  # 只有开头那条和结尾那条


def test_credential_payload_serialises_datetimes_and_hides_values():
    """`collect_reports` 给的是 datetime 对象，JSON 塞不进去 —— 要转 ISO。"""
    items = [{
        "platform": "tongyi", "status": "ok", "node_label": "changsha",
        "issuer_region": "unknown", "waf_kind": "none", "cookie_count": 2,
        "cookie_names": ["cna", "tfstk"],
        "earliest_expiry": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "file_mtime": None, "issues": [],
    }]

    encoded = json.loads(WorkerClient.encode_credentials(items))

    assert encoded["items"][0]["earliest_expiry"].startswith("2026-09-01")
    assert encoded["items"][0]["file_mtime"] is None
    assert "value" not in json.dumps(encoded)


# ─────────────────────────────────────────────────────────────────────────
# 三、配置
# ─────────────────────────────────────────────────────────────────────────


def test_http_mode_is_off_unless_an_api_base_is_configured():
    """**只加不改**：不设 `WORKER_API_BASE` 就还是隧道模式，行为一个字节不变。"""
    from app.worker_http import http_mode_enabled

    assert not http_mode_enabled(_Settings())
    s = _Settings()
    s.worker_api_base = "http://100.64.240.17:8200"
    assert http_mode_enabled(s)


def test_client_refuses_to_start_without_a_key():
    """没有 key 的话每一发都会 401，而节点会把它当成「没活干」静静跑一整夜。"""
    with pytest.raises(ValueError):
        WorkerClient("http://100.64.240.17:8200", "")


def test_blank_database_url_does_not_kill_the_container(monkeypatch):
    """**worker 模式下这台机器没有数据库，而 `DATABASE_URL=` 是最直觉的写法。**

    2026-08-19 在 VPS 上预检新镜像时真撞到了：`app/core/db.py` 在 **import 期**
    就建 engine，而 `create_engine("")` 抛 ArgumentError —— 容器起不来，
    traceback 里一个字都不提 worker 模式，只有一句
    「Could not parse SQLAlchemy URL」。

    修之前更坏的一点是它会和自检对上谎：`deploy.sh verify` 那条
    「容器无数据库凭证」检的是 `^DATABASE_URL=.`（至少一个字符），
    空值照样算「✓ 没有凭证」—— 自检说通过，容器却在后台反复重启。
    修完之后两者都成立：空值不再致命，而「没有凭证」这句话也仍然是真的。
    """
    from app.core import db as db_mod
    from app.core.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        assert db_mod._make_engine() is not None
    finally:
        get_settings.cache_clear()


def test_client_identifies_itself_honestly():
    """请求带一个**诚实**的 User-Agent，不是伪装成浏览器。

    2026-08-21 实测（从采集节点容器里发）：

        走 tailnet                     200 · 0.22s
        走 https://geo.xg22.top 默认UA  **403 error code: 1010**（CF Bot 检查）
        走 https://geo.xg22.top 浏览器UA 200 · 3.0s（慢 14 倍）
        390KB multipart 走 CF           16s

    **所以公网那条路没有采用**：要过去就得让采集器谎称自己是浏览器，
    那是在绕过我们自己域名上的 Bot 保护，而且慢一个数量级。
    将来真要走公网，正确的做法是在 Cloudflare 上给 `/v1/worker/*` 加一条
    WAF skip 规则 —— **在 CF 那边开门，而不是在这边伪装。**

    这个 UA 的价值是让我们的流量在访问日志里认得出来。
    """
    from app.worker_http import USER_AGENT

    assert "geo-crawler" in USER_AGENT
    assert "Mozilla" not in USER_AGENT, "别伪装成浏览器"


def test_the_loop_actually_pauses_when_configured(monkeypatch):
    """纯函数对不代表接上了 —— 这条钉的是「循环真的调了它」。"""
    from app import worker_http

    slept = []
    monkeypatch.setattr(worker_http.time, "sleep", lambda s: slept.append(s))

    s = _Settings()
    s.crawl_pace_min_sec, s.crawl_pace_max_sec = 20.0, 90.0
    worker_http._pause(s)

    assert len(slept) == 1 and 20.0 <= slept[0] <= 90.0


def test_the_loop_does_not_pause_when_off(monkeypatch):
    """**默认必须一秒都不多等** —— 否则「只加不改」就不成立。"""
    from app import worker_http

    slept = []
    monkeypatch.setattr(worker_http.time, "sleep", lambda s: slept.append(s))

    worker_http._pause(_Settings())      # 没配 crawl_pace_*

    assert slept == []
