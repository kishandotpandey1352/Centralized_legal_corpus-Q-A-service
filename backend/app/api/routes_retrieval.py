from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.retrieval.service import answer_question, retrieve_similar_chunks


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


router = APIRouter(prefix="/query", tags=["retrieval"])


@router.post("/retrieve")
def retrieve(request: RetrievalRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return retrieve_similar_chunks(db, query=request.query, top_k=request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/answer")
def answer(request: AnswerRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return answer_question(db, question=request.question, top_k=request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
