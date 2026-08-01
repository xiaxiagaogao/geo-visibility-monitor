"""清理 DeepSeek 账号里由爬虫产生的历史对话。

⚠️ **这个账号里绝大多数是用户的私人对话。**
2026-08-01 实测侧栏 46 条，只有 6 条是爬虫产生的，其余是个人记录
（期权交易、面试、技术排查、相机设置……）。

因此本脚本刻意做得很笨，不提供任何「自动识别爬虫对话」的能力：

- 不加 ``--title`` 时**只列出**侧栏标题，不删任何东西
- 只删标题**完全等于** ``--title`` 所给值的对话；无模糊匹配、无前缀匹配
- 默认 dry-run，必须显式加 ``--apply``
- 单次最多删 ``--max`` 条（默认 10），超过直接拒绝执行

之所以不做「从库里的 prompt 反推标题」：DeepSeek 的对话标题是提问的**概括**
（「2026年装修公司哪家好？」→「2026装修公司推荐」），靠猜匹配不可靠，
在这种账号里配上批量删除风险不成比例。日常抓取已经「抓完即删」
（见 deepseek_web.DELETE_SESSION_API），这个脚本只用来清历史遗留。

用法：
    python -m app.scripts.deepseek_cleanup                          # 只列出，什么都不删
    python -m app.scripts.deepseek_cleanup --title "测试响应确认"     # 预览
    python -m app.scripts.deepseek_cleanup --title "测试响应确认" --apply
"""
from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.providers.deepseek_web import DELETE_SESSION_API

ITEM_SEL = "a[href^='/a/chat/s/']"
DEEPSEEK_URL = "https://chat.deepseek.com"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--title",
        action="append",
        default=[],
        help="要删除的对话标题（完全匹配，可重复）。不给则只列出。",
    )
    ap.add_argument("--apply", action="store_true", help="真的执行删除（默认只预览）")
    ap.add_argument("--max", type=int, default=10, help="单次最多删几条，超过直接拒绝")
    args = ap.parse_args()

    settings = get_settings()
    storage = settings.deepseek_storage_state
    if not storage:
        print("DEEPSEEK_STORAGE_STATE 未设置")
        return 1

    from playwright.sync_api import sync_playwright

    wanted = {t.strip() for t in args.title if t.strip()}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.playwright_headless)
        ctx = browser.new_context(
            storage_state=storage,
            viewport={"width": 1400, "height": 1000},
            locale="zh-CN",
        )
        page = ctx.new_page()
        page.goto(
            DEEPSEEK_URL, wait_until="domcontentloaded", timeout=settings.crawl_timeout_ms
        )
        page.wait_for_timeout(6000)

        items = page.locator(ITEM_SEL)
        found: list[tuple[str, str]] = []
        for i in range(items.count()):
            try:
                title = (items.nth(i).inner_text(timeout=1200) or "").strip()
                href = items.nth(i).get_attribute("href") or ""
            except Exception:
                continue
            if title and href:
                found.append((title, href.rsplit("/", 1)[-1]))

        print(f"侧栏共 {len(found)} 条对话\n")

        if not wanted:
            for title, _ in found:
                print(f"  {title}")
            print(
                "\n（未指定 --title，未做任何修改）\n"
                "确认哪些是爬虫产生的之后，用 --title 逐条指定，再加 --apply 执行。"
            )
            ctx.close()
            browser.close()
            return 0

        targets = [(t, s) for t, s in found if t in wanted]
        missing = wanted - {t for t, _ in targets}
        print(f"命中 {len(targets)} 条；其余 {len(found) - len(targets)} 条**不会被碰**")
        if missing:
            print(f"侧栏里找不到这些标题（已忽略）：{sorted(missing)}")
        print()
        for title, sid in targets:
            print(f"  {'删除' if args.apply else '将删除'}  {title:<28} {sid}")

        if not targets:
            ctx.close()
            browser.close()
            return 0

        if len(targets) > args.max:
            print(
                f"\n拒绝执行：命中 {len(targets)} 条，超过 --max {args.max}。"
                "\n请缩小 --title 范围，或确认无误后显式调高 --max。"
            )
            ctx.close()
            browser.close()
            return 1

        if not args.apply:
            print("\n（dry-run，未做任何修改。确认无误后加 --apply）")
            ctx.close()
            browser.close()
            return 0

        ok = fail = 0
        for title, sid in targets:
            try:
                resp = page.request.post(
                    DELETE_SESSION_API,
                    data={"chat_session_id": sid},
                    headers={"content-type": "application/json"},
                )
                if resp.ok:
                    ok += 1
                else:
                    fail += 1
                    print(f"  失败 {title}: HTTP {resp.status}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                print(f"  失败 {title}: {exc}")
        print(f"\n完成：成功 {ok}，失败 {fail}")
        ctx.close()
        browser.close()
        return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
