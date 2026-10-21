from datetime import date

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ingestion.service import DocumentMetadata, ingest_sample_docs


class DocumentMetadataRequest(BaseModel):
    jurisdiction: str | None = None
    court: str | None = None
    canonical_citation: str | None = None
    decision_date: date | None = None
    practice_area: str | None = None


class SampleDocsIngestionRequest(BaseModel):
    metadata_by_source: dict[str, DocumentMetadataRequest] | None = None


router = APIRouter(prefix="/ingest", tags=["ingestion"])


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
