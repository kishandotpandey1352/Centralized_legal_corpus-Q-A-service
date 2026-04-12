from pydantic import BaseModel, Field
from fastapi import APIRouter

from app.evaluation.scoring import ExperimentMetrics, compare_experiments, compute_overall_score


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


@router.post("/score")
def score_experiment(request: EvaluationMetricsRequest) -> dict[str, object]:
    metrics = ExperimentMetrics(**request.model_dump())
    return compute_overall_score(metrics)


@router.post("/compare")
def compare(request: CompareExperimentsRequest) -> dict[str, object]:
    baseline = ExperimentMetrics(**request.baseline.model_dump())
    challenger = ExperimentMetrics(**request.challenger.model_dump())
    return compare_experiments(baseline=baseline, challenger=challenger)
