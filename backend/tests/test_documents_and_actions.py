from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
import app.api.routes_documents as routes_documents
import app.api.routes_retrieval as routes_retrieval
import app.ingestion.service as ingestion_service
import app.retrieval.service as retrieval_service


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class RecordingDb:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.params: dict[str, object] = {}
        self.calls: list[tuple[object, dict[str, object]]] = []

    def execute(self, statement, params=None):
        self.calls.append((statement, params or {}))
        if "FROM chunks" in str(statement) or "FROM documents" in str(statement):
            self.params.update(params or {})
        return FakeResult(self._rows)


def test_list_documents_service_returns_metadata_and_counts() -> None:
    rows = [
        {
            "id": "d1",
            "source_file": "judgment.pdf",
            "document_type": "pdf",
            "title": "Judgment",
            "jurisdiction": "UK",
            "court": "Supreme Court",
            "canonical_citation": "[2024] UKSC 1",
            "decision_date": date(2024, 1, 1),
            "practice_area": "public law",
            "created_at": None,
            "chunk_count": 3,
        }
    ]
    result = ingestion_service.list_documents(RecordingDb(rows))

    assert result[0]["document_id"] == "d1"
    assert result[0]["source_file"] == "judgment.pdf"
    assert result[0]["chunk_count"] == 3
    assert result[0]["decision_date"] == "2024-01-01"


def test_list_documents_service_empty() -> None:
    result = ingestion_service.list_documents(RecordingDb([]))
    assert result == []


def test_list_documents_service_multiple() -> None:
    rows = [
        {
            "id": "d2",
            "source_file": "b.pdf",
            "document_type": "pdf",
            "title": "B",
            "jurisdiction": None,
            "court": None,
            "canonical_citation": None,
            "decision_date": None,
            "practice_area": None,
            "created_at": None,
            "chunk_count": 5,
        },
        {
            "id": "d1",
            "source_file": "a.txt",
            "document_type": "txt",
            "title": "A",
            "jurisdiction": None,
            "court": None,
            "canonical_citation": None,
            "decision_date": None,
            "practice_area": None,
            "created_at": None,
            "chunk_count": 2,
        },
    ]
    result = ingestion_service.list_documents(RecordingDb(rows))
    assert len(result) == 2
    assert {item["document_id"] for item in result} == {"d1", "d2"}


def test_list_documents_route_returns_empty_list_without_404(monkeypatch) -> None:
    monkeypatch.setattr(routes_documents, "list_documents", lambda db: [])
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.get("/documents")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"documents": []}


def test_list_documents_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_documents,
        "list_documents",
        lambda db: [{"document_id": "d1", "source_file": "judgment.pdf"}],
    )
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.get("/documents")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["documents"][0]["document_id"] == "d1"


def test_retrieve_filters_by_document_id(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_service, "embed_texts", lambda texts, *args, **kwargs: [[0.0] * 1024 for _ in texts])
    db = RecordingDb()

    retrieval_service.retrieve_similar_chunks(db, query="material breach", top_k=3, document_id="doc-123")

    assert db.params.get("document_id") == "doc-123"


def test_answer_passes_document_id_to_retrieval(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_search(db, query: str, candidate_k: int, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(retrieval_service, "_search_candidates", fake_search)

    retrieval_service.answer_question(object(), "What is the filing deadline?", document_id="doc-123")

    assert captured.get("document_id") == "doc-123"


def test_summarize_by_document_id(monkeypatch) -> None:
    rows = [
        {
            "id": "c1",
            "chunk_index": 0,
            "chunk_text": "A filing deadline of twenty one days applies.",
            "page_range": "1",
            "section_title": None,
            "source_file": "judgment.pdf",
        }
    ]
    db = RecordingDb(rows)
    monkeypatch.setattr(retrieval_service, "generate_answer_with_ollama", lambda **kwargs: "1. Filing deadline is twenty one days. [C1]")

    result = retrieval_service.summarize_document(db, document_id="doc-9", max_chunks=20)

    assert db.params.get("document_id") == "doc-9"
    assert result["document_id"] == "doc-9"
    assert result["source_file"] == "judgment.pdf"


def test_extract_key_topics_returns_structured_list(monkeypatch) -> None:
    rows = [{"chunk_text": "Unfair dismissal and procedural fairness.", "source_file": "judgment.pdf"}]
    db = RecordingDb(rows)
    monkeypatch.setattr(
        retrieval_service,
        "generate_answer_with_ollama",
        lambda **kwargs: '["unfair dismissal", "procedural fairness"]',
    )

    result = retrieval_service.extract_key_topics(db, "doc-1", limit=5)

    assert result["document_id"] == "doc-1"
    assert result["source_file"] == "judgment.pdf"
    assert result["topics"] == ["unfair dismissal", "procedural fairness"]


def test_extract_key_topics_filters_generic_terms(monkeypatch) -> None:
    rows = [{"chunk_text": "A case about procedural fairness and unfair dismissal.", "source_file": "judgment.pdf"}]
    db = RecordingDb(rows)
    monkeypatch.setattr(
        retrieval_service,
        "generate_answer_with_ollama",
        lambda **kwargs: '["document", "case", "procedural fairness", "unfair dismissal"]',
    )

    result = retrieval_service.extract_key_topics(db, "doc-1", limit=5)

    assert "document" not in result["topics"]
    assert "case" not in result["topics"]
    assert "procedural fairness" in result["topics"]


def test_extract_key_topics_reuses_chunks_without_ingestion_or_embeddings(monkeypatch) -> None:
    rows = [{"chunk_text": "Unfair dismissal procedural fairness.", "source_file": "judgment.pdf"}]
    db = RecordingDb(rows)
    monkeypatch.setattr(
        retrieval_service,
        "generate_answer_with_ollama",
        lambda **kwargs: '["unfair dismissal", "procedural fairness"]',
    )
    monkeypatch.setattr(retrieval_service, "embed_texts", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("embed_texts must not run")))

    result = retrieval_service.extract_key_topics(db, "doc-1", limit=5)

    assert result["topics"]
    # Only the chunk SELECT was issued; no INSERT/UPDATE statements.
    assert not any("INSERT" in str(statement) for statement, _ in db.calls)
    assert not any("UPDATE" in str(statement) for statement, _ in db.calls)


def test_extract_key_topics_unknown_document_raises(monkeypatch) -> None:
    db = RecordingDb([])

    try:
        retrieval_service.extract_key_topics(db, "missing-doc", limit=5)
    except ValueError as exc:
        assert "missing-doc" in str(exc)
    else:
        raise AssertionError("ValueError was not raised")


def test_extract_key_topics_falls_back_when_generation_not_strict(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_service.settings, "generation_strict", False)
    rows = [{"chunk_text": "compensation compensation unfair dismissal", "source_file": "judgment.pdf"}]
    db = RecordingDb(rows)

    def failing_generate(**kwargs):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(retrieval_service, "generate_answer_with_ollama", failing_generate)

    result = retrieval_service.extract_key_topics(db, "doc-1", limit=5)

    assert result["topics"]
    assert "compensation" in result["topics"]


def test_keywords_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_retrieval,
        "extract_key_topics",
        lambda db, document_id, limit: {"document_id": document_id, "source_file": "a.pdf", "topics": ["k"]},
    )
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.post("/query/keywords", json={"document_id": "d1", "limit": 5})

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["topics"] == ["k"]
