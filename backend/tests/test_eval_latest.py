import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
import app.api.routes_eval as routes_eval
from app.evaluation.scoring import ExperimentMetrics, compute_overall_score, pass_fail_gates


def _write_run(dir_path: Path, run_id: str, *, smoke: bool = True) -> Path:
    path = dir_path / f"run_{run_id}.json"
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "cases_file": "mvp/golden_set_smoke.json" if smoke else "mvp/golden_set.json",
                "eval_source": "api",
                "summary": {"total_cases": 11, "abstention_accuracy": 0.7273},
                "challenger_metrics": {
                    "faithfulness": 0.91,
                    "answer_correctness": 0.89,
                    "retrieval_recall_at_5": 1.0,
                    "abstention_accuracy": 0.75,
                    "hallucination_rate": 0.0,
                    "invalid_citation_rate": 0.0,
                    "latency_p95_ms": 2224,
                },
                "score": {
                    "overall_score": 0.87,
                    "gates": {
                        "faithfulness": True,
                        "answer_correctness": True,
                        "retrieval_recall_at_5": True,
                        "hallucination_rate": True,
                        "invalid_citation_rate": True,
                        "latency_p95_ms": True,
                    },
                    "pass_fail": "pass",
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_latest_evaluation_available(tmp_path: Path) -> None:
    _write_run(tmp_path, "20260101_120000_000001")

    result = routes_eval._latest_evaluation(tmp_path)

    assert result["available"] is True
    assert result["run_id"] == "20260101_120000_000001"
    assert result["mode"] == "smoke"
    assert result["total_cases"] == 11
    assert result["metrics"]["recall_at_5"] == 1.0
    assert result["metrics"]["p95_latency_ms"] == 2224
    assert result["overall_score"] == 0.87
    assert result["status"] == "pass"
    # Gate keys are normalized to match metric keys.
    assert result["gates"]["recall_at_5"] is True
    assert result["gates"]["p95_latency_ms"] is True
    assert any(item["key"] == "recall_at_5" and item["threshold"] == ">= 0.65" for item in result["gate_definitions"])


def test_latest_evaluation_recall_passes_and_latency_fails(tmp_path: Path) -> None:
    path = tmp_path / "run_20260101_120000_000003.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "20260101_120000_000003",
                "cases_file": "mvp/golden_set_smoke.json",
                "summary": {"total_cases": 11},
                "challenger_metrics": {
                    "faithfulness": 0.92,
                    "answer_correctness": 0.89,
                    "retrieval_recall_at_5": 1.0,
                    "abstention_accuracy": 0.73,
                    "hallucination_rate": 0.0,
                    "invalid_citation_rate": 0.0,
                    "latency_p95_ms": 6700,
                },
                "score": {
                    "overall_score": 0.8587,
                    "gates": {
                        "faithfulness": True,
                        "answer_correctness": True,
                        "retrieval_recall_at_5": True,
                        "hallucination_rate": True,
                        "invalid_citation_rate": True,
                        "latency_p95_ms": False,
                    },
                    "pass_fail": "fail",
                },
            }
        ),
        encoding="utf-8",
    )

    result = routes_eval._latest_evaluation(tmp_path)

    assert result["gates"]["recall_at_5"] is True
    assert result["gates"]["p95_latency_ms"] is False
    assert result["status"] == "fail"
    assert "p95 latency" in result["failed_gates"]
    assert "Recall@5" not in result["failed_gates"]


def test_scoring_recall_gate_passes_and_latency_gate_fails() -> None:
    metrics = ExperimentMetrics(
        faithfulness=0.92,
        answer_correctness=0.89,
        retrieval_recall_at_5=1.0,
        abstention_accuracy=0.73,
        hallucination_rate=0.0,
        invalid_citation_rate=0.0,
        latency_p95_ms=6700,
    )

    gates = pass_fail_gates(metrics)
    assert gates["retrieval_recall_at_5"] is True
    assert gates["latency_p95_ms"] is False

    result = compute_overall_score(metrics)
    assert result["gates"]["retrieval_recall_at_5"] is True
    assert result["pass_fail"] == "fail"


def test_latest_evaluation_no_artifact(tmp_path: Path) -> None:
    result = routes_eval._latest_evaluation(tmp_path)
    assert result == {"available": False}


def test_latest_evaluation_skips_corrupt_artifact(tmp_path: Path) -> None:
    (tmp_path / "run_bad.json").write_text("{not json", encoding="utf-8")
    _write_run(tmp_path, "20260101_120000_000002")

    result = routes_eval._latest_evaluation(tmp_path)

    assert result["available"] is True
    assert result["run_id"] == "20260101_120000_000002"


def test_latest_evaluation_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_eval,
        "_latest_evaluation",
        lambda experiments_dir: {"available": True, "run_id": "x", "status": "pass"},
    )
    client = TestClient(app)

    response = client.get("/eval/latest")

    assert response.status_code == 200
    assert response.json()["run_id"] == "x"


def test_latest_evaluation_route_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(routes_eval, "_latest_evaluation", lambda experiments_dir: {"available": False})
    client = TestClient(app)

    response = client.get("/eval/latest")

    assert response.status_code == 200
    assert response.json() == {"available": False}
