"""``POST /v1/worker/jobs/{id}/result`` 与 ``.../fail``（P2-34 第 2 步）。

采集节点跑完一条 job 之后把结果回传到这里，由 api 落库 —— 节点不碰数据库。

这一档钉的是四件**换成 HTTP 之后才出现**的事：

1. **重复提交不能造出第二条样本。** 节点在大陆家宽、api 在新加坡，
   「结果写成功了但响应没回到节点」是必然会发生的形态，节点重试是对的做法。
   不做幂等，一次网络抖动就多出一条样本，而样本直接进 KPI 分母。
2. **`prompt_text` 由服务端查，不听节点的。** 我们知道自己问了什么，
   让节点回传等于给证据页开了一个可以说谎的口子。
3. **`failure_kind` 要由节点算好带上来。** ``classify_failure`` 的判定顺序是
   「异常类型 → 消息模式」，而**异常类型过不了 HTTP** —— 只传字符串的话，
   ``QianwenLoginRequired`` 这种会退化成靠中文子串猜。
4. **重复提交 fail 不能重复消耗 `attempt`。** 那是重试预算，多扣一次就少试一次。

行为档在 VPS 的一次性 postgres 里跑：

    GEO_TEST_DATABASE_URL="$DATABASE_URL" python -m pytest tests/test_worker_result.py -q
"""
from __future__ import annotations

import json
import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")

#: 一张合法的 1×1 PNG。用真的字节而不是 b"fake" —— 服务端按**魔数**判类型，
#: 只看 content-type 的话节点传什么都能进来
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

PROBE = "__pytest_result__"

behaviour = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


def _purge(session) -> None:
    from sqlalchemy import text

    p = f"{PROBE}%"
    for sql in (
        "DELETE FROM mentions WHERE response_id IN (SELECT r.id FROM raw_responses r JOIN crawl_jobs j ON j.id = r.job_id JOIN prompts pr ON pr.id = j.prompt_id WHERE pr.text LIKE :p)",
        "DELETE FROM citations WHERE response_id IN (SELECT r.id FROM raw_responses r JOIN crawl_jobs j ON j.id = r.job_id JOIN prompts pr ON pr.id = j.prompt_id WHERE pr.text LIKE :p)",
        "DELETE FROM raw_responses WHERE job_id IN (SELECT id FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text LIKE :p))",
        "DELETE FROM crawl_jobs WHERE prompt_id IN (SELECT id FROM prompts WHERE text LIKE :p)",
        "DELETE FROM prompts WHERE text LIKE :p",
        "DELETE FROM brand_aliases WHERE brand_id IN (SELECT id FROM brands WHERE name LIKE :p)",
        "DELETE FROM brands WHERE name LIKE :p",
    ):
        session.execute(text(sql), {"p": p})
    session.commit()


@pytest.fixture
def db():
    from app.core.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        _purge(session)
        session.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def running_job(db):
    """一条已被领走（``running``）的 job —— 回传结果的正常前置状态。"""
    from app.models import Brand, BrandAlias, CrawlJob, Prompt

    brand = Brand(name=f"{PROBE}_安踏", name_en="ANTA", workspace_id=1)
    db.add(brand)
    db.flush()
    db.add(BrandAlias(brand_id=brand.id, alias="安踏体育"))
    prompt = Prompt(brand_id=brand.id, text=f"{PROBE} 国产运动鞋有哪些值得买？", is_active=True)
    db.add(prompt)
    db.flush()
    job = CrawlJob(prompt_id=prompt.id, platform="tongyi", status="running", sample_index=1)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


RESULT = {
    "full_text": "国产运动鞋里安踏值得买，其次是李宁。安踏体育的缓震做得不错。",
    "latency_ms": 27000,
    "citations": [
        {"url": "https://example.com/a", "title": "运动鞋横评", "cite_index": 1},
        {"url": "https://sports.example.cn/b", "title": "安踏评测", "cite_index": 2},
    ],
    "raw_json": {"provider": "qianwen", "match_num": 2},
}


def _post_result(client, job_id, result=None, screenshot=None, filename="shot.png"):
    """回传走 **multipart**：正文在 ``payload`` 这个表单字段里（JSON 字符串），
    截图是可选的第二个 part。截图关掉时就只有 payload 一个字段。"""
    data = {"payload": json.dumps(result if result is not None else RESULT)}
    files = (
        {"screenshot": (filename, screenshot, "image/png")} if screenshot is not None else None
    )
    return client.post(f"/v1/worker/jobs/{job_id}/result", data=data, files=files)


def _count_responses(db, job_id: int) -> int:
    from sqlalchemy import func, select

    from app.models import RawResponse

    return int(db.scalar(select(func.count(RawResponse.id)).where(RawResponse.job_id == job_id)))


# ─────────────────────────────────────────────────────────────────────────
# 一、回传成功结果
# ─────────────────────────────────────────────────────────────────────────


@behaviour
def test_result_creates_sample_and_marks_job_success(client, db, running_job):
    r = _post_result(client, running_job.id)

    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == running_job.id
    assert body["response_id"] is not None

    db.expire_all()
    assert db.get(type(running_job), running_job.id).status == "success"


@behaviour
def test_result_stores_the_answer_and_citations(client, db, running_job):
    from app.models import Citation, RawResponse

    rid = _post_result(client, running_job.id).json()["response_id"]

    db.expire_all()
    resp = db.get(RawResponse, rid)
    assert resp.full_text == RESULT["full_text"]
    assert resp.latency_ms == 27000
    assert resp.platform == "tongyi"

    from sqlalchemy import select

    cites = list(db.scalars(select(Citation).where(Citation.response_id == rid)).all())
    assert len(cites) == 2
    # domain 没传时由 url 推出来 —— 与隧道模式的 _persist_result 同一套口径
    assert {c.domain for c in cites} == {"example.com", "sports.example.cn"}


@behaviour
def test_result_uses_server_side_prompt_text(client, db, running_job):
    """**我们知道自己问了什么**，不听节点的 —— 证据页不能有一个可以说谎的口子。"""
    from app.models import RawResponse

    payload = dict(RESULT, prompt_text="这不是我们问的问题")
    rid = _post_result(client, running_job.id, result=payload).json()["response_id"]

    db.expire_all()
    assert db.get(RawResponse, rid).prompt_text == f"{PROBE} 国产运动鞋有哪些值得买？"


@behaviour
def test_result_runs_l1_annotation(client, db, running_job):
    """样本落库但没标注 = 前端只能显示「未标注」。L1 必须在这一步跑掉。"""
    from sqlalchemy import func, select

    from app.models import Mention, RawResponse

    rid = _post_result(client, running_job.id).json()["response_id"]

    db.expire_all()
    assert db.get(RawResponse, rid).answer_status is not None
    assert int(db.scalar(select(func.count(Mention.id)).where(Mention.response_id == rid))) > 0


@behaviour
def test_result_resubmit_does_not_create_a_second_sample(client, db, running_job):
    """**这条是本步最重要的。**

    节点在大陆家宽、api 在新加坡：「库里写成功了但 200 没回到节点」是必然会发生的，
    而节点重试是对的做法。不幂等的话一次抖动就多一条样本，直接污染 KPI 分母。
    """
    first = _post_result(client, running_job.id).json()
    second = _post_result(client, running_job.id).json()

    assert first["response_id"] == second["response_id"]
    db.expire_all()
    assert _count_responses(db, running_job.id) == 1


@behaviour
def test_result_on_missing_job_is_404(client, db):
    assert _post_result(client, 99999999).status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# 一之二、截图（P2-34 第 4 步）
# ─────────────────────────────────────────────────────────────────────────
#
# 迁到大陆节点之后截图一直是关着的（`SCREENSHOT_DIR=` 置空）：截图写在节点本地，
# 而 api 在 VPS，留着只会让证据页 404。随结果传回来之后这笔债才还上。


@pytest.fixture
def shots_dir(tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@behaviour
def test_screenshot_lands_on_disk_and_is_served_back(client, db, running_job, shots_dir):
    """**第 4 步的验收就是这条**：证据页那个「查看截图」按钮重新出现。

    只断言「文件写下来了」不够 —— 真正要成立的是「api 能把它端回去」，
    那条路径（`/v1/media/screenshots/{basename}`）另有归属校验和 basename 约束。
    """
    from app.models import RawResponse

    rid = _post_result(client, running_job.id, screenshot=PNG_1X1).json()["response_id"]

    db.expire_all()
    name = db.get(RawResponse, rid).screenshot_path
    assert name, "screenshot_path 空 = 证据页仍然不显示按钮"
    assert (shots_dir / name).is_file()

    served = client.get(f"/v1/media/screenshots/{name}")
    assert served.status_code == 200
    assert served.content == PNG_1X1
    # 需要鉴权的证据文件不能被 CDN 缓存到边缘（URL 以 .png 结尾）
    assert "no-store" in served.headers["cache-control"]


@behaviour
def test_result_without_screenshot_is_still_a_clean_degrade(client, db, running_job, shots_dir):
    """截图是可选 part。没有它照样落样本，`screenshot_path` 留空 ——
    证据页那个按钮是条件渲染的，**降级是干净的，不会 404**。"""
    from app.models import RawResponse

    rid = _post_result(client, running_job.id).json()["response_id"]

    db.expire_all()
    assert db.get(RawResponse, rid).screenshot_path is None
    assert list(shots_dir.iterdir()) == []


@behaviour
def test_screenshot_filename_is_generated_server_side(client, db, running_job, shots_dir):
    """**绝不使用节点给的文件名。** 它会被直接拼进落盘路径与取图 URL。"""
    from app.models import RawResponse

    rid = _post_result(
        client, running_job.id, screenshot=PNG_1X1, filename="../../../etc/passwd.png"
    ).json()["response_id"]

    db.expire_all()
    name = db.get(RawResponse, rid).screenshot_path
    assert "/" not in name and ".." not in name
    assert str(running_job.id) in name  # 服务端按 job 命名，看得出是哪条
    assert [p.name for p in shots_dir.iterdir()] == [name]


@behaviour
def test_a_file_that_is_not_a_png_is_rejected(client, db, running_job, shots_dir):
    """按**魔数**判，不信 content-type —— 后者是节点随口说的。"""
    r = _post_result(client, running_job.id, screenshot=b"<?php echo 1; ?>")

    assert r.status_code == 415
    assert _count_responses(db, running_job.id) == 0
    assert list(shots_dir.iterdir()) == []


@behaviour
def test_an_oversized_screenshot_is_rejected(client, db, running_job, shots_dir, monkeypatch):
    """没有上限 = 一个跑飞的节点能把 VPS 的盘写满，而那块盘上还有数据库。"""
    from app.core.config import get_settings

    monkeypatch.setenv("SCREENSHOT_MAX_BYTES", "1024")
    get_settings.cache_clear()

    r = _post_result(client, running_job.id, screenshot=PNG_1X1 + b"\x00" * 4096)

    assert r.status_code == 413
    assert _count_responses(db, running_job.id) == 0
    assert list(shots_dir.iterdir()) == []


# ─────────────────────────────────────────────────────────────────────────
# 二、回传失败
# ─────────────────────────────────────────────────────────────────────────


@behaviour
def test_fail_records_reason_and_kind(client, db, running_job):
    r = client.post(
        f"/v1/worker/jobs/{running_job.id}/fail",
        json={"reason": "等答案超时：正文 0 字符", "kind": "timeout"},
    )

    assert r.status_code == 200
    db.expire_all()
    job = db.get(type(running_job), running_job.id)
    assert job.failure_kind == "timeout"
    assert "正文 0 字符" in job.error_message


@behaviour
def test_fail_trusts_the_kind_the_node_computed(client, db, running_job):
    """``classify_failure`` 的判定顺序是「异常类型 → 消息模式」，而**类型过不了 HTTP**。

    所以分类在节点上算（它手里有异常对象），这里只校验取值合法。
    一条纯英文的登录墙报错，光靠消息模式会掉进 unknown；带上 kind 就不会。
    """
    client.post(
        f"/v1/worker/jobs/{running_job.id}/fail",
        json={"reason": "session invalid", "kind": "login_required"},
    )

    db.expire_all()
    assert db.get(type(running_job), running_job.id).failure_kind == "login_required"


@behaviour
def test_fail_rejects_a_kind_we_do_not_know(client, db, running_job):
    """乱写的 kind 会静默毁掉重试决策与 API 契约 —— 宁可 422 也不写进库。"""
    r = client.post(
        f"/v1/worker/jobs/{running_job.id}/fail",
        json={"reason": "x", "kind": "banana"},
    )

    assert r.status_code == 422
    db.expire_all()
    assert db.get(type(running_job), running_job.id).failure_kind is None


@behaviour
def test_fail_without_kind_falls_back_to_server_side_classification(client, db, running_job):
    """节点是老版本、不带 kind 时不能崩 —— 退回按消息文本分类。"""
    client.post(
        f"/v1/worker/jobs/{running_job.id}/fail",
        json={"reason": "Page.goto: Timeout 120000ms exceeded"},
    )

    db.expire_all()
    assert db.get(type(running_job), running_job.id).failure_kind == "timeout"


@behaviour
def test_fail_resubmit_does_not_double_count_attempt(client, db, running_job):
    """``attempt`` 是重试预算 —— 一次网络抖动多扣一次，就少试一次。"""
    body = {"reason": "boom", "kind": "unknown"}
    client.post(f"/v1/worker/jobs/{running_job.id}/fail", json=body)
    client.post(f"/v1/worker/jobs/{running_job.id}/fail", json=body)

    db.expire_all()
    assert db.get(type(running_job), running_job.id).attempt == 1


@behaviour
def test_fail_on_missing_job_is_404(client, db):
    r = client.post("/v1/worker/jobs/99999999/fail", json={"reason": "x"})
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# 三、鉴权（不需要数据库）
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("suffix", ["result", "fail"])
def test_worker_callbacks_are_not_public(monkeypatch, suffix):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import worker as worker_api
    from app.api.deps import get_db
    from app.core.config import get_settings
    from app.core.security import ApiKeyMiddleware

    monkeypatch.setenv("API_KEY", "test-key-abc123")
    get_settings.cache_clear()

    def _explode():
        raise AssertionError("未认证的请求不该走到数据库")

    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware)
    app.include_router(worker_api.router)
    app.dependency_overrides[get_db] = _explode
    try:
        client = TestClient(app, base_url="https://testserver")
        assert client.post(f"/v1/worker/jobs/1/{suffix}", json={}).status_code == 401
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "fn_name,path",
    [
        ("report_result", "/v1/worker/jobs/{job_id}/result"),
        ("report_failure", "/v1/worker/jobs/{job_id}/fail"),
    ],
)
def test_worker_callbacks_require_write(fn_name, path):
    """顺带钉住路由真的挂上了。

    上面那条 401 的用例**单独证明不了这一点** —— 中间件在路由之前就拦下了，
    一个根本不存在的路径同样会 401。
    """
    import inspect

    from app.api import worker as worker_api

    assert path in {r.path for r in worker_api.router.routes}
    assert "require_write" in inspect.getsource(getattr(worker_api, fn_name))


# ─────────────────────────────────────────── 四、联网标注 search_used（P2-37）
#
# §4.0.1 拍板的口径是「**记录 search 是否激活；无搜索输出是结果，不是废样本**」。
# 所以它要能分桶报告，而分桶的前提是三态分得开：
#
#   True  = 这次联网了      False = 确认没联网      None = 我们不知道
#
# **None 和 False 混起来就是把「没记」说成「没联网」** —— 老样本、别的平台、
# 解析失败全都会落在 None 上，把它们算进「没联网」那一桶，报告里就多一条假结论。
# 一个 `or False` 或者一句 `bool(x)` 就够把三态压成两态，而且不会报错。


@behaviour
@pytest.mark.parametrize("value", [True, False, None])
def test_search_used_survives_the_whole_round_trip(client, db, running_job, value):
    """provider → HTTP → 库 → 读回来，三个取值都要原样活着。"""
    from app.models import RawResponse

    rid = _post_result(
        client, running_job.id, result=dict(RESULT, search_used=value)
    ).json()["response_id"]

    db.expire_all()
    assert db.get(RawResponse, rid).search_used is value


@behaviour
def test_search_used_defaults_to_unknown_not_to_false(client, db, running_job):
    """老版本节点不带这个字段时必须是 `None` —— 默认成 False 等于凭空断言没联网。"""
    from app.models import RawResponse

    payload = {k: v for k, v in RESULT.items()}
    rid = _post_result(client, running_job.id, result=payload).json()["response_id"]

    db.expire_all()
    assert db.get(RawResponse, rid).search_used is None


@behaviour
def test_search_used_is_exposed_on_the_response_api(client, db, running_job):
    """报告要按它分桶，取不到就等于没做。"""
    rid = _post_result(
        client, running_job.id, result=dict(RESULT, search_used=True)
    ).json()["response_id"]

    body = client.get(f"/v1/responses/{rid}").json()
    assert body["search_used"] is True
