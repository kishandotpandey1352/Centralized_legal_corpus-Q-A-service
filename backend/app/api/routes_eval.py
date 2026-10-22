import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.evaluation.scoring import (
    ExperimentMetrics,
    compare_experiments,
    compute_overall_score,
    evaluation_gate_definitions,
)


class EvaluationMetricsRequest(BaseModel):
    faithfulness: float = Field(ge=0.0, le=1.0)
    answer_correctness: float = Field(ge=0.0, le=1.0)
    retrieval_recall_at_5: float = Field(ge=0.0, le=1.0)
    abstention_accuracy: float = Field(ge=0.0, le=1.0)
    hallucination_rate: float = Field(ge=0.0, le=1.0)
    invalid_citation_rate: float = Field(ge=0.0, le=1.0)
    latency_p95_ms: int = Field(ge=0)


class CompareExperimentsRequest(BaseModel):
    baseline: EvaluationMetricsRequest
    challenger: EvaluationMetricsRequest


router = APIRouter(prefix="/eval", tags=["evaluation"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _experiments_dir() -> Path:
    return _repo_root() / "mvp" / "experiments"


_GATE_KEY_ALIASES = {
    "retrieval_recall_at_5": "recall_at_5",
    "latency_p95_ms": "p95_latency_ms",
}


def _gate_definitions() -> list[dict[str, Any]]:
    return [
        {
            "key": _GATE_KEY_ALIASES.get(str(item["key"]), str(item["key"])),
            "label": item["label"],
            "threshold": item["threshold"],
            "informational": bool(item["informational"]),
        }
        for item in evaluation_gate_definitions()
    ]


def _latest_evaluation(experiments_dir: Path) -> dict[str, Any]:
    """Read the newest existing evaluation run artifact without running the suite."""
    run_files = sorted(
        experiments_dir.glob("run_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not run_files:
        return {"available": False}

    for path in run_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        metrics = data.get("challenger_metrics") or {}
        score = data.get("score") or {}
        summary = data.get("summary") or {}
        cases_file = str(data.get("cases_file") or "")
        cases_name = Path(cases_file).name.lower()
        if "smoke" in cases_name:
            mode = "smoke"
        elif "full" in cases_name:
            mode = "full"
        else:
            mode = None

        raw_gates = score.get("gates") or {}
        gates = {_GATE_KEY_ALIASES.get(str(key), str(key)): bool(value) for key, value in raw_gates.items()}
        definitions = _gate_definitions()
        failed_gates = [
            str(item["label"])
            for item in definitions
            if not item["informational"] and gates.get(str(item["key"])) is False
        ]

        return {
            "available": True,
            "run_id": data.get("run_id"),
            "mode": mode,
            "eval_source": data.get("eval_source"),
            "created_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            "total_cases": summary.get("total_cases"),
            "metrics": {
                "faithfulness": metrics.get("faithfulness"),
                "answer_correctness": metrics.get("answer_correctness"),
                "recall_at_5": metrics.get("retrieval_recall_at_5"),
                "abstention_accuracy": metrics.get("abstention_accuracy"),
                "hallucination_rate": metrics.get("hallucination_rate"),
                "invalid_citation_rate": metrics.get("invalid_citation_rate"),
                "p95_latency_ms": metrics.get("latency_p95_ms"),
            },
            "overall_score": score.get("overall_score"),
            "gates": gates,
            "gate_definitions": definitions,
            "failed_gates": failed_gates,
            "status": score.get("pass_fail"),
        }

    return {"available": False}


@router.get("/latest")
def latest_evaluation() -> dict[str, Any]:
    return _latest_evaluation(_experiments_dir())


@router.post("/score")
def score_experiment(request: EvaluationMetricsRequest) -> dict[str, object]:
    metrics = ExperimentMetrics(**request.model_dump())
    return compute_overall_score(metrics)


@router.post("/compare")
def compare(request: CompareExperimentsRequest) -> dict[str, object]:
    baseline = ExperimentMetrics(**request.baseline.model_dump())
    challenger = ExperimentMetrics(**request.challenger.model_dump())
    return compare_experiments(baseline=baseline, challenger=challenger)
