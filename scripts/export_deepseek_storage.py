#!/usr/bin/env python3
"""Export DeepSeek storage_state with an isolated Chromium profile.

Does NOT touch your daily Chrome profile or Chrome Safe Storage keychain.

Usage:
  apps/api/.venv/bin/python scripts/export_deepseek_storage.py
  apps/api/.venv/bin/python scripts/export_deepseek_storage.py --auto   # detect login then save
"""
from __future__ import annotations

import argparse
import json
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true", help="auto-save when login detected (max wait)")
    parser.add_argument("--wait-sec", type=int, default=300, help="max seconds for --auto")
    args = parser.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DeepSeek storage_state 导出（独立浏览器，不碰主 Chrome）")
    print("Profile:", PROFILE_DIR)
    print("输出:  ", OUT_PATH)
    print("=" * 60)
    print("请在弹出的 Chromium 窗口登录 DeepSeek（不要用日常 Chrome）。")
    if args.auto:
        print(f"--auto: 检测到登录后自动保存（最长 {args.wait_sec}s）")
    else:
        print("登录成功后回到终端按 Enter 保存。")
    print("=" * 60)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        print("\n浏览器已打开。\n")

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
