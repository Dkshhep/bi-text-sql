"""增加轻量语义层索引表

Revision ID: 0006_semantic_context_layer
Revises: 0005_chat_message_turn_id
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op

from app.core.config import settings

revision = "0006_semantic_context_layer"
down_revision = "0005_chat_message_turn_id"
branch_labels = None
depends_on = None

DIM = settings.EMBEDDING_DIM


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_jieba")
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS semantic_doc (
            id          BIGSERIAL PRIMARY KEY,
            db_id       TEXT NOT NULL,
            doc_type    TEXT NOT NULL,
            name        TEXT NOT NULL,
            content     TEXT NOT NULL,
            payload     JSONB DEFAULT '{{}}'::jsonb,
            embedding   vector({DIM}),
            tsv         tsvector,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_semantic_doc_embedding ON semantic_doc "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_semantic_doc_tsv ON semantic_doc USING gin (tsv)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_semantic_doc_db_type ON semantic_doc (db_id, doc_type)")
    op.execute("ALTER TABLE fewshot_example ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE fewshot_example DROP COLUMN IF EXISTS metadata")
    op.execute("DROP TABLE IF EXISTS semantic_doc")
