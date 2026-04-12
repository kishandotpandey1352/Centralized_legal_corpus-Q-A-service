from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_eval_score_endpoint() -> None:
    payload = {
        "faithfulness": 0.79,
        "answer_correctness": 0.75,
        "retrieval_recall_at_5": 0.72,
        "abstention_accuracy": 0.86,
        "hallucination_rate": 0.09,
        "invalid_citation_rate": 0.07,
        "latency_p95_ms": 3200,
    }

    response = client.post("/eval/score", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["overall_score"] == 0.7385
    assert body["pass_fail"] == "pass"


def test_eval_compare_endpoint() -> None:
    payload = {
        "baseline": {
            "faithfulness": 0.78,
            "answer_correctness": 0.73,
            "retrieval_recall_at_5": 0.70,
            "abstention_accuracy": 0.84,
            "hallucination_rate": 0.10,
            "invalid_citation_rate": 0.08,
            "latency_p95_ms": 3400,
        },
        "challenger": {
            "faithfulness": 0.81,
            "answer_correctness": 0.76,
            "retrieval_recall_at_5": 0.73,
            "abstention_accuracy": 0.86,
            "hallucination_rate": 0.08,
            "invalid_citation_rate": 0.06,
            "latency_p95_ms": 3200,
        },
    }

    response = client.post("/eval/compare", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["winner"] == "challenger"
    assert body["has_gate_regression"] is False
