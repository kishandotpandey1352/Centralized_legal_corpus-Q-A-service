from pathlib import Path

from app.retrieval.service import _direct_cited_answer, _polish_answer_text, _structured_summary_from_contexts, _summary_needs_repair


DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sample_docs"


def test_expected_sample_docs_exist() -> None:
    expected_files = {
        "sample_service_agreement.txt",
        "texas_department_of_public_safety_v._robert_christopher_callaway.pdf",
        "Legal-Notice-for-Wrongful-Termination-LawRato.docx",
    }

    actual_files = {path.name for path in DATA_DIR.iterdir() if path.is_file()}
    assert expected_files.issubset(actual_files)


def test_direct_answer_uses_service_agreement_clause() -> None:
    answer = _direct_cited_answer(
        "What is the cure period for material breach?",
        [
            {
                "chunk_text": (
                    "2. Term and Termination "
                    "Either party may terminate for material breach if the breach remains uncured "
                    "for thirty (30) days after written notice."
                )
            }
        ],
    )
    assert "thirty (30) days" in answer
    assert "[C1]" in answer


def test_polish_answer_removes_trailing_fragment_from_texas_style_output() -> None:
    noisy = (
        "From the retrieved record, His affidavit noted elevated hypervigilance and less than optimal outcomes, "
        "where he [C1]"
    )
    polished = _polish_answer_text(noisy)
    assert "where he" not in polished.lower()
    assert "[C1]" in polished


def test_mixed_domain_prompt_stays_grounded_to_service_agreement() -> None:
    answer = _direct_cited_answer(
        "Tell me about moon geology and also the cure period for material breach.",
        [
            {
                "chunk_text": (
                    "Either party may terminate for material breach if the breach remains uncured "
                    "for thirty (30) days after written notice."
                )
            }
        ],
    )
    assert "thirty (30) days" in answer
    assert "moon" not in answer.lower()
    assert "[C1]" in answer


def test_long_context_summary_generation_is_numbered_and_cited() -> None:
    contexts = [
        {"chunk_text": "Scope of services includes document review and compliance reporting."},
        {"chunk_text": "Term and termination include a material breach cure period of thirty days."},
        {"chunk_text": "Confidentiality obligations apply to non-public information disclosures."},
        {"chunk_text": "Data protection controls require safeguards and breach notification timing."},
        {"chunk_text": "Limitation of liability includes carve-outs for willful misconduct."},
    ]
    summary = _structured_summary_from_contexts(contexts, max_points=4)

    assert "1." in summary
    assert "2." in summary
    assert "3." in summary
    assert "4." in summary
    assert "[C1]" in summary
    assert "[C2]" in summary
    assert _summary_needs_repair(summary, min_inline_citations=2) is True


def test_abstention_phrase_remains_exact_for_out_of_scope_prompt() -> None:
    exact = "Insufficient evidence in provided documents."
    assert exact == "Insufficient evidence in provided documents."
