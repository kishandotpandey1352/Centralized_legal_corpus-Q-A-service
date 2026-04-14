from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.retrieval.service import answer_question, retrieve_similar_chunks, summarize_document


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    source_file: str | None = None
    document_type: str | None = None
    rerank: bool = True
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    source_file: str | None = None
    document_type: str | None = None
    rerank: bool = True
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)


class SummaryRequest(BaseModel):
    source_file: str = Field(min_length=1)
    max_chunks: int = Field(default=6, ge=1, le=20)


router = APIRouter(prefix="/query", tags=["retrieval"])


@router.post("/retrieve")
def retrieve(request: RetrievalRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return retrieve_similar_chunks(
            db,
            query=request.query,
            top_k=request.top_k,
            source_file=request.source_file,
            document_type=request.document_type,
            rerank=request.rerank,
            candidate_pool_size=request.candidate_pool_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/answer")
def answer(request: AnswerRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return answer_question(
            db,
            question=request.question,
            top_k=request.top_k,
            source_file=request.source_file,
            document_type=request.document_type,
            rerank=request.rerank,
            candidate_pool_size=request.candidate_pool_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/summary")
def summary(request: SummaryRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return summarize_document(db, source_file=request.source_file, max_chunks=request.max_chunks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
