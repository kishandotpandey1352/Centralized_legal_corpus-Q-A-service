from fastapi.testclient import TestClient

import app.retrieval.service as retrieval_service
from app.db.session import get_db
from app.main import app


def test_query_answer_returns_citation_structure(monkeypatch) -> None:
    question = "Tell me about Colonel Steve McCraw?"

    def fake_retrieve_similar_chunks(db, query: str, top_k: int = 5):
        assert query == question
        return {
            "query": query,
            "top_k": top_k,
            "results": [
                {
                    "chunk_id": "4f8d02f4-1ceb-42f2-a7a8-786ed832a4db",
                    "document_id": "doc-1",
                    "source_file": "texas_department_of_public_safety_v._robert_christopher_callaway.pdf",
                    "chunk_index": 5,
                    "page_range": "3",
                    "section_title": None,
                    "score": 0.82,
                    "chunk_text": (
                        "Colonel Steve McCraw is discussed in relation to affidavit statements and "
                        "high-stress response during the high school situation."
                    ),
                },
                {
                    "chunk_id": "2172c3e5-96cc-4e33-8f18-2384768b7c14",
                    "document_id": "doc-1",
                    "source_file": "texas_department_of_public_safety_v._robert_christopher_callaway.pdf",
                    "chunk_index": 18,
                    "page_range": "8",
                    "section_title": None,
                    "score": 0.76,
                    "chunk_text": "The filing references related conduct and procedural context.",
                },
            ],
        }

    def fake_attach_adjacent_context(db, results):
        return results

    monkeypatch.setattr(retrieval_service, "retrieve_similar_chunks", fake_retrieve_similar_chunks)
    monkeypatch.setattr(retrieval_service, "_attach_adjacent_context", fake_attach_adjacent_context)

    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/query/answer",
        json={"question": question, "top_k": 2},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["question"] == question
    assert payload["mode"] == "evidence-direct"
    assert isinstance(payload["citations"], list)
    assert len(payload["citations"]) >= 1

    citation = payload["citations"][0]
    assert citation["id"] == "C1"
    assert citation["source_file"].endswith("callaway.pdf")
    assert "chunk_id" in citation
    assert "chunk_index" in citation
    assert "score" in citation
