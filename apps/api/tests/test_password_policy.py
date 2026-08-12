"""密码最短长度：**只能有一个定义处**（不依赖数据库）。

背景：``api/users.py`` 与 ``scripts/create_user.py`` 原先各写了一份
``MIN_PASSWORD_LEN = 12``，谁也不知道对方存在。这种重复不会报错，
只会在某天只改一边之后，让「API 收得下的密码，脚本拒绝」——
两边都正常运行，只是行为对不上，而且没有任何地方会提示你。

所以这组用例守的不是「阈值是多少」（那是产品决策，会变），
而是**两条路径必须共用同一个常量**。
"""
from __future__ import annotations

import inspect

from app.api import users as users_api
from app.core.auth import MIN_PASSWORD_LEN
from app.scripts import create_user


def test_single_source_of_truth():
    """两个调用方拿到的必须是 core.auth 那一个对象。"""
    assert users_api.MIN_PASSWORD_LEN is MIN_PASSWORD_LEN
    assert create_user.MIN_PASSWORD_LEN is MIN_PASSWORD_LEN


def test_no_local_redefinition():
    """import 进来之后又在本地赋值，上面那条断言照样过 —— 这条堵住它。"""
    for mod in (users_api, create_user):
        src = inspect.getsource(mod)
        assert "MIN_PASSWORD_LEN =" not in src, (
            f"{mod.__name__} 不该自己定义 MIN_PASSWORD_LEN，应从 app.core.auth 导入"
        )


def test_schemas_reference_the_constant_not_a_literal():
    """约束写死字面量的话，上面两条都逮不到 —— Pydantic 的 Field 是在类定义时
    求值的，改了常量而字面量没跟着改，模型行为不会变。

    这里查源码而不是 model_fields 的 metadata：后者在 ``Optional[str]`` 上的
    存放位置随 Pydantic 版本变过，把用例绑到那个内部结构上，
    将来升级会挂在一个和密码策略毫无关系的地方。
    """
    src = inspect.getsource(users_api)
    assert src.count("min_length=MIN_PASSWORD_LEN") == 2, (
        "UserCreate.password 与 UserUpdate.password 都要用这个常量"
    )
    # 改密码和建用户必须同一个门槛 —— 只卡建用户的话，
    # 建完再 PATCH 一次就能绕过去
    assert "password: str = Field(..., min_length=MIN_PASSWORD_LEN)" in src
    assert "password: Optional[str] = Field(None, min_length=MIN_PASSWORD_LEN)" in src


def test_script_checks_length_too():
    """脚本走 getpass 不过 Pydantic，长度得自己判。"""
    src = inspect.getsource(create_user)
    assert "len(pw) < MIN_PASSWORD_LEN" in src


def test_threshold_is_at_least_eight():
    """阈值本身会变（产品决策），但不该低到形同虚设。"""
    assert MIN_PASSWORD_LEN >= 8
