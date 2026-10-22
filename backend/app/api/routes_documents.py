from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ingestion.service import list_documents


router = APIRouter(tags=["documents"])


@router.get("/documents")
def get_documents(db: Session = Depends(get_db)) -> dict[str, object]:
    return {"documents": list_documents(db)}
