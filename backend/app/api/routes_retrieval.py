from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.retrieval.service import retrieve_similar_chunks


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


router = APIRouter(prefix="/query", tags=["retrieval"])


@router.post("/retrieve")
def retrieve(request: RetrievalRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return retrieve_similar_chunks(db, query=request.query, top_k=request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
