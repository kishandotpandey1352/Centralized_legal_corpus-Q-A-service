from app.retrieval.service import (
    _clean_sentence,
    _contains_force_keyword,
    _direct_cited_answer,
    _enforce_citation_integrity,
    _fallback_answer,
    _force_concise_cited_answer,
    _lexical_confidence,
    _polish_answer_text,
    _polish_summary_text,
    _question_terms,
    _structured_summary_from_contexts,
    _summary_needs_repair,
    _should_force_cited_answer,
    _top_score,
)


def test_fallback_answer_with_no_results() -> None:
    answer = _fallback_answer("Any question", [])
    assert answer == "Insufficient evidence in provided documents."


def test_fallback_answer_uses_top_chunk() -> None:
    answer = _fallback_answer(
        "What is the cure period?",
        [
            {
                "chunk_text": "The cure period is thirty (30) days after written notice.",
            }
        ],
    )
    assert "[C1]" in answer
    assert "thirty (30) days" in answer


def test_top_score_returns_zero_without_results() -> None:
    assert _top_score([]) == 0.0


def test_contains_force_keyword_detects_material_breach() -> None:
    results = [{"chunk_text": "Either party may terminate for material breach after notice."}]
    assert _contains_force_keyword(results, "material breach") is True


def test_force_concise_cited_answer_adds_citation() -> None:
    answer = _force_concise_cited_answer(
        [{"chunk_text": "Either party may terminate for material breach if uncured for thirty days."}]
    )
    assert "material breach" in answer.lower()
    assert "[C1]" in answer


def test_should_force_cited_answer_requires_keyword_and_score_threshold() -> None:
    assert _should_force_cited_answer(top_score=0.50, has_forced_keyword=True, min_score=0.45) is True
    assert _should_force_cited_answer(top_score=0.44, has_forced_keyword=True, min_score=0.45) is False
    assert _should_force_cited_answer(top_score=0.50, has_forced_keyword=False, min_score=0.45) is False


def test_question_terms_filters_stopwords() -> None:
    terms = _question_terms("What is the cure period for material breach?")
    assert "what" not in terms
    assert "material" in terms
    assert "breach" in terms


def test_lexical_confidence_higher_for_relevant_chunk() -> None:
    results = [
        {"chunk_text": "Random procedural registry text unrelated to breach."},
        {"chunk_text": "Either party may terminate for material breach after thirty days."},
    ]
    confidence = _lexical_confidence("What is the cure period for material breach?", results)
    assert confidence > 0.3


def test_direct_cited_answer_adds_citation() -> None:
    answer = _direct_cited_answer(
        "What is the cure period for material breach?",
        [{"chunk_text": "Either party may terminate for material breach if uncured for thirty (30) days."}],
    )
    assert "[C1]" in answer


def test_clean_sentence_trims_trailing_fragment() -> None:
    cleaned = _clean_sentence("This is a complete sentence with trailing frag")
    assert cleaned == "This is a complete sentence with trailing frag."


def test_direct_cited_answer_person_question_prefix() -> None:
    answer = _direct_cited_answer(
        "Tell me about Colonel Steve McCraw",
        [{"chunk_text": "Colonel Steve McCraw served as Director of DPS in the cited filing."}],
    )
    assert answer.startswith("From the retrieved record,")
    assert "[C1]" in answer


def test_clean_sentence_removes_dangling_where_clause() -> None:
    cleaned = _clean_sentence("Callaway acted emotionally during the situation, where he")
    assert "where he" not in cleaned.lower()
    assert cleaned.endswith(".")


def test_polish_answer_text_preserves_citations() -> None:
    polished = _polish_answer_text("He acted emotionally during the situation, where he [C1]")
    assert "where he" not in polished.lower()
    assert "[C1]" in polished


def test_polish_summary_text_trims_dangling_tail_and_keeps_citations() -> None:
    noisy = (
        "- Scope of Services: Provider will deliver document review and compliance reporting services as defined in SOW-001 . "
        "- Term and Termination: The Agreement is for twelve months with thirty days cure notice for material breach . "
        "- Con [C1] [C2]"
    )

    polished = _polish_summary_text(noisy)
    assert "- Con" not in polished
    assert polished.endswith("[C1] [C2]")
    assert ". [C1]" in polished or ". [C2]" in polished


def test_polish_summary_text_removes_bullet_prefixes() -> None:
    noisy = (
        "- Scope of Services includes document review and compliance reporting. "
        "- The agreement term is twelve months from January 1, 2026. "
        "- The agreement is governed by New York law. [C1] [C2]"
    )

    polished = _polish_summary_text(noisy)
    assert "- " not in polished
    assert polished.startswith("Scope of Services")
    assert polished.endswith("[C1] [C2]")


def test_enforce_citation_integrity_appends_required_inline_markers() -> None:
    citations = [
        {"id": "C1"},
        {"id": "C2"},
        {"id": "C3"},
    ]
    enriched = _enforce_citation_integrity("Grounded answer text.", citations, min_required=2)
    assert enriched.endswith("[C1] [C2]")


def test_enforce_citation_integrity_filters_unknown_markers() -> None:
    citations = [{"id": "C1"}, {"id": "C2"}]
    enriched = _enforce_citation_integrity("Grounded answer [C9]", citations, min_required=1)
    assert "[C9]" not in enriched
    assert enriched.endswith("[C1]")


def test_enforce_citation_integrity_adds_marker_to_abstention_text() -> None:
    citations = [{"id": "C1"}]
    enriched = _enforce_citation_integrity("Insufficient evidence in provided documents.", citations, min_required=1)
    assert enriched == "Insufficient evidence in provided documents. [C1]"


def test_enforce_citation_integrity_preserves_lines_for_summary() -> None:
    citations = [{"id": "C1"}, {"id": "C2"}]
    text = "1. Scope of services text [C1]\n2. Term and termination text [C2]"
    enriched = _enforce_citation_integrity(text, citations, min_required=2, preserve_line_breaks=True)
    assert "\n" in enriched
    assert enriched.endswith("[C1] [C2]")


def test_structured_summary_from_contexts_returns_numbered_lines() -> None:
    summary = _structured_summary_from_contexts(
        [
            {"chunk_text": "The agreement term is twelve months from January 1, 2026."},
            {"chunk_text": "Material breach requires a thirty day cure period before termination."},
        ],
        max_points=3,
    )
    assert "1." in summary
    assert "2." in summary
    assert "[C1]" in summary
    assert "[C2]" in summary


def test_summary_needs_repair_for_verbose_or_uncertain_text() -> None:
    verbose = " ".join(["This is a long summary sentence with uncertain language maybe."] * 20)
    assert _summary_needs_repair(verbose, min_inline_citations=2) is True


def test_summary_needs_repair_false_for_compact_cited_summary() -> None:
    text = "1. Term is twelve months. [C1] 2. Cure period is thirty days. [C2]"
    assert _summary_needs_repair(text, min_inline_citations=2) is False
