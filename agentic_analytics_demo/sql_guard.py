from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "attach",
    "detach",
    "pragma",
    "replace",
    "vacuum",
    "create",
    "truncate",
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    sql: str
    error: str = ""


def clean_sql(raw_sql: str) -> str:
    sql = raw_sql.strip()
    sql = re.sub(r"^```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
    sql = re.sub(r"```$", "", sql).strip()
    return sql


def validate_sql(raw_sql: str, db_path: Path, max_rows: int = 500) -> ValidationResult:
    sql = clean_sql(raw_sql)
    if not sql:
        return ValidationResult(False, sql, "SQL 为空。")
    if "--" in sql or "/*" in sql or "*/" in sql:
        return ValidationResult(False, sql, "SQL 中不允许出现注释。")

    statements = [part.strip() for part in sql.split(";") if part.strip()]
    if len(statements) != 1:
        return ValidationResult(False, sql, "只允许单条 SQL 语句。")
    sql = statements[0]

    first_token = sql.lstrip().split(maxsplit=1)[0].lower()
    if first_token not in {"select", "with"}:
        return ValidationResult(False, sql, "只允许 SELECT 或 WITH 查询。")

    tokens = set(re.findall(r"\b[a-z_]+\b", sql.lower()))
    blocked = sorted(tokens & FORBIDDEN)
    if blocked:
        return ValidationResult(False, sql, f"SQL 包含禁止关键字: {', '.join(blocked)}。")

    limited_sql = _enforce_limit(sql, max_rows)
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute(f"EXPLAIN QUERY PLAN {limited_sql}")
    except sqlite3.Error as exc:
        return ValidationResult(False, limited_sql, f"SQL 无法通过 SQLite 校验: {exc}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return ValidationResult(True, limited_sql)


def _enforce_limit(sql: str, max_rows: int) -> str:
    if re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
        return sql
    return f"{sql.rstrip()} LIMIT {max_rows}"

