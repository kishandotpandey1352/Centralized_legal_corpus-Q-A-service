from fastapi import FastAPI

from app.api.routes_health import router as health_router
from app.api.routes_ingestion import router as ingestion_router
from app.api.routes_retrieval import router as retrieval_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(ingestion_router)
app.include_router(retrieval_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Legal RAG API is running"}
