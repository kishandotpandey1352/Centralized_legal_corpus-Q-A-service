from pathlib import Path

from scripts.eval_runner import _load_cases, _run_case_offline


def test_offline_summary_cases_meet_structure_and_citation_requirements() -> None:
    cases_path = Path(__file__).parents[2] / "mvp" / "golden_set_template.json"
    cases = _load_cases(cases_path)

    summary_results = [
        _run_case_offline(case)
        for case in cases
        if case.kind == "summary" and not case.should_abstain
    ]

    assert summary_results
    assert all(result["ok"] for result in summary_results)
    assert all(result["checks"]["summary_structure_ok"] for result in summary_results)
    assert all(result["checks"]["citation_requirement_met"] for result in summary_results)


def test_offline_answer_cases_emit_required_inline_citations() -> None:
    cases_path = Path(__file__).parents[2] / "mvp" / "golden_set_smoke.json"
    cases = _load_cases(cases_path)

    results = [
        _run_case_offline(case)
        for case in cases
        if case.kind == "answer" and not case.should_abstain and case.min_citations > 0
    ]

    assert results
    assert all(result["checks"]["inline_citation_requirement_met"] for result in results)
    assert all(result["citation_validation"]["inline_ids"] for result in results)
