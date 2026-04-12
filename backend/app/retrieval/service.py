from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.service import build_grounded_prompt, build_summary_prompt, generate_answer_with_ollama
from app.retrieval.embeddings import embed_texts, vector_to_pg_literal


def retrieve_similar_chunks(db: Session, query: str, top_k: int = 5) -> dict[str, object]:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Query cannot be empty")

    top_k = max(1, min(top_k, 20))
    query_embedding = embed_texts(
        [cleaned_query],
        model_name=settings.embedding_model,
        backend=settings.embedding_backend,
        cache_dir=settings.embedding_cache_dir,
    )[0]
    query_vector = vector_to_pg_literal(query_embedding)

    # For tiny datasets in early MVP, exact scan is more reliable than IVFFlat approximation.
    db.execute(text("SET LOCAL enable_indexscan = off"))
    db.execute(text("SET LOCAL enable_bitmapscan = off"))
    db.execute(text("SET LOCAL ivfflat.probes = 10"))

    rows = db.execute(
        text(
            """
            SELECT
                c.id,
                c.document_id,
                c.chunk_index,
                c.chunk_text,
                c.page_range,
                c.section_title,
                d.source_file,
                (1 - (c.embedding <=> CAST(:query_vector AS vector))) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> CAST(:query_vector AS vector)
            LIMIT :top_k
            """
        ),
        {"query_vector": query_vector, "top_k": top_k},
    ).mappings().all()

    return {
        "query": cleaned_query,
        "top_k": top_k,
        "results": [
            {
                "chunk_id": str(row["id"]),
                "document_id": str(row["document_id"]),
                "source_file": row["source_file"],
                "chunk_index": row["chunk_index"],
                "page_range": row["page_range"],
                "section_title": row["section_title"],
                "score": round(float(row["score"]), 6) if row["score"] is not None else None,
                "chunk_text": row["chunk_text"],
            }
            for row in rows
        ],
    }


def _build_citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for index, item in enumerate(results, start=1):
        citations.append(
            {
                "id": f"C{index}",
                "source_file": item.get("source_file"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "page_range": item.get("page_range"),
                "section_title": item.get("section_title"),
                "score": item.get("score"),
            }
        )
    return citations


def _fallback_answer(question: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "Insufficient evidence in provided documents."

    top_chunk = results[0].get("chunk_text", "").strip()
    if not top_chunk:
        return "Insufficient evidence in provided documents."

    concise = top_chunk[:500].strip()
    return f"Based on retrieved evidence [C1], {concise}"


def _top_score(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    score = results[0].get("score")
    if isinstance(score, (float, int)):
        return float(score)
    return 0.0


def _contains_force_keyword(results: list[dict[str, Any]], keyword: str) -> bool:
    target = keyword.strip().lower()
    if not target:
        return False
    for item in results[:3]:
        chunk_text = str(item.get("chunk_text", "")).lower()
        if target in chunk_text:
            return True
    return False


def _should_force_cited_answer(*, top_score: float, has_forced_keyword: bool, min_score: float) -> bool:
    return has_forced_keyword and top_score >= min_score


def _question_terms(question: str) -> set[str]:
    stopwords = {
        "what",
        "which",
        "when",
        "where",
        "who",
        "why",
        "how",
        "is",
        "the",
        "a",
        "an",
        "in",
        "on",
        "for",
        "to",
        "of",
        "and",
        "or",
        "with",
        "from",
        "before",
        "after",
    }
    tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return {token for token in tokens if len(token) > 2 and token not in stopwords}


def _chunk_overlap_ratio(terms: set[str], chunk_text: str) -> float:
    if not terms:
        return 0.0
    text = chunk_text.lower()
    hits = 0
    for term in terms:
        if term in text:
            hits += 1
    return hits / len(terms)


def _lexical_confidence(question: str, results: list[dict[str, Any]]) -> float:
    terms = _question_terms(question)
    if not terms or not results:
        return 0.0
    best = 0.0
    for item in results[:3]:
        ratio = _chunk_overlap_ratio(terms, str(item.get("chunk_text", "")))
        if ratio > best:
            best = ratio
    return best


def _best_overlap_chunk(question: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    terms = _question_terms(question)
    if not terms:
        return results[0] if results else None

    best_item: dict[str, Any] | None = None
    best_ratio = -1.0
    for item in results[:3]:
        ratio = _chunk_overlap_ratio(terms, str(item.get("chunk_text", "")))
        if ratio > best_ratio:
            best_ratio = ratio
            best_item = item
    return best_item


def _direct_cited_answer(question: str, results: list[dict[str, Any]]) -> str:
    item = _best_overlap_chunk(question, results)
    if not item:
        return "Insufficient evidence in provided documents."

    chunk_text = str(item.get("chunk_text", "")).strip()
    if not chunk_text:
        return "Insufficient evidence in provided documents."

    terms = _question_terms(question)
    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", chunk_text) if segment.strip()]
    if not sentences:
        sentences = [chunk_text]

    best_sentence = sentences[0]
    best_ratio = -1.0
    for sentence in sentences:
        ratio = _chunk_overlap_ratio(terms, sentence)
        if ratio > best_ratio:
            best_ratio = ratio
            best_sentence = sentence

    concise = _clean_sentence(best_sentence)
    if _is_person_question(question):
        return f"From the retrieved record, {concise} [C1]"
    return f"{concise} [C1]"


def _is_person_question(question: str) -> bool:
    lowered = question.lower().strip()
    return lowered.startswith("tell me about") or lowered.startswith("who is")


def _clean_sentence(text_value: str) -> str:
    compact = " ".join(text_value.split())
    if not compact:
        return "Insufficient evidence in provided documents."

    if compact.endswith((".", "!", "?")):
        return compact[:320].strip()

    last_terminal = max(compact.rfind("."), compact.rfind("!"), compact.rfind("?"), compact.rfind(";"), compact.rfind(":"))
    if last_terminal >= 40:
        compact = compact[: last_terminal + 1]
        return compact[:320].strip()

    compact = re.sub(
        r",\s*(where|which|who|that|when|while|because|if|as|and|or|but)\s+[^,.;:!?]{0,100}$",
        "",
        compact,
        flags=re.IGNORECASE,
    ).strip()

    compact = re.sub(r"\s+", " ", compact).strip()
    if compact and not compact.endswith((".", "!", "?")):
        compact = f"{compact}."
    return compact[:320].strip()


def _polish_answer_text(answer_text: str) -> str:
    stripped = answer_text.strip()
    if not stripped or stripped == "Insufficient evidence in provided documents.":
        return stripped

    citations = re.findall(r"\[C\d+\]", stripped)
    core = re.sub(r"\s*\[C\d+\]\s*", " ", stripped)
    core = _clean_sentence(core)

    if not citations:
        return core

    ordered_unique: list[str] = []
    for citation in citations:
        if citation not in ordered_unique:
            ordered_unique.append(citation)
    return f"{core} {' '.join(ordered_unique)}".strip()


def _polish_summary_text(summary_text: str) -> str:
    stripped = summary_text.strip()
    if not stripped or stripped == "Insufficient evidence in provided documents.":
        return stripped

    citations = re.findall(r"\[C\d+\]", stripped)
    core = re.sub(r"\s*\[C\d+\]\s*", " ", stripped)
    core = re.sub(r"(?m)^\s*-\s*", "", core)
    core = re.sub(r"\s+-\s+", " ", core)
    core = re.sub(r"\s+", " ", core).strip()

    if core and not core.endswith((".", "!", "?")):
        last_terminal = max(core.rfind("."), core.rfind("!"), core.rfind("?"), core.rfind(";"), core.rfind(":"))
        if last_terminal >= 20:
            core = core[: last_terminal + 1].strip()

    core = re.sub(r"\s+([,.;:!?])", r"\1", core).strip()
    if core and not core.endswith((".", "!", "?")):
        core = f"{core}."

    if not citations:
        return core

    ordered_unique: list[str] = []
    for citation in citations:
        if citation not in ordered_unique:
            ordered_unique.append(citation)
    return f"{core} {' '.join(ordered_unique)}".strip()


def _attach_adjacent_context(db: Session, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results:
        return results

    expanded: list[dict[str, Any]] = []
    for item in results:
        doc_id = item.get("document_id")
        chunk_index = item.get("chunk_index")
        if not isinstance(chunk_index, int):
            expanded.append(item)
            continue

        neighbors = db.execute(
            text(
                """
                SELECT chunk_index, chunk_text
                FROM chunks
                WHERE document_id = :document_id
                  AND chunk_index BETWEEN :start_idx AND :end_idx
                ORDER BY chunk_index
                """
            ),
            {
                "document_id": doc_id,
                "start_idx": max(chunk_index - 1, 0),
                "end_idx": chunk_index + 1,
            },
        ).mappings().all()

        stitched = " ".join(str(row["chunk_text"]).strip() for row in neighbors if row.get("chunk_text"))
        if stitched:
            updated = dict(item)
            updated["chunk_text"] = stitched
            expanded.append(updated)
        else:
            expanded.append(item)

    return expanded


def _force_concise_cited_answer(results: list[dict[str, Any]]) -> str:
    if not results:
        return "Insufficient evidence in provided documents."

    chunk_text = str(results[0].get("chunk_text", "")).strip()
    if not chunk_text:
        return "Insufficient evidence in provided documents."

    lowered = chunk_text.lower()
    target_phrase = "material breach"
    sentence = ""
    if target_phrase in lowered:
        start_idx = lowered.rfind(".", 0, lowered.find(target_phrase)) + 1
        end_idx = lowered.find(".", lowered.find(target_phrase))
        if end_idx == -1:
            end_idx = len(chunk_text)
        sentence = chunk_text[start_idx:end_idx].strip()

    if not sentence:
        sentence = chunk_text[:320].strip()

    return f"{sentence} [C1]"


def answer_question(db: Session, question: str, top_k: int = 5) -> dict[str, Any]:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("Question cannot be empty")

    retrieval = retrieve_similar_chunks(db=db, query=cleaned_question, top_k=top_k)
    results = retrieval.get("results", [])
    citations = _build_citations(results)

    if not results:
        return {
            "question": cleaned_question,
            "answer": "Insufficient evidence in provided documents.",
            "citations": [],
            "used_chunks": 0,
            "mode": "no-context",
        }

    enriched_results = _attach_adjacent_context(db, results)
    top_score_raw = _top_score(results)
    lexical_conf = _lexical_confidence(cleaned_question, enriched_results)
    top_score = min(top_score_raw, lexical_conf if lexical_conf > 0 else top_score_raw)
    has_forced_keyword = _contains_force_keyword(results, settings.qa_force_keyword)
    force_cited = _should_force_cited_answer(
        top_score=top_score,
        has_forced_keyword=has_forced_keyword,
        min_score=settings.qa_force_min_score,
    )
    confident_enough = top_score >= settings.qa_min_retrieval_score and lexical_conf >= settings.qa_min_lexical_overlap

    if lexical_conf >= settings.qa_direct_answer_min_overlap:
        return {
            "question": cleaned_question,
            "answer": _polish_answer_text(_direct_cited_answer(cleaned_question, enriched_results)),
            "citations": citations,
            "used_chunks": len(results),
            "mode": "evidence-direct",
            "top_score": round(top_score, 6),
            "raw_top_score": round(top_score_raw, 6),
            "lexical_confidence": round(lexical_conf, 6),
        }

    if force_cited:
        return {
            "question": cleaned_question,
            "answer": _polish_answer_text(_force_concise_cited_answer(enriched_results)),
            "citations": citations,
            "used_chunks": len(results),
            "mode": "forced-cited",
            "top_score": round(top_score, 6),
            "raw_top_score": round(top_score_raw, 6),
            "lexical_confidence": round(lexical_conf, 6),
        }

    if not confident_enough:
        return {
            "question": cleaned_question,
            "answer": "Insufficient evidence in provided documents.",
            "citations": citations,
            "used_chunks": len(results),
            "mode": "low-confidence",
            "top_score": round(top_score, 6),
            "raw_top_score": round(top_score_raw, 6),
            "lexical_confidence": round(lexical_conf, 6),
        }

    prompt = build_grounded_prompt(cleaned_question, enriched_results)
    if settings.generation_backend.strip().lower() != "ollama":
        raise RuntimeError(f"Unsupported generation backend: {settings.generation_backend}")

    try:
        answer_text = generate_answer_with_ollama(
            base_url=settings.ollama_base_url,
            model=settings.generation_model,
            prompt=prompt,
            timeout_seconds=settings.generation_timeout_seconds,
        )
        mode = "llm"
    except Exception:
        if settings.generation_strict:
            raise
        answer_text = _fallback_answer(cleaned_question, enriched_results)
        mode = "fallback"

    if force_cited and answer_text.strip() == "Insufficient evidence in provided documents.":
        answer_text = _force_concise_cited_answer(enriched_results)
        mode = "forced-cited"

    answer_text = _polish_answer_text(answer_text)

    return {
        "question": cleaned_question,
        "answer": answer_text,
        "citations": citations,
        "used_chunks": len(results),
        "mode": mode,
        "top_score": round(top_score, 6),
        "raw_top_score": round(top_score_raw, 6),
        "lexical_confidence": round(lexical_conf, 6),
    }


def _fallback_summary(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return "Insufficient evidence in provided documents."

    bullets: list[str] = []
    for index, item in enumerate(contexts[:4], start=1):
        chunk_text = str(item.get("chunk_text", "")).strip()
        if not chunk_text:
            continue
        cleaned = _clean_sentence(chunk_text)
        if cleaned and cleaned != "Insufficient evidence in provided documents.":
            bullets.append(f"- {cleaned} [C{index}]")

    if not bullets:
        return "Insufficient evidence in provided documents."
    return "\n".join(bullets)


def summarize_document(db: Session, source_file: str, max_chunks: int | None = None) -> dict[str, Any]:
    cleaned_source = source_file.strip()
    if not cleaned_source:
        raise ValueError("source_file cannot be empty")

    chunk_limit = max_chunks if max_chunks is not None else settings.summary_default_chunks
    chunk_limit = max(1, min(chunk_limit, 20))

    rows = db.execute(
        text(
            """
            SELECT
                c.id,
                c.chunk_index,
                c.chunk_text,
                c.page_range,
                c.section_title,
                d.source_file
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.source_file = :source_file
            ORDER BY c.chunk_index
            LIMIT :chunk_limit
            """
        ),
        {"source_file": cleaned_source, "chunk_limit": chunk_limit},
    ).mappings().all()

    contexts = [
        {
            "chunk_id": str(row["id"]),
            "source_file": row["source_file"],
            "chunk_index": row["chunk_index"],
            "page_range": row["page_range"],
            "section_title": row["section_title"],
            "chunk_text": row["chunk_text"],
            "score": 1.0,
        }
        for row in rows
    ]

    if not contexts:
        raise ValueError(f"No chunks found for source_file='{cleaned_source}'")

    citations = _build_citations(contexts)
    prompt = build_summary_prompt(cleaned_source, contexts)

    if settings.generation_backend.strip().lower() != "ollama":
        raise RuntimeError(f"Unsupported generation backend: {settings.generation_backend}")

    try:
        summary_text = generate_answer_with_ollama(
            base_url=settings.ollama_base_url,
            model=settings.generation_model,
            prompt=prompt,
            timeout_seconds=settings.generation_timeout_seconds,
        )
        mode = "llm-summary"
    except Exception:
        if settings.generation_strict:
            raise
        summary_text = _fallback_summary(contexts)
        mode = "fallback-summary"

    summary_text = _polish_summary_text(summary_text)

    return {
        "source_file": cleaned_source,
        "summary": summary_text,
        "citations": citations,
        "used_chunks": len(contexts),
        "mode": mode,
    }
