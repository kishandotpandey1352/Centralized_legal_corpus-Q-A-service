from app.evaluation.scoring import ExperimentMetrics, compare_experiments, compute_overall_score


def test_compute_overall_score_matches_rubric() -> None:
    metrics = ExperimentMetrics(
        faithfulness=0.79,
        answer_correctness=0.75,
        retrieval_recall_at_5=0.72,
        abstention_accuracy=0.86,
        hallucination_rate=0.09,
        invalid_citation_rate=0.07,
        latency_p95_ms=3200,
    )

    result = compute_overall_score(metrics)

    assert result["overall_score"] == 0.7385
    assert result["latency_penalty"] == 0.02
    assert result["pass_fail"] == "pass"


def test_compare_experiments_selects_challenger_when_improved_without_regression() -> None:
    baseline = ExperimentMetrics(
        faithfulness=0.78,
        answer_correctness=0.73,
        retrieval_recall_at_5=0.70,
        abstention_accuracy=0.84,
        hallucination_rate=0.10,
        invalid_citation_rate=0.08,
        latency_p95_ms=3400,
    )
    challenger = ExperimentMetrics(
        faithfulness=0.81,
        answer_correctness=0.76,
        retrieval_recall_at_5=0.73,
        abstention_accuracy=0.86,
        hallucination_rate=0.08,
        invalid_citation_rate=0.06,
        latency_p95_ms=3200,
    )

    result = compare_experiments(baseline=baseline, challenger=challenger)

    assert result["winner"] == "challenger"
    assert result["has_gate_regression"] is False
    assert float(result["delta_overall_score"]) >= 0.02
