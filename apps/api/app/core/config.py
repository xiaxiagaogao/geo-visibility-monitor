from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://geo:geo@127.0.0.1:5432/geo"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 鉴权：空 = 不校验（仅限本机开发）。公网部署必须设置。
    # 生成：python -c "import secrets; print(secrets.token_urlsafe(32))"
    api_key: str = ""
    # Cookie 是否只走 HTTPS（上了证书后置 true）。samesite=none 时**必须**为 true，
    # 否则浏览器直接丢弃该 Cookie。
    api_cookie_secure: bool = False
    # 前后端**分离部署**时置 "none"：跨站请求才会带上 Cookie
    # （截图 <img src> 靠它，见 core/security.py）。同源部署保持 "lax"。
    api_cookie_samesite: str = "lax"

    # CORS：逗号分隔的前端 Origin 白名单，空 = 不启用 CORS（同源部署）。
    # 例：https://geo.xg22.top,http://localhost:3000
    # 注意：带 Cookie 的跨站请求**不允许**用 "*"，必须逐个列出。
    cors_allow_origins: str = ""

    # CSRF 双提交校验（D2-4）。**默认关**：前端未适配前开了会让所有会话写操作 403。
    # 前端在真浏览器里验过「读 geo_csrf Cookie 回填 X-CSRF-Token」之后再置 true。
    # 只影响**会话身份的写操作**；X-API-Key 的机器调用不受影响（它本来就免疫 CSRF）。
    csrf_protection_enabled: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in (self.cors_allow_origins or "").split(",") if o.strip()]

    # Worker loop (API process and/or crawler process)
    fake_worker_enabled: bool = True
    fake_worker_interval_sec: float = 2.0
    fake_worker_batch_size: int = 5

    # B5 crawl mode: fake | real
    crawl_mode: str = "fake"
    crawl_timeout_ms: int = 120_000
    # running 超过这个时长视为「worker 死了没来得及收尾」，回收成 failed。
    # 要大于 crawl_timeout_ms + process_job 的硬上限（+45s），留足余量。
    crawl_stuck_job_sec: int = 600

    # P2-16 自动退避重试。**默认关**：先只跑失败分类，在真实 run 上确认
    # timeout 认得准，再打开重试 —— 调试时不能有两个变量同时在动。
    # 这个开关同时是回滚手段：出事改环境变量重启即可，不必 git revert。
    crawl_auto_retry_enabled: bool = False
    # 首次 + 最多重试 (max-1) 次。耗尽后终态 failed，永不自动重排
    crawl_max_attempts: int = 3
    # 退避曲线 min(base * 2**(n-1), max)：30s → 60s → …，封顶 300s
    crawl_retry_base_sec: float = 30.0
    crawl_retry_max_sec: float = 300.0
    # ±20% 抖动。同一批 job 被同一次限流打中会同时失败、同时到期、同时再撞，
    # 抖开的成本近乎为零。置 0 可让退避完全确定（测试用）
    crawl_retry_jitter: float = 0.2
    playwright_headless: bool = True
    # 浏览器上报的时区。**必须和采集出口所在的地区一致** —— 不设的话
    # Playwright 取容器的系统时区（UTC），页面看到的就是「IP 在长沙、时区在伦敦」。
    # 切到 VPS 冷备（新加坡出口）时要改成 Asia/Singapore，否则只是换一种不一致。
    crawl_timezone_id: str = "Asia/Shanghai"
    # P2-07 登录态健康度。期望的签发地：`cn` | `overseas` | 空（= 不判）。
    # **和 crawl_timezone_id 是同一件事的两面** —— 切到 VPS 冷备时两个都要改。
    crawl_expected_credential_region: str = "cn"
    # 登录态文件多久没更新算「该换了」。0 = 不判
    crawl_credential_max_age_days: int = 14
    # 多久自检一次登录态（crawler 进程内，0 = 关）
    crawl_credential_check_sec: int = 300
    # P2-36 的第一块：这条采集是哪台机器报的。空 = 未标注
    crawl_node_label: str = ""
    deepseek_storage_state: str = ""
    # 豆包（P2-06a）。**没有 user_data_dir 时用临时 profile** ——
    # 每次干净，代价是每次重灌 storage_state
    doubao_storage_state: str = ""
    doubao_user_data_dir: str = ""
    doubao_delete_session: bool = True
    deepseek_user_data_dir: str = ""
    # 抓完即删该会话。默认开：不删则侧栏无限堆积，DOM 抓取迟早又抓到侧栏
    # （docs/18 的事故，库里已有两条 answer_status=error 的样本）
    deepseek_delete_session: bool = True
    # 通义千问（P2-06b）。**平台代码是 tongyi、站点是 qianwen.com** ——
    # 阿里把产品改名叫「千问」，但代码已在 ALLOWED_PLATFORMS 与历史数据里，
    # 改它等于一次数据迁移，收益只是名字好看。这个不一致是有意保留的。
    tongyi_storage_state: str = ""
    # **持久 profile 从第一天就有，不重蹈豆包的覆辙**：豆包是先用临时 profile
    # 上线、抓了两轮才发现「老会话 + 空白设备」这个自相矛盾的组合可能正是
    # 被封的诱因（PHASE2 现象 C）。空值仍会回落到临时目录，但 deploy.sh 会设它
    tongyi_user_data_dir: str = ""
    tongyi_delete_session: bool = True
    screenshot_dir: str = "/data/screenshots"
    # P2-34：截图随结果 multipart 传回来时的单张上限。**必须有上限** ——
    # 没有的话一个跑飞的采集节点就能把 VPS 的盘写满，而那块盘上还有数据库。
    # 8MB 对一张整页 PNG 足够宽裕（实测的在几百 KB 量级）
    screenshot_max_bytes: int = 8_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
