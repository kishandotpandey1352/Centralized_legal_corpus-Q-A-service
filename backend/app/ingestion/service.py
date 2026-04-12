from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import fitz
from docx import Document
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.retrieval.embeddings import embed_texts, vector_to_pg_literal


SUPPORTED_EXTENSIONS = {".txt", ".docx", ".pdf"}


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


def ingest_sample_docs(db: Session) -> dict[str, object]:
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
            segments = _load_segments_from_path(file_path)
            full_text = "\n\n".join(segment.text for segment in segments).strip()
            if not full_text:
                continue

            db.execute(
                text("DELETE FROM documents WHERE source_file = :source_file"),
                {"source_file": file_path.name},
            )

            document_id = str(uuid4())
            db.execute(
                text(
                    """
                    INSERT INTO documents (id, source_file, document_type, title)
                    VALUES (:id, :source_file, :document_type, :title)
                    """
                ),
                {
                    "id": document_id,
                    "source_file": file_path.name,
                    "document_type": file_path.suffix.lower().lstrip("."),
                    "title": _extract_title(full_text, file_path.stem),
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

            document_count += 1
            chunk_count += chunk_index
            ingested_files.append(file_path.name)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "sample_docs_path": str(sample_docs_dir),
        "documents_ingested": document_count,
        "chunks_ingested": chunk_count,
        "files": ingested_files,
    }
