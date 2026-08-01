"""从已抓回答里挖「AI 实际点名了谁」（docs/22 C1）。

用途：本品提及率为 0 时，先搞清楚 AI 到底在推荐谁，再决定把谁录成竞品 ——
否则看板一排 0，L3 的比率 / SoV / 位置分都没法验证算得对不对。

只统计 answer_status=ok 的样本，按「出现于多少条样本」排序（不是总次数，
避免一条答案里刷屏的名字压过普遍被提到的名字）。

用法：
    python -m app.scripts.brand_candidates
    python -m app.scripts.brand_candidates --min-samples 3 --top 40
    python -m app.scripts.brand_candidates --brand-id 1     # 只看该品牌的 prompt 产生的样本
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import CrawlJob, Prompt, RawResponse

# 中文机构名常见收尾词。想扩到别的行业就加词。
SUFFIX = r"(?:装饰|装修|家居|设计|建设|工程|集团|网|居)"
NAME_RE = re.compile(rf"[一-鿿]{{2,6}}{SUFFIX}")

# 长得像品牌但其实是通用说法，命中即丢弃
GENERIC = frozenset(
    {
        "装修公司", "家装公司", "装饰公司", "全屋定制", "局部装修", "老房装修",
        "半包装修", "整装装修", "家装设计", "室内设计", "装修设计", "公装装饰",
        "二手房装修", "精装修", "硬装装修", "软装设计", "装修工程", "装饰工程",
        "家居设计", "房屋装修", "装修网", "隐蔽工程", "水电工程", "水电隐蔽工程",
        "全案设计", "准备装修", "选择装修", "一次装修", "年的装修", "找到一家好的装修",
    }
)
# 这些词出现在候选名里就丢（用于滤掉「防水等隐蔽工程」这类半截短语）
GENERIC_PARTS = ("隐蔽工程", "获奖设计", "核心", "等")


def _looks_generic(name: str) -> bool:
    if name in GENERIC:
        return True
    return any(part in name for part in GENERIC_PARTS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand-id", type=int, default=None, help="只看该品牌 prompt 的样本")
    ap.add_argument("--min-samples", type=int, default=2, help="至少出现在几条样本里")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = select(RawResponse).where(RawResponse.answer_status == "ok")
        if args.brand_id is not None:
            q = (
                q.join(CrawlJob, CrawlJob.id == RawResponse.job_id)
                .join(Prompt, Prompt.id == CrawlJob.prompt_id)
                .where(Prompt.brand_id == args.brand_id)
            )
        rows = list(db.scalars(q).all())
        if not rows:
            print("没有 answer_status=ok 的样本")
            return 1

        by_sample: Counter[str] = Counter()
        for r in rows:
            for name in set(NAME_RE.findall(r.full_text or "")):
                if not _looks_generic(name):
                    by_sample[name] += 1

        print(f"有效样本 {len(rows)} 条\n")
        print(f"{'候选品牌':<16}{'出现样本数':>10}{'覆盖率':>10}")
        print("-" * 36)
        shown = 0
        for name, c in by_sample.most_common():
            if c < args.min_samples or shown >= args.top:
                continue
            print(f"{name:<16}{c:>10}{c / len(rows) * 100:>9.1f}%")
            shown += 1
        if not shown:
            print("（无候选：可能样本太少，或需要调整 SUFFIX 词表）")
        print(
            "\n提示：确认后用 PUT /v1/brands/{id}/competitors 挂为竞品，"
            "再跑 POST /v1/responses/annotate/run 重跑 L1。"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
