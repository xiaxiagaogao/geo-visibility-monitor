"""建用户（含首个超管）。

「首个超管直接在数据库定义」的可执行形式 —— 密码必须是 argon2 哈希，
手写 SQL 生成不了，所以用这个脚本 INSERT，与手写等价，只是把哈希算对。

    docker exec -it geo-api python -m app.scripts.create_user \
        --email you@example.com --role superadmin

**密码走交互式输入，不接受命令行参数** —— 命令行会进 shell history，
也会出现在同机其他进程可见的 /proc/<pid>/cmdline 里。
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.auth import MIN_PASSWORD_LEN, ROLE_CLIENT, ROLES, hash_password
from app.core.db import SessionLocal
from app.models import User


def main() -> int:
    ap = argparse.ArgumentParser(description="创建用户（不接受命令行传密码）")
    ap.add_argument("--email", required=True)
    ap.add_argument("--role", required=True, choices=list(ROLES))
    ap.add_argument(
        "--workspace-id",
        type=int,
        default=None,
        help="仅 client 需要：该客户能看到的品牌范围（对上 brands.workspace_id）",
    )
    args = ap.parse_args()

    email = args.email.strip().lower()
    if args.role == ROLE_CLIENT and args.workspace_id is None:
        print("client 必须指定 --workspace-id，否则他什么都看不到", file=sys.stderr)
        return 2
    if args.role != ROLE_CLIENT and args.workspace_id is not None:
        print(
            f"{args.role} 看全部数据，--workspace-id 无意义，已忽略",
            file=sys.stderr,
        )

    pw = getpass.getpass("密码: ")
    if len(pw) < MIN_PASSWORD_LEN:
        print(f"密码至少 {MIN_PASSWORD_LEN} 位", file=sys.stderr)
        return 2
    if pw != getpass.getpass("再输一次: "):
        print("两次输入不一致", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        if db.scalars(select(User).where(User.email == email)).first():
            print(f"用户已存在: {email}", file=sys.stderr)
            return 1
        user = User(
            email=email,
            password_hash=hash_password(pw),
            role=args.role,
            workspace_id=args.workspace_id if args.role == ROLE_CLIENT else None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"已创建 id={user.id} email={user.email} role={user.role} "
              f"workspace_id={user.workspace_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
