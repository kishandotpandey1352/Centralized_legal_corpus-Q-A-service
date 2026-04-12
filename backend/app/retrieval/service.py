from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.retrieval.embeddings import embed_texts, vector_to_pg_literal


def retrieve_similar_chunks(db: Session, query: str, top_k: int = 5) -> dict[str, object]:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Query cannot be empty")

    top_k = max(1, min(top_k, 20))
    query_embedding = embed_texts(
        [cleaned_query],
        model_name=settings.embedding_model,
        backend=settings.embedding_backend,
        cache_dir=settings.embedding_cache_dir,
    )[0]
    query_vector = vector_to_pg_literal(query_embedding)

    # For tiny datasets in early MVP, exact scan is more reliable than IVFFlat approximation.
    db.execute(text("SET LOCAL enable_indexscan = off"))
    db.execute(text("SET LOCAL enable_bitmapscan = off"))
    db.execute(text("SET LOCAL ivfflat.probes = 10"))

    rows = db.execute(
        text(
            """
            SELECT
                c.id,
                c.document_id,
                c.chunk_index,
                c.chunk_text,
                c.page_range,
                c.section_title,
                d.source_file,
                (1 - (c.embedding <=> CAST(:query_vector AS vector))) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:query_vector AS vector)
            LIMIT :top_k
            """
        ),
        {"query_vector": query_vector, "top_k": top_k},
    ).mappings().all()

    return {
        "query": cleaned_query,
        "top_k": top_k,
        "results": [
            {
                "chunk_id": str(row["id"]),
                "document_id": str(row["document_id"]),
                "source_file": row["source_file"],
                "chunk_index": row["chunk_index"],
                "page_range": row["page_range"],
                "section_title": row["section_title"],
                "score": round(float(row["score"]), 6) if row["score"] is not None else None,
                "chunk_text": row["chunk_text"],
            }
            for row in rows
        ],
    }
