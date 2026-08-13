#!/usr/bin/env python3
"""L2 冒烟：用真浏览器把客户那条只读路径走一遍。

**定位：部署后检查，不是合并门禁。** 它测的是**已经部署的那个版本**，
所以该接在 post-receive 后面 —— 把现在那个「直连 3000 看端口活着吗」的探针
升级成「整条路走得通吗」。

**为什么用客户账号：** 客户角色是纯只读的，`require_write` 在服务端挡着。
所以即使这个脚本写错、点到了什么，也不可能写进生产 ——
边界不在脚本里，在后端。这是 RBAC 设计白送的安全网。

代价是覆盖不到超管路径（写操作、用户管理）。可以接受：
权限矩阵由后端那 280 条测试管，冒烟只管「路断没断」。

**凭证只从环境变量读，绝不进 Git**（BACKEND.md：密钥、pem、storage_state
禁止进 Git）。没设就直接退出，不做任何猜测。

跑法（在 VPS 上，crawler 容器里已经装好 Playwright 与浏览器）：

    docker exec -e SMOKE_EMAIL=... -e SMOKE_PASSWORD=... \\
        geo-crawler python /app/scripts/smoke/browser_smoke.py

想绕开 CF/Caddy 直连容器（**测不到路径分流**，仅在公网不通时用）：

    ... -e SMOKE_BASE_URL=http://web:3000 ...
"""
from __future__ import annotations

import os
import sys
from typing import List

BASE_URL = os.environ.get("SMOKE_BASE_URL", "https://geo.xg22.top").rstrip("/")
EMAIL = os.environ.get("SMOKE_EMAIL")
PASSWORD = os.environ.get("SMOKE_PASSWORD")
#: 失败时把截图丢这儿，便于区分「部署断了」和「网络抖了」
ARTIFACT_DIR = os.environ.get("SMOKE_ARTIFACT_DIR", "/data/smoke")
TIMEOUT_MS = int(os.environ.get("SMOKE_TIMEOUT_MS", "20000"))

steps: List[str] = []
console_errors: List[str] = []
http_failures: List[str] = []

#: 预期之内的失败响应，**必须精确到 URL**。
#:
#: `AuthProvider` 挂载时拉一次 `/v1/auth/me` 判断「我是谁」——在登录页
#: （还没登录）和退出之后，它**本来就该返回 401**（API.md §2.2：401 = 未登录），
#: 前端也正确地把它当成 anonymous 处理。但浏览器对任何 4xx 都会往控制台记一条
#: `Failed to load resource`，哪怕应用处理得完全正确。
#:
#: **不能因此把 401 全部忽略**：中途掉 401 是真 bug（会话断了）。
#: 所以这里按「URL + 状态码」成对放行，放行范围小到不会盖住真问题。
EXPECTED_FAILURES = [("/v1/auth/me", 401)]


def _is_expected(url: str, status: int) -> bool:
    return any(path in url and status == code for path, code in EXPECTED_FAILURES)


def step(msg: str) -> None:
    steps.append(msg)
    print(f"  ✓ {msg}", flush=True)


class SmokeFailed(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SmokeFailed(msg)


def run() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        # 盯 HTTP 响应而不是 console 文本：`Failed to load resource` 那类
        # console 消息拿不到可靠的 URL，而没有 URL 就没法区分
        # 「预期内的 /v1/auth/me 401」和「中途会话掉了」。
        page.on(
            "response",
            lambda r: http_failures.append(f"{r.status} {r.url}")
            if r.status >= 400 and not _is_expected(r.url, r.status)
            else None,
        )

        # console 里的 error 另收 —— 页面「看起来正常」但控制台在报错，
        # 是最容易在人工点检里漏掉的一类。
        # 但 `Failed to load resource` 排除掉：它是上面那个 response 钩子的
        # 重复报告，且不带 URL，留着只会制造分不清来源的噪音。
        page.on(
            "console",
            lambda m: console_errors.append(f"{m.type}: {m.text}")
            if m.type == "error" and "Failed to load resource" not in m.text
            else None,
        )

        try:
            _walk(page)
        except Exception:
            _dump(page)
            raise
        finally:
            ctx.close()
            browser.close()

    problems = []
    if http_failures:
        problems.append(
            f"{len(http_failures)} 个请求失败：\n  " + "\n  ".join(http_failures[:10])
        )
    if console_errors:
        problems.append(
            f"控制台有 {len(console_errors)} 条 error：\n  "
            + "\n  ".join(console_errors[:10])
        )
    if problems:
        raise SmokeFailed("\n".join(problems))
    return 0


def _walk(page) -> None:
    # ── 登录 ────────────────────────────────────────────────
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    check("登录" in page.content() or page.locator("input[type=password]").count() > 0,
          "登录页没渲染出密码框")
    step("登录页可达")

    page.fill("input[type=email]", EMAIL)
    page.fill("input[type=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(lambda url: "/login" not in url, timeout=TIMEOUT_MS)
    step("登录成功")

    # ── 客户首页分流（A8）─────────────────────────────────────
    page.goto(f"{BASE_URL}/", wait_until="networkidle")
    page.wait_for_url(lambda url: "/tasks/" in url, timeout=TIMEOUT_MS)
    check("/tasks/" in page.url, f"客户首页应落到任务详情，实际是 {page.url}")
    task_url = page.url
    step(f"首页分流到任务详情：{task_url.replace(BASE_URL, '')}")

    # 客户看不到运维入口，也没有写操作
    check(page.get_by_text("运维质检").count() == 0, "客户不该看到「运维质检」入口")
    check(page.get_by_role("button", name="立即运行").count() == 0,
          "客户不该看到「立即运行」")
    step("客户视角：无运维入口、无写操作按钮")

    # ── 任务详情有数（不是全 —）──────────────────────────────
    body = page.inner_text("body")
    check("%" in body, "任务详情一个百分比都没有 —— KPI 可能全是不可算")
    check("覆盖缺口" in body, "缺口清单面板没渲染")
    step("任务详情：KPI 有数、缺口面板在")

    # ── 命中矩阵 ────────────────────────────────────────────
    page.get_by_role("tab", name="命中矩阵").click()
    rows = page.locator("table tbody tr")
    check(rows.count() > 0, "命中矩阵一行都没有")
    step(f"命中矩阵渲染出 {rows.count()} 行")

    # ── 样本列表 → 证据页（A7）───────────────────────────────
    page.get_by_role("tab", name="样本列表").click()
    page.wait_for_selector("table tbody tr", timeout=TIMEOUT_MS)
    first_sample = page.locator("table tbody tr a").first
    check(first_sample.count() > 0, "样本表里没有可点的样本 id")
    first_sample.click()
    page.wait_for_url(lambda url: "/r/" in url, timeout=TIMEOUT_MS)
    step(f"进入证据页：{page.url.replace(BASE_URL, '')}")

    page.wait_for_selector("text=回答原文", timeout=TIMEOUT_MS)
    check(len(page.inner_text("body")) > 500, "证据页正文太短，可能没加载出全文")

    # **这一条是最值的**：那条告警是数据完整性不变量的 UI 出口。
    # 标注一旦漂了（first_offset 对不上 matched_term），它会亮红，
    # 而页面其余部分看起来完全正常。
    check(
        "标注与原文对不上" not in page.inner_text("body"),
        "证据页出现「标注与原文对不上」告警 —— L1 的不变量在真实数据上破了",
    )
    check(page.locator("mark").count() > 0, "证据页一处高亮都没有")
    step(f"证据页：全文已加载、{page.locator('mark').count()} 处高亮、无标注告警")

    # ── 退出 ────────────────────────────────────────────────
    page.get_by_role("button", name="退出账户").click()
    page.wait_for_url(lambda url: "/login" in url, timeout=TIMEOUT_MS)
    step("退出成功，回到登录页")


def _dump(page) -> None:
    """失败时留证。**区分「部署断了」和「网络抖了」全靠这个。**"""
    try:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        shot = os.path.join(ARTIFACT_DIR, "smoke-failure.png")
        page.screenshot(path=shot, full_page=True)
        print(f"\n  失败截图：{shot}", file=sys.stderr)
        print(f"  当前 URL：{page.url}", file=sys.stderr)
    except Exception as e:  # 留证失败不该盖掉真正的失败原因
        print(f"  （截图失败：{e}）", file=sys.stderr)


def main() -> int:
    if not EMAIL or not PASSWORD:
        print(
            "缺 SMOKE_EMAIL / SMOKE_PASSWORD。\n"
            "凭证只从环境变量读，不写进代码也不进 Git。",
            file=sys.stderr,
        )
        return 2

    print(f"冒烟目标：{BASE_URL}", flush=True)
    try:
        run()
    except SmokeFailed as e:
        print(f"\n✗ 冒烟失败：{e}", file=sys.stderr)
        print(f"  已完成 {len(steps)} 步", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ 冒烟异常（{type(e).__name__}）：{e}", file=sys.stderr)
        print(f"  已完成 {len(steps)} 步", file=sys.stderr)
        return 1

    print(f"\n✓ 冒烟通过，{len(steps)} 步全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
