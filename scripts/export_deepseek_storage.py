#!/usr/bin/env python3
"""Export DeepSeek storage_state with an isolated Chromium profile.

Does NOT touch your daily Chrome profile or Chrome Safe Storage keychain.

Usage:
  apps/api/.venv/bin/python scripts/export_deepseek_storage.py
  apps/api/.venv/bin/python scripts/export_deepseek_storage.py --auto   # detect login then save

**登录态是带地理位置的。** 会话建立时的出口 IP 决定了服务端下发给它的功能开关、
模型通道与 WAF 令牌（这些都会进 storage_state 的 localStorage / cookies）。
从新加坡登、拿到大陆去用，等于「IP 切了、环境没切」—— 2026-08-15 实际踩过。

所以要让登录流量从**采集节点**出去。先开一条到节点的 SOCKS 隧道：

  ssh -i <node.pem> -D 18080 -N -f root@<节点>
  apps/api/.venv/bin/python scripts/export_deepseek_storage.py --proxy socks5://127.0.0.1:18080

脚本会在你登录**之前**把当前出口 IP 打出来，不是大陆会大声警告 ——
这一步不确认，登完才发现登错了地方就白搭。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "deepseek_profile"
OUT_PATH = ROOT / "deploy" / "deepseek_storage.json"
URL = "https://chat.deepseek.com/"


def looks_logged_in(page) -> bool:
    try:
        # input box present
        if page.locator("textarea").count() == 0:
            return False
        body = (page.inner_text("body") or "")[:2500]
        # still on hard login wall
        if "手机号登录" in body or "验证码登录" in body:
            # might still show side text; require absence of phone login form dominant
            if page.locator("text=手机号登录").count() > 0 and page.locator("textarea").count() == 0:
                return False
        # conversation UI signals
        if "开启新对话" in body or "深度思考" in body or "智能搜索" in body:
            return True
        if page.locator("textarea").count() > 0 and "登录" not in page.url.lower():
            # soft pass: can type
            return True
    except Exception:
        return False
    return False


def check_exit_ip(page) -> None:
    """把出口 IP 摆在登录**之前**。

    不做判定、不阻断 —— 只是让「登错了地方」这件事无法在无声中发生。
    从哪儿登决定了服务端给这个会话下发什么，而那个错误一旦发生，
    表现是「数据照样采得到，只是口径不对」，没有任何地方会报错。
    """
    try:
        page.goto("https://ipinfo.io/json", wait_until="domcontentloaded", timeout=30000)
        info = json.loads(page.inner_text("body"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠ 取不到出口 IP（{exc}）—— 请自行确认再登录\n")
        return

    ip, org, country = info.get("ip"), info.get("org"), info.get("country")
    city, region = info.get("city"), info.get("region")
    print(f"  出口 IP: {ip} | {org} | {city} {region} {country}")
    if country == "CN":
        print("  ✓ 大陆出口，可以登录\n")
    else:
        print()
        print("  " + "!" * 62)
        print(f"  ！出口不在大陆（country={country}）。在这里登录会拿到一份")
        print("  ！**新加坡/境外的会话**：功能开关、模型通道、WAF 令牌都是那边下发的，")
        print("  ！拿到采集节点上用，等于 IP 切了环境没切 —— 正是要修的那个问题。")
        print("  ！")
        print("  ！先开隧道再重来：ssh -i <node.pem> -D 18080 -N -f root@<节点>")
        print("  ！                 然后加 --proxy socks5://127.0.0.1:18080")
        print("  " + "!" * 62)
        print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true", help="auto-save when login detected (max wait)")
    parser.add_argument("--wait-sec", type=int, default=300, help="max seconds for --auto")
    parser.add_argument(
        "--proxy",
        default=None,
        help="Chromium 走的代理，例如 socks5://127.0.0.1:18080（到采集节点的 SOCKS 隧道）",
    )
    parser.add_argument(
        "--timezone",
        default="Asia/Shanghai",
        help="浏览器上报的时区，要和出口所在地区一致（默认 Asia/Shanghai）",
    )
    args = parser.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DeepSeek storage_state 导出（独立浏览器，不碰主 Chrome）")
    print("Profile:", PROFILE_DIR)
    print("输出:  ", OUT_PATH)
    print("=" * 60)
    print("请在弹出的 Chromium 窗口登录 DeepSeek（不要用日常 Chrome）。")
    print("代理:  ", args.proxy or "（无 —— 走本机默认网络出口）")
    print("时区:  ", args.timezone)
    if args.auto:
        print(f"--auto: 检测到登录后自动保存（最长 {args.wait_sec}s）")
    else:
        print("登录成功后回到终端按 Enter 保存。")
    print("=" * 60)

    with sync_playwright() as p:
        ctx_kwargs = dict(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            # 和 providers/deepseek_web.py 保持同一套指纹 —— 登录时是一个时区、
            # 抓取时是另一个，等于给服务端看两个不同的人
            timezone_id=args.timezone,
            args=["--disable-blink-features=AutomationControlled"],
        )
        if args.proxy:
            # SOCKS 代理在 Chromium 上必须在 launch 时给，不能按 context 设
            ctx_kwargs["proxy"] = {"server": args.proxy}
        context = p.chromium.launch_persistent_context(**ctx_kwargs)
        page = context.pages[0] if context.pages else context.new_page()

        print("\n=== 登录前先确认出口 ===")
        check_exit_ip(page)

        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        print("浏览器已打开。\n")

        if args.auto:
            deadline = time.time() + args.wait_sec
            while time.time() < deadline:
                if looks_logged_in(page):
                    print("检测到疑似已登录 UI，导出中…")
                    break
                time.sleep(2)
            else:
                print("等待超时，仍尝试导出当前 state。")
        else:
            try:
                input(">>> 登录完成后按 Enter 导出 … ")
            except EOFError:
                print("非交互：切换为自动等待 180s…")
                deadline = time.time() + 180
                while time.time() < deadline:
                    if looks_logged_in(page):
                        break
                    time.sleep(2)

        context.storage_state(path=str(OUT_PATH))
        context.storage_state(path=str(PROFILE_DIR / "storage_state.json"))
        context.close()

    data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    cookies = data.get("cookies") or []
    domains = sorted({c.get("domain", "") for c in cookies})
    print("\n导出完成")
    print("  cookies:", len(cookies))
    print("  domains:", domains)
    print("  file:", OUT_PATH)
    print("\n下一步: ./scripts/deploy_deepseek_storage_to_vps.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
