"""共用的测试替身。

这里只有一个东西：够 ``app/api/deps.py`` 那几个归属校验走完的最小 Session。
需要它是因为**归属校验是纯查询**（run → task → brand → workspace），
用替身就能验「客户借别家的 id 会不会被挡下」，不必起 Postgres ——
真库那档另有 test_task_rbac_behavior.py，靠 GEO_TEST_DATABASE_URL 开关。

放 conftest 而不是各测试文件里复制：两组测试（responses / crawl-jobs）都要用，
复制两份迟早跟着 deps 的实现漂移。
"""
from __future__ import annotations

from typing import Iterable, Optional

import pytest


class _FakeBrand:
    def __init__(self, workspace_id: int) -> None:
        self.workspace_id = workspace_id


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = list(rows)

    def all(self):
        return self._rows


class FakeSession:
    """按调用顺序回放 scalar 结果，不解析 SQL。

    ``assert_run_visible`` 的链路是两次 ``scalar``（``Run.task_id`` →
    ``Task.brand_id``）加一次 ``get(Brand, id)``；``visible_brand_ids``
    走 ``scalars``。替身只需覆盖这三个方法。

    ``task_id`` / ``brand_id`` 传 ``None`` 表示「这一跳查不到」——
    对应 deps 里那条「不存在与不属于你都返回 404」的分支。
    """

    def __init__(
        self,
        *,
        task_id: Optional[int] = 7,
        brand_id: Optional[int] = 34,
        brand_workspace: Optional[int] = 1,
        brand_ids: Iterable[int] = (),
    ) -> None:
        self._scalars = [task_id, brand_id]
        self._brand_workspace = brand_workspace
        self._brand_ids = list(brand_ids)

    def scalar(self, *_a, **_k):
        return self._scalars.pop(0) if self._scalars else None

    def get(self, _model, _ident):
        if self._brand_workspace is None:
            return None
        return _FakeBrand(self._brand_workspace)

    def scalars(self, *_a, **_k):
        return _FakeResult(self._brand_ids)


@pytest.fixture
def fake_db():
    """``fake_db(brand_workspace=2)`` → 一个「这条 run 属于别家」的 Session。"""
    return FakeSession
