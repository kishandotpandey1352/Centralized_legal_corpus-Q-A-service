from datetime import date
from pathlib import Path

import app.ingestion.service as ingestion_service
from app.ingestion.service import DocumentMetadata, ingest_sample_docs


class RecordingDb:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []
        self.committed = False

    def execute(self, statement: object, params: dict[str, object] | None = None):
        self.calls.append((statement, params or {}))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        raise AssertionError("rollback was not expected")


def test_ingestion_persists_only_explicit_optional_metadata(tmp_path: Path, monkeypatch) -> None:
    sample_docs = tmp_path / "data" / "sample_docs"
    sample_docs.mkdir(parents=True)
    (sample_docs / "case.txt").write_text("A short legal record.", encoding="utf-8")

    monkeypatch.setattr(ingestion_service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ingestion_service, "embed_texts", lambda *args, **kwargs: [[0.1] * 1024])

    db = RecordingDb()
    result = ingest_sample_docs(
        db,
        metadata_by_source={
            "case.txt": DocumentMetadata(
                jurisdiction=" UK ",
                court="Supreme Court",
                canonical_citation="[2024] UKSC 1",
                decision_date=date(2024, 1, 15),
                practice_area="public law",
            )
        },
    )

    insert_calls = [
        params
        for _, params in db.calls
        if "canonical_citation" in params
    ]

    assert result["documents_ingested"] == 1
    assert db.committed is True
    assert insert_calls == [
        {
            "id": insert_calls[0]["id"],
            "source_file": "case.txt",
            "document_type": "txt",
            "title": "A short legal record.",
            "jurisdiction": "UK",
            "court": "Supreme Court",
            "canonical_citation": "[2024] UKSC 1",
            "decision_date": date(2024, 1, 15),
            "practice_area": "public law",
        }
    ]


def test_ingestion_leaves_metadata_null_when_not_provided(tmp_path: Path, monkeypatch) -> None:
    sample_docs = tmp_path / "data" / "sample_docs"
    sample_docs.mkdir(parents=True)
    (sample_docs / "agreement.txt").write_text("Agreement text.", encoding="utf-8")

    monkeypatch.setattr(ingestion_service, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ingestion_service, "embed_texts", lambda *args, **kwargs: [[0.1] * 1024])

    db = RecordingDb()
    ingest_sample_docs(db)

    insert_params = next(params for _, params in db.calls if "canonical_citation" in params)
    assert insert_params["jurisdiction"] is None
    assert insert_params["court"] is None
    assert insert_params["canonical_citation"] is None
    assert insert_params["decision_date"] is None
    assert insert_params["practice_area"] is None
