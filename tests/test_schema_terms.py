from app.core.config import settings
from app.core.rag import keyword
from app.core.rag import schema_terms


def test_schema_terms_default_table_switches():
    assert settings.KEYWORD_SCHEMA_TERMS_SCHEMA_DOC_ENABLED is True
    assert settings.KEYWORD_SCHEMA_TERMS_FEWSHOT_ENABLED is False
    assert settings.KEYWORD_SCHEMA_TERMS_RAG_CHUNK_ENABLED is False
    assert schema_terms.schema_terms_enabled_for_table("schema_doc") is True
    assert schema_terms.schema_terms_enabled_for_table("fewshot_example") is False
    assert schema_terms.schema_terms_enabled_for_table("rag_chunk") is False


def test_parse_schema_terms_filters_to_backend_tokens_and_preserves_order():
    tokens = ["查询", "学生", "成绩", "班级"]
    text = '{"schema_terms": ["班级", "学生", "不存在", "成绩"]}'

    assert schema_terms.parse_schema_terms_response(text, tokens) == ["学生", "成绩", "班级"]


def test_parse_schema_terms_filters_non_schema_default_terms():
    tokens = ["查询", "成绩", "排名", "前", "名", "学生", "信息", "平均", "数量"]
    text = '{"schema_terms": ["查询", "成绩", "排名", "前", "名", "学生", "信息", "平均", "数量"]}'

    assert schema_terms.parse_schema_terms_response(text, tokens) == ["成绩", "学生"]


def test_parse_schema_terms_rejects_invalid_json_and_unsafe_terms():
    assert schema_terms.parse_schema_terms_response("not json", ["学生"]) == []
    assert schema_terms.parse_schema_terms_response('{"schema_terms": ["学生|成绩", "学生"]}', ["学生|成绩", "学生"]) == [
        "学生"
    ]


def test_min_match_count_uses_percentage_with_single_term_floor():
    assert schema_terms.min_match_count(0, ratio=0.5) == 0
    assert schema_terms.min_match_count(1, ratio=0.5) == 1
    assert schema_terms.min_match_count(2, ratio=0.5) == 1
    assert schema_terms.min_match_count(3, ratio=0.5) == 2
    assert schema_terms.min_match_count(5, ratio=0.6) == 3


def test_sort_schema_term_rows_uses_matched_terms_score_then_id():
    rows = [
        {"id": 3, "matched_terms": 2, "_kscore": 0.12},
        {"id": 4, "matched_terms": 1, "_kscore": 0.30},
        {"id": 1, "matched_terms": 3, "_kscore": 0.05},
        {"id": 2, "matched_terms": 2, "_kscore": 0.18},
    ]

    assert [row["id"] for row in schema_terms.sort_schema_term_rows(rows)] == [1, 2, 3, 4]


def test_pg_or_tsquery_expression_is_parenthesized():
    expr = keyword._or_plain_tsquery_expr(2)

    assert expr.startswith("(")
    assert expr.endswith(")")
    assert " || " in expr
