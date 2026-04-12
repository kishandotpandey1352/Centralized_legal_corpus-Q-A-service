from pathlib import Path

from app.retrieval.service import _direct_cited_answer, _polish_answer_text


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
