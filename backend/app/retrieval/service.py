from __future__ import annotations

import re
import json
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.service import build_grounded_prompt, build_summary_prompt, generate_answer_with_ollama
from app.retrieval.embeddings import embed_texts, vector_to_pg_literal


_CITATION_MARKER_RE = re.compile(r"\[C[^\]\s]+\]")
_VALID_CITATION_ID_RE = re.compile(r"C[1-9]\d*")


def _normalize_vector_score(score_value: float | int | None) -> float:
    if not isinstance(score_value, (float, int)):
        return 0.0
    score = float(score_value)
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _normalize_decision_date(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("decision_date must use ISO format YYYY-MM-DD") from exc


def _rerank_results(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    lexical_weight: float = 0.35,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    lexical_weight = max(0.0, min(lexical_weight, 1.0))
    vector_weight = 1.0 - lexical_weight

    rescored: list[dict[str, Any]] = []
    for item in candidates:
        lexical_score = _lexical_relevance(query, str(item.get("chunk_text", "")))
        vector_score = _normalize_vector_score(item.get("score"))
        hybrid_score = (vector_weight * vector_score) + (lexical_weight * lexical_score)

        updated = dict(item)
        updated["vector_score"] = round(vector_score, 6)
        updated["lexical_score"] = round(lexical_score, 6)
        updated["hybrid_score"] = round(hybrid_score, 6)
        rescored.append(updated)

    rescored.sort(
        key=lambda row: (
            float(row.get("hybrid_score", 0.0)),
            float(row.get("vector_score", 0.0)),
        ),
        reverse=True,
    )
    return rescored[:top_k]


def _search_candidates(
    db: Session,
    query: str,
    candidate_k: int,
    *,
    source_file: str | None = None,
    document_id: str | None = None,
    document_type: str | None = None,
    jurisdiction: str | None = None,
    court: str | None = None,
    canonical_citation: str | None = None,
    decision_date: date | None = None,
    practice_area: str | None = None,
    rerank: bool = True,
) -> list[dict[str, Any]]:
    """Stage 1: dense candidate retrieval over pgvector, optionally reranked."""
    query_embedding = embed_texts(
        [query],
        model_name=settings.embedding_model,
        backend=settings.embedding_backend,
        cache_dir=settings.embedding_cache_dir,
    )[0]
    query_vector = vector_to_pg_literal(query_embedding)

    # For tiny datasets in early MVP, exact scan is more reliable than IVFFlat approximation.
    db.execute(text("SET LOCAL enable_indexscan = off"))
    db.execute(text("SET LOCAL enable_bitmapscan = off"))
    db.execute(text("SET LOCAL ivfflat.probes = 10"))

    where_clauses = ["c.embedding IS NOT NULL"]
    sql_params: dict[str, Any] = {"query_vector": query_vector, "candidate_pool": candidate_k}

    if source_file:
        where_clauses.append("d.source_file = :source_file")
        sql_params["source_file"] = source_file
    if document_id:
        where_clauses.append("c.document_id = :document_id")
        sql_params["document_id"] = document_id
    if document_type:
        where_clauses.append("d.document_type = :document_type")
        sql_params["document_type"] = document_type
    metadata_filters = {
        "jurisdiction": jurisdiction,
        "court": court,
        "canonical_citation": canonical_citation,
        "decision_date": decision_date.isoformat() if decision_date else None,
        "practice_area": practice_area,
    }
    for field, value in metadata_filters.items():
        if value:
            where_clauses.append(f"d.{field} = :{field}")
            sql_params[field] = value

    sql_query = f"""
        SELECT
            c.id,
            c.document_id,
            c.chunk_index,
            c.chunk_text,
            c.page_range,
            c.section_title,
            d.source_file,
            d.document_type,
            d.jurisdiction,
            d.court,
            d.canonical_citation,
            d.decision_date,
            d.practice_area,
            (1 - (c.embedding <=> CAST(:query_vector AS vector))) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY c.embedding <=> CAST(:query_vector AS vector)
        LIMIT :candidate_pool
    """

    rows = db.execute(text(sql_query), sql_params).mappings().all()

    candidates = [
        {
            "chunk_id": str(row["id"]),
            "document_id": str(row["document_id"]),
            "source_file": row["source_file"],
            "document_type": row["document_type"],
            "jurisdiction": row["jurisdiction"],
            "court": row["court"],
            "canonical_citation": row["canonical_citation"],
            "decision_date": row["decision_date"].isoformat() if row["decision_date"] else None,
            "practice_area": row["practice_area"],
            "chunk_index": row["chunk_index"],
            "page_range": row["page_range"],
            "section_title": row["section_title"],
            "score": round(float(row["score"]), 6) if row["score"] is not None else None,
            "chunk_text": row["chunk_text"],
        }
        for row in rows
    ]

    if rerank:
        return _rerank_results(
            query=query,
            candidates=candidates,
            top_k=candidate_k,
            lexical_weight=settings.qa_rerank_lexical_weight,
        )
    return candidates


def _select_final_context(
    candidates: list[dict[str, Any]],
    top_k: int,
    min_relevance_score: float | None,
) -> list[dict[str, Any]]:
    """Stage 2: keep only the strongest reranked evidence for generation."""
    ranked = sorted(
        candidates,
        key=lambda row: (float(row.get("hybrid_score", 0.0)), float(row.get("vector_score", 0.0))),
        reverse=True,
    )
    if min_relevance_score is not None:
        ranked = [row for row in ranked if float(row.get("hybrid_score", 0.0)) >= min_relevance_score]
    return ranked[:top_k]


def retrieve_similar_chunks(
    db: Session,
    query: str,
    top_k: int = 5,
    source_file: str | None = None,
    document_id: str | None = None,
    document_type: str | None = None,
    jurisdiction: str | None = None,
    court: str | None = None,
    canonical_citation: str | None = None,
    decision_date: str | date | None = None,
    practice_area: str | None = None,
    rerank: bool = True,
    candidate_pool_size: int | None = None,
) -> dict[str, object]:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("Query cannot be empty")

    top_k = max(1, min(top_k, 20))

    cleaned_source_file = source_file.strip() if isinstance(source_file, str) and source_file.strip() else None
    cleaned_document_id = document_id.strip() if isinstance(document_id, str) and document_id.strip() else None
    cleaned_document_type = document_type.strip().lower() if isinstance(document_type, str) and document_type.strip() else None
    cleaned_jurisdiction = jurisdiction.strip() if isinstance(jurisdiction, str) and jurisdiction.strip() else None
    cleaned_court = court.strip() if isinstance(court, str) and court.strip() else None
    cleaned_citation = canonical_citation.strip() if isinstance(canonical_citation, str) and canonical_citation.strip() else None
    cleaned_decision_date = _normalize_decision_date(decision_date)
    cleaned_practice_area = practice_area.strip() if isinstance(practice_area, str) and practice_area.strip() else None

    pool_size = candidate_pool_size if candidate_pool_size is not None else max(settings.retrieval_candidate_k, top_k)
    pool_size = max(top_k, min(pool_size, 100))

    ranked = _search_candidates(
        db,
        cleaned_query,
        pool_size,
        source_file=cleaned_source_file,
        document_id=cleaned_document_id,
        document_type=cleaned_document_type,
        jurisdiction=cleaned_jurisdiction,
        court=cleaned_court,
        canonical_citation=cleaned_citation,
        decision_date=cleaned_decision_date,
        practice_area=cleaned_practice_area,
        rerank=rerank,
    )

    return {
        "query": cleaned_query,
        "top_k": top_k,
        "source_file": cleaned_source_file,
        "document_id": cleaned_document_id,
        "document_type": cleaned_document_type,
        "jurisdiction": cleaned_jurisdiction,
        "court": cleaned_court,
        "canonical_citation": cleaned_citation,
        "decision_date": cleaned_decision_date.isoformat() if cleaned_decision_date else None,
        "practice_area": cleaned_practice_area,
        "rerank_enabled": rerank,
        "candidate_pool_size": pool_size,
        "results": ranked[:top_k],
    }


def _build_citations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for item in results:
        if not str(item.get("source_file") or "").strip() or not str(item.get("chunk_id") or "").strip():
            continue
        index = len(citations) + 1
        citations.append(
            {
                "id": f"C{index}",
                "document_id": item.get("document_id"),
                "source_file": item.get("source_file"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "page_range": item.get("page_range"),
                "section_title": item.get("section_title"),
                "jurisdiction": item.get("jurisdiction"),
                "court": item.get("court"),
                "canonical_citation": item.get("canonical_citation"),
                "decision_date": item.get("decision_date"),
                "practice_area": item.get("practice_area"),
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


_STOPWORDS = {
    "what",
    "which",
    "when",
    "where",
    "who",
    "why",
    "how",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "do",
    "does",
    "did",
    "have",
    "has",
    "had",
    "the",
    "a",
    "an",
    "in",
    "on",
    "at",
    "for",
    "to",
    "of",
    "and",
    "or",
    "with",
    "from",
    "by",
    "about",
    "before",
    "after",
    "between",
    "into",
    "their",
    "there",
    "these",
    "those",
    "should",
    "would",
    "could",
    "can",
    "may",
    "must",
    "doesn",
    "don",
}


def _question_terms(question: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
    return [token for token in tokens if len(token) > 2 and token not in _STOPWORDS]


def _question_phrases(question: str) -> list[str]:
    terms = _question_terms(question)
    phrases: list[str] = []
    for size in (2, 3):
        for index in range(len(terms) - size + 1):
            phrases.append(" ".join(terms[index : index + size]))
    return phrases


def _lexical_relevance(question: str, chunk_text: str) -> float:
    terms = _question_terms(question)
    phrases = _question_phrases(question)
    if not terms and not phrases:
        return 0.0

    text = chunk_text.lower()
    term_hits = sum(1 for term in terms if term in text)
    phrase_hits = sum(1 for phrase in phrases if phrase in text)
    total = len(terms) + len(phrases)
    return (term_hits + phrase_hits) / total if total else 0.0


def _lexical_confidence(question: str, results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    best = 0.0
    for item in results[:3]:
        ratio = _lexical_relevance(question, str(item.get("chunk_text", "")))
        if ratio > best:
            best = ratio
    return best


def _best_overlap_chunk(question: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None

    best_item: dict[str, Any] | None = None
    best_ratio = -1.0
    for item in results[:3]:
        ratio = _lexical_relevance(question, str(item.get("chunk_text", "")))
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

    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", chunk_text) if segment.strip()]
    if not sentences:
        sentences = [chunk_text]

    best_sentence = sentences[0]
    best_ratio = -1.0
    for sentence in sentences:
        ratio = _lexical_relevance(question, sentence)
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


def _extract_fact_sentence(chunk_text: str) -> str:
    cleaned = _clean_sentence(chunk_text)
    if cleaned == "Insufficient evidence in provided documents.":
        return ""
    return cleaned


def _structured_summary_from_contexts(contexts: list[dict[str, Any]], max_points: int = 4) -> str:
    lines: list[str] = []
    for index, item in enumerate(contexts[:max_points], start=1):
        sentence = _extract_fact_sentence(str(item.get("chunk_text", "")).strip())
        if not sentence:
            continue
        lines.append(f"{index}. {sentence} [C{index}]")

    if not lines:
        return "Insufficient evidence in provided documents."
    return "\n".join(lines)


def _summary_word_count(text_value: str) -> int:
    return len(re.findall(r"\b\w+\b", text_value))


def _summary_sentences(text_value: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text_value) if segment.strip()]


def _summary_needs_repair(summary_text: str, min_inline_citations: int) -> bool:
    stripped = summary_text.strip()
    if not stripped:
        return True

    lowered = stripped.lower()
    drift_markers = (
        "i think",
        "maybe",
        "likely",
        "might",
        "could be",
        "possibly",
        "outside the provided context",
    )
    if any(marker in lowered for marker in drift_markers):
        return True

    sentence_count = len(_summary_sentences(stripped))
    word_count = _summary_word_count(stripped)
    inline_count = len(re.findall(r"\[C\d+\]", stripped))

    if sentence_count > 6:
        return True
    if word_count > 170:
        return True
    if inline_count < min_inline_citations:
        return True
    return False


def _extract_inline_citation_ids(text_value: str) -> list[str]:
    return [match[1:-1] for match in _CITATION_MARKER_RE.findall(text_value or "")]


def _enforce_citation_integrity(
    text_value: str,
    citations: list[dict[str, Any]],
    min_required: int = 1,
    preserve_line_breaks: bool = False,
) -> str:
    stripped = text_value.strip()
    if not stripped:
        return stripped

    valid_ids: list[str] = []
    for citation in citations:
        citation_id = str(citation.get("id", "")).strip()
        if _VALID_CITATION_ID_RE.fullmatch(citation_id) and citation_id not in valid_ids:
            valid_ids.append(citation_id)

    if not valid_ids:
        if stripped == "Insufficient evidence in provided documents.":
            return stripped
        return "Insufficient evidence in provided documents."

    inline_ids = _extract_inline_citation_ids(stripped)
    filtered_inline = [citation_id for citation_id in inline_ids if citation_id in valid_ids]

    required = max(1, min(min_required, len(valid_ids)))
    if len(filtered_inline) < required:
        for citation_id in valid_ids:
            if citation_id not in filtered_inline:
                filtered_inline.append(citation_id)
            if len(filtered_inline) >= required:
                break

    # Rebuild text with a stable inline citation tail using only known citation IDs.
    if preserve_line_breaks:
        core = _CITATION_MARKER_RE.sub("", stripped)
        lines = [re.sub(r"\s+", " ", line).strip() for line in core.splitlines() if line.strip()]
        core = "\n".join(lines)
    else:
        core = _CITATION_MARKER_RE.sub(" ", stripped)
        core = re.sub(r"\s+", " ", core).strip()
    if not core:
        core = "Insufficient evidence in provided documents."

    ordered_unique: list[str] = []
    for citation_id in filtered_inline:
        if citation_id not in ordered_unique:
            ordered_unique.append(citation_id)

    return f"{core} {' '.join(f'[{citation_id}]' for citation_id in ordered_unique)}".strip()


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


def answer_question(
    db: Session,
    question: str,
    top_k: int = 5,
    source_file: str | None = None,
    document_id: str | None = None,
    document_type: str | None = None,
    jurisdiction: str | None = None,
    court: str | None = None,
    canonical_citation: str | None = None,
    decision_date: str | date | None = None,
    practice_area: str | None = None,
    rerank: bool = True,
    candidate_pool_size: int | None = None,
) -> dict[str, Any]:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("Question cannot be empty")

    cleaned_source_file = source_file.strip() if isinstance(source_file, str) and source_file.strip() else None
    cleaned_document_id = document_id.strip() if isinstance(document_id, str) and document_id.strip() else None
    cleaned_document_type = document_type.strip().lower() if isinstance(document_type, str) and document_type.strip() else None
    cleaned_jurisdiction = jurisdiction.strip() if isinstance(jurisdiction, str) and jurisdiction.strip() else None
    cleaned_court = court.strip() if isinstance(court, str) and court.strip() else None
    cleaned_citation = canonical_citation.strip() if isinstance(canonical_citation, str) and canonical_citation.strip() else None
    cleaned_decision_date = _normalize_decision_date(decision_date)
    cleaned_practice_area = practice_area.strip() if isinstance(practice_area, str) and practice_area.strip() else None

    candidate_k = candidate_pool_size if candidate_pool_size is not None else max(settings.retrieval_candidate_k, settings.rag_context_top_k)
    candidate_k = max(settings.rag_context_top_k, min(candidate_k, 100))

    candidates = _search_candidates(
        db,
        cleaned_question,
        candidate_k,
        source_file=cleaned_source_file,
        document_id=cleaned_document_id,
        document_type=cleaned_document_type,
        jurisdiction=cleaned_jurisdiction,
        court=cleaned_court,
        canonical_citation=cleaned_citation,
        decision_date=cleaned_decision_date,
        practice_area=cleaned_practice_area,
        rerank=rerank,
    )

    final_context = _select_final_context(
        candidates,
        settings.rag_context_top_k,
        settings.rag_min_relevance_score,
    )
    citations = _build_citations(final_context)
    answer_min_inline = 2 if len(citations) >= 2 else 1

    diagnostics: dict[str, Any] = {
        "candidates_retrieved": len(candidates),
        "context_chunks": len(final_context),
    }

    if not final_context:
        return {
            "question": cleaned_question,
            "answer": "Insufficient evidence in provided documents.",
            "citations": [],
            "used_chunks": 0,
            "mode": "no-context",
            "evidence": [],
            **diagnostics,
        }

    enriched_results = _attach_adjacent_context(db, final_context)
    top_score_raw = _top_score(final_context)
    lexical_conf = _lexical_confidence(cleaned_question, enriched_results)
    top_score = min(top_score_raw, lexical_conf if lexical_conf > 0 else top_score_raw)
    has_forced_keyword = _contains_force_keyword(final_context, settings.qa_force_keyword)
    force_cited = _should_force_cited_answer(
        top_score=top_score,
        has_forced_keyword=has_forced_keyword,
        min_score=settings.qa_force_min_score,
    )
    confident_enough = top_score >= settings.qa_min_retrieval_score and lexical_conf >= settings.qa_min_lexical_overlap

    if lexical_conf >= settings.qa_direct_answer_min_overlap:
        return {
            "question": cleaned_question,
            "answer": _enforce_citation_integrity(
                _polish_answer_text(_direct_cited_answer(cleaned_question, enriched_results)),
                citations,
                min_required=answer_min_inline,
            ),
            "citations": citations,
            "used_chunks": len(final_context),
            "mode": "evidence-direct",
            "evidence": final_context,
            "top_score": round(top_score, 6),
            "raw_top_score": round(top_score_raw, 6),
            "lexical_confidence": round(lexical_conf, 6),
            **diagnostics,
        }

    if force_cited:
        return {
            "question": cleaned_question,
            "answer": _enforce_citation_integrity(
                _polish_answer_text(_force_concise_cited_answer(enriched_results)),
                citations,
                min_required=answer_min_inline,
            ),
            "citations": citations,
            "used_chunks": len(final_context),
            "mode": "forced-cited",
            "evidence": final_context,
            "top_score": round(top_score, 6),
            "raw_top_score": round(top_score_raw, 6),
            "lexical_confidence": round(lexical_conf, 6),
            **diagnostics,
        }

    if not confident_enough:
        return {
            "question": cleaned_question,
            "answer": _enforce_citation_integrity(
                "Insufficient evidence in provided documents.",
                citations,
                min_required=answer_min_inline,
            ),
            "citations": citations,
            "used_chunks": len(final_context),
            "mode": "low-confidence",
            "evidence": final_context,
            "top_score": round(top_score, 6),
            "raw_top_score": round(top_score_raw, 6),
            "lexical_confidence": round(lexical_conf, 6),
            **diagnostics,
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

    answer_text = _enforce_citation_integrity(
        _polish_answer_text(answer_text),
        citations,
        min_required=answer_min_inline,
    )

    return {
        "question": cleaned_question,
        "answer": answer_text,
        "citations": citations,
        "used_chunks": len(final_context),
        "mode": mode,
        "evidence": final_context,
        "source_file_filter": cleaned_source_file,
        "document_id_filter": cleaned_document_id,
        "document_type_filter": cleaned_document_type,
        "rerank_enabled": rerank,
        "top_score": round(top_score, 6),
        "raw_top_score": round(top_score_raw, 6),
        "lexical_confidence": round(lexical_conf, 6),
        **diagnostics,
    }


def _fallback_summary(contexts: list[dict[str, Any]]) -> str:
    return _structured_summary_from_contexts(contexts, max_points=4)


def summarize_document(
    db: Session,
    source_file: str | None = None,
    document_id: str | None = None,
    max_chunks: int | None = None,
) -> dict[str, Any]:
    cleaned_source = source_file.strip() if isinstance(source_file, str) and source_file.strip() else None
    cleaned_document_id = document_id.strip() if isinstance(document_id, str) and document_id.strip() else None
    if not cleaned_source and not cleaned_document_id:
        raise ValueError("source_file or document_id is required")

    chunk_limit = max_chunks if max_chunks is not None else settings.summary_default_chunks
    chunk_limit = max(1, min(chunk_limit, 20))

    if cleaned_source:
        where_clause = "d.source_file = :source_file"
        sql_params: dict[str, Any] = {"source_file": cleaned_source, "chunk_limit": chunk_limit}
    else:
        where_clause = "c.document_id = :document_id"
        sql_params = {"document_id": cleaned_document_id, "chunk_limit": chunk_limit}

    rows = db.execute(
        text(
            f"""
            SELECT
                c.id,
                c.chunk_index,
                c.chunk_text,
                c.page_range,
                c.section_title,
                d.source_file
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE {where_clause}
            ORDER BY c.chunk_index
            LIMIT :chunk_limit
            """
        ),
        sql_params,
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
        target = f"source_file='{cleaned_source}'" if cleaned_source else f"document_id='{cleaned_document_id}'"
        raise ValueError(f"No chunks found for {target}")

    summary_source = cleaned_source or contexts[0]["source_file"]
    citations = _build_citations(contexts)
    prompt = build_summary_prompt(summary_source, contexts)

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

    min_summary_inline = 2 if len(citations) >= 2 else 1
    polished_summary = _enforce_citation_integrity(
        _polish_summary_text(summary_text),
        citations,
        min_required=min_summary_inline,
        preserve_line_breaks=True,
    )

    if _summary_needs_repair(polished_summary, min_summary_inline):
        polished_summary = _enforce_citation_integrity(
            _structured_summary_from_contexts(contexts, max_points=4),
            citations,
            min_required=min_summary_inline,
            preserve_line_breaks=True,
        )

    return {
        "source_file": summary_source,
        "document_id": cleaned_document_id,
        "summary": polished_summary,
        "citations": citations,
        "used_chunks": len(contexts),
        "mode": mode,
    }


_KEYWORD_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "shall",
    "have",
    "been",
    "were",
    "will",
    "each",
    "such",
    "which",
    "under",
    "upon",
    "after",
    "before",
    "between",
    "other",
    "into",
    "their",
    "there",
    "these",
    "those",
    "where",
    "when",
    "then",
    "than",
    "also",
    "not",
    "are",
    "was",
    "has",
    "had",
    "does",
    "did",
    "any",
    "all",
    "may",
    "must",
    "document",
    "documents",
    "legal",
    "law",
    "laws",
    "case",
    "cases",
    "court",
    "courts",
    "information",
    "agreement",
    "contract",
    "party",
    "parties",
    "section",
    "sections",
    "clause",
    "clauses",
    "term",
    "terms",
    "provision",
    "provisions",
}

_GENERIC_TOPIC_TERMS = {
    "document",
    "documents",
    "legal",
    "law",
    "laws",
    "case",
    "cases",
    "court",
    "courts",
    "information",
    "agreement",
    "contract",
    "party",
    "parties",
    "section",
    "sections",
    "clause",
    "clauses",
    "term",
    "terms",
    "provision",
    "provisions",
}

_TOPIC_CHUNK_LIMIT = 24
_TOPIC_CONTEXT_CHAR_LIMIT = 24000


def _clean_topics(topics: list[str], limit: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        normalized = " ".join(topic.strip().lower().split())
        if (
            not normalized
            or len(normalized) < 4
            or len(normalized) > 80
            or normalized in _GENERIC_TOPIC_TERMS
            or normalized in seen
        ):
            continue
        seen.add(normalized)
        cleaned.append(topic.strip())
        if len(cleaned) >= limit:
            break
    return cleaned


def _parse_topics_json(raw: str, limit: int) -> list[str] | None:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE).strip()
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None

    topics: list[str] = []
    for item in data:
        if isinstance(item, str):
            topics.append(item.strip())
        elif isinstance(item, dict):
            value = item.get("topic") or item.get("keyword") or item.get("phrase") or item.get("term")
            if isinstance(value, str):
                topics.append(value.strip())
    return _clean_topics(topics, limit) or None


def _fallback_topics(context: str, limit: int) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z'-]{3,}", context.lower())
    counts = Counter(token for token in tokens if token not in _KEYWORD_STOPWORDS)
    topics = [word for word, _ in counts.most_common(limit * 2)]
    return _clean_topics(topics, limit) or [word for word, _ in counts.most_common(limit)]


def extract_key_topics(db: Session, document_id: str, limit: int = 5) -> dict[str, Any]:
    cleaned_document_id = document_id.strip()
    if not cleaned_document_id:
        raise ValueError("document_id cannot be empty")

    limit = max(1, min(limit, 10))

    rows = db.execute(
        text(
            """
            SELECT c.chunk_text, d.source_file
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = :document_id
            ORDER BY c.chunk_index
            LIMIT :chunk_limit
            """
        ),
        {"document_id": cleaned_document_id, "chunk_limit": _TOPIC_CHUNK_LIMIT},
    ).mappings().all()

    if not rows:
        raise ValueError(f"No chunks found for document_id='{cleaned_document_id}'")

    source_file = rows[0]["source_file"]

    context_parts: list[str] = []
    total_chars = 0
    for row in rows:
        chunk_text = str(row["chunk_text"]).strip()
        if not chunk_text:
            continue
        remaining = _TOPIC_CONTEXT_CHAR_LIMIT - total_chars
        if remaining <= 0:
            break
        part = chunk_text[:remaining]
        context_parts.append(part)
        total_chars += len(part)
    context = "\n\n".join(context_parts)

    prompt = (
        "You are a legal assistant. Extract 5 to 10 of the most important legal "
        "or domain-specific concepts from the supplied document content.\n"
        "Rules:\n"
        "1) Use only the supplied content.\n"
        "2) Each topic must be directly supported by the document.\n"
        "3) Prefer meaningful multi-word concepts where appropriate, for example "
        "'procedural fairness' or 'data retention'.\n"
        "4) Do not return generic terms such as 'document', 'law', 'case', or 'information'.\n"
        "5) Do not invent concepts not supported by the document.\n"
        "6) Return structured JSON only: an array of short phrases.\n"
        f"7) Return between 5 and 10 items; limit to {limit}.\n\n"
        f"Document content:\n{context}\n\n"
        "Return only the JSON array."
    )

    topics: list[str]
    try:
        raw = generate_answer_with_ollama(
            base_url=settings.ollama_base_url,
            model=settings.generation_model,
            prompt=prompt,
            timeout_seconds=settings.generation_timeout_seconds,
        )
        topics = _parse_topics_json(raw, limit)
        if not topics:
            raise ValueError("LLM did not return valid topic JSON")
    except Exception:
        if settings.generation_strict:
            raise
        topics = _fallback_topics(context, limit)

    return {
        "document_id": cleaned_document_id,
        "source_file": source_file,
        "topics": topics,
    }
