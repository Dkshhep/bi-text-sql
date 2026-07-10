"""节点：检索文件式业务语义层。"""

from __future__ import annotations

from app.core.context_layer.retriever import retrieve_context
from app.core.langgraph.state import GraphState
from app.core.logging import logger


async def retrieve_semantics(state: GraphState) -> dict:
    db_id = state.get("db_id", "")
    primary = state.get("rewritten_question") or state["question"]
    queries = [primary, *state.get("expanded_queries", [])]
    result = await retrieve_context(db_id, queries)
    logger.info(
        "semantic_context_retrieved",
        db_id=db_id,
        metrics=len(result.get("matched_metrics", [])),
        rules=len(result.get("matched_rules", [])),
        relationships=len(result.get("matched_relationships", [])),
        examples=len(result.get("matched_examples", [])),
        global_rules=len(result.get("global_rules", [])),
    )
    return result
