from datetime import date

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.retrieval.service import (
    answer_question,
    extract_key_topics,
    retrieve_similar_chunks,
    summarize_document,
)


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    source_file: str | None = None
    document_id: str | None = None
    document_type: str | None = None
    jurisdiction: str | None = None
    court: str | None = None
    canonical_citation: str | None = None
    decision_date: date | None = None
    practice_area: str | None = None
    rerank: bool = True
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    source_file: str | None = None
    document_id: str | None = None
    document_type: str | None = None
    jurisdiction: str | None = None
    court: str | None = None
    canonical_citation: str | None = None
    decision_date: date | None = None
    practice_area: str | None = None
    rerank: bool = True
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)


class SummaryRequest(BaseModel):
    source_file: str | None = None
    document_id: str | None = None
    max_chunks: int = Field(default=20, ge=1, le=20)


class KeywordsRequest(BaseModel):
    document_id: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


router = APIRouter(prefix="/query", tags=["retrieval"])


@router.post("/retrieve")
def retrieve(request: RetrievalRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        kwargs = {
            "source_file": request.source_file,
            "document_id": request.document_id,
            "document_type": request.document_type,
            "jurisdiction": request.jurisdiction,
            "court": request.court,
            "canonical_citation": request.canonical_citation,
            "decision_date": request.decision_date.isoformat() if request.decision_date else None,
            "practice_area": request.practice_area,
            "rerank": request.rerank,
            "candidate_pool_size": request.candidate_pool_size,
        }
        return retrieve_similar_chunks(
            db,
            query=request.query,
            top_k=request.top_k,
            **{key: value for key, value in kwargs.items() if value is not None or key in {"rerank"}},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/answer")
def answer(request: AnswerRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        kwargs = {
            "source_file": request.source_file,
            "document_id": request.document_id,
            "document_type": request.document_type,
            "jurisdiction": request.jurisdiction,
            "court": request.court,
            "canonical_citation": request.canonical_citation,
            "decision_date": request.decision_date.isoformat() if request.decision_date else None,
            "practice_area": request.practice_area,
            "rerank": request.rerank,
            "candidate_pool_size": request.candidate_pool_size,
        }
        return answer_question(
            db,
            question=request.question,
            top_k=request.top_k,
            **{key: value for key, value in kwargs.items() if value is not None or key in {"rerank"}},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/summary")
def summary(request: SummaryRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    if not request.source_file and not request.document_id:
        raise HTTPException(status_code=400, detail="source_file or document_id is required")
    try:
        return summarize_document(
            db,
            source_file=request.source_file,
            document_id=request.document_id,
            max_chunks=request.max_chunks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/keywords")
def keywords(request: KeywordsRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return extract_key_topics(db, document_id=request.document_id, limit=request.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
