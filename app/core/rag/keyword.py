"""关键词检索（PostgreSQL 全文 + pg_jieba 中文分词）.

用 ts_rank_cd 作为 BM25 近似打分，与向量检索互补（混合检索的稀疏侧）。
ES 留到后期；当前在同库内用 pg_jieba 即可覆盖中文场景。
"""

from __future__ import annotations

from typing import Any

from app.core.rag import schema_terms

JIEBA_CFG = "jiebacfg"


async def keyword_search(table: str, query: str, top_k: int, db_id: str | None = None) -> list[dict]:
    """全文检索，返回含 _kscore（ts_rank_cd）的行（降序）。"""
    rows = await _plain_keyword_search(table, query, top_k, db_id)
    if rows:
        return rows
    if not schema_terms.schema_terms_enabled_for_table(table):
        return []

    try:
        tokens = await tokenize_query(query)
        terms = await schema_terms.select_schema_terms(query, tokens)
        if not terms:
            _logger().info("keyword_schema_terms_fallback_skipped", table=table, reason="empty_terms", tokens=tokens)
            return []
        fallback_rows = await schema_terms_keyword_search(table, terms, top_k, db_id)
        _logger().info(
            "keyword_schema_terms_fallback",
            table=table,
            tokens=tokens,
            schema_terms=terms,
            result_count=len(fallback_rows),
        )
        return fallback_rows
    except Exception as e:  # noqa: BLE001
        _logger().warning("keyword_schema_terms_fallback_failed", table=table, error=str(e))
        return []


async def _plain_keyword_search(table: str, query: str, top_k: int, db_id: str | None = None) -> list[dict]:
    """Run the original strict keyword search."""
    where_db = "AND db_id = %s" if db_id and table != "rag_chunk" else ""
    params: list[Any] = [query, query]  # tsv @@ query 用一次，ts_rank_cd 用一次
    if where_db:
        params.append(db_id)
    params.append(top_k)
    from app.core.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"""
            SELECT *, ts_rank_cd(tsv, plainto_tsquery('{JIEBA_CFG}', %s)) AS _kscore
            FROM {table}
            WHERE tsv @@ plainto_tsquery('{JIEBA_CFG}', %s)
            {where_db}
            ORDER BY _kscore DESC
            LIMIT %s
            """,
            params,
        )
        cols = [c.name for c in cur.description]
        return [_strip_internal_columns(dict(zip(cols, row, strict=True))) for row in await cur.fetchall()]


async def tokenize_query(query: str) -> list[str]:
    """Tokenize a query with the same pg_jieba config used by keyword indexes."""
    from app.core.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"""
            SELECT lexeme
            FROM (
                SELECT row_number() OVER () AS pos, unnest(lexemes) AS lexeme
                FROM ts_debug('{JIEBA_CFG}', %s)
                WHERE array_length(lexemes, 1) > 0
            ) AS tokens
            GROUP BY lexeme
            ORDER BY min(pos)
            """,
            [query],
        )
        return schema_terms.normalize_tokens(row[0] for row in await cur.fetchall())


async def schema_terms_keyword_search(
    table: str,
    terms: list[str],
    top_k: int,
    db_id: str | None = None,
) -> list[dict]:
    """OR keyword fallback over LLM-filtered backend tokens."""
    terms = schema_terms.normalize_tokens(terms)
    if not terms or top_k <= 0:
        return []

    tsquery_expr = _or_plain_tsquery_expr(len(terms))
    matched_expr = " + ".join(
        f"CASE WHEN tsv @@ plainto_tsquery('{JIEBA_CFG}', %s) THEN 1 ELSE 0 END" for _ in terms
    )
    where_db = "AND db_id = %s" if db_id and table != "rag_chunk" else ""
    min_match = schema_terms.min_match_count(len(terms))
    widened_limit = schema_terms.candidate_limit(top_k)

    params: list[Any] = []
    params.extend(terms)  # ts_rank_cd
    params.extend(terms)  # matched_terms
    params.extend(terms)  # WHERE OR
    if where_db:
        params.append(db_id)
    params.extend([widened_limit, min_match, top_k])
    from app.core.db import get_pool

    pool = await get_pool()
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"""
            WITH candidates AS (
                SELECT
                    *,
                    ts_rank_cd(tsv, {tsquery_expr}) AS _kscore,
                    ({matched_expr}) AS matched_terms
                FROM {table}
                WHERE tsv @@ {tsquery_expr}
                {where_db}
                ORDER BY _kscore DESC
                LIMIT %s
            )
            SELECT *
            FROM candidates
            WHERE matched_terms >= %s
            ORDER BY matched_terms DESC, _kscore DESC, id ASC
            LIMIT %s
            """,
            params,
        )
        cols = [c.name for c in cur.description]
        return [_strip_internal_columns(dict(zip(cols, row, strict=True))) for row in await cur.fetchall()]


def _or_plain_tsquery_expr(term_count: int) -> str:
    return "(" + " || ".join(f"plainto_tsquery('{JIEBA_CFG}', %s)" for _ in range(term_count)) + ")"


def _strip_internal_columns(row: dict) -> dict:
    """Remove database-native helper columns before rows enter LangGraph state."""
    row.pop("embedding", None)
    row.pop("tsv", None)
    return row


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
