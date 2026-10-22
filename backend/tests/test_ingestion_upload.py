from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import get_db
import app.api.routes_ingestion as routes_ingestion
import app.ingestion.service as ingestion_service
import app.retrieval.service as retrieval_service
from app.ingestion.service import DocumentMetadata, EmptyDocumentError, ingest_document
from app.retrieval.service import retrieve_similar_chunks


class RecordingDb:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement: object, params: dict[str, object] | None = None):
        self.calls.append((statement, params or {}))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def calls_matching(self, needle: str) -> list[dict[str, object]]:
        return [params for statement, params in self.calls if needle in str(statement)]


def test_ingest_document_reuses_shared_pipeline(tmp_path: Path, monkeypatch) -> None:
    file_path = tmp_path / "case.txt"
    file_path.write_text("A short legal record.", encoding="utf-8")

    monkeypatch.setattr(ingestion_service, "embed_texts", lambda *args, **kwargs: [[0.1] * 1024])

    db = RecordingDb()
    result = ingest_document(
        db,
        file_path=file_path,
        source_filename="case.txt",
        document_type="txt",
        metadata=DocumentMetadata(
            title="Custom Title",
            jurisdiction="UK",
            decision_date=date(2024, 1, 15),
        ),
    )

    insert_doc = next(
        params for _, params in db.calls
        if "canonical_citation" in params and "chunk_index" not in params
    )
    insert_chunks = [
        params for _, params in db.calls
        if "chunk_index" in params
    ]
    update_embeddings = [
        params for statement, params in db.calls
        if "SET embedding" in str(statement)
    ]

    assert result["source_file"] == "case.txt"
    assert result["document_type"] == "txt"
    assert result["title"] == "Custom Title"
    assert result["chunks_ingested"] == 1
    assert insert_doc["jurisdiction"] == "UK"
    assert insert_doc["decision_date"] == date(2024, 1, 15)
    assert len(insert_chunks) == 1
    assert len(update_embeddings) == 1


def test_ingest_document_rejects_empty_content(tmp_path: Path) -> None:
    file_path = tmp_path / "blank.txt"
    file_path.write_text("   \n\n   ", encoding="utf-8")

    db = RecordingDb()
    try:
        ingest_document(
            db,
            file_path=file_path,
            source_filename="blank.txt",
            document_type="txt",
        )
    except EmptyDocumentError as exc:
        assert "blank.txt" in str(exc)
    else:
        raise AssertionError("EmptyDocumentError was not raised")


class FakeDb:
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_upload_route_passes_file_and_metadata_to_shared_service(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_document(db, *, file_path, source_filename, document_type, metadata=None):
        captured["source_filename"] = source_filename
        captured["document_type"] = document_type
        captured["metadata"] = metadata
        captured["file_path"] = file_path
        return {
            "document_id": "doc-1",
            "source_file": source_filename,
            "document_type": document_type,
            "title": "Derived",
            "chunks_ingested": 3,
            "metadata": metadata if metadata else DocumentMetadata(),
            "embedding_backend": "hash",
            "embedding_model": "BAAI/bge-m3",
        }

    monkeypatch.setattr(routes_ingestion, "ingest_document", fake_ingest_document)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("case.txt", b"A short legal record.", "text/plain")},
        data={
            "jurisdiction": "UK",
            "court": "Supreme Court",
            "decision_date": "2024-01-15",
            "practice_area": "public law",
        },
    )

    app.dependency_overrides.clear()

    body = response.json()
    assert response.status_code == 200
    assert captured["source_filename"] == "case.txt"
    assert captured["document_type"] == "txt"
    assert captured["metadata"].jurisdiction == "UK"
    assert captured["metadata"].court == "Supreme Court"
    assert captured["metadata"].decision_date.isoformat() == "2024-01-15"
    assert captured["metadata"].practice_area == "public law"
    assert not Path(captured["file_path"]).exists()
    assert body["status"] == "indexed"
    assert body["document_id"] == "doc-1"
    assert body["source_file"] == "case.txt"
    assert body["document_type"] == "txt"
    assert body["chunks_indexed"] == 3
    assert body["embedding_backend"] == "hash"
    assert body["embedding_model"] == "BAAI/bge-m3"
    assert body["metadata"]["jurisdiction"] == "UK"
    assert body["metadata"]["court"] == "Supreme Court"
    assert body["metadata"]["decision_date"] == "2024-01-15"
    assert body["metadata"]["practice_area"] == "public law"
    assert isinstance(body["processing_time_ms"], int)


def test_upload_route_rejects_unsupported_extension(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("malware.exe", b"not a document", "application/octet-stream")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_route_rejects_unsupported_media_type(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("judgment.pdf", b"not really a pdf", "image/png")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 415
    assert "Unsupported media type" in response.json()["detail"]


def test_upload_route_rejects_oversized_file(monkeypatch) -> None:
    monkeypatch.setattr(routes_ingestion.settings, "max_upload_size_mb", 1)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("big.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 413
    assert "maximum upload size" in response.json()["detail"]


def test_upload_route_sanitizes_path_traversal_filename(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_document(db, *, file_path, source_filename, document_type, metadata=None):
        captured["source_filename"] = source_filename
        return {
            "document_id": "doc-1",
            "source_file": source_filename,
            "document_type": document_type,
            "title": "Derived",
            "chunks_ingested": 1,
            "metadata": metadata if metadata else DocumentMetadata(),
            "embedding_backend": "hash",
            "embedding_model": "BAAI/bge-m3",
        }

    monkeypatch.setattr(routes_ingestion, "ingest_document", fake_ingest_document)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("../../secret.txt", b"secret content", "text/plain")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["source_filename"] == "secret.txt"


def test_upload_route_rejects_empty_file(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 400


def test_upload_route_rejects_malformed_file(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("broken.pdf", b"this is not a valid pdf", "application/pdf")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Could not parse" in response.json()["detail"]


def test_upload_route_hides_internal_errors(monkeypatch) -> None:
    def exploding_ingest_document(db, *, file_path, source_filename, document_type, metadata=None):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(routes_ingestion, "ingest_document", exploding_ingest_document)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("case.txt", b"A short legal record.", "text/plain")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Document ingestion failed unexpectedly."
    assert "sensitive internal detail" not in response.text


def _make_pdf_bytes(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_docx_bytes(text: str) -> bytes:
    import io

    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _fake_embed(texts, *args, **kwargs):
    return [[0.1] * 1024 for _ in texts]


def test_upload_valid_txt_creates_document_chunks_and_embeddings(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "embed_texts", _fake_embed)
    db = RecordingDb()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("case.txt", b"A short legal record about material breach.", "text/plain")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "indexed"
    assert body["document_type"] == "txt"
    assert body["chunks_indexed"] >= 1

    assert len(db.calls_matching("INSERT INTO documents")) == 1
    chunk_inserts = db.calls_matching("INSERT INTO chunks")
    assert len(chunk_inserts) >= 1
    assert len(db.calls_matching("SET embedding")) == len(chunk_inserts)
    assert db.committed is True
    assert db.rolled_back is False


def test_upload_valid_pdf(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "embed_texts", _fake_embed)
    db = RecordingDb()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("judgment.pdf", _make_pdf_bytes("Material breach cure period is thirty days."), "application/pdf")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_type"] == "pdf"
    assert body["chunks_indexed"] >= 1
    assert len(db.calls_matching("INSERT INTO chunks")) >= 1


def test_upload_valid_docx(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "embed_texts", _fake_embed)
    db = RecordingDb()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("agreement.docx", _make_docx_bytes("Material breach cure period is thirty days."), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["document_type"] == "docx"
    assert body["chunks_indexed"] >= 1
    assert len(db.calls_matching("INSERT INTO chunks")) >= 1


def test_upload_persists_optional_metadata(monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "embed_texts", _fake_embed)
    db = RecordingDb()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("case.txt", b"A short legal record.", "text/plain")},
        data={
            "jurisdiction": " UK ",
            "court": "Supreme Court",
            "canonical_citation": "[2024] UKSC 1",
            "decision_date": "2024-01-15",
            "practice_area": "public law",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["jurisdiction"] == "UK"
    assert body["metadata"]["court"] == "Supreme Court"
    assert body["metadata"]["canonical_citation"] == "[2024] UKSC 1"
    assert body["metadata"]["decision_date"] == "2024-01-15"
    assert body["metadata"]["practice_area"] == "public law"

    document_insert = db.calls_matching("INSERT INTO documents")[0]
    assert document_insert["jurisdiction"] == "UK"
    assert document_insert["court"] == "Supreme Court"
    assert document_insert["canonical_citation"] == "[2024] UKSC 1"
    assert document_insert["decision_date"] == date(2024, 1, 15)
    assert document_insert["practice_area"] == "public law"


def test_reupload_same_source_replaces_prior_document(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "embed_texts", _fake_embed)
    file_path = tmp_path / "case.txt"
    file_path.write_text("A short legal record.", encoding="utf-8")

    db = RecordingDb()
    first = ingest_document(db, file_path=file_path, source_filename="case.txt", document_type="txt")
    second = ingest_document(db, file_path=file_path, source_filename="case.txt", document_type="txt")

    deletes = db.calls_matching("DELETE FROM documents")
    document_inserts = db.calls_matching("INSERT INTO documents")
    chunk_inserts = db.calls_matching("INSERT INTO chunks")

    assert len(deletes) == 2
    assert len(document_inserts) == 2
    assert first["document_id"] != second["document_id"]
    assert len(chunk_inserts) == 2
    assert chunk_inserts[0]["document_id"] == first["document_id"]
    assert chunk_inserts[1]["document_id"] == second["document_id"]


def test_embedding_failure_rolls_back_transaction(monkeypatch) -> None:
    def failing_embed(texts, *args, **kwargs):
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(ingestion_service, "embed_texts", failing_embed)
    db = RecordingDb()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    response = client.post(
        "/ingest/upload",
        files={"file": ("case.txt", b"A short legal record.", "text/plain")},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 500
    assert db.rolled_back is True
    assert db.committed is False


class FakeRow(dict):
    pass


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class RetrievalDb:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, statement, params=None):
        if "FROM chunks" in str(statement):
            return FakeResult(self._rows)
        return FakeResult([])


def test_uploaded_document_is_retrievable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ingestion_service, "embed_texts", _fake_embed)
    file_path = tmp_path / "case.txt"
    file_path.write_text("Material breach cure period is thirty days after written notice.", encoding="utf-8")

    db = RecordingDb()
    ingest_document(db, file_path=file_path, source_filename="case.txt", document_type="txt")

    doc = db.calls_matching("INSERT INTO documents")[0]
    chunks = db.calls_matching("INSERT INTO chunks")

    rows = [
        FakeRow(
            id=chunk["id"],
            document_id=chunk["document_id"],
            chunk_index=chunk["chunk_index"],
            chunk_text=chunk["chunk_text"],
            page_range=chunk["page_range"],
            section_title=chunk["section_title"],
            source_file=doc["source_file"],
            document_type=doc["document_type"],
            jurisdiction=doc["jurisdiction"],
            court=doc["court"],
            canonical_citation=doc["canonical_citation"],
            decision_date=doc["decision_date"],
            practice_area=doc["practice_area"],
            score=0.9,
        )
        for chunk in chunks
    ]

    monkeypatch.setattr(
        retrieval_service,
        "embed_texts",
        lambda texts, *args, **kwargs: [[0.0] * 1024 for _ in texts],
    )
    retrieval = retrieve_similar_chunks(
        RetrievalDb(rows),
        query="What is the cure period for material breach?",
        top_k=5,
    )

    assert retrieval["results"]
    assert retrieval["results"][0]["source_file"] == "case.txt"
    assert "cure period" in retrieval["results"][0]["chunk_text"].lower()
