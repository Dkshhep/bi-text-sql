"""轻量 SQL 语义校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp


@dataclass
class SemanticValidationResult:
    ok: bool
    warnings: list[str] = field(default_factory=list)


def validate_sql_semantics(sql: str, semantic_docs: list[dict[str, Any]]) -> SemanticValidationResult:
    """检查 hidden/sensitive 字段、approved joins 和命中指标默认过滤。"""
    if not semantic_docs:
        return SemanticValidationResult(ok=True)

    warnings: list[str] = []
    try:
        stmt = sqlglot.parse_one(sql)
    except Exception as e:  # noqa: BLE001
        return SemanticValidationResult(ok=False, warnings=[f"语义校验无法解析 SQL: {e}"])

    columns = _referenced_columns(stmt)
    table_pairs = _join_table_pairs(stmt)
    hidden = _flagged_columns(semantic_docs, "hidden")
    sensitive = _flagged_columns(semantic_docs, "sensitive")

    for col in sorted(columns):
        if col in hidden:
            warnings.append(f"SQL 使用了隐藏字段: {col}")
        if col in sensitive:
            warnings.append(f"SQL 使用了敏感字段: {col}")

    approved_pairs = _approved_table_pairs(semantic_docs)
    if approved_pairs and table_pairs:
        for pair in sorted(table_pairs):
            if pair not in approved_pairs:
                warnings.append(f"SQL 使用了未审批 JOIN 表对: {' <-> '.join(pair)}")

    lowered_sql = _compact(sql)
    for doc in semantic_docs:
        if doc.get("doc_type") != "metric":
            continue
        payload = doc.get("payload") or {}
        for filt in payload.get("default_filters") or []:
            if _compact(str(filt)) not in lowered_sql:
                warnings.append(f"命中指标 {doc.get('name')} 但 SQL 可能缺少默认过滤: {filt}")

    return SemanticValidationResult(ok=not warnings, warnings=warnings)


def _referenced_columns(stmt: exp.Expression) -> set[str]:
    cols = set()
    for col in stmt.find_all(exp.Column):
        table = col.table
        name = col.name
        cols.add(f"{table}.{name}" if table else name)
    return cols


def _join_table_pairs(stmt: exp.Expression) -> set[tuple[str, str]]:
    base_tables = [t.name for t in stmt.find_all(exp.Table)]
    if len(base_tables) < 2:
        return set()
    pairs = set()
    first = base_tables[0]
    for table in base_tables[1:]:
        pairs.add(tuple(sorted((first, table))))
    return pairs


def _flagged_columns(docs: list[dict[str, Any]], flag: str) -> set[str]:
    out = set()
    for doc in docs:
        if doc.get("doc_type") != "column":
            continue
        payload = doc.get("payload") or {}
        if payload.get(flag):
            table = payload.get("table")
            name = payload.get("name") or doc.get("name")
            out.add(f"{table}.{name}" if table and "." not in str(name) else str(name))
            out.add(str(name))
    return out


def _approved_table_pairs(docs: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs = set()
    for doc in docs:
        if doc.get("doc_type") != "relationship":
            continue
        payload = doc.get("payload") or {}
        if not payload.get("approved", True):
            continue
        models = payload.get("models") or []
        if len(models) >= 2:
            pairs.add(tuple(sorted((str(models[0]), str(models[1])))))
            continue
        condition = str(payload.get("condition") or "")
        tables = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\.", condition)
        if len(tables) >= 2:
            pairs.add(tuple(sorted((tables[0], tables[1]))))
    return pairs


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()
