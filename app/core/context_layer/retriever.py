"""语义层检索与格式化。"""

from __future__ import annotations

from app.core.config import settings
from app.core.rag import retriever
from app.core.rag.vectorstore import fetch_semantic_docs


async def retrieve_context(db_id: str, queries: list[str]) -> dict:
    """检索业务语义；关闭语义层时返回空上下文。"""
    if not settings.CONTEXT_LAYER_ENABLED:
        return _empty()

    global_docs = await fetch_semantic_docs(db_id, ["global_rule"])
    relationship_docs = await fetch_semantic_docs(db_id, ["relationship"])
    column_docs = await fetch_semantic_docs(db_id, ["column"])
    matched = await retriever.hybrid_search(
        "semantic_doc",
        queries,
        db_id=db_id,
        top_k=min(settings.RETRIEVE_TOP_K, 12),
        do_rerank=True,
    )
    matched = [d for d in matched if d.get("doc_type") != "global_rule"]
    metrics = [d for d in matched if d.get("doc_type") == "metric"]
    rules = [d for d in matched if d.get("doc_type") == "rule"]
    examples = [d for d in matched if d.get("doc_type") == "example"]
    matched_columns = [d for d in matched if d.get("doc_type") == "column"]
    models = [d for d in matched if d.get("doc_type") == "model"]

    return {
        "global_rules": [d.get("payload", {}).get("rule") or d.get("content", "") for d in global_docs],
        "matched_metrics": metrics,
        "matched_rules": rules,
        "matched_relationships": relationship_docs,
        "matched_examples": examples,
        "matched_columns": column_docs,
        "matched_models": models,
        "semantic_context": format_semantic_context([*metrics, *rules, *matched_columns, *models, *examples]),
        "approved_relationships": format_relationships(relationship_docs),
    }


def format_semantic_context(docs: list[dict]) -> str:
    if not docs:
        return "（无）"
    lines = []
    for d in docs[:12]:
        dtype = d.get("doc_type", "context")
        name = d.get("name", "")
        content = d.get("content", "")
        lines.append(f"- [{dtype}] {name}: {content}")
    return "\n".join(lines)


def format_relationships(docs: list[dict]) -> str:
    approved = [d for d in docs if (d.get("payload") or {}).get("approved", True)]
    if not approved:
        return "（无）"
    return "\n".join(f"- {d.get('content', '')}" for d in approved)


def _empty() -> dict:
    return {
        "global_rules": [],
        "matched_metrics": [],
        "matched_rules": [],
        "matched_relationships": [],
        "matched_examples": [],
        "matched_columns": [],
        "matched_models": [],
        "semantic_context": "（无）",
        "approved_relationships": "（无）",
    }
