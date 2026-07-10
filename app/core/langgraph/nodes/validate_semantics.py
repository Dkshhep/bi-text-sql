"""节点：轻量语义校验。"""

from __future__ import annotations

from app.core.config import settings
from app.core.context_layer.validator import validate_sql_semantics
from app.core.langgraph.state import GraphState
from app.core.logging import logger


async def validate_semantics(state: GraphState) -> dict:
    if not (settings.CONTEXT_LAYER_ENABLED and settings.SQL_SEMANTIC_VALIDATE_ENABLED):
        return {"error": None}

    docs = [
        *state.get("matched_metrics", []),
        *state.get("matched_rules", []),
        *state.get("matched_relationships", []),
        *state.get("matched_examples", []),
        *state.get("matched_columns", []),
        *state.get("matched_models", []),
    ]
    result = validate_sql_semantics(state.get("sql", ""), docs)
    if result.ok:
        logger.info("validate_semantics_ok")
        return {"error": None, "semantic_warnings": []}

    logger.warning("validate_semantics_warning", warnings=result.warnings, mode=settings.SQL_SEMANTIC_VALIDATE_MODE)
    if settings.SQL_SEMANTIC_VALIDATE_MODE == "enforce":
        return {"error": "SQL 语义校验未通过: " + "；".join(result.warnings), "semantic_warnings": result.warnings}
    return {"error": None, "semantic_warnings": result.warnings}
