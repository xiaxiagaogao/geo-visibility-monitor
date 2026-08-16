"""通义千问 Provider 的接线与常量（P2-06b）。不需要 playwright，本机可跑。

选择器与判定**全部来自 2026-08-16 在采集节点上的实测**（PHASE2「P2-06b 第 0 步」），
不是照抄 DeepSeek 或豆包 —— 三家的 DOM 没有一处是通用的。

平台代码是 `tongyi`、站点是 `qianwen.com`：阿里把产品改名叫「千问」，
但代码已经在 `ALLOWED_PLATFORMS` 与历史数据里，改它等于一次数据迁移，
收益只是名字好看。**这个不一致是有意保留的。**
"""
from __future__ import annotations

from app.core.config import Settings


# ---------------------------------------------------------------- 凭证接线


def test_settings_have_a_tongyi_storage_state():
    """多一个平台就多一份会悄悄过期的凭证。

    漏了这个字段的话，登录态根本没有地方可以配，
    而表现是「每一条抓取都失败在登录页」—— 排查方向完全跑偏。
    """
    s = Settings()
    assert hasattr(s, "tongyi_storage_state")


def test_settings_have_a_tongyi_user_data_dir():
    """**持久 profile 从第一天就要有。**

    豆包是先用临时 profile 上线、抓了两轮才发现「老会话 + 空白设备」
    这个自相矛盾的组合可能正是被封的诱因（PHASE2 现象 C）。
    千问不重蹈：这个字段一开始就在，deploy.sh 一开始就设。
    """
    s = Settings()
    assert hasattr(s, "tongyi_user_data_dir")


def test_credential_health_covers_tongyi():
    """漏登记的话 `GET /v1/health/credentials` 里根本不会出现千问这一行 ——
    而「少一行」比「报红」更难发现。"""
    from app.services.credential_health import _STORAGE_SETTING

    assert _STORAGE_SETTING["tongyi"] == "tongyi_storage_state"


def test_export_script_knows_tongyi():
    """`scripts/export_storage_state.py` 的 PLATFORMS 是「加平台只改这里」的那个表。

    漏了它，登录态**没有任何办法导出** —— provider 写得再对也跑不起来。
    入口用 `qianwen.com`：`tongyi.com` 只是 302 跳过来（实测 `?ch=tongyi_redirect`）。

    ⚠️ **用 ast 静态解析，绝不 import 那个脚本。** 它顶层
    `from playwright.sync_api import sync_playwright`，而 **api 容器里没装
    playwright**（它不跑抓取）—— import 一下整条测试就挂。
    这条约束 `services/failure_kinds._has_type` 的 docstring 已经写过一次，
    2026-08-16 我在这里又踩了一遍：本机 venv 有 playwright 所以本机是绿的，
    只有 VPS 真环境跑全量才抓得到。**这就是为什么真库档不能只在本机跑。**
    """
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[3]
           / "scripts" / "export_storage_state.py").read_text(encoding="utf-8")
    table = next(
        node.value
        for node in ast.parse(src).body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "PLATFORMS" for t in node.targets)
    )
    platforms = ast.literal_eval(table)

    cfg = platforms["tongyi"]
    assert cfg["url"].startswith("https://www.qianwen.com")
    assert cfg["out"] == "tongyi_storage.json"
    # **不为新平台瞎写登录检测器**（同豆包）：检测错了会在你还没登完时
    # 就导出一份空会话，而空会话拿去采集的表现是「一批 job 全 failed」
    assert cfg["detect"] is None
