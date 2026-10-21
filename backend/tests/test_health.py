from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
import app.api.routes_ingestion as routes_ingestion


client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingestion_route_accepts_explicit_document_metadata(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_sample_docs(db, metadata_by_source=None):
        captured["metadata_by_source"] = metadata_by_source
        return {"documents_ingested": 0, "chunks_ingested": 0, "files": []}

    monkeypatch.setattr(routes_ingestion, "ingest_sample_docs", fake_ingest_sample_docs)
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/ingest/sample-docs",
        json={
            "metadata_by_source": {
                "known_case.pdf": {
                    "jurisdiction": "UK",
                    "court": "Supreme Court",
                    "decision_date": "2024-01-15",
                }
            }
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    metadata = captured["metadata_by_source"]["known_case.pdf"]
    assert metadata.jurisdiction == "UK"
    assert metadata.court == "Supreme Court"
    assert metadata.decision_date.isoformat() == "2024-01-15"
