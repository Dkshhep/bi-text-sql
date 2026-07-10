"""Elasticsearch BM25 关键词检索后端（pg_jieba 的可选替代）.

当 RETRIEVAL_BACKEND=es 时，混合检索的稀疏侧改用 Elasticsearch：
- ES 内建 BM25 与成熟的中文分析器（需在索引时配置 ik / smartcn analyzer）；
- 文档由 `eval/sync_es.py` 从 PostgreSQL 批量同步（ES 作为搜索镜像，id 与 PG 一致）。

返回结构与 `keyword.keyword_search` 对齐（含 id / content / _kscore），
使 retriever 可无缝切换后端。elasticsearch 客户端惰性导入，未装则报错由上层兜底。
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.rag import schema_terms


@lru_cache
def _client():
    from elasticsearch import AsyncElasticsearch

    return AsyncElasticsearch(hosts=[f"http://{settings.ES_HOST}:{settings.ES_PORT}"])


def index_name(table: str) -> str:
    return f"{settings.ES_INDEX_PREFIX}_{table}"


async def keyword_search(table: str, query: str, top_k: int, db_id: str | None = None) -> list[dict]:
    """ES BM25 检索，返回含 _kscore（_score）的行。"""
    rows = await _plain_keyword_search(table, query, top_k, db_id)
    if rows:
        return rows
    if not schema_terms.schema_terms_enabled_for_table(table):
        return []

    try:
        tokens = await tokenize_query(table, query)
        terms = await schema_terms.select_schema_terms(query, tokens)
        if not terms:
            _logger().info("es_keyword_schema_terms_fallback_skipped", table=table, reason="empty_terms", tokens=tokens)
            return []
        fallback_rows = await schema_terms_keyword_search(table, terms, top_k, db_id)
        _logger().info(
            "es_keyword_schema_terms_fallback",
            table=table,
            tokens=tokens,
            schema_terms=terms,
            result_count=len(fallback_rows),
        )
        return fallback_rows
    except Exception as e:  # noqa: BLE001
        _logger().warning("es_keyword_schema_terms_fallback_failed", table=table, error=str(e))
        return []


async def _plain_keyword_search(table: str, query: str, top_k: int, db_id: str | None = None) -> list[dict]:
    """Run the original ES keyword search."""
    must: list[dict] = [{"match": {"content": query}}]
    filt: list[dict] = []
    if db_id and table != "rag_chunk":
        filt.append({"term": {"db_id": db_id}})

    resp = await _client().search(
        index=index_name(table),
        size=top_k,
        query={"bool": {"must": must, "filter": filt}},
    )
    out = []
    for hit in resp["hits"]["hits"]:
        row = dict(hit["_source"])
        row["id"] = int(hit["_id"])
        row["_kscore"] = hit["_score"]
        out.append(row)
    return out


async def tokenize_query(table: str, query: str) -> list[str]:
    """Tokenize a query with the ES analyzer attached to the target index."""
    resp = await _client().indices.analyze(index=index_name(table), text=query)
    return schema_terms.normalize_tokens(token["token"] for token in resp.get("tokens", []))


async def schema_terms_keyword_search(
    table: str,
    terms: list[str],
    top_k: int,
    db_id: str | None = None,
) -> list[dict]:
    """OR keyword fallback over LLM-filtered ES analyzer tokens."""
    terms = schema_terms.normalize_tokens(terms)
    if not terms or top_k <= 0:
        return []

    min_match = schema_terms.min_match_count(len(terms))
    should = [{"match": {"content": {"query": term, "_name": f"term_{i}"}}} for i, term in enumerate(terms)]
    filt: list[dict] = []
    if db_id and table != "rag_chunk":
        filt.append({"term": {"db_id": db_id}})

    resp = await _client().search(
        index=index_name(table),
        size=schema_terms.candidate_limit(top_k),
        query={
            "bool": {
                "should": should,
                "minimum_should_match": min_match,
                "filter": filt,
            }
        },
    )
    out = []
    max_score = resp["hits"].get("max_score") or 1.0
    for hit in resp["hits"]["hits"]:
        row = dict(hit["_source"])
        row["id"] = int(hit["_id"])
        row["_kscore"] = (hit["_score"] or 0.0) / max_score
        row["matched_terms"] = len(hit.get("matched_queries", []))
        out.append(row)
    return schema_terms.sort_schema_term_rows(out)[:top_k]


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
