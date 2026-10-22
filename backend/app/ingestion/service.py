from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping
from uuid import uuid4

import fitz
from docx import Document
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.retrieval.embeddings import embed_texts, vector_to_pg_literal


SUPPORTED_EXTENSIONS = {".txt", ".docx", ".pdf"}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentMetadata:
    jurisdiction: str | None = None
    court: str | None = None
    canonical_citation: str | None = None
    decision_date: date | None = None
    practice_area: str | None = None
    title: str | None = None


class EmptyDocumentError(ValueError):
    """Raised when a supported document yields no extractable text."""


class DocumentParseError(ValueError):
    """Raised when a supported document cannot be parsed into text."""


@dataclass(frozen=True)
class TextSegment:
    text: str
    page_range: str | None = None


def _normalize_text(raw_text: str) -> str:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.strip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        clean_line = line.strip()
        if clean_line:
            return clean_line[:200]
    return fallback


def _extract_section_title(chunk_text: str) -> str | None:
    for line in chunk_text.splitlines()[:6]:
        heading_match = re.match(r"^\d+\.\s+(.+)$", line.strip())
        if heading_match:
            return heading_match.group(1)[:200]
    return None


def _chunk_text(text_value: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    if not text_value:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(text_value)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            split_at = text_value.rfind(" ", start + max(100, chunk_size - 120), end)
            if split_at > start + 100:
                end = split_at

        candidate = text_value[start:end].strip()
        if candidate:
            chunks.append(candidate)

        if end >= text_length:
            break

        start = max(end - overlap, start + 1)

    return chunks


def _load_segments_from_path(file_path: Path) -> list[TextSegment]:
    extension = file_path.suffix.lower()

    if extension == ".txt":
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        normalized = _normalize_text(raw_text)
        return [TextSegment(text=normalized)] if normalized else []

    if extension == ".docx":
        doc = Document(str(file_path))
        raw_text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        normalized = _normalize_text(raw_text)
        return [TextSegment(text=normalized)] if normalized else []

    if extension == ".pdf":
        segments: list[TextSegment] = []
        with fitz.open(file_path) as pdf_doc:
            for page_index, page in enumerate(pdf_doc, start=1):
                normalized = _normalize_text(page.get_text("text"))
                if normalized:
                    segments.append(TextSegment(text=normalized, page_range=str(page_index)))
        return segments

    return []


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _clean_metadata_value(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_document_metadata(metadata: DocumentMetadata | None) -> DocumentMetadata:
    if metadata is None:
        return DocumentMetadata()
    return DocumentMetadata(
        jurisdiction=_clean_metadata_value(metadata.jurisdiction),
        court=_clean_metadata_value(metadata.court),
        canonical_citation=_clean_metadata_value(metadata.canonical_citation),
        decision_date=metadata.decision_date,
        practice_area=_clean_metadata_value(metadata.practice_area),
        title=_clean_metadata_value(metadata.title),
    )


def ingest_document(
    db: Session,
    *,
    file_path: Path,
    source_filename: str,
    document_type: str,
    metadata: DocumentMetadata | None = None,
) -> dict[str, object]:
    """Ingest a single supported document into the vector store.

    Shared by sample-corpus ingestion and uploaded-file ingestion. Deletes any
    prior rows for ``source_filename``, then inserts a fresh document record,
    chunk rows, and pgvector embeddings. The caller owns the transaction and is
    responsible for committing or rolling back.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    started = time.perf_counter()

    try:
        segments = _load_segments_from_path(file_path)
    except Exception as exc:
        logger.warning(
            json.dumps(
                {
                    "event": "ingestion_failed",
                    "status": "failed",
                    "source_file": source_filename,
                    "document_type": document_type,
                    "error_category": "parse_error",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        )
        raise DocumentParseError(f"Could not parse '{source_filename}': {exc}") from exc

    full_text = "\n\n".join(segment.text for segment in segments).strip()
    if not full_text:
        logger.warning(
            json.dumps(
                {
                    "event": "ingestion_failed",
                    "status": "failed",
                    "source_file": source_filename,
                    "document_type": document_type,
                    "error_category": "empty_document",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        )
        raise EmptyDocumentError(f"No extractable text found in '{source_filename}'")

    db.execute(
        text("DELETE FROM documents WHERE source_file = :source_file"),
        {"source_file": source_filename},
    )

    document_id = str(uuid4())
    cleaned_metadata = _normalize_document_metadata(metadata)
    title = cleaned_metadata.title or _extract_title(full_text, Path(source_filename).stem)
    db.execute(
        text(
            """
            INSERT INTO documents (
                id, source_file, document_type, title, jurisdiction, court,
                canonical_citation, decision_date, practice_area
            )
            VALUES (
                :id, :source_file, :document_type, :title, :jurisdiction, :court,
                :canonical_citation, :decision_date, :practice_area
            )
            """
        ),
        {
            "id": document_id,
            "source_file": source_filename,
            "document_type": document_type,
            "title": title,
            "jurisdiction": cleaned_metadata.jurisdiction,
            "court": cleaned_metadata.court,
            "canonical_citation": cleaned_metadata.canonical_citation,
            "decision_date": cleaned_metadata.decision_date,
            "practice_area": cleaned_metadata.practice_area,
        },
    )

    chunk_index = 0
    pending_embeddings: list[tuple[str, str]] = []
    for segment in segments:
        for chunk_text in _chunk_text(segment.text):
            chunk_id = str(uuid4())
            db.execute(
                text(
                    """
                    INSERT INTO chunks (id, document_id, chunk_index, chunk_text, page_range, section_title)
                    VALUES (:id, :document_id, :chunk_index, :chunk_text, :page_range, :section_title)
                    """
                ),
                {
                    "id": chunk_id,
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "chunk_text": chunk_text,
                    "page_range": segment.page_range,
                    "section_title": _extract_section_title(chunk_text),
                },
            )
            pending_embeddings.append((chunk_id, chunk_text))
            chunk_index += 1

    if pending_embeddings:
        embedding_vectors = embed_texts(
            [chunk_text for _, chunk_text in pending_embeddings],
            model_name=settings.embedding_model,
            backend=settings.embedding_backend,
            cache_dir=settings.embedding_cache_dir,
        )
        for (chunk_id, _), vector in zip(pending_embeddings, embedding_vectors):
            db.execute(
                text("UPDATE chunks SET embedding = CAST(:embedding AS vector) WHERE id = :chunk_id"),
                {"embedding": vector_to_pg_literal(vector), "chunk_id": chunk_id},
            )

    logger.info(
        json.dumps(
            {
                "event": "document_indexed",
                "status": "indexed",
                "document_id": document_id,
                "source_file": source_filename,
                "document_type": document_type,
                "chunk_count": chunk_index,
                "embedding_backend": settings.embedding_backend,
                "embedding_model": settings.embedding_model,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
        )
    )

    return {
        "document_id": document_id,
        "source_file": source_filename,
        "document_type": document_type,
        "title": title,
        "chunks_ingested": chunk_index,
        "metadata": cleaned_metadata,
        "embedding_backend": settings.embedding_backend,
        "embedding_model": settings.embedding_model,
    }


def ingest_sample_docs(
    db: Session,
    metadata_by_source: Mapping[str, DocumentMetadata] | None = None,
) -> dict[str, object]:
    sample_docs_dir = _repo_root() / "data" / "sample_docs"
    if not sample_docs_dir.exists():
        raise FileNotFoundError(f"Sample docs folder not found: {sample_docs_dir}")

    candidate_files = sorted(
        [path for path in sample_docs_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
    )
    if not candidate_files:
        raise ValueError("No supported sample documents found in data/sample_docs")

    ingested_files: list[str] = []
    document_count = 0
    chunk_count = 0

    try:
        for file_path in candidate_files:
            try:
                result = ingest_document(
                    db,
                    file_path=file_path,
                    source_filename=file_path.name,
                    document_type=file_path.suffix.lower().lstrip("."),
                    metadata=metadata_by_source.get(file_path.name) if metadata_by_source else None,
                )
            except EmptyDocumentError:
                continue

            ingested_files.append(file_path.name)
            document_count += 1
            chunk_count += int(result["chunks_ingested"])

        db.commit()
        logger.info(
            json.dumps(
                {
                    "event": "sample_ingestion_complete",
                    "status": "indexed",
                    "document_count": document_count,
                    "chunk_count": chunk_count,
                }
            )
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            json.dumps(
                {
                    "event": "sample_ingestion_failed",
                    "status": "failed",
                    "error_category": "internal",
                    "error_type": type(exc).__name__,
                }
            )
        )
        raise

    return {
        "sample_docs_path": str(sample_docs_dir),
        "documents_ingested": document_count,
        "chunks_ingested": chunk_count,
        "files": ingested_files,
    }


def list_documents(db: Session) -> list[dict[str, object]]:
    """Return indexed-document summaries (metadata + chunk counts), newest first."""
    rows = db.execute(
        text(
            """
            SELECT
                d.id, d.source_file, d.document_type, d.title,
                d.jurisdiction, d.court, d.canonical_citation,
                d.decision_date, d.practice_area, d.created_at,
                COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC, d.source_file ASC
            """
        )
    ).mappings().all()

    return [
        {
            "document_id": str(row["id"]),
            "source_file": row["source_file"],
            "document_type": row["document_type"],
            "title": row["title"],
            "chunk_count": int(row["chunk_count"]),
            "jurisdiction": row["jurisdiction"],
            "court": row["court"],
            "canonical_citation": row["canonical_citation"],
            "decision_date": row["decision_date"].isoformat() if row["decision_date"] else None,
            "practice_area": row["practice_area"],
        }
        for row in rows
    ]
