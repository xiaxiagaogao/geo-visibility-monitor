"""迁移脚本的语句切分（不依赖数据库）。

原实现是 ``sql.split(";")``。分号不只是语句分隔符 —— 它还会出现在注释、
字符串字面量、以及 $$ 函数体里。裸切会把一条语句劈成两半，而报错信息
离现场很远（数据库只会说「语法错误」，不会说「你切错地方了」）。

现有的五个迁移都是简单 DDL，裸切碰巧没出事；这组用例守的是**下一个**
带触发器或默认值的迁移。
"""
from __future__ import annotations

from app.core.schema import _MIGRATIONS, split_statements


def test_simple_ddl_unchanged():
    sql = "ALTER TABLE a ADD COLUMN x INT; ALTER TABLE b ADD COLUMN y TEXT;"
    assert split_statements(sql) == [
        "ALTER TABLE a ADD COLUMN x INT",
        "ALTER TABLE b ADD COLUMN y TEXT",
    ]


def test_semicolon_inside_line_comment_does_not_split():
    sql = """
    -- 见 issue #12; 已修
    ALTER TABLE a ADD COLUMN x INT;
    """
    stmts = split_statements(sql)
    assert len(stmts) == 1
    assert "ADD COLUMN x INT" in stmts[0]


def test_semicolon_inside_string_literal_does_not_split():
    sql = "ALTER TABLE a ADD COLUMN s TEXT DEFAULT 'a;b'; ALTER TABLE b ADD COLUMN t INT;"
    stmts = split_statements(sql)
    assert len(stmts) == 2
    assert "'a;b'" in stmts[0]


def test_escaped_quote_inside_literal():
    sql = "INSERT INTO t VALUES ('it''s; fine'); SELECT 1;"
    stmts = split_statements(sql)
    assert len(stmts) == 2
    assert "it''s; fine" in stmts[0]


def test_dollar_quoted_function_body_stays_whole():
    """PL/pgSQL 函数体里每行都以分号结尾 —— 这是裸切最致命的场景。"""
    sql = """
    CREATE FUNCTION bump() RETURNS trigger AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    CREATE INDEX idx_x ON t(x);
    """
    stmts = split_statements(sql)
    assert len(stmts) == 2, f"函数体被切碎了：{stmts}"
    assert "RETURN NEW" in stmts[0] and "LANGUAGE plpgsql" in stmts[0]
    assert stmts[1].startswith("CREATE INDEX")


def test_trailing_statement_without_semicolon():
    assert split_statements("SELECT 1; SELECT 2") == ["SELECT 1", "SELECT 2"]


def test_blank_and_comment_only_input():
    assert split_statements("") == []
    assert split_statements("   ;;  ") == []


def _has_tricky_construct(sql: str) -> bool:
    """含 $$ 函数体、或注释/字符串里带分号 —— 这些正是裸切会切错的地方。"""
    if "$$" in sql:
        return True
    for line in sql.splitlines():
        head, _, comment = line.partition("--")
        if ";" in comment:
            return True
        if head.count("'") >= 2 and ";" in head[head.index("'") : head.rindex("'")]:
            return True
    return False


def test_existing_simple_migrations_split_identically():
    """回归：换实现不能改变现有迁移的切分结果。

    只对**不含 tricky 结构**的迁移做等价断言 —— 将来有人加带 $$ 函数体的
    迁移时，新旧实现本就该不一致（那正是这次改动的目的），
    不该因此让这条测试变成拦路虎。
    """
    checked = 0
    for mid, sql in _MIGRATIONS:
        if _has_tricky_construct(sql):
            continue
        naive = [s.strip() for s in sql.strip().split(";") if s.strip()]
        assert split_statements(sql) == naive, f"{mid} 的切分结果变了"
        checked += 1
    assert checked > 0, "至少要覆盖到一个现有迁移，否则这条回归是空跑"
