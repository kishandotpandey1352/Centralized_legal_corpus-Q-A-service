import json
import logging
import os
import tempfile
import time
from datetime import date
from pathlib import Path

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.ingestion.service import (
    DocumentMetadata,
    DocumentParseError,
    EmptyDocumentError,
    SUPPORTED_EXTENSIONS,
    ingest_document,
    ingest_sample_docs,
)

logger = logging.getLogger(__name__)


class DocumentMetadataRequest(BaseModel):
    jurisdiction: str | None = None
    court: str | None = None
    canonical_citation: str | None = None
    decision_date: date | None = None
    practice_area: str | None = None


class SampleDocsIngestionRequest(BaseModel):
    metadata_by_source: dict[str, DocumentMetadataRequest] | None = None


class IngestionMetadataResponse(BaseModel):
    jurisdiction: str | None = None
    court: str | None = None
    canonical_citation: str | None = None
    decision_date: date | None = None
    practice_area: str | None = None


class IngestionResponse(BaseModel):
    status: str
    document_id: str
    source_file: str
    document_type: str
    chunks_indexed: int
    embedding_backend: str
    embedding_model: str
    metadata: IngestionMetadataResponse
    processing_time_ms: int | None = None


router = APIRouter(prefix="/ingest", tags=["ingestion"])

_ALLOWED_CONTENT_TYPES: dict[str, set[str]] = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".txt": {"text/plain"},
}
_GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _sanitize_source_filename(filename: str | None) -> str:
    if not filename:
        return ""
    # Keep only the base name so client-supplied paths can never traverse directories.
    return Path(filename.replace("\\", "/")).name.strip()


def _content_type_is_allowed(extension: str, content_type: str | None) -> bool:
    normalized = (content_type or "").split(";")[0].strip().lower()
    if not normalized:
        return True
    if normalized in _GENERIC_CONTENT_TYPES:
        return True
    if normalized in _ALLOWED_CONTENT_TYPES.get(extension, set()):
        return True
    if extension == ".txt" and normalized.startswith("text/"):
        return True
    return False


def _stage_upload(file: UploadFile, extension: str) -> Path:
    """Stream the upload to a generated temporary file, enforcing the size limit."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    fd, tmp_name = tempfile.mkstemp(prefix="rag-upload-", suffix=extension)
    os.close(fd)
    temp_path = Path(tmp_name)
    try:
        with temp_path.open("wb") as tmp:
            total = 0
            while True:
                chunk = file.file.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum upload size of {settings.max_upload_size_mb} MB",
                    )
                tmp.write(chunk)
    except HTTPException:
        temp_path.unlink(missing_ok=True)
        raise
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to stage uploaded file.") from None
    return temp_path


@router.post("/sample-docs")
def ingest_local_sample_docs(
    request: SampleDocsIngestionRequest | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        metadata_by_source = {
            source_file: DocumentMetadata(**metadata.model_dump())
            for source_file, metadata in (request.metadata_by_source or {}).items()
        } if request else None
        return ingest_sample_docs(db, metadata_by_source=metadata_by_source)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/upload",
    summary="Upload and index a legal document",
    description=(
        "Upload a PDF, DOCX, or TXT document for text extraction, chunking, "
        "embedding, and pgvector indexing. The document becomes immediately "
        "available to `/query/retrieve` and `/query/answer`.\n\n"
        "- Supported formats: .pdf, .docx, .txt\n"
        "- Optional legal metadata: jurisdiction, court, canonical_citation, "
        "decision_date (YYYY-MM-DD), practice_area\n"
        "- Maximum upload size is configured via `MAX_UPLOAD_SIZE_MB` (default 25 MB)"
    ),
    responses={
        200: {"description": "Document indexed successfully"},
        400: {"description": "Empty, malformed, or unparseable document content"},
        413: {"description": "File exceeds the configured maximum upload size"},
        415: {"description": "Unsupported file extension or media type"},
        422: {"description": "Invalid optional metadata (e.g. malformed date)"},
        500: {"description": "Unexpected server-side ingestion failure"},
    },
)
def upload_document(
    file: UploadFile = File(..., description="The document to ingest (.pdf, .docx, or .txt)"),
    jurisdiction: str | None = Form(None, description="Optional jurisdiction metadata"),
    court: str | None = Form(None, description="Optional court metadata"),
    canonical_citation: str | None = Form(None, description="Optional canonical citation metadata"),
    decision_date: date | None = Form(None, description="Optional decision date (YYYY-MM-DD)"),
    practice_area: str | None = Form(None, description="Optional practice area metadata"),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    source_filename = _sanitize_source_filename(file.filename)
    if not source_filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename")

    extension = Path(source_filename).suffix.lower()
    document_type = extension.lstrip(".")
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{extension or '(none)'}'. Supported types: {supported}",
        )

    if not _content_type_is_allowed(extension, file.content_type):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{file.content_type}' for '{extension}' files",
        )

    metadata = DocumentMetadata(
        jurisdiction=jurisdiction,
        court=court,
        canonical_citation=canonical_citation,
        decision_date=decision_date,
        practice_area=practice_area,
    )

    temp_path = _stage_upload(file, extension)
    started = time.perf_counter()
    try:
        result = ingest_document(
            db,
            file_path=temp_path,
            source_filename=source_filename,
            document_type=document_type,
            metadata=metadata,
        )
        db.commit()
        processing_time_ms = int((time.perf_counter() - started) * 1000)

        cleaned_metadata = result["metadata"]
        return IngestionResponse(
            status="indexed",
            document_id=str(result["document_id"]),
            source_file=str(result["source_file"]),
            document_type=str(result["document_type"]),
            chunks_indexed=int(result["chunks_ingested"]),
            embedding_backend=str(result["embedding_backend"]),
            embedding_model=str(result["embedding_model"]),
            metadata=IngestionMetadataResponse(
                jurisdiction=cleaned_metadata.jurisdiction,
                court=cleaned_metadata.court,
                canonical_citation=cleaned_metadata.canonical_citation,
                decision_date=cleaned_metadata.decision_date,
                practice_area=cleaned_metadata.practice_area,
            ),
            processing_time_ms=processing_time_ms,
        )
    except ValueError as exc:
        db.rollback()
        error_category = (
            "empty_document"
            if isinstance(exc, EmptyDocumentError)
            else ("parse_error" if isinstance(exc, DocumentParseError) else "invalid_content")
        )
        logger.warning(
            json.dumps(
                {
                    "event": "ingestion_failed",
                    "status": "failed",
                    "source_file": source_filename,
                    "document_type": document_type,
                    "error_category": error_category,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.error(
            json.dumps(
                {
                    "event": "ingestion_failed",
                    "status": "failed",
                    "source_file": source_filename,
                    "document_type": document_type,
                    "error_category": "internal",
                    "error_type": type(exc).__name__,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        )
        raise HTTPException(status_code=500, detail="Document ingestion failed unexpectedly.") from None
    finally:
        temp_path.unlink(missing_ok=True)
