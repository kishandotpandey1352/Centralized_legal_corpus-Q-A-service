from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentMetrics:
    faithfulness: float
    answer_correctness: float
    retrieval_recall_at_5: float
    abstention_accuracy: float
    hallucination_rate: float
    invalid_citation_rate: float
    latency_p95_ms: int


def latency_penalty(latency_p95_ms: int) -> float:
    if latency_p95_ms <= 3000:
        return 0.0
    if latency_p95_ms <= 5000:
        return 0.02
    return 0.05


GATE_DEFINITIONS: tuple[tuple[str, str, str, float, str | None], ...] = (
    ("faithfulness", "Faithfulness", ">=", 0.75, None),
    ("answer_correctness", "Answer correctness", ">=", 0.70, None),
    ("retrieval_recall_at_5", "Recall@5", ">=", 0.65, None),
    ("hallucination_rate", "Hallucination rate", "<=", 0.12, None),
    ("invalid_citation_rate", "Invalid citation rate", "<=", 0.10, None),
    ("latency_p95_ms", "p95 latency", "<=", 5000, "ms"),
)


def pass_fail_gates(metrics: ExperimentMetrics) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for key, _label, operator, threshold, _unit in GATE_DEFINITIONS:
        value = getattr(metrics, key)
        gates[key] = value >= threshold if operator == ">=" else value <= threshold
    return gates


def evaluation_gate_definitions() -> list[dict[str, object]]:
    definitions: list[dict[str, object]] = []
    for key, label, operator, threshold, unit in GATE_DEFINITIONS:
        unit_suffix = f" {unit}" if unit else ""
        formatted_threshold = f"{threshold:.2f}" if isinstance(threshold, float) else str(threshold)
        definitions.append(
            {
                "key": key,
                "label": label,
                "threshold": f"{operator} {formatted_threshold}{unit_suffix}",
                "informational": False,
            }
        )
    definitions.append(
        {
            "key": "abstention_accuracy",
            "label": "Abstention accuracy",
            "threshold": "Informational",
            "informational": True,
        }
    )
    return definitions


def compute_overall_score(metrics: ExperimentMetrics) -> dict[str, object]:
    penalty = latency_penalty(metrics.latency_p95_ms)
    overall_score = (
        0.40 * metrics.faithfulness
        + 0.30 * metrics.answer_correctness
        + 0.20 * metrics.retrieval_recall_at_5
        + 0.10 * metrics.abstention_accuracy
        - 0.10 * metrics.hallucination_rate
        - 0.05 * metrics.invalid_citation_rate
        - penalty
    )

    gates = pass_fail_gates(metrics)
    is_pass = all(gates.values())

    return {
        "overall_score": round(overall_score, 4),
        "latency_penalty": penalty,
        "gates": gates,
        "pass_fail": "pass" if is_pass else "fail",
    }


def compare_experiments(baseline: ExperimentMetrics, challenger: ExperimentMetrics) -> dict[str, object]:
    baseline_eval = compute_overall_score(baseline)
    challenger_eval = compute_overall_score(challenger)

    baseline_score = float(baseline_eval["overall_score"])
    challenger_score = float(challenger_eval["overall_score"])
    delta = round(challenger_score - baseline_score, 4)

    baseline_gates: dict[str, bool] = baseline_eval["gates"]  # type: ignore[assignment]
    challenger_gates: dict[str, bool] = challenger_eval["gates"]  # type: ignore[assignment]
    has_regression = any(baseline_gates[key] and not challenger_gates.get(key, False) for key in baseline_gates)

    if delta >= 0.02 and not has_regression:
        winner = "challenger"
        reason = "Challenger improved overall_score by at least 0.02 with no gate regression."
    elif abs(delta) < 0.02:
        if challenger.latency_p95_ms < baseline.latency_p95_ms and challenger.hallucination_rate <= baseline.hallucination_rate:
            winner = "challenger"
            reason = "Scores are close; challenger wins on latency and hallucination tie-breaker."
        elif baseline.latency_p95_ms < challenger.latency_p95_ms and baseline.hallucination_rate <= challenger.hallucination_rate:
            winner = "baseline"
            reason = "Scores are close; baseline wins on latency and hallucination tie-breaker."
        else:
            winner = "tie"
            reason = "Scores are close and tie-breakers are mixed."
    else:
        winner = "baseline"
        reason = "Challenger did not meet the minimum improvement and gate criteria."

    return {
        "winner": winner,
        "delta_overall_score": delta,
        "baseline": baseline_eval,
        "challenger": challenger_eval,
        "has_gate_regression": has_regression,
        "decision_reason": reason,
    }
