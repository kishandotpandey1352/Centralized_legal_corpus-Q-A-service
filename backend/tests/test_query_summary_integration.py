from fastapi.testclient import TestClient

import app.api.routes_retrieval as routes_retrieval
from app.db.session import get_db
from app.main import app


def test_query_summary_returns_citation_structure(monkeypatch) -> None:
    source_file = "sample_service_agreement.txt"

    def fake_summarize_document(db, source_file: str, max_chunks: int = 6):
        assert source_file == "sample_service_agreement.txt"
        assert max_chunks == 4
        return {
            "source_file": source_file,
            "summary": "- Termination clause requires a cure period of thirty days [C1]",
            "citations": [
                {
                    "id": "C1",
                    "source_file": source_file,
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "page_range": None,
                    "section_title": "Term and Termination",
                    "score": None,
                }
            ],
            "used_chunks": 1,
            "mode": "llm-summary",
        }

    monkeypatch.setattr(routes_retrieval, "summarize_document", fake_summarize_document)

    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/query/summary",
        json={"source_file": source_file, "max_chunks": 4},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_file"] == source_file
    assert payload["mode"] == "llm-summary"
    assert payload["used_chunks"] == 1
    assert isinstance(payload["citations"], list)
    assert payload["citations"][0]["id"] == "C1"
