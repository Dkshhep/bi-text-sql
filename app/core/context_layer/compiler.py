"""把文件式语义层编译为可检索文档。"""

from __future__ import annotations

from typing import Any

from app.core.context_layer.parser import ContextBundle


def compile_semantic_docs(bundle: ContextBundle) -> list[dict[str, Any]]:
    """生成 semantic_doc rows，不做 embedding/DB 写入。"""
    rows: list[dict[str, Any]] = []
    rows.extend(_compile_models(bundle))
    rows.extend(_compile_metrics(bundle))
    rows.extend(_compile_relationships(bundle))
    rows.extend(_compile_rules(bundle))
    rows.extend(_compile_examples(bundle))
    return rows


def compile_fewshots(bundle: ContextBundle) -> list[dict[str, Any]]:
    """生成 confirmed examples 对应的 fewshot rows。"""
    rows = []
    for ex in bundle.examples:
        rows.append(
            {
                "db_id": ex["db_id"] or bundle.db_id,
                "question": ex["question"],
                "sql": ex["sql"],
                "metadata": {
                    "source": ex.get("source") or "manual",
                    "context_db_id": bundle.db_id,
                    "filename": ex.get("filename"),
                },
            }
        )
    return rows


def global_rules(bundle: ContextBundle) -> list[dict[str, Any]]:
    return [
        {
            "db_id": bundle.db_id,
            "doc_type": "global_rule",
            "name": f"global_rule_{i}",
            "content": rule,
            "payload": {"rule": rule, "scope": "global"},
        }
        for i, rule in enumerate(bundle.global_rules, start=1)
    ]


def _compile_models(bundle: ContextBundle) -> list[dict[str, Any]]:
    rows = []
    for model in bundle.models:
        table = str(model.get("table") or "").strip()
        if not table:
            continue
        description = str(model.get("description") or "").strip()
        columns = model.get("columns") or []
        rows.append(
            {
                "db_id": bundle.db_id,
                "doc_type": "model",
                "name": table,
                "content": f"业务模型 {table}: {description}".strip(),
                "payload": model,
            }
        )
        for col in columns:
            name = str(col.get("name") or "").strip()
            if not name:
                continue
            alias = str(col.get("alias") or "").strip()
            desc = str(col.get("description") or "").strip()
            flags = []
            if col.get("hidden"):
                flags.append("隐藏字段")
            if col.get("sensitive"):
                flags.append("敏感字段")
            content = "；".join(
                part
                for part in [
                    f"字段 {table}.{name}",
                    f"别名 {alias}" if alias else "",
                    desc,
                    "、".join(flags),
                ]
                if part
            )
            payload = {**col, "table": table}
            rows.append(
                {
                    "db_id": bundle.db_id,
                    "doc_type": "column",
                    "name": f"{table}.{name}",
                    "content": content,
                    "payload": payload,
                }
            )
    return rows


def _compile_metrics(bundle: ContextBundle) -> list[dict[str, Any]]:
    rows = []
    for metric in bundle.metrics:
        name = str(metric.get("name") or "").strip()
        if not name:
            continue
        alias = str(metric.get("alias") or "").strip()
        desc = str(metric.get("description") or "").strip()
        expr = str(metric.get("expression") or "").strip()
        filters = "；".join(metric.get("default_filters") or [])
        dims = "、".join(metric.get("dimensions") or [])
        content = (
            f"指标 {name}"
            + (f"（{alias}）" if alias else "")
            + f": {desc}。计算口径: {expr}。默认过滤: {filters or '无'}。可用维度: {dims or '无'}。"
        )
        rows.append(
            {
                "db_id": bundle.db_id,
                "doc_type": "metric",
                "name": name,
                "content": content,
                "payload": metric,
            }
        )
    return rows


def _compile_relationships(bundle: ContextBundle) -> list[dict[str, Any]]:
    rows = []
    for rel in bundle.relationships:
        name = str(rel.get("name") or rel.get("condition") or "").strip()
        if not name:
            continue
        condition = str(rel.get("condition") or "").strip()
        models = "、".join(str(m) for m in rel.get("models") or [])
        approved = "已审批" if rel.get("approved", True) else "未审批"
        rows.append(
            {
                "db_id": bundle.db_id,
                "doc_type": "relationship",
                "name": name,
                "content": f"审批连接路径 {name}: {models}; 条件: {condition}; 状态: {approved}",
                "payload": rel,
            }
        )
    return rows


def _compile_rules(bundle: ContextBundle) -> list[dict[str, Any]]:
    rows = global_rules(bundle)
    for i, rule in enumerate(bundle.contextual_rules, start=1):
        rows.append(
            {
                "db_id": bundle.db_id,
                "doc_type": "rule",
                "name": f"contextual_rule_{i}",
                "content": f"上下文业务规则: {rule}",
                "payload": {"rule": rule, "scope": "contextual"},
            }
        )
    return rows


def _compile_examples(bundle: ContextBundle) -> list[dict[str, Any]]:
    rows = []
    for ex in bundle.examples:
        rows.append(
            {
                "db_id": ex["db_id"] or bundle.db_id,
                "doc_type": "example",
                "name": ex["question"],
                "content": f"已确认查询示例: {ex['question']}\nSQL: {ex['sql']}",
                "payload": ex,
            }
        )
    return rows
