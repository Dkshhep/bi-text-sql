from app.core.rag.keyword import _strip_internal_columns as strip_keyword_internal_columns
from app.core.rag.vectorstore import _strip_internal_columns as strip_vector_internal_columns


def test_vectorstore_strips_non_serializable_internal_columns():
    row = {
        "id": 1,
        "content": "schema text",
        "embedding": object(),
        "tsv": object(),
        "_vscore": 0.9,
    }

    assert strip_vector_internal_columns(row) == {"id": 1, "content": "schema text", "_vscore": 0.9}


def test_keyword_strips_non_serializable_internal_columns():
    row = {
        "id": 1,
        "content": "schema text",
        "embedding": object(),
        "tsv": object(),
        "_kscore": 0.4,
    }

    assert strip_keyword_internal_columns(row) == {"id": 1, "content": "schema text", "_kscore": 0.4}
