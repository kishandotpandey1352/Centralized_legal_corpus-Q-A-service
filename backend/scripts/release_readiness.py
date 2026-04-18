from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REQUIRED_METRICS = [
    "faithfulness",
    "answer_correctness",
    "retrieval_recall_at_5",
    "abstention_accuracy",
    "hallucination_rate",
    "invalid_citation_rate",
    "latency_p95_ms",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Day 20 release readiness checkpoint: freeze baseline candidate, run final multi-run "
            "comparison, and publish a release report."
        )
    )
    parser.add_argument("--api-base-url", default="http://localhost:8000", help="FastAPI base URL")
    parser.add_argument(
        "--cases",
        default="../mvp/golden_set_template.json",
        help="Golden set for final comparison run",
    )
    parser.add_argument(
        "--baseline-file",
        default="../mvp/experiments/baseline_metrics.json",
        help="Current baseline metrics file",
    )
    parser.add_argument(
        "--runs-dir",
        default="../mvp/experiments",
        help="Directory containing historical run_*.json artifacts",
    )
    parser.add_argument(
        "--output-dir",
        default="../mvp/experiments/release_readiness",
        help="Output directory for Day 20 checkpoint artifacts",
    )
    parser.add_argument(
        "--candidate-run-json",
        default=None,
        help="Optional run_*.json to freeze as candidate. Defaults to latest run in --runs-dir.",
    )
    parser.add_argument("--runs", type=int, default=2, help="Number of final comparison runs")
    parser.add_argument(
        "--require-winner-rate",
        type=float,
        default=0.7,
        help="Required challenger winner rate for final comparison",
    )
    parser.add_argument(
        "--require-passing-rate",
        type=float,
        default=1.0,
        help="Required pass rate for final comparison",
    )
    parser.add_argument(
        "--require-consecutive-live-runs",
        type=int,
        default=2,
        help="Promotion-policy streak length for check-only validation",
    )

    # Pass-through runtime controls for eval_series/eval_runner.
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--answer-timeout-seconds", type=float, default=25.0)
    parser.add_argument("--summary-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--answer-max-retries", type=int, default=2)
    parser.add_argument("--summary-max-retries", type=int, default=2)
    parser.add_argument("--connect-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--read-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--write-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--pool-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--retry-backoff-seconds", type=float, default=0.5)
    parser.add_argument("--retry-backoff-multiplier", type=float, default=2.0)
    parser.add_argument("--max-retry-backoff-seconds", type=float, default=5.0)

    return parser.parse_args()


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _latest_run_json(runs_dir: Path) -> Path:
    run_files = sorted(runs_dir.glob("run_*.json"), key=lambda p: p.stat().st_mtime)
    if not run_files:
        raise ValueError(f"No run_*.json artifacts found in {runs_dir}")
    return run_files[-1]


def _extract_candidate_metrics(run_payload: dict[str, Any]) -> dict[str, Any]:
    challenger = run_payload.get("challenger_metrics")
    if not isinstance(challenger, dict):
        raise ValueError("Candidate run is missing challenger_metrics")

    metrics: dict[str, Any] = {}
    for key in REQUIRED_METRICS:
        if key not in challenger:
            raise ValueError(f"Candidate run missing challenger_metrics.{key}")
        metrics[key] = challenger[key]
    return metrics


def _health_check(api_base_url: str) -> tuple[bool, str]:
    health_url = f"{api_base_url.rstrip('/')}/health"
    try:
        response = httpx.get(health_url, timeout=5.0)
        if response.status_code == 200:
            return True, response.text
        return False, f"status={response.status_code} body={response.text}"
    except Exception as exc:  # pragma: no cover - defensive for local env variability
        return False, str(exc)


def _run_subprocess(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def _write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Day 20 Release Readiness Report")
    lines.append("")
    lines.append(f"- generated_at_utc: {payload.get('generated_at_utc')}")
    lines.append(f"- api_base_url: {payload.get('api_base_url')}")
    lines.append(f"- cases_file: {payload.get('cases_file')}")
    lines.append(f"- health_ok: {payload.get('health', {}).get('ok')}")
    lines.append(f"- release_ready: {payload.get('release_ready')}")
    lines.append("")

    freeze = payload.get("freeze", {})
    lines.append("## Candidate Freeze")
    lines.append("")
    lines.append(f"- candidate_run_json: {freeze.get('candidate_run_json')}")
    lines.append(f"- candidate_snapshot_file: {freeze.get('candidate_snapshot_file')}")
    lines.append(f"- baseline_snapshot_file: {freeze.get('baseline_snapshot_file')}")
    lines.append("")

    final_series = payload.get("final_series", {})
    lines.append("## Final Multi-Run Comparison")
    lines.append("")
    lines.append(f"- runner_exit_code: {final_series.get('runner_exit_code')}")
    lines.append(f"- series_pass: {final_series.get('series_pass')}")
    lines.append(f"- winner_rate: {final_series.get('winner_rate')}")
    lines.append(f"- passing_rate: {final_series.get('passing_rate')}")
    lines.append(f"- overall_score_mean: {final_series.get('overall_score_mean')}")
    lines.append(f"- latency_p95_ms_mean: {final_series.get('latency_p95_ms_mean')}")
    lines.append("")

    policy = payload.get("promotion_policy_check", {})
    lines.append("## Promotion Policy Check (Check-Only)")
    lines.append("")
    lines.append(f"- exit_code: {policy.get('exit_code')}")
    lines.append(f"- passed: {policy.get('passed')}")

    stdout = str(policy.get("stdout", "")).strip()
    if stdout:
        lines.append("")
        lines.append("### promote_baseline.py output")
        lines.append("")
        lines.append("```text")
        lines.append(stdout)
        lines.append("```")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()

    if args.runs <= 0:
        raise ValueError("--runs must be > 0")
    if args.require_consecutive_live_runs <= 0:
        raise ValueError("--require-consecutive-live-runs must be >= 1")

    script_dir = Path(__file__).resolve().parent
    backend_root = script_dir.parent

    cases_file = _resolve_path(args.cases)
    baseline_file = _resolve_path(args.baseline_file)
    runs_dir = _resolve_path(args.runs_dir)
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    health_ok, health_detail = _health_check(args.api_base_url)
    if not health_ok:
        raise RuntimeError(f"API health check failed: {health_detail}")

    if args.candidate_run_json:
        candidate_run_json = _resolve_path(args.candidate_run_json)
    else:
        candidate_run_json = _latest_run_json(runs_dir)

    run_payload = _read_json(candidate_run_json)
    candidate_metrics = _extract_candidate_metrics(run_payload)
    baseline_metrics = _read_json(baseline_file)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    candidate_snapshot_file = output_dir / f"release_candidate_metrics_{ts}.json"
    baseline_snapshot_file = output_dir / f"baseline_snapshot_{ts}.json"
    _write_json(candidate_snapshot_file, candidate_metrics)
    _write_json(baseline_snapshot_file, baseline_metrics)

    eval_series_cmd = [
        sys.executable,
        str(script_dir / "eval_series.py"),
        "--api-base-url",
        args.api_base_url,
        "--cases",
        str(cases_file),
        "--baseline",
        str(baseline_file),
        "--output-dir",
        str(output_dir),
        "--runs",
        str(args.runs),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--answer-timeout-seconds",
        str(args.answer_timeout_seconds),
        "--summary-timeout-seconds",
        str(args.summary_timeout_seconds),
        "--max-retries",
        str(args.max_retries),
        "--answer-max-retries",
        str(args.answer_max_retries),
        "--summary-max-retries",
        str(args.summary_max_retries),
        "--connect-timeout-seconds",
        str(args.connect_timeout_seconds),
        "--read-timeout-seconds",
        str(args.read_timeout_seconds),
        "--write-timeout-seconds",
        str(args.write_timeout_seconds),
        "--pool-timeout-seconds",
        str(args.pool_timeout_seconds),
        "--retry-backoff-seconds",
        str(args.retry_backoff_seconds),
        "--retry-backoff-multiplier",
        str(args.retry_backoff_multiplier),
        "--max-retry-backoff-seconds",
        str(args.max_retry_backoff_seconds),
        "--require-winner-rate",
        str(args.require_winner_rate),
        "--require-passing-rate",
        str(args.require_passing_rate),
    ]

    series_exit, series_stdout, series_stderr = _run_subprocess(eval_series_cmd, cwd=backend_root)

    series_latest_file = output_dir / "series_latest.json"
    if not series_latest_file.exists():
        raise RuntimeError(
            "Final multi-run comparison did not produce series_latest.json in output-dir. "
            f"stdout={series_stdout}\nstderr={series_stderr}"
        )
    series_latest = _read_json(series_latest_file)

    run_reports = series_latest.get("run_reports") if isinstance(series_latest.get("run_reports"), list) else []
    latest_series_run_json = None
    for item in reversed(run_reports):
        if isinstance(item, dict) and item.get("run_json"):
            latest_series_run_json = str(item.get("run_json"))
            break
    if not latest_series_run_json:
        raise RuntimeError("series_latest.json has no run_reports.run_json entry")

    promote_cmd = [
        sys.executable,
        str(script_dir / "promote_baseline.py"),
        "--run-json",
        latest_series_run_json,
        "--runs-dir",
        str(output_dir),
        "--require-consecutive-live-runs",
        str(args.require_consecutive_live_runs),
        "--check-only",
    ]
    promote_exit, promote_stdout, promote_stderr = _run_subprocess(promote_cmd, cwd=backend_root)

    report_payload = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "api_base_url": args.api_base_url,
        "cases_file": str(cases_file),
        "health": {
            "ok": health_ok,
            "detail": health_detail,
        },
        "freeze": {
            "candidate_run_json": str(candidate_run_json),
            "candidate_snapshot_file": str(candidate_snapshot_file),
            "baseline_snapshot_file": str(baseline_snapshot_file),
        },
        "final_series": {
            "runner_exit_code": series_exit,
            "series_latest_file": str(series_latest_file),
            "series_pass": bool(series_latest.get("series_pass", False)),
            "winner_rate": series_latest.get("winner_rate"),
            "passing_rate": series_latest.get("passing_rate"),
            "overall_score_mean": series_latest.get("overall_score_mean"),
            "latency_p95_ms_mean": series_latest.get("latency_p95_ms_mean"),
            "stdout": series_stdout,
            "stderr": series_stderr,
        },
        "promotion_policy_check": {
            "exit_code": promote_exit,
            "passed": promote_exit == 0,
            "stdout": promote_stdout,
            "stderr": promote_stderr,
            "validated_run_json": latest_series_run_json,
        },
    }

    release_ready = bool(series_latest.get("series_pass", False)) and promote_exit == 0
    report_payload["release_ready"] = release_ready

    json_report_file = output_dir / "release_readiness_latest.json"
    md_report_file = output_dir / "release_readiness_latest.md"
    _write_json(json_report_file, report_payload)
    _write_markdown_report(md_report_file, report_payload)

    print(f"Candidate snapshot: {candidate_snapshot_file}")
    print(f"Baseline snapshot: {baseline_snapshot_file}")
    print(f"Series aggregate: {series_latest_file}")
    print(f"Release report JSON: {json_report_file}")
    print(f"Release report MD: {md_report_file}")
    print(f"release_ready={release_ready}")

    return 0 if release_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
