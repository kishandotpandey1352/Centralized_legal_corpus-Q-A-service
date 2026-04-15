from scripts.eval_runner import _build_failure_taxonomy, _compute_run_analytics
from scripts.eval_trends import _build_trend_report


def test_failure_taxonomy_detects_request_error() -> None:
    case = {
        "ok": False,
        "mode": "request-error",
        "error": "request-error: timeout",
        "checks": {
            "mode_match": None,
        },
    }

    taxonomy = _build_failure_taxonomy(case)
    assert taxonomy["primary_issue"] == "request_error"
    assert "request_error" in taxonomy["issues"]


def test_failure_taxonomy_detects_summary_drift() -> None:
    case = {
        "ok": True,
        "mode": "llm-summary",
        "checks": {
            "summary_verbosity_ok": False,
            "summary_structure_ok": False,
        },
    }

    taxonomy = _build_failure_taxonomy(case)
    assert "summary_verbosity_drift" in taxonomy["issues"]
    assert "summary_structure_invalid" in taxonomy["issues"]


def test_run_analytics_aggregates_issues_and_kind_breakdown() -> None:
    case_results = [
        {
            "kind": "answer",
            "mode": "evidence-direct",
            "latency_ms": 100,
            "ok": True,
            "checks": {"mode_match": True},
            "failure_taxonomy": {"primary_issue": "none", "issues": ["none"]},
        },
        {
            "kind": "summary",
            "mode": "llm-summary",
            "latency_ms": 200,
            "ok": True,
            "checks": {"summary_verbosity_ok": False},
            "failure_taxonomy": {
                "primary_issue": "summary_verbosity_drift",
                "issues": ["summary_verbosity_drift"],
            },
        },
        {
            "kind": "answer",
            "mode": "request-error",
            "latency_ms": 300,
            "ok": False,
            "checks": {"mode_match": None},
            "failure_taxonomy": {"primary_issue": "request_error", "issues": ["request_error"]},
        },
    ]

    analytics = _compute_run_analytics(case_results)

    assert analytics["total_cases"] == 3
    assert analytics["successful_cases"] == 2
    assert analytics["failed_cases"] == 1
    assert analytics["kind_breakdown"]["answer"]["count"] == 2
    assert analytics["failure_taxonomy"]["issue_counts"]["request_error"] == 1
    assert analytics["failure_taxonomy"]["issue_counts"]["summary_verbosity_drift"] == 1


def test_build_trend_report_computes_deltas_and_pass_rate() -> None:
    points = [
        {
            "run_id": "r1",
            "pass_fail": "pass",
            "overall_score": 0.80,
            "latency_p95_ms": 1000,
            "invalid_citation_rate": 0.05,
            "abstention_accuracy": 0.90,
            "failed_cases": 0,
            "top_non_pass_issues": [{"issue": "request_error", "count": 1}],
        },
        {
            "run_id": "r2",
            "pass_fail": "fail",
            "overall_score": 0.75,
            "latency_p95_ms": 1200,
            "invalid_citation_rate": 0.07,
            "abstention_accuracy": 0.85,
            "failed_cases": 1,
            "top_non_pass_issues": [{"issue": "summary_verbosity_drift", "count": 2}],
        },
    ]

    report = _build_trend_report(points)

    assert report["run_count"] == 2
    assert report["pass_rate"] == 0.5
    assert report["deltas_vs_previous"]["overall_score"] == -0.05
    assert report["deltas_vs_previous"]["latency_p95_ms"] == 200.0
    assert report["latest_run_id"] == "r2"
