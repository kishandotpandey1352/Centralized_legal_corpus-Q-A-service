from fastapi.testclient import TestClient

import app.api.routes_retrieval as routes_retrieval
from app.db.session import get_db
from app.main import app
from app.retrieval.service import _rerank_results


def test_rerank_promotes_lexically_relevant_chunk() -> None:
    candidates = [
        {
            "chunk_id": "c1",
            "document_id": "d1",
            "source_file": "file_a.txt",
            "document_type": "txt",
            "chunk_index": 0,
            "page_range": None,
            "section_title": None,
            "score": 0.92,
            "chunk_text": "General litigation process overview.",
        },
        {
            "chunk_id": "c2",
            "document_id": "d2",
            "source_file": "file_b.txt",
            "document_type": "txt",
            "chunk_index": 1,
            "page_range": None,
            "section_title": None,
            "score": 0.80,
            "chunk_text": "Material breach cure period is thirty days after written notice.",
        },
    ]

    reranked = _rerank_results(
        query="What is the cure period for material breach?",
        candidates=candidates,
        top_k=2,
        lexical_weight=0.6,
    )

    assert reranked[0]["chunk_id"] == "c2"
    assert reranked[0]["hybrid_score"] >= reranked[1]["hybrid_score"]


def test_retrieve_route_passes_filters_and_rerank_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_retrieve_similar_chunks(
        db,
        query: str,
        top_k: int = 5,
        source_file: str | None = None,
        document_type: str | None = None,
        rerank: bool = True,
        candidate_pool_size: int | None = None,
    ):
        captured["query"] = query
        captured["top_k"] = top_k
        captured["source_file"] = source_file
        captured["document_type"] = document_type
        captured["rerank"] = rerank
        captured["candidate_pool_size"] = candidate_pool_size
        return {
            "query": query,
            "top_k": top_k,
            "source_file": source_file,
            "document_type": document_type,
            "rerank_enabled": rerank,
            "candidate_pool_size": candidate_pool_size,
            "results": [],
        }

    monkeypatch.setattr(routes_retrieval, "retrieve_similar_chunks", fake_retrieve_similar_chunks)

    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/query/retrieve",
        json={
            "query": "material breach",
            "top_k": 4,
            "source_file": "sample_service_agreement.txt",
            "document_type": "txt",
            "rerank": True,
            "candidate_pool_size": 12,
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["query"] == "material breach"
    assert captured["top_k"] == 4
    assert captured["source_file"] == "sample_service_agreement.txt"
    assert captured["document_type"] == "txt"
    assert captured["rerank"] is True
    assert captured["candidate_pool_size"] == 12
