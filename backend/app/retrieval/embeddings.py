from __future__ import annotations

import hashlib
import math
from pathlib import Path
from functools import lru_cache


EMBEDDING_DIMENSION = 1024


@lru_cache(maxsize=1)
def _load_sentence_transformer(model_name: str, cache_dir: str):
    from sentence_transformers import SentenceTransformer

    resolved_cache = Path(cache_dir)
    if not resolved_cache.is_absolute():
        resolved_cache = Path(__file__).resolve().parents[3] / resolved_cache
    resolved_cache.mkdir(parents=True, exist_ok=True)

    return SentenceTransformer(
        model_name,
        cache_folder=str(resolved_cache),
        model_kwargs={"use_safetensors": False},
    )


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _hashed_embedding(text_value: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    tokens = text_value.lower().split()
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    return _normalize(vector)


def embed_texts(
    texts: list[str], model_name: str, backend: str = "hash", cache_dir: str = "backend/.model_cache/sentence-transformers"
) -> list[list[float]]:
    if not texts:
        return []

    backend_normalized = backend.strip().lower()

    if backend_normalized == "sentence-transformers":
        try:
            model = _load_sentence_transformer(model_name, cache_dir)
            embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [list(map(float, row)) for row in embeddings]
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load sentence-transformers model '{model_name}'. "
                "Check network access and model availability."
            ) from exc

    if backend_normalized != "hash":
        # Unknown backend values should not break ingestion/retrieval in early MVP stages.
        backend_normalized = "hash"

    if backend_normalized == "hash":
        return [_hashed_embedding(text_value) for text_value in texts]

    return [_hashed_embedding(text_value) for text_value in texts]


def vector_to_pg_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
