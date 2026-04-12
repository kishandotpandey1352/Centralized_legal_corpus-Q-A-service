from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Legal RAG API"
    app_env: str = "dev"
    api_port: int = 8000

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "legal_rag"
    postgres_user: str = "legal_rag"
    postgres_password: str = "legal_rag"
    database_url: str = "postgresql+psycopg://legal_rag:legal_rag@localhost:5432/legal_rag"

    ollama_base_url: str = "http://localhost:11434"
    embedding_backend: str = "hash"
    embedding_model: str = "BAAI/bge-m3"
    embedding_cache_dir: str = "backend/.model_cache/sentence-transformers"
    generation_backend: str = "ollama"
    generation_model: str = "qwen2.5:7b-instruct"
    generation_timeout_seconds: float = 60.0
    generation_strict: bool = True
    qa_min_retrieval_score: float = 0.35
    qa_force_keyword: str = "material breach"
    qa_force_min_score: float = 0.45
    qa_min_lexical_overlap: float = 0.2
    qa_direct_answer_min_overlap: float = 0.55
    summary_default_chunks: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
