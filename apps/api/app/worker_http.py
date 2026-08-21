"""采集节点的 HTTP 模式（P2-34 第 5 步）—— **不碰数据库**。

## 与隧道模式的关系：并存，不替换

``worker_main.py`` 按 ``WORKER_API_BASE`` 是否设置分流：

- **没设** → 隧道模式（``run_once`` 直连数据库），**行为一个字节不变**
- **设了** → 本模块，只出站 HTTP

回滚因此不需要动代码：把节点的环境变量改回去、重启容器即可
（``PHASE2.md`` §6 规矩 1：能不用 git 回滚的，就别依赖 git 回滚）。

## 为什么用 urllib 而不是 requests / httpx

**生产镜像里没有它们**（api 容器连跑测试都要临时 `pip install httpx`）。
为了一个每几秒发一次的循环去加一个依赖不划算，而 multipart 手拼也就十几行。

## 哪些活留在节点上，为什么

| 留在节点 | 理由 |
|---|---|
| 跑 Provider | 出口 IP 要是大陆家宽 —— 这是整件事的前提 |
| 读 ``storage_state`` 判级 | 文件在这台机器上，api 读不到 |
| 探出口 IP | 要的就是**这个节点**从哪儿出去 |
| **失败分类** | ``classify_failure`` 先看**异常类型**，而类型过不了 HTTP |

其余（指纹计算、``checked_at``、截图文件名、样本落库）全在服务端，
理由逐条写在 ``API.md`` §8.6。
"""
from __future__ import annotations

import json
import logging
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.providers.base import CrawlResult
from app.providers.registry import ProviderContext, build_provider
from app.services.crawl_env import FINGERPRINT_FIELDS, describe_environment, probe_exit_ip
from app.services.crawl_runner import run_with_timeout
from app.services.credential_health import collect_reports
from app.services.failure_kinds import classify_failure
from app.services.pacing import next_pause_sec

logger = logging.getLogger("geo.worker_http")

#: 我们自己的标识，**不伪装成浏览器**。作用是让采集流量在访问日志里认得出来。
#:
#: ⚠️ **它过不了 Cloudflare 的 Bot 检查，这是有意接受的。** 2026-08-21 从采集
#: 节点容器里实测三条路：
#:
#: =============================  ==========================
#: tailnet (`100.64.240.17:8200`)  200 · **0.22s**
#: `https://geo.xg22.top` 默认 UA   **403 `error code: 1010`**
#: `https://geo.xg22.top` 浏览器 UA  200 · 3.0s（慢 14 倍；390KB 上传要 16s）
#: =============================  ==========================
#:
#: 也就是说，走公网的前提是**让采集器谎称自己是浏览器，绕过我们自己域名上的
#: Bot 保护** —— 还慢一个数量级。所以链路留在 tailnet。
#:
#: 将来真要走公网，正确的做法是在 Cloudflare 上给 `/v1/worker/*` 加一条
#: WAF skip 规则：**在 CF 那边开门，而不是在这边伪装。**
USER_AGENT = "geo-crawler/1.0 (+P2-34 worker)"


def http_mode_enabled(settings) -> bool:
    """**只加不改的那道闸**：没配 ``WORKER_API_BASE`` 就还是隧道模式。"""
    return bool((getattr(settings, "worker_api_base", "") or "").strip())


def _json_default(o: Any):
    """``collect_reports`` 给的是 ``datetime``，JSON 塞不进去。"""
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def build_multipart(payload: Dict[str, Any], screenshot: Optional[bytes]):
    """拼 ``POST .../result`` 的 multipart 请求体，返回 ``(body, content_type)``。

    **分隔符每次随机生成**，不写死 —— 写死的话正文里恰好出现同一串字符
    就会把 body 解析错（答案是 AI 生成的任意文本，这不是杞人忧天）。

    **截图为 None 时不带那个 part**，而不是带一个空的：服务端按魔数判类型，
    0 字节会被判成「不是 PNG」直接 415，整条结果跟着丢。
    """
    boundary = f"----geo{secrets.token_hex(16)}"
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="payload"\r\n'
    body += b"Content-Type: application/json\r\n\r\n"
    body += json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
    body += b"\r\n"
    if screenshot is not None:
        body += f"--{boundary}\r\n".encode()
        # filename 服务端不采信（它自己生成），给一个占位就行
        body += b'Content-Disposition: form-data; name="screenshot"; filename="shot.png"\r\n'
        body += b"Content-Type: image/png\r\n\r\n"
        body += screenshot
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class WorkerClient:
    """五个 worker 端点的客户端。每个方法失败就抛，由调用方决定要不要继续。"""

    def __init__(self, base: str, api_key: str, timeout: float = 60.0):
        if not (api_key or "").strip():
            # 没有 key 的话每一发都会 401，而节点会把它当成「没活干」
            # 静静跑一整夜 —— 那种失败比直接崩掉难查得多
            raise ValueError("worker 模式需要 API_KEY（复用现有那把，见 API.md §8.6）")
        self.base = base.rstrip("/")
        self.key = api_key.strip()
        self.timeout = timeout

    # ---------- 底层 ----------

    def _call(self, method: str, path: str, *, body=None, ctype=None) -> Any:
        req = urllib.request.Request(self.base + path, method=method, data=body)
        req.add_header("X-API-Key", self.key)
        req.add_header("User-Agent", USER_AGENT)
        if ctype:
            req.add_header("Content-Type", ctype)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            # **绝不把 self.key 打进日志** —— 它是超管等价凭证
            raise RuntimeError(f"{method} {path} → HTTP {exc.code}: {detail}") from exc
        return json.loads(raw) if raw else None

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        return self._call("POST", path, body=body, ctype="application/json")

    # ---------- 五个端点 ----------

    def lease(self, batch_size: int, environment_id: Optional[int] = None) -> List[dict]:
        path = f"/v1/worker/lease?batch_size={int(batch_size)}"
        if environment_id is not None:
            path += f"&environment_id={int(environment_id)}"
        return (self._call("POST", path) or {}).get("jobs", [])

    def report_result(self, job_id: int, result: CrawlResult, screenshot: Optional[bytes] = None):
        payload = {
            "full_text": result.full_text,
            "latency_ms": result.latency_ms,
            "raw_json": result.raw_json,
            "citations": [
                {
                    "url": c.url,
                    "title": c.title,
                    "snippet": c.snippet,
                    "domain": c.domain,
                    "cite_index": c.cite_index,
                }
                for c in (result.citations or [])
            ],
        }
        body, ctype = build_multipart(payload, screenshot)
        return self._call("POST", f"/v1/worker/jobs/{int(job_id)}/result", body=body, ctype=ctype)

    def report_failure(self, job_id: int, reason: str, kind: Optional[str]):
        return self._post_json(
            f"/v1/worker/jobs/{int(job_id)}/fail", {"reason": reason[:500], "kind": kind}
        )

    def report_environment(self, fields: Dict[str, Any]) -> Optional[int]:
        payload = {k: fields.get(k) for k in FINGERPRINT_FIELDS}
        return (self._post_json("/v1/worker/environment", payload) or {}).get("environment_id")

    @staticmethod
    def encode_credentials(items: List[Dict[str, Any]]) -> str:
        """单独拆出来是为了能验「datetime 转了 ISO、且没夹带 cookie 的值」。"""
        return json.dumps({"items": items}, ensure_ascii=False, default=_json_default)

    def report_credentials(self, items: List[Dict[str, Any]]) -> int:
        body = self.encode_credentials(items).encode("utf-8")
        out = self._call(
            "POST", "/v1/worker/credentials", body=body, ctype="application/json"
        )
        return (out or {}).get("accepted", 0)


def _read_screenshot(result: CrawlResult) -> Optional[bytes]:
    """Provider 把图写在节点本地，这里读出来准备随结果传回去。

    读不到不算失败 —— 证据图没了不该把一条真答案一起丢掉。
    """
    path = getattr(result, "screenshot_path", None)
    if not path:
        return None
    try:
        return Path(path).read_bytes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("截图读不出来（样本照传）: %s %s", path, type(exc).__name__)
        return None


def process_leased_job(client, settings, job: dict) -> str:
    """跑一条领到的 job 并回传。返回 ``"success"`` / ``"failed"``。

    **整个函数不往外抛** —— 一条 job 炸了不能让整轮循环挂掉，后面那些还等着跑。

    失败分类在这里算：此刻手里还有异常**对象**，而 ``classify_failure``
    的第一判据就是异常类型（消息模式只是兜底）。等它变成 HTTP 上的一个字符串
    就只能靠子串猜了。
    """
    job_id = job["job_id"]
    try:
        provider = build_provider(
            job["platform"],
            ProviderContext(
                settings=settings,
                sample_index=job.get("sample_index") or 1,
                brand_names=list(job.get("brand_names") or []),
            ),
        )
        result = run_with_timeout(provider, job["prompt_text"], settings)
    except Exception as exc:  # noqa: BLE001
        kind = classify_failure(exc)
        logger.warning("job %s 失败 kind=%s: %s", job_id, kind, str(exc)[:200])
        try:
            client.report_failure(job_id, str(exc), kind)
        except Exception:  # noqa: BLE001
            # 回传失败也失败了：这条 job 会停在 running，600 秒后被僵死回收。
            # 那是设计好的兜底，不需要在这里另造一套
            logger.exception("job %s 的失败回传没送到", job_id)
        return "failed"

    try:
        client.report_result(job_id, result, _read_screenshot(result))
    except Exception:  # noqa: BLE001
        # **抓到了但没送回去。** 不在这里重试 —— 端点是幂等的，
        # 而这条 job 会被僵死回收后按 P2-16 的规则重排
        logger.exception("job %s 抓到了但结果没送到", job_id)
        return "failed"
    return "success"


def _refresh_self_report(client, settings) -> Optional[int]:
    """上报登录态与采集环境，换回 ``environment_id``。**失败不阻断采集。**"""
    env_id = None
    try:
        creds = collect_reports(settings)
        for r in creds:
            log = logger.warning if r["status"] != "ok" else logger.info
            log("credential %s status=%s %s", r["platform"], r["status"], r["issues"] or "")
        client.report_credentials(creds)
    except Exception:  # noqa: BLE001
        logger.exception("登录态上报失败（采集继续）")
        creds = []

    try:
        cred = creds[0] if creds else {}
        env_id = client.report_environment(
            describe_environment(
                settings,
                credential_region=cred.get("issuer_region"),
                waf_kind=cred.get("waf_kind"),
                exit_ip=probe_exit_ip(),
            )
        )
    except Exception:  # noqa: BLE001
        # 记不上就留 None：那一批 job 的 environment_id 是 NULL，
        # 表示「没记」—— 比编一个准确（P2-36 的规矩）
        logger.exception("采集环境上报失败（本轮 job 不带环境标记）")
    return env_id


def _pause(settings) -> None:
    """按配置随机停一下（P2-38 前置）。默认 0 秒 = 什么都不做。"""
    sec = next_pause_sec(settings)
    if sec > 0:
        logger.info("节奏打散：等 %.1f 秒", sec)
        time.sleep(sec)


def run_forever(settings) -> None:
    """HTTP 模式主循环。结构与隧道模式的 ``worker_main.main()`` 一一对应。"""
    client = WorkerClient(
        settings.worker_api_base,
        settings.api_key,
        timeout=getattr(settings, "worker_http_timeout_sec", 60.0),
    )
    logger.info(
        "crawler starting mode=http api=%s interval=%s",
        settings.worker_api_base,
        settings.fake_worker_interval_sec,
    )
    next_cred_check = 0.0
    env_id = None

    while True:
        try:
            if settings.crawl_credential_check_sec > 0 and time.time() >= next_cred_check:
                next_cred_check = time.time() + settings.crawl_credential_check_sec
                env_id = _refresh_self_report(client, settings)

            jobs = client.lease(settings.fake_worker_batch_size, environment_id=env_id)
            for i, job in enumerate(jobs):
                process_leased_job(client, settings, job)
                # P2-38 前置：**把固定心跳变成一个分布**。默认 0 = 不等。
                # 最后一条之后不等 —— 那段等待没有意义，下一轮的 lease
                # 本来就要隔 fake_worker_interval_sec
                if i + 1 < len(jobs):
                    _pause(settings)
            if jobs:
                logger.info("processed %s", [j["job_id"] for j in jobs])
                # batch_size=1 时上面那个循环内的间隔永远不生效（只有一条），
                # 所以真正起作用的是这里 —— 领完一批之后再打散一次
                _pause(settings)
        except Exception:  # noqa: BLE001
            # 领不到就下一轮再来。api 重启 / 家宽抖一下都会走到这里，
            # 不该让容器退出（它是 restart: unless-stopped，退出反而更慢）
            logger.exception("worker iteration failed")
        time.sleep(settings.fake_worker_interval_sec)
