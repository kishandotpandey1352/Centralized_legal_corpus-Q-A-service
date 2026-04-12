from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import quantiles
from time import perf_counter
from typing import Any

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.evaluation.scoring import ExperimentMetrics, compare_experiments, compute_overall_score


INSUFFICIENT_EVIDENCE_TEXT = "Insufficient evidence in provided documents."


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    kind: str
    category: str | None
    question: str | None
    source_file: str | None
    top_k: int
    max_chunks: int
    should_abstain: bool | None
    expected_mode: str | None
    min_citations: int
    require_valid_citations: bool
    expected_contains_any: tuple[str, ...]
    expected_not_contains_any: tuple[str, ...]
    human_faithfulness: float | None
    human_correctness: float | None
    notes: str | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluation runner skeleton")
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:8000",
        help="FastAPI base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--cases",
        required=True,
        help="Path to golden set JSON file",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Optional baseline metrics JSON path for /eval/compare",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults to <repo>/mvp/experiments",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90.0,
        help="Per-request timeout in seconds",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run deterministic offline simulation (no API calls) while preserving report flow.",
    )
    return parser.parse_args()


def _load_cases(file_path: Path) -> list[GoldenCase]:
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    raw_cases = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Golden set must contain a non-empty cases list")

    cases: list[GoldenCase] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Case at index {index} is not an object")

        case_id = str(item.get("id") or f"case-{index}")
        kind = str(item.get("kind", "")).strip().lower()
        category = item.get("category")
        question = item.get("question")
        source_file = item.get("source_file")
        top_k = int(item.get("top_k", 5))
        max_chunks = int(item.get("max_chunks", 6))
        should_abstain = item.get("should_abstain")
        expected_mode = item.get("expected_mode")
        min_citations = int(item.get("min_citations", 1))
        require_valid_citations = bool(item.get("require_valid_citations", True))
        expected_contains_any = item.get("expected_contains_any", [])
        expected_not_contains_any = item.get("expected_not_contains_any", [])
        human_scores = item.get("human_scores", {}) if isinstance(item.get("human_scores", {}), dict) else {}
        human_faithfulness = human_scores.get("faithfulness")
        human_correctness = human_scores.get("answer_correctness")
        notes = item.get("notes")

        if kind not in {"answer", "summary"}:
            raise ValueError(f"Case {case_id}: kind must be 'answer' or 'summary'")
        if kind == "answer" and (not isinstance(question, str) or not question.strip()):
            raise ValueError(f"Case {case_id}: answer case requires non-empty question")
        if kind == "summary" and (not isinstance(source_file, str) or not source_file.strip()):
            raise ValueError(f"Case {case_id}: summary case requires non-empty source_file")
        if should_abstain is not None and not isinstance(should_abstain, bool):
            raise ValueError(f"Case {case_id}: should_abstain must be true/false/null")
        if expected_mode is not None and not isinstance(expected_mode, str):
            raise ValueError(f"Case {case_id}: expected_mode must be a string when set")
        if min_citations < 0:
            raise ValueError(f"Case {case_id}: min_citations must be >= 0")
        if not isinstance(expected_contains_any, list) or not all(isinstance(x, str) for x in expected_contains_any):
            raise ValueError(f"Case {case_id}: expected_contains_any must be a string list")
        if not isinstance(expected_not_contains_any, list) or not all(isinstance(x, str) for x in expected_not_contains_any):
            raise ValueError(f"Case {case_id}: expected_not_contains_any must be a string list")
        if human_faithfulness is not None and not isinstance(human_faithfulness, (float, int)):
            raise ValueError(f"Case {case_id}: human_scores.faithfulness must be numeric when set")
        if human_correctness is not None and not isinstance(human_correctness, (float, int)):
            raise ValueError(f"Case {case_id}: human_scores.answer_correctness must be numeric when set")

        cases.append(
            GoldenCase(
                case_id=case_id,
                kind=kind,
                category=category.strip() if isinstance(category, str) else None,
                question=question.strip() if isinstance(question, str) else None,
                source_file=source_file.strip() if isinstance(source_file, str) else None,
                top_k=max(1, min(top_k, 20)),
                max_chunks=max(1, min(max_chunks, 20)),
                should_abstain=should_abstain,
                expected_mode=expected_mode.strip() if isinstance(expected_mode, str) else None,
                min_citations=min_citations,
                require_valid_citations=require_valid_citations,
                expected_contains_any=tuple(x.strip() for x in expected_contains_any if x.strip()),
                expected_not_contains_any=tuple(x.strip() for x in expected_not_contains_any if x.strip()),
                human_faithfulness=float(human_faithfulness) if human_faithfulness is not None else None,
                human_correctness=float(human_correctness) if human_correctness is not None else None,
                notes=notes.strip() if isinstance(notes, str) else None,
            )
        )

    return cases


def _load_baseline_metrics(file_path: Path) -> dict[str, Any]:
    payload = json.loads(file_path.read_text(encoding="utf-8"))

    if isinstance(payload, dict) and "challenger_metrics" in payload:
        metrics = payload["challenger_metrics"]
    elif isinstance(payload, dict) and "metrics" in payload:
        metrics = payload["metrics"]
    else:
        metrics = payload

    required_keys = {
        "faithfulness",
        "answer_correctness",
        "retrieval_recall_at_5",
        "abstention_accuracy",
        "hallucination_rate",
        "invalid_citation_rate",
        "latency_p95_ms",
    }
    if not isinstance(metrics, dict) or not required_keys.issubset(metrics.keys()):
        raise ValueError("Baseline metrics file missing required scoring keys")

    return {k: metrics[k] for k in required_keys}


def _extract_invalid_citations(citations: list[dict[str, Any]]) -> int:
    invalid = 0
    for citation in citations:
        citation_id = str(citation.get("id", "")).strip()
        source_file = str(citation.get("source_file", "")).strip()
        if not citation_id.startswith("C") or not source_file:
            invalid += 1
    return invalid


def _is_abstained(payload: dict[str, Any]) -> bool:
    text_value = str(payload.get("answer") or payload.get("summary") or "").strip()
    return text_value == INSUFFICIENT_EVIDENCE_TEXT


def _contains_expected_terms(text_value: str, expected_terms: tuple[str, ...]) -> bool | None:
    if not expected_terms:
        return None
    lowered = text_value.lower()
    return any(term.lower() in lowered for term in expected_terms)


def _contains_forbidden_terms(text_value: str, forbidden_terms: tuple[str, ...]) -> bool | None:
    if not forbidden_terms:
        return None
    lowered = text_value.lower()
    return any(term.lower() in lowered for term in forbidden_terms)


def _run_case(client: httpx.Client, api_base_url: str, case: GoldenCase, timeout_seconds: float) -> dict[str, Any]:
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be non-negative")

    if case.kind == "answer":
        endpoint = f"{api_base_url.rstrip('/')}/query/answer"
        request_payload: dict[str, Any] = {"question": case.question, "top_k": case.top_k}
    else:
        endpoint = f"{api_base_url.rstrip('/')}/query/summary"
        request_payload = {"source_file": case.source_file, "max_chunks": case.max_chunks}

    start = perf_counter()
    try:
        response = client.post(endpoint, json=request_payload, timeout=timeout_seconds)
        latency_ms = int((perf_counter() - start) * 1000)
    except httpx.HTTPError as exc:
        latency_ms = int((perf_counter() - start) * 1000)
        return {
            "case_id": case.case_id,
            "kind": case.kind,
            "category": case.category,
            "request": request_payload,
            "latency_ms": latency_ms,
            "should_abstain": case.should_abstain,
            "expected_mode": case.expected_mode,
            "min_citations": case.min_citations,
            "require_valid_citations": case.require_valid_citations,
            "expected_contains_any": list(case.expected_contains_any),
            "expected_not_contains_any": list(case.expected_not_contains_any),
            "human_scores": {
                "faithfulness": case.human_faithfulness,
                "answer_correctness": case.human_correctness,
            },
            "notes": case.notes,
            "status_code": None,
            "ok": False,
            "error": f"request-error: {exc}",
            "mode": "request-error",
            "used_chunks": 0,
            "citation_count": 0,
            "invalid_citation_count": 0,
            "abstained": None,
            "checks": {
                "mode_match": None,
                "citation_requirement_met": False,
                "valid_citation_requirement_met": False,
                "abstention_match": None,
                "contains_expected_terms": None,
                "contains_forbidden_terms": None,
                "content_expectation_passed": None,
            },
        }

    record: dict[str, Any] = {
        "case_id": case.case_id,
        "kind": case.kind,
        "category": case.category,
        "request": request_payload,
        "latency_ms": latency_ms,
        "should_abstain": case.should_abstain,
        "expected_mode": case.expected_mode,
        "min_citations": case.min_citations,
        "require_valid_citations": case.require_valid_citations,
        "expected_contains_any": list(case.expected_contains_any),
        "expected_not_contains_any": list(case.expected_not_contains_any),
        "human_scores": {
            "faithfulness": case.human_faithfulness,
            "answer_correctness": case.human_correctness,
        },
        "notes": case.notes,
        "status_code": response.status_code,
    }

    if response.status_code != 200:
        detail: str
        try:
            error_payload = response.json()
            detail = str(error_payload.get("detail", error_payload))
        except Exception:
            detail = response.text[:300]

        record.update(
            {
                "ok": False,
                "error": detail,
                "mode": "http-error",
                "used_chunks": 0,
                "citation_count": 0,
                "invalid_citation_count": 0,
                "abstained": None,
            }
        )
        return record

    body = response.json()
    citations = body.get("citations", [])
    if not isinstance(citations, list):
        citations = []

    citation_dicts = [item for item in citations if isinstance(item, dict)]
    invalid_citation_count = _extract_invalid_citations(citation_dicts)
    abstained = _is_abstained(body)
    content_text = str(body.get("answer") or body.get("summary") or "")

    mode_value = str(body.get("mode")) if body.get("mode") is not None else None
    mode_match = (mode_value == case.expected_mode) if case.expected_mode else None
    citation_requirement_met = len(citation_dicts) >= case.min_citations
    valid_citation_requirement_met = invalid_citation_count == 0 if case.require_valid_citations else True
    abstention_match = (abstained == case.should_abstain) if case.should_abstain is not None else None
    contains_expected = _contains_expected_terms(content_text, case.expected_contains_any)
    contains_forbidden = _contains_forbidden_terms(content_text, case.expected_not_contains_any)
    content_expectation_passed = None
    if contains_expected is not None or contains_forbidden is not None:
        expected_ok = True if contains_expected is None else contains_expected
        forbidden_ok = True if contains_forbidden is None else not contains_forbidden
        content_expectation_passed = expected_ok and forbidden_ok

    record.update(
        {
            "ok": True,
            "mode": mode_value,
            "used_chunks": body.get("used_chunks"),
            "citation_count": len(citation_dicts),
            "invalid_citation_count": invalid_citation_count,
            "abstained": abstained,
            "checks": {
                "mode_match": mode_match,
                "citation_requirement_met": citation_requirement_met,
                "valid_citation_requirement_met": valid_citation_requirement_met,
                "abstention_match": abstention_match,
                "contains_expected_terms": contains_expected,
                "contains_forbidden_terms": contains_forbidden,
                "content_expectation_passed": content_expectation_passed,
            },
            "response": body,
        }
    )
    return record


def _run_case_offline(case: GoldenCase) -> dict[str, Any]:
    mode_value = case.expected_mode or ("low-confidence" if case.should_abstain else "evidence-direct")
    citation_count = case.min_citations
    invalid_citation_count = 0 if case.require_valid_citations else 0
    citations = [
        {
            "id": f"C{i + 1}",
            "source_file": case.source_file or "sample_service_agreement.txt",
        }
        for i in range(citation_count)
    ]

    expected_phrase = case.expected_contains_any[0] if case.expected_contains_any else "Grounded response"
    body_text = INSUFFICIENT_EVIDENCE_TEXT if case.should_abstain else f"{expected_phrase} [C1]"
    response_payload: dict[str, Any]
    if case.kind == "summary":
        response_payload = {
            "summary": body_text,
            "citations": citations,
            "used_chunks": max(1, case.max_chunks // 2),
            "mode": mode_value,
        }
    else:
        response_payload = {
            "answer": body_text,
            "citations": citations,
            "used_chunks": max(1, case.top_k // 2),
            "mode": mode_value,
        }

    abstained = case.should_abstain is True
    content_text = str(response_payload.get("answer") or response_payload.get("summary") or "")
    contains_expected = _contains_expected_terms(content_text, case.expected_contains_any)
    contains_forbidden = _contains_forbidden_terms(content_text, case.expected_not_contains_any)
    content_expectation_passed = None
    if contains_expected is not None or contains_forbidden is not None:
        expected_ok = True if contains_expected is None else contains_expected
        forbidden_ok = True if contains_forbidden is None else not contains_forbidden
        content_expectation_passed = expected_ok and forbidden_ok

    return {
        "case_id": case.case_id,
        "kind": case.kind,
        "category": case.category,
        "request": {
            "question": case.question,
            "source_file": case.source_file,
            "top_k": case.top_k,
            "max_chunks": case.max_chunks,
        },
        "latency_ms": 1,
        "should_abstain": case.should_abstain,
        "expected_mode": case.expected_mode,
        "min_citations": case.min_citations,
        "require_valid_citations": case.require_valid_citations,
        "expected_contains_any": list(case.expected_contains_any),
        "expected_not_contains_any": list(case.expected_not_contains_any),
        "human_scores": {
            "faithfulness": case.human_faithfulness,
            "answer_correctness": case.human_correctness,
        },
        "notes": case.notes,
        "status_code": 200,
        "ok": True,
        "mode": mode_value,
        "used_chunks": response_payload.get("used_chunks"),
        "citation_count": citation_count,
        "invalid_citation_count": invalid_citation_count,
        "abstained": abstained,
        "checks": {
            "mode_match": (mode_value == case.expected_mode) if case.expected_mode else None,
            "citation_requirement_met": citation_count >= case.min_citations,
            "valid_citation_requirement_met": invalid_citation_count == 0 if case.require_valid_citations else True,
            "abstention_match": (abstained == case.should_abstain) if case.should_abstain is not None else None,
            "contains_expected_terms": contains_expected,
            "contains_forbidden_terms": contains_forbidden,
            "content_expectation_passed": content_expectation_passed,
        },
        "response": response_payload,
    }


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    return int(round(quantiles(values, n=100, method="inclusive")[94]))


def _compute_proxy_metrics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    ok_results = [item for item in case_results if item.get("ok")]
    total = len(case_results)

    if not ok_results:
        return {
            "faithfulness": 0.0,
            "answer_correctness": 0.0,
            "retrieval_recall_at_5": 0.0,
            "abstention_accuracy": 0.0,
            "hallucination_rate": 1.0,
            "invalid_citation_rate": 1.0,
            "latency_p95_ms": 9999,
            "notes": ["All cases failed; proxy metrics are pessimistic placeholders."],
        }

    with_citations = [item for item in ok_results if int(item.get("citation_count", 0)) > 0]
    non_abstained = [item for item in ok_results if item.get("abstained") is False]
    non_abstained_without_citations = [item for item in non_abstained if int(item.get("citation_count", 0)) == 0]

    labeled = [item for item in ok_results if item.get("should_abstain") is not None]
    if labeled:
        abstention_correct = [item for item in labeled if bool(item.get("abstained")) == bool(item.get("should_abstain"))]
        abstention_accuracy = len(abstention_correct) / len(labeled)
    else:
        abstention_accuracy = 1.0

    answer_correctness_proxy = len(ok_results) / total if total else 0.0
    faithfulness_proxy = len(with_citations) / len(ok_results)
    retrieval_recall_proxy = faithfulness_proxy
    hallucination_rate = (
        len(non_abstained_without_citations) / len(non_abstained) if non_abstained else 0.0
    )

    total_citations = sum(int(item.get("citation_count", 0)) for item in ok_results)
    invalid_citations = sum(int(item.get("invalid_citation_count", 0)) for item in ok_results)
    invalid_citation_rate = (invalid_citations / total_citations) if total_citations else 0.0

    latencies = [int(item.get("latency_ms", 0)) for item in ok_results]

    human_faithfulness = [
        float(item["human_scores"]["faithfulness"])
        for item in ok_results
        if isinstance(item.get("human_scores"), dict)
        and item["human_scores"].get("faithfulness") is not None
    ]
    human_correctness = [
        float(item["human_scores"]["answer_correctness"])
        for item in ok_results
        if isinstance(item.get("human_scores"), dict)
        and item["human_scores"].get("answer_correctness") is not None
    ]

    faithfulness = sum(human_faithfulness) / len(human_faithfulness) if human_faithfulness else faithfulness_proxy
    answer_correctness = sum(human_correctness) / len(human_correctness) if human_correctness else answer_correctness_proxy

    notes: list[str] = [
        "Metrics are proxy estimates; replace with human-graded correctness/faithfulness for production benchmarking.",
    ]
    if human_faithfulness:
        notes.append("Faithfulness uses human_scores labels where present; proxy used for unlabeled cases.")
    if human_correctness:
        notes.append("Answer correctness uses human_scores labels where present; proxy used for unlabeled cases.")
    if not labeled:
        notes.append("No should_abstain labels were provided; abstention_accuracy defaults to 1.0.")

    return {
        "faithfulness": round(faithfulness, 4),
        "answer_correctness": round(answer_correctness, 4),
        "retrieval_recall_at_5": round(retrieval_recall_proxy, 4),
        "abstention_accuracy": round(abstention_accuracy, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "invalid_citation_rate": round(invalid_citation_rate, 4),
        "latency_p95_ms": _p95(latencies),
        "proxy_components": {
            "faithfulness_proxy": round(faithfulness_proxy, 4),
            "answer_correctness_proxy": round(answer_correctness_proxy, 4),
            "human_faithfulness_count": len(human_faithfulness),
            "human_correctness_count": len(human_correctness),
            "abstention_labeled_cases": len(labeled),
            "abstention_matches": len(abstention_correct) if labeled else 0,
        },
        "notes": notes,
    }


def _write_outputs(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = report["run_id"]

    json_path = output_dir / f"run_{run_id}.json"
    md_path = output_dir / f"run_{run_id}.md"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    compare = report.get("compare")
    winner = compare.get("winner") if isinstance(compare, dict) else "n/a"
    delta = compare.get("delta_overall_score") if isinstance(compare, dict) else "n/a"

    lines = [
        "# Evaluation Run",
        "",
        f"- Run ID: {run_id}",
        f"- API Base URL: {report['api_base_url']}",
        f"- Eval source: {report['eval_source']}",
        f"- Cases: {report['summary']['total_cases']}",
        f"- Successful: {report['summary']['successful_cases']}",
        f"- Failed: {report['summary']['failed_cases']}",
        f"- Challenger overall_score: {report['score']['overall_score']}",
        f"- Compare winner: {winner}",
        f"- Compare delta_overall_score: {delta}",
        f"- Abstention labeled cases: {report['challenger_metrics']['proxy_components']['abstention_labeled_cases']}",
        f"- Abstention matches: {report['challenger_metrics']['proxy_components']['abstention_matches']}",
        "",
        "## Challenger Metrics",
        "",
    ]

    for key in (
        "faithfulness",
        "answer_correctness",
        "retrieval_recall_at_5",
        "abstention_accuracy",
        "hallucination_rate",
        "invalid_citation_rate",
        "latency_p95_ms",
    ):
        lines.append(f"- {key}: {report['challenger_metrics'][key]}")

    lines.extend(["", "## Per-Case Logging Validation", ""])
    lines.append("- case-level latency: captured in each case result as latency_ms")
    lines.append("- mode: captured in each case result as mode")
    lines.append("- citation counts and validity: captured as citation_count and invalid_citation_count")
    lines.append("- abstention accuracy behavior: captured per case in checks.abstention_match and aggregated in proxy_components")

    lines.extend(["", "## Notes", ""])
    for note in report["challenger_metrics"].get("notes", []):
        lines.append(f"- {note}")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = _parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "mvp" / "experiments"

    case_file = Path(args.cases)
    if not case_file.is_absolute():
        case_file = (Path.cwd() / case_file).resolve()

    baseline_metrics: dict[str, Any] | None = None
    if args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_absolute():
            baseline_path = (Path.cwd() / baseline_path).resolve()
        baseline_metrics = _load_baseline_metrics(baseline_path)

    cases = _load_cases(case_file)

    case_results: list[dict[str, Any]] = []
    eval_source = "api"
    with httpx.Client() as client:
        for case in cases:
            if args.offline:
                case_results.append(_run_case_offline(case))
            else:
                case_results.append(
                    _run_case(
                        client=client,
                        api_base_url=args.api_base_url,
                        case=case,
                        timeout_seconds=args.timeout_seconds,
                    )
                )

        challenger_metrics = _compute_proxy_metrics(case_results)

        score_input = {
            "faithfulness": challenger_metrics["faithfulness"],
            "answer_correctness": challenger_metrics["answer_correctness"],
            "retrieval_recall_at_5": challenger_metrics["retrieval_recall_at_5"],
            "abstention_accuracy": challenger_metrics["abstention_accuracy"],
            "hallucination_rate": challenger_metrics["hallucination_rate"],
            "invalid_citation_rate": challenger_metrics["invalid_citation_rate"],
            "latency_p95_ms": challenger_metrics["latency_p95_ms"],
        }

        if args.offline:
            eval_source = "offline-local"
            score_payload = compute_overall_score(ExperimentMetrics(**score_input))
        else:
            try:
                score_response = client.post(
                    f"{args.api_base_url.rstrip('/')}/eval/score",
                    json=score_input,
                    timeout=args.timeout_seconds,
                )
                score_response.raise_for_status()
                score_payload = score_response.json()
            except httpx.HTTPError:
                eval_source = "local-fallback"
                score_payload = compute_overall_score(ExperimentMetrics(**score_input))

        compare_payload: dict[str, Any] | None = None
        if baseline_metrics is not None:
            compare_input = {"baseline": baseline_metrics, "challenger": {k: challenger_metrics[k] for k in baseline_metrics}}
            if args.offline:
                eval_source = "offline-local"
                compare_payload = compare_experiments(
                    baseline=ExperimentMetrics(**baseline_metrics),
                    challenger=ExperimentMetrics(**{k: challenger_metrics[k] for k in baseline_metrics}),
                )
            else:
                try:
                    compare_response = client.post(
                        f"{args.api_base_url.rstrip('/')}/eval/compare",
                        json=compare_input,
                        timeout=args.timeout_seconds,
                    )
                    compare_response.raise_for_status()
                    compare_payload = compare_response.json()
                except httpx.HTTPError:
                    eval_source = "local-fallback"
                    compare_payload = compare_experiments(
                        baseline=ExperimentMetrics(**baseline_metrics),
                        challenger=ExperimentMetrics(**{k: challenger_metrics[k] for k in baseline_metrics}),
                    )

    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")

    report: dict[str, Any] = {
        "run_id": run_id,
        "api_base_url": args.api_base_url,
        "cases_file": str(case_file),
        "eval_source": eval_source,
        "summary": {
            "total_cases": len(case_results),
            "successful_cases": len([item for item in case_results if item.get("ok")]),
            "failed_cases": len([item for item in case_results if not item.get("ok")]),
            "abstention_labeled_cases": challenger_metrics["proxy_components"]["abstention_labeled_cases"],
            "abstention_matches": challenger_metrics["proxy_components"]["abstention_matches"],
            "abstention_accuracy": challenger_metrics["abstention_accuracy"],
        },
        "case_results": case_results,
        "challenger_metrics": challenger_metrics,
        "score": score_payload,
        "compare": compare_payload,
    }

    if baseline_metrics is not None:
        report["baseline_metrics"] = baseline_metrics

    json_path, md_path = _write_outputs(output_dir, report)

    print(f"Run saved: {json_path}")
    print(f"Summary: {md_path}")
    print(f"Challenger overall_score: {score_payload.get('overall_score')}")

    if compare_payload is not None:
        winner = str(compare_payload.get("winner", "unknown"))
        print(f"Compare winner: {winner}")
        # CI gate: runner fails if challenger does not win.
        if winner != "challenger":
            print("Regression gate failed: challenger did not win.")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
