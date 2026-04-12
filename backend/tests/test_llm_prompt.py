from app.llm.service import build_grounded_prompt


def test_build_grounded_prompt_includes_question_and_citations() -> None:
    prompt = build_grounded_prompt(
        question="What is the termination cure period?",
        contexts=[
            {
                "source_file": "sample_service_agreement.txt",
                "chunk_index": 0,
                "page_range": None,
                "section_title": "Term and Termination",
                "chunk_text": "Either party may terminate for material breach if the breach remains uncured for thirty (30) days after written notice.",
            }
        ],
    )

    assert "What is the termination cure period?" in prompt
    assert "[C1] source_file=sample_service_agreement.txt" in prompt
    assert "[C1] text=Either party may terminate" in prompt
