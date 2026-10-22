from app.retrieval.service import answer_question, _rerank_results, _select_final_context
import app.retrieval.service as retrieval_service


def _chunk(chunk_id: str, text: str, vector_score: float, hybrid_score: float) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "source_file": "northbridge_data_retention_protocol_2026.docx",
        "document_type": "docx",
        "chunk_index": int(chunk_id[1:]),
        "chunk_text": text,
        "page_range": "1",
        "section_title": None,
        "score": vector_score,
        "vector_score": vector_score,
        "lexical_score": 0.0,
        "hybrid_score": hybrid_score,
    }


def test_select_final_context_returns_top_k_sorted_desc() -> None:
    candidates = [
        _chunk("c1", "a", 0.9, 0.5),
        _chunk("c2", "b", 0.8, 0.7),
        _chunk("c3", "c", 0.7, 0.9),
        _chunk("c4", "d", 0.6, 0.3),
        _chunk("c5", "e", 0.5, 0.1),
    ]
    selected = _select_final_context(candidates, top_k=3, min_relevance_score=None)

    assert len(selected) == 3
    assert [item["chunk_id"] for item in selected] == ["c3", "c2", "c1"]


def test_select_final_context_excludes_weak_when_threshold_configured() -> None:
    candidates = [
        _chunk("c1", "a", 0.9, 0.5),
        _chunk("c2", "b", 0.8, 0.7),
        _chunk("c3", "c", 0.7, 0.9),
        _chunk("c4", "d", 0.6, 0.3),
        _chunk("c5", "e", 0.5, 0.1),
    ]
    selected = _select_final_context(candidates, top_k=3, min_relevance_score=0.6)

    assert all(float(item["hybrid_score"]) >= 0.6 for item in selected)
    assert len(selected) == 2


def test_select_final_context_permissive_without_threshold() -> None:
    candidates = [_chunk("c1", "a", 0.1, 0.05), _chunk("c2", "b", 0.2, 0.1)]
    selected = _select_final_context(candidates, top_k=3, min_relevance_score=None)

    assert len(selected) == 2


def test_rerank_keeps_exact_legal_term_chunk_despite_lower_vector_score() -> None:
    candidates = [
        {
            "chunk_id": "c1",
            "chunk_text": "General record retention policies apply across the company.",
            "score": 0.9,
        },
        {
            "chunk_id": "c2",
            "chunk_text": "Disposal controls and legal holds prevent deletion of records under retention suspension.",
            "score": 0.7,
        },
    ]

    reranked = _rerank_results(
        query="What are the impacts of disposal controls on legal holds?",
        candidates=candidates,
        top_k=2,
        lexical_weight=0.5,
    )

    assert reranked[0]["chunk_id"] == "c2"


def test_answer_receives_only_final_selected_chunks(monkeypatch) -> None:
    candidates = [
        _chunk("c1", "filler content one", 0.9, 0.9),
        _chunk("c2", "filler content two", 0.8, 0.8),
        _chunk("c3", "filler content three", 0.7, 0.7),
        _chunk("c4", "filler content four", 0.6, 0.6),
        _chunk("c5", "filler content five", 0.5, 0.5),
    ]
    captured: dict[str, object] = {}

    monkeypatch.setattr(retrieval_service, "_search_candidates", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(retrieval_service, "_attach_adjacent_context", lambda db, results: results)

    def fake_prompt(question, contexts):
        captured["contexts"] = contexts
        return "Answer [C1] [C2] [C3]"

    monkeypatch.setattr(retrieval_service, "build_grounded_prompt", fake_prompt)
    monkeypatch.setattr(retrieval_service, "generate_answer_with_ollama", lambda **kwargs: "Answer [C1] [C2] [C3]")
    monkeypatch.setattr(retrieval_service.settings, "rag_context_top_k", 3)
    monkeypatch.setattr(retrieval_service.settings, "qa_min_retrieval_score", 0.0)
    monkeypatch.setattr(retrieval_service.settings, "qa_min_lexical_overlap", 0.0)
    monkeypatch.setattr(retrieval_service.settings, "qa_direct_answer_min_overlap", 1.0)
    monkeypatch.setattr(retrieval_service.settings, "qa_force_keyword", "")

    result = answer_question(object(), "What is the filing deadline?", document_id="doc-1")

    assert len(captured["contexts"]) == 3
    assert result["used_chunks"] == 3
    assert result["candidates_retrieved"] == 5
    assert result["context_chunks"] == 3
    assert len(result["citations"]) == 3
    assert result["evidence"][0]["chunk_id"] == "c1"


def test_zero_acceptable_chunks_triggers_abstention(monkeypatch) -> None:
    candidates = [
        _chunk("c1", "filler content one", 0.4, 0.4),
        _chunk("c2", "filler content two", 0.3, 0.3),
    ]

    monkeypatch.setattr(retrieval_service, "_search_candidates", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(retrieval_service.settings, "rag_min_relevance_score", 0.8)
    monkeypatch.setattr(retrieval_service.settings, "rag_context_top_k", 3)

    result = answer_question(object(), "What is the filing deadline?", document_id="doc-1")

    assert result["mode"] == "no-context"
    assert result["used_chunks"] == 0
    assert result["citations"] == []
