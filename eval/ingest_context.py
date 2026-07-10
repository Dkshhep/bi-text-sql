"""编译文件式语义层并写入 pgvector。

运行：
    python -m eval.ingest_context --db-id concert_singer --replace
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import settings
from app.core.context_layer.compiler import compile_fewshots, compile_semantic_docs
from app.core.context_layer.parser import load_context_bundle
from app.core.db import close_pool
from app.core.logging import logger
from app.core.rag.vectorstore import (
    delete_context_fewshots,
    delete_semantic_docs,
    upsert_fewshots,
    upsert_semantic_docs,
)


async def ingest_context(db_id: str, replace: bool = False, context_dir: str | None = None) -> dict:
    root = context_dir or settings.CONTEXT_DIR
    bundle = load_context_bundle(root, db_id)
    semantic_rows = compile_semantic_docs(bundle)
    fewshot_rows = compile_fewshots(bundle)

    deleted_semantic = 0
    deleted_fewshots = 0
    if replace:
        deleted_semantic = await delete_semantic_docs(db_id)
        deleted_fewshots = await delete_context_fewshots(db_id)

    n_semantic = await upsert_semantic_docs(semantic_rows)
    n_fewshot = await upsert_fewshots(fewshot_rows)
    stats = {
        "db_id": db_id,
        "semantic_docs": n_semantic,
        "fewshots": n_fewshot,
        "deleted_semantic_docs": deleted_semantic,
        "deleted_fewshots": deleted_fewshots,
    }
    logger.info("context_ingested", **stats)
    return stats


async def main(db_id: str, replace: bool, context_dir: str | None) -> None:
    await ingest_context(db_id, replace=replace, context_dir=context_dir)
    await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-id", required=True, help="context/<db_id> 目录名")
    parser.add_argument("--replace", action="store_true", help="重建该 db_id 的语义层派生索引")
    parser.add_argument("--context-dir", default=None, help="语义层根目录，默认读取 CONTEXT_DIR")
    args = parser.parse_args()
    asyncio.run(main(args.db_id, args.replace, args.context_dir))
