"""D1：安踏监测集入库（品牌 + 竞品 + 无提示 prompt）。幂等，可重复执行。

口径见 docs/26-monitoring-set-anta.md：

- **提问词一律不含监测品牌名。** 含品牌名的提问，AI 必然提到，提及率恒 ~100%，
  从定义上就不是「可见性」。这类提问不进监测集，也不靠 category 隔离。
- 提问词刻意覆盖「通用向 / 国产向 / 中性」三种倾向：全通用会把安踏压到 0%，
  全国产会推到 100%，两种极端都看不出趋势。
- 迪桑特 / FILA 中国区虽属安踏集团，但作为独立消费者品牌 **不计入安踏**。
- 361 不收裸数字别名 —— 会误匹配正文里任何 361。

用法：
    python -m app.scripts.seed_anta            # 只建品牌与 prompt
    python -m app.scripts.seed_anta --jobs 3   # 另外给每条 prompt 入队 3 个抓取任务
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Brand, CrawlJob, Prompt
from app.schemas.brand import BrandCreate
from app.schemas.prompt import PromptCreate
from app.services.brands import create_brand, replace_competitors
from app.services.prompts import create_prompt

INDUSTRY = "运动鞋服"
OWNER = ("安踏", "ANTA", ["ANTA", "安踏体育", "安踏集团"])
COMPETITORS = [
    ("李宁", "Li-Ning", ["Li-Ning", "LI-NING", "李宁公司"]),
    ("耐克", "Nike", ["Nike", "NIKE"]),
    ("阿迪达斯", "Adidas", ["Adidas", "adidas", "阿迪"]),
    ("特步", "Xtep", ["Xtep", "XTEP"]),
    ("361度", "361 Degrees", ["361°", "361度"]),
    ("鸿星尔克", "ERKE", ["ERKE", "erke", "鸿星尔克体育"]),
    ("亚瑟士", "ASICS", ["ASICS", "asics", "Asics"]),
]

# (提问词, category, 倾向)
PROMPTS = [
    ("2026年跑步鞋哪个品牌好？", "unprompted", "通用向"),
    ("国产运动鞋品牌有哪些值得买的？", "unprompted", "国产向"),
    ("500元左右的运动鞋推荐", "unprompted", "中性"),
    ("打篮球穿什么牌子的鞋好？", "unprompted", "中性"),
    ("运动鞋品牌排行榜前十有哪些？", "unprompted", "通用向"),
    ("适合跑步新手的鞋子推荐哪个牌子？", "unprompted", "中性"),
    ("马拉松比赛穿什么跑鞋？", "scenario", "通用向"),
    ("学生党性价比高的运动鞋推荐", "scenario", "国产向"),
    ("大体重跑者适合什么跑鞋？", "scenario", "通用向"),
    ("健身房训练穿什么鞋合适？", "scenario", "中性"),
]


def _ensure_brand(db, name: str, name_en: str, aliases: list[str]) -> int:
    brand = db.scalar(select(Brand).where(Brand.name == name))
    if brand:
        print(f"  已存在 {name} (id={brand.id})")
        return brand.id
    brand = create_brand(
        db, BrandCreate(name=name, name_en=name_en, industry=INDUSTRY, aliases=aliases)
    )
    print(f"  新建   {name} (id={brand.id}) aliases={aliases}")
    return brand.id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="给每条 prompt 入队几个抓取任务（0=不建，默认）",
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        print("=== 1) 品牌 ===")
        owner_id = _ensure_brand(db, *OWNER)
        comp_ids = [_ensure_brand(db, *c) for c in COMPETITORS]

        print("\n=== 2) 竞品关系 ===")
        replace_competitors(db, owner_id, comp_ids)
        print(f"  {OWNER[0]}(id={owner_id}) 竞品 = {comp_ids}")

        print("\n=== 3) Prompt ===")
        prompt_ids = []
        for text, category, lean in PROMPTS:
            # 守住口径：提问词不能出现监测品牌
            for token in (OWNER[0], OWNER[1]):
                if token.lower() in text.lower():
                    raise SystemExit(f"提问词含监测品牌名，违反口径: {text}")
            prompt = db.scalar(
                select(Prompt).where(Prompt.text == text, Prompt.brand_id == owner_id)
            )
            if prompt:
                prompt.category = category
                prompt.tags = [lean]
                db.commit()
                print(f"  已存在 #{prompt.id:<3} [{category:<10}] {text}  ({lean})")
            else:
                prompt = create_prompt(
                    db,
                    PromptCreate(
                        brand_id=owner_id, text=text, category=category, tags=[lean]
                    ),
                )
                print(f"  新建   #{prompt.id:<3} [{category:<10}] {text}  ({lean})")
            prompt_ids.append(prompt.id)

        n_up = sum(1 for _, c, _ in PROMPTS if c == "unprompted")
        print(f"\n共 {len(PROMPTS)} 条：unprompted={n_up} scenario={len(PROMPTS) - n_up}")

        if args.jobs > 0:
            print(f"\n=== 4) 抓取任务（每条 prompt {args.jobs} 个样本）===")
            for pid in prompt_ids:
                for i in range(1, args.jobs + 1):
                    db.add(
                        CrawlJob(
                            prompt_id=pid,
                            platform="deepseek",
                            status="pending",
                            sample_index=i,
                        )
                    )
            db.commit()
            total = len(prompt_ids) * args.jobs
            print(f"  已入队 {total} 个任务（约 {total * 25 // 60} 分钟）")
        else:
            print("\n未建抓取任务（--jobs N 可入队）")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
