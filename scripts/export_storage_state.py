#!/usr/bin/env python3
"""导出某个平台的 storage_state（独立 Chromium profile，不碰日常 Chrome）。

Does NOT touch your daily Chrome profile or Chrome Safe Storage keychain.

Usage:
  apps/api/.venv/bin/python scripts/export_storage_state.py                      # 默认 deepseek
  apps/api/.venv/bin/python scripts/export_storage_state.py --platform doubao
  apps/api/.venv/bin/python scripts/export_storage_state.py --auto             # 检测到登录就保存

**登录态是带地理位置的。** 会话建立时的出口 IP 决定了服务端下发给它的功能开关、
模型通道与 WAF 令牌（这些都会进 storage_state 的 localStorage / cookies）。
从新加坡登、拿到大陆去用，等于「IP 切了、环境没切」—— 2026-08-15 实际踩过。

所以要让登录流量从**采集节点**出去。先开一条到节点的 SOCKS 隧道：

  ssh -i <node.pem> -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -D 18080 -N -f root@<节点>
  apps/api/.venv/bin/python scripts/export_storage_state.py --proxy socks5://127.0.0.1:18080

``ExitOnForwardFailure=yes`` **不能省**：`-f -N` 在端口已被占用时照样会 fork
到后台挂着，只是没有转发 —— 反复重试就会在节点上攒出一串没用的 SSH 会话
（2026-08-15 攒了 4 条），而命令行看起来和正常那条一模一样，事后只能靠
`lsof -nP -iTCP:18080` 分辨谁真的在 LISTEN。加上它，绑不上就直接退出。

`ServerAliveInterval` / `ServerAliveCountMax` 也不能省：**隧道断了之后
ssh 进程不会自己退**，端口继续被占着，而经它发出去的请求全部失败 ——
表现是「隧道明明在，就是不通」，重开还会撞 `Address already in use`。
2026-08-15 实际卡过一次。加上保活，连接断了 90 秒内进程自己退出，端口释放。


用完按精确 PID 关，**别用 `pkill -f`** —— 节点上还跑着别的生产服务：

  lsof -nP -iTCP:18080 | grep LISTEN     # 拿到 PID
  kill <那个PID>

脚本会在你登录**之前**把当前出口 IP 打出来，不是大陆会大声警告 ——
这一步不确认，登完才发现登错了地方就白搭。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from app.providers.browser import (  # noqa: E402
    context_kwargs,
    launch_kwargs,
    resolve_user_agent,
)

ROOT = Path(__file__).resolve().parents[1]

#: 每个平台一条。**加平台只改这里** —— 与 `providers/registry.py` 同一条纪律。
#:
#: `detect` 为 None 表示没有自动登录检测：`--auto` 不可用，只能手动按 Enter。
#: 刻意不为新平台瞎写一个检测器 —— 检测错了会在你还没登完时就导出一份空会话，
#: 而那份会话拿去采集的表现是「一批 job 全 failed」，排查方向完全跑偏。
PLATFORMS = {
    "deepseek": {
        "url": "https://chat.deepseek.com/",
        "profile": "deepseek_profile",
        "out": "deepseek_storage.json",
        "detect": "deepseek",
    },
    "doubao": {
        "url": "https://www.doubao.com/chat/",
        "profile": "doubao_profile",
        "out": "doubao_storage.json",
        "detect": None,     # 未实测，见 PHASE2 P2-06a 第 0 步
    },
}


def looks_logged_in_deepseek(page) -> bool:
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


#: 检测器注册。加平台若写了检测器，往这里加一行。
DETECTORS = {"deepseek": looks_logged_in_deepseek}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform",
        default="deepseek",
        choices=sorted(PLATFORMS),
        help="要导出哪个平台的登录态（默认 deepseek）",
    )
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

    cfg = PLATFORMS[args.platform]
    profile_dir = ROOT / "data" / cfg["profile"]
    out_path = ROOT / "deploy" / cfg["out"]
    url = cfg["url"]
    detect = DETECTORS.get(cfg["detect"]) if cfg["detect"] else None

    if args.auto and detect is None:
        print(f"⚠ {args.platform} 还没有登录检测器，--auto 不可用 —— 改为手动按 Enter。")
        print("  （不为新平台瞎写检测器是有意的：检测错了会导出一份空会话，")
        print("    而空会话拿去采集的表现是「一批 job 全 failed」，排查方向完全跑偏）")
        args.auto = False

    profile_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DeepSeek storage_state 导出（独立浏览器，不碰主 Chrome）")
    print("平台:  ", args.platform)
    print("Profile:", profile_dir)
    print("输出:  ", out_path)
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
        # **和 crawler 用同一套指纹**（app/providers/browser.py）——
        # 登录态在一种浏览器里出生、在另一种里使用，本身就是信号。
        # 2026-08-15 豆包第一条探针就是这么被登出的。
        ctx_kwargs = launch_kwargs(headless=False)
        ctx_kwargs.update(
            context_kwargs(
                user_agent=resolve_user_agent(p, headless=False),
                timezone_id=args.timezone,
            )
        )
        if args.proxy:
            # SOCKS 代理在 Chromium 上必须在 launch 时给，不能按 context 设
            ctx_kwargs["proxy"] = {"server": args.proxy}
        context = p.chromium.launch_persistent_context(str(profile_dir), **ctx_kwargs)
        page = context.pages[0] if context.pages else context.new_page()

        print("\n=== 登录前先确认出口 ===")
        check_exit_ip(page)

        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        print("浏览器已打开。\n")

        if args.auto:
            deadline = time.time() + args.wait_sec
            while time.time() < deadline:
                if detect and detect(page):
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
                    if detect and detect(page):
                        break
                    time.sleep(2)

        context.storage_state(path=str(out_path))
        context.storage_state(path=str(profile_dir / "storage_state.json"))
        context.close()

    data = json.loads(out_path.read_text(encoding="utf-8"))
    cookies = data.get("cookies") or []
    domains = sorted({c.get("domain", "") for c in cookies})
    print("\n导出完成")
    print("  cookies:", len(cookies))
    print("  domains:", domains)
    print("  file:", out_path)
    print("\n下一步：把它管道送到采集节点，见 scripts/crawl-node/README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
