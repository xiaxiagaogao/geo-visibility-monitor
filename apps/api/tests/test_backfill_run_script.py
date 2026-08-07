"""历史数据回填脚本（不依赖数据库）—— 只验安全默认与「别用错工具」。

这个脚本会建 Task/Run、批量改 crawl_jobs.run_id 这个外键，比
data_governance_min.py 危险得多（那个只删已判定为垃圾的行）。
所以这里反过来：默认只读，--apply 才写库。测的就是这两条：
默认不会碰到写库分支，且写库必须靠显式 --apply 打开。

另外一条最容易被后人改错的地方单独钉住：脚本不能 import/调用
services.tasks.create_run —— 它会再建一批新 job，而回填要的是把
旧 job 挂上去，用 create_run 会导致这 35 条历史样本被复制、
crawl_jobs 表里凭空多出一批从未真正抓取过的 job。
"""
from __future__ import annotations

import ast
import inspect

from app.scripts import backfill_run


def test_does_not_import_or_call_create_run():
    """回填要把旧 job 挂上去，不是再建一批新 job —— create_run 两者都做不到前者。

    脚本里刻意留了一句提醒这件事的注释（含 "create_run" 字样作为文档），
    所以不能直接 grep 整个源码字符串；解析成 AST 再查——注释本就不在 AST 里，
    只会查到真正的 import 语句和函数调用。
    """
    assert not hasattr(backfill_run, "create_run"), (
        "backfill_run 模块命名空间里不该有 create_run —— 说明它被 import 进来了"
    )

    tree = ast.parse(inspect.getsource(backfill_run))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "create_run" not in imported_names, "不能 import create_run"

    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "create_run" not in called_names, (
        "不能调用 create_run()：它会为每条提问×平台×采样建新 job，"
        "回填要的是把已存在的无主 job 挂上新 run，语义完全不同"
    )


def test_apply_flag_exists_and_defaults_to_off():
    """--apply 必须存在，且不加参数时是 False —— 默认只读。"""
    ap = backfill_run._build_arg_parser()
    args = ap.parse_args(["--brand-id", "34"])
    assert hasattr(args, "apply"), "必须有 --apply 开关"
    assert args.apply is False, "不加 --apply 时必须是关闭状态（只读）"


def test_apply_flag_turns_on_explicitly():
    ap = backfill_run._build_arg_parser()
    args = ap.parse_args(["--brand-id", "34", "--apply"])
    assert args.apply is True


def test_dry_run_flag_removed():
    """--dry-run 已删除：默认即只读，不需要一个和 --apply 语义可能打架的开关。"""
    ap = backfill_run._build_arg_parser()
    try:
        ap.parse_args(["--brand-id", "34", "--dry-run"])
    except SystemExit:
        pass
    else:
        raise AssertionError("--dry-run 不应再被接受")


def test_main_does_not_write_without_apply():
    """不加 --apply 时，main() 的写库分支必须整体不可达 —— 用源码结构守住这条，
    而不是跑一遍指望它「碰巧」没写：即便本机没有数据库连接，这条也要能验证。

    main() 里 `if not args.apply:` 之后必须 return，且写库（db.add(task) /
    db.commit()）的代码必须在这个 return 之后 —— 静态确认执行不到那里。
    """
    src = inspect.getsource(backfill_run.main)
    idx_guard = src.index("if not args.apply:")
    idx_return = src.index("return", idx_guard)
    idx_task_write = src.index("Task(")
    assert idx_guard < idx_return < idx_task_write, (
        "--apply 的判断必须先于任何写库代码，且判断为 False 时要 return"
    )


def test_preview_runs_before_any_write_branch():
    """预览（_print_plan）必须在写库分支之前执行 —— 不然「先看后写」的顺序保证不了。"""
    src = inspect.getsource(backfill_run.main)
    idx_plan = src.index("_print_plan(")
    idx_apply_check = src.index("if not args.apply:")
    idx_task_write = src.index("Task(")
    assert idx_plan < idx_apply_check < idx_task_write


def test_plan_reports_no_op_when_no_orphans():
    """一条无主 job 都没有时，输出要明确说「无事可做」，不能只是数字 0 让人自己猜。"""
    src = inspect.getsource(backfill_run._print_plan)
    assert "无事可做" in src
