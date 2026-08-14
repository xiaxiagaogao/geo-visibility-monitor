"""发起 run 时可以带口径说明（不依赖数据库）。

背景：`run.note` 是「这一次的口径和别的不一样」的唯一落点 ——
比如「采集出口已迁至大陆」「本次未采集截图」。而在此之前**没有任何接口
能写它**（`/v1/runs/{id}` 只有 GET），于是 2026-08-14 迁移采集出口那次，
基线断点就没记上，run 215 的 note 至今是 null。

这组用例守两件事：body 是**可选**的（老调用方不能被打断），
以及 note 在**创建时**写入而不是建完再补。
"""
from __future__ import annotations

import inspect

from app.api import tasks as tasks_api
from app.schemas.task import RunCreate
from app.services import tasks as task_svc


def test_body_is_optional():
    """老调用方不带 body 照样能发起 —— 加字段不该让现有调用变成 422。

    前端的 `startRun` 和运维脚本都是不带 body 直接 POST 的。
    """
    sig = inspect.signature(tasks_api.start_run)
    body = sig.parameters["body"]
    assert body.default is None, "body 必须有默认值 None，否则变成必填"
    assert "Optional" in str(body.annotation) or "None" in str(body.annotation)


def test_note_is_optional_and_bounded():
    assert RunCreate().note is None
    assert RunCreate(note="采集出口已迁至大陆").note == "采集出口已迁至大陆"
    # 上界是输入卫生 —— Run.note 是 Text，库里不限长，但接口不该收无限长的串
    field = RunCreate.model_fields["note"]
    assert any(getattr(m, "max_length", None) for m in field.metadata)


def test_create_run_takes_note():
    sig = inspect.signature(task_svc.create_run)
    assert "note" in sig.parameters
    assert sig.parameters["note"].default is None


def test_note_written_at_creation_not_patched_after():
    """note 必须在构造 Run 时就写进去。

    分成「先建 run，再 UPDATE note」两步的话，中间会出现一个
    「run 已存在但口径说明还没写」的状态 —— 而发起与口径说明本来就是同一件事。
    """
    src = inspect.getsource(task_svc.create_run)
    ctor = src[src.index("Run("):src.index(")", src.index("Run("))]
    assert "note=" in ctor, "note 要在 Run(...) 构造里传，不是建完再赋值"


def test_route_passes_note_through():
    src = inspect.getsource(tasks_api.start_run)
    assert "body.note" in src, "路由必须把 note 传给 create_run"
    # 不带 body 时要退化成 None，而不是抛 AttributeError
    assert "if body else None" in src or "body is not None" in src


def test_empty_string_becomes_null():
    """空串和「没填」是一回事 —— 别在库里留一行空的 note。"""
    src = inspect.getsource(task_svc.create_run)
    assert "note or None" in src
