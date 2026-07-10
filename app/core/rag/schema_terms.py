"""Schema-aware keyword terms for sparse retrieval fallback."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable

from app.core.config import settings
from app.core.langgraph.prompts import SCHEMA_TERMS_FILTER_PROMPT

_UNSAFE_TERM_CHARS = re.compile(r"[&|!:*()<>\"']")
_DEFAULT_REJECT_TERMS = {
    "查询",
    "显示",
    "列出",
    "信息",
    "前",
    "名",
    "个",
    "所有",
    "哪些",
    "排名",
    "平均",
    "总数",
    "最高",
    "最低",
    "数量",
}


def schema_terms_enabled_for_table(table: str) -> bool:
    """Return whether schema-term fallback is enabled for a retrieval table."""
    return {
        "schema_doc": settings.KEYWORD_SCHEMA_TERMS_SCHEMA_DOC_ENABLED,
        "fewshot_example": settings.KEYWORD_SCHEMA_TERMS_FEWSHOT_ENABLED,
        "rag_chunk": settings.KEYWORD_SCHEMA_TERMS_RAG_CHUNK_ENABLED,
    }.get(table, False)


def min_match_count(term_count: int, ratio: float | None = None) -> int:
    """Calculate the minimum number of schema terms that a candidate must match."""
    if term_count <= 0:
        return 0
    ratio = settings.KEYWORD_SCHEMA_TERMS_MIN_MATCH_RATIO if ratio is None else ratio
    return max(1, math.ceil(term_count * ratio))


def candidate_limit(top_k: int) -> int:
    """Return the widened candidate limit used before threshold filtering."""
    return max(top_k, top_k * settings.KEYWORD_SCHEMA_TERMS_CANDIDATE_MULTIPLIER)


def normalize_tokens(tokens: Iterable[str]) -> list[str]:
    """Deduplicate non-empty backend tokens while preserving backend order."""
    out: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        t = str(token).strip()
        if not t or t in seen or not is_safe_term(t):
            continue
        seen.add(t)
        out.append(t)
    return out


def parse_schema_terms_response(text: str, backend_tokens: Iterable[str]) -> list[str]:
    """Parse and constrain LLM output to backend tokens only."""
    tokens = normalize_tokens(backend_tokens)
    token_set = set(tokens)
    try:
        payload = json.loads(_strip_json_fence(text))
    except json.JSONDecodeError:
        _logger().warning("schema_terms_parse_failed", text=text[:200])
        return []

    raw_terms = payload.get("schema_terms", []) if isinstance(payload, dict) else []
    if not isinstance(raw_terms, list):
        return []

    selected = {str(term).strip() for term in raw_terms if isinstance(term, str)}
    selected = {term for term in selected if term in token_set and is_schema_candidate_term(term)}
    return [token for token in tokens if token in selected]


async def select_schema_terms(question: str, backend_tokens: Iterable[str]) -> list[str]:
    """Ask the LLM to filter backend tokens into schema terms."""
    from langchain_core.messages import HumanMessage

    from app.services import llm

    tokens = normalize_tokens(backend_tokens)
    if not tokens:
        return []

    prompt = SCHEMA_TERMS_FILTER_PROMPT.format(question=question, tokens=json.dumps(tokens, ensure_ascii=False))
    text = await llm.ainvoke([HumanMessage(content=prompt)], temperature=0.0, json_mode=True)
    terms = parse_schema_terms_response(text, tokens)
    _logger().info("schema_terms_selected", token_count=len(tokens), terms=terms)
    return terms


def sort_schema_term_rows(rows: list[dict]) -> list[dict]:
    """Sort fallback rows by matched terms, keyword score, and id."""
    return sorted(rows, key=lambda r: (-int(r.get("matched_terms") or 0), -float(r.get("_kscore") or 0), int(r["id"])))


def is_safe_term(term: str) -> bool:
    """Reject terms that would be unsafe or ambiguous in backend query syntaxes."""
    return bool(term.strip()) and not _UNSAFE_TERM_CHARS.search(term)


def is_schema_candidate_term(term: str) -> bool:
    """Apply deterministic guardrails after LLM filtering."""
    return is_safe_term(term) and term not in _DEFAULT_REJECT_TERMS


def _strip_json_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _logger():
    try:
        from app.core.logging import logger

        return logger
    except Exception:  # noqa: BLE001
        return _FallbackLogger(__name__)


class _FallbackLogger:
    def __init__(self, name: str) -> None:
        import logging

        self._logger = logging.getLogger(name)

    def info(self, event: str, **kwargs) -> None:
        self._logger.info("%s %s", event, kwargs)

    def warning(self, event: str, **kwargs) -> None:
        self._logger.warning("%s %s", event, kwargs)
