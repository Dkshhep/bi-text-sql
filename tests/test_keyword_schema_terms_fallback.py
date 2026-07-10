import asyncio

from app.core.rag import keyword


def test_keyword_search_returns_original_results_without_fallback(monkeypatch):
    calls = {"tokenize": 0}

    async def plain(*_args, **_kwargs):
        return [{"id": 1, "content": "schema", "_kscore": 0.4}]

    async def tokenize(*_args, **_kwargs):
        calls["tokenize"] += 1
        return ["学生"]

    monkeypatch.setattr(keyword, "_plain_keyword_search", plain)
    monkeypatch.setattr(keyword, "tokenize_query", tokenize)

    rows = asyncio.run(keyword.keyword_search("schema_doc", "查询学生信息", 5))

    assert rows == [{"id": 1, "content": "schema", "_kscore": 0.4}]
    assert calls["tokenize"] == 0


def test_keyword_search_schema_doc_default_fallback(monkeypatch):
    calls = {"tokenize": 0, "select": 0, "fallback": 0}

    async def plain(*_args, **_kwargs):
        return []

    async def tokenize(query):
        calls["tokenize"] += 1
        assert query == "查询成绩排名前5名的学生信息"
        return ["查询", "成绩", "排名", "前", "名", "学生", "信息"]

    async def select(question, tokens):
        calls["select"] += 1
        assert question == "查询成绩排名前5名的学生信息"
        assert tokens == ["查询", "成绩", "排名", "前", "名", "学生", "信息"]
        return ["成绩", "学生"]

    async def fallback(table, terms, top_k, db_id=None):
        calls["fallback"] += 1
        assert table == "schema_doc"
        assert terms == ["成绩", "学生"]
        assert top_k == 5
        assert db_id is None
        return [{"id": 2, "matched_terms": 2, "_kscore": 0.2}]

    monkeypatch.setattr(keyword, "_plain_keyword_search", plain)
    monkeypatch.setattr(keyword, "tokenize_query", tokenize)
    monkeypatch.setattr(keyword.schema_terms, "select_schema_terms", select)
    monkeypatch.setattr(keyword, "schema_terms_keyword_search", fallback)

    rows = asyncio.run(keyword.keyword_search("schema_doc", "查询成绩排名前5名的学生信息", 5))

    assert rows == [{"id": 2, "matched_terms": 2, "_kscore": 0.2}]
    assert calls == {"tokenize": 1, "select": 1, "fallback": 1}


def test_keyword_search_fewshot_and_rag_chunk_default_do_not_fallback(monkeypatch):
    calls = {"tokenize": 0}

    async def plain(*_args, **_kwargs):
        return []

    async def tokenize(*_args, **_kwargs):
        calls["tokenize"] += 1
        return ["学生"]

    monkeypatch.setattr(keyword, "_plain_keyword_search", plain)
    monkeypatch.setattr(keyword, "tokenize_query", tokenize)

    assert asyncio.run(keyword.keyword_search("fewshot_example", "查询学生信息", 5)) == []
    assert asyncio.run(keyword.keyword_search("rag_chunk", "查询学生信息", 5)) == []
    assert calls["tokenize"] == 0


def test_keyword_search_fallback_failure_does_not_break_chain(monkeypatch):
    async def plain(*_args, **_kwargs):
        return []

    async def tokenize(*_args, **_kwargs):
        raise RuntimeError("tokenizer down")

    monkeypatch.setattr(keyword, "_plain_keyword_search", plain)
    monkeypatch.setattr(keyword, "tokenize_query", tokenize)

    assert asyncio.run(keyword.keyword_search("schema_doc", "查询学生信息", 5)) == []
