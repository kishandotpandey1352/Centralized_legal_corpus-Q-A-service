from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ingestion.service import ingest_sample_docs


router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/sample-docs")
def ingest_local_sample_docs(db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return ingest_sample_docs(db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
