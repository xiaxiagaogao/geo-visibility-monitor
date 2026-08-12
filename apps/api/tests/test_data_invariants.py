"""L1 冒烟：**在真实数据上**验那几条不变量（需要真实 Postgres）。

和其它测试的分工：

- 单元测试验「函数在造出来的输入上对不对」——输入是我们自己写的，
  所以它验不到「真实数据长得跟我们以为的不一样」。
- 这一组把**库里现有的全部数据**过一遍。它抓的是数据漂移：
  标注器改了口径、某次抓取写坏了、迁移漏了一批行。

**只读。** 不建任何行、不改任何行，所以可以直接指向生产库跑。

**不硬编码任何 id。** 早期版本会写「task 27 应该有 35 条」——
那种断言在数据被清或重抓之后会假红，红几次就没人看了。
这里一律从库里现取，没有数据就 skip。
"""
from __future__ import annotations

import os

import pytest

TEST_DB = os.environ.get("GEO_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="需要 GEO_TEST_DATABASE_URL 指向真实 Postgres"
)


@pytest.fixture(scope="module")
def db():
    from app.core.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()  # 只读，但保证不留下事务
        s.close()


@pytest.fixture(scope="module")
def latest_run_with_data(db):
    """最近一次真的产出了响应的 run。没有就 skip 整组。"""
    from sqlalchemy import select

    from app.models import CrawlJob, RawResponse, Run

    run = db.scalars(
        select(Run)
        .join(CrawlJob, CrawlJob.run_id == Run.id)
        .join(RawResponse, RawResponse.job_id == CrawlJob.id)
        .order_by(Run.id.desc())
        .limit(1)
    ).first()
    if run is None:
        pytest.skip("库里还没有产出过响应的 run")
    return run


# ══════ 一、高亮的那条不变量（API.md §7.1）══════


def test_first_offset_slices_back_to_matched_term(db):
    """``full_text[first_offset : +len(matched_term)] == matched_term``

    **这是全库扫描，不是抽样。** 证据页的高亮完全建立在这条上 ——
    它一旦不成立，页面不会报错，只会把底色画在错误的字上，
    而用户会拿那段错的原文去跟客户解释结论。

    前端有 14 条单测验这个函数，但那些用的是我们自己造的输入。
    只有在全量真实数据上跑一遍，才验得到标注器有没有漂。
    """
    from sqlalchemy import select

    from app.models import Mention, RawResponse

    rows = db.execute(
        select(
            Mention.id,
            Mention.brand_id,
            Mention.first_offset,
            Mention.matched_term,
            RawResponse.id,
            RawResponse.full_text,
        )
        .join(RawResponse, RawResponse.id == Mention.response_id)
        .where(Mention.first_offset.is_not(None), Mention.matched_term.is_not(None))
    ).all()

    if not rows:
        pytest.skip("库里还没有带 first_offset 的命中")

    bad = []
    for mid, brand_id, offset, term, resp_id, full_text in rows:
        actual = (full_text or "")[offset : offset + len(term)]
        if actual != term:
            bad.append(
                f"mention {mid}（brand {brand_id} / response {resp_id}）"
                f" offset={offset} 标注「{term}」实际「{actual}」"
            )

    assert not bad, f"{len(bad)}/{len(rows)} 条命中对不上：\n" + "\n".join(bad[:10])


def test_citation_only_has_no_position_rank(db):
    """引用里命中 = 正文没出现，**没有出场位置**，所以 rank 必须是 NULL。

    写成「排最后」会让证据页把一个没出现在正文里的品牌报成第 N 名。
    """
    from sqlalchemy import select

    from app.models import Mention

    bad = db.scalars(
        select(Mention.id).where(
            Mention.mention_type == "citation_only",
            Mention.position_rank.is_not(None),
        )
    ).all()
    assert not bad, f"citation_only 却有 position_rank 的 mention: {list(bad)[:10]}"


def test_body_hit_ranks_are_dense_within_response(db):
    """同一条响应里，正文命中的 rank 必须是从 1 开始的连续整数。

    rank 是「在被监测品牌里第几个出场」，跳号意味着排名时漏了谁 ——
    而首位提及率的分子正是 rank == 1 的条数。
    """
    from collections import defaultdict

    from sqlalchemy import select

    from app.models import Mention

    by_resp: dict[int, list[int]] = defaultdict(list)
    for resp_id, rank in db.execute(
        select(Mention.response_id, Mention.position_rank).where(
            Mention.position_rank.is_not(None)
        )
    ).all():
        by_resp[resp_id].append(rank)

    if not by_resp:
        pytest.skip("库里还没有带 position_rank 的命中")

    bad = [
        f"response {rid}: {sorted(ranks)}"
        for rid, ranks in by_resp.items()
        if sorted(ranks) != list(range(1, len(ranks) + 1))
    ]
    assert not bad, "rank 不连续：\n" + "\n".join(bad[:10])


# ══════ 二、counts 的内部一致性 ══════


def _counts(db, brand_id: int, run_id: int, group_by: str = "none"):
    from app.services.counts import compute_counts

    return compute_counts(db, brand_id=brand_id, run_id=run_id, group_by=group_by)


@pytest.fixture(scope="module")
def run_ctx(db, latest_run_with_data):
    """(run, brand_id) —— counts 要的两个参数。"""
    from app.models import Task

    task = db.get(Task, latest_run_with_data.task_id)
    return latest_run_with_data, task.brand_id


def test_m_first_never_exceeds_m_mentioned(db, run_ctx):
    """前端拿 m_first / m_mentioned 当比率 —— 分子大于分母会出现 >100%。"""
    run, brand_id = run_ctx
    out = _counts(db, brand_id, run.id)
    for bc in [out["brand"], *out["competitors"]]:
        assert bc.get("m_first", 0) <= bc["m_mentioned"], (
            f"brand {bc['brand_id']}: m_first={bc.get('m_first')} > "
            f"m_mentioned={bc['m_mentioned']}"
        )


def test_m_mentioned_never_exceeds_n_valid(db, run_ctx):
    """提及率的分母是 n_valid。分子超过它就是 >100% 的提及率。"""
    run, brand_id = run_ctx
    out = _counts(db, brand_id, run.id)
    n_valid = out["denominator"]["n_valid"]
    for bc in [out["brand"], *out["competitors"]]:
        assert bc["m_mentioned"] <= n_valid, (
            f"brand {bc['brand_id']}: m_mentioned={bc['m_mentioned']} > n_valid={n_valid}"
        )


def test_series_denominators_sum_to_overall(db, run_ctx):
    """逐提问的 n_valid 之和 == 总的 n_valid。

    对不上意味着有样本落在了任何一个 prompt 分组之外 ——
    那种样本在矩阵里一行都不占，却算进了 KPI 的分母。
    """
    run, brand_id = run_ctx
    out = _counts(db, brand_id, run.id, group_by="prompt")
    total = sum(b["denominator"]["n_valid"] for b in out["series"])
    assert total == out["denominator"]["n_valid"]


def test_series_keys_are_all_in_run_snapshot(db, run_ctx):
    """``group_by=prompt`` 的 key 必须都能在 run 的提问快照里找到。

    矩阵的行源是快照、数据源是 series，两者靠 key 关联。
    series 里出现快照没有的 key，那一格的数就无处可放 —— 会被静默丢掉。
    """
    from sqlalchemy import select

    from app.models import RunPrompt

    run, brand_id = run_ctx
    snapshot = {
        str(pid)
        for pid in db.scalars(
            select(RunPrompt.prompt_id).where(RunPrompt.run_id == run.id)
        ).all()
    }
    if not snapshot:
        pytest.skip("这次 run 没有提问快照（迁移前的老数据）")

    out = _counts(db, brand_id, run.id, group_by="prompt")
    extra = {b["key"] for b in out["series"]} - snapshot
    assert not extra, f"series 里有快照中不存在的 prompt_id: {sorted(extra)}"


def test_counts_competitors_match_run_snapshot(db, run_ctx):
    """带 run_id 时竞品集必须取自快照，不是当前的 CompetitorLink。

    这条是「两次 run 之间的差异可信」的地基：不成立的话，
    今天给品牌加一个竞品，上个月那次 run 的缺口清单会当场重算。
    """
    from sqlalchemy import select

    from app.models import RunCompetitor

    run, brand_id = run_ctx
    snapshot = set(
        db.scalars(
            select(RunCompetitor.competitor_brand_id).where(RunCompetitor.run_id == run.id)
        ).all()
    )
    if not snapshot:
        pytest.skip("这次 run 没有竞品快照（迁移前的老数据）")

    out = _counts(db, brand_id, run.id)
    assert {c["brand_id"] for c in out["competitors"]} == snapshot


def test_denominator_buckets_sum_to_total(db, run_ctx):
    """五个分状态计数之和 == n_total_responses。

    对不上说明有 answer_status 落在已知枚举之外 —— 那种样本既不进分母、
    也不出现在任何一档里，等于凭空消失。
    """
    run, brand_id = run_ctx
    d = _counts(db, brand_id, run.id)["denominator"]
    parts = d["n_valid"] + d["n_empty"] + d["n_too_short"] + d["n_error"] + d["n_unannotated"]
    assert parts == d["n_total_responses"]
