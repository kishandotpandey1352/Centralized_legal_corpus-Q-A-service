from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run repeated live evals and summarize winner variance/confidence"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of repeated runs to execute (default: 5)",
    )
    parser.add_argument(
        "--runner-script",
        default="scripts/eval_runner.py",
        help="Path to eval runner script (default: scripts/eval_runner.py)",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://localhost:8000",
        help="FastAPI base URL for eval runs",
    )
    parser.add_argument(
        "--cases",
        required=True,
        help="Path to cases file for each run",
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to baseline metrics JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="../mvp/experiments",
        help="Directory for run artifacts and aggregate output",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90.0,
        help="Global eval request timeout",
    )
    parser.add_argument(
        "--answer-timeout-seconds",
        type=float,
        default=None,
        help="Answer timeout override",
    )
    parser.add_argument(
        "--summary-timeout-seconds",
        type=float,
        default=None,
        help="Summary timeout override",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=1,
        help="Retry count for each case",
    )
    parser.add_argument(
        "--answer-max-retries",
        type=int,
        default=None,
        help="Optional retry override for answer cases",
    )
    parser.add_argument(
        "--summary-max-retries",
        type=int,
        default=None,
        help="Optional retry override for summary cases",
    )
    parser.add_argument(
        "--connect-timeout-seconds",
        type=float,
        default=None,
        help="Optional connect timeout override",
    )
    parser.add_argument(
        "--read-timeout-seconds",
        type=float,
        default=None,
        help="Optional read timeout override",
    )
    parser.add_argument(
        "--write-timeout-seconds",
        type=float,
        default=None,
        help="Optional write timeout override",
    )
    parser.add_argument(
        "--pool-timeout-seconds",
        type=float,
        default=None,
        help="Optional pool timeout override",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=0.5,
        help="Initial backoff delay in seconds between retries",
    )
    parser.add_argument(
        "--retry-backoff-multiplier",
        type=float,
        default=2.0,
        help="Backoff multiplier between retries",
    )
    parser.add_argument(
        "--max-retry-backoff-seconds",
        type=float,
        default=5.0,
        help="Maximum retry backoff in seconds",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop series immediately if any run fails",
    )
    parser.add_argument(
        "--require-winner-rate",
        type=float,
        default=0.6,
        help="Minimum challenger win rate required for success (default: 0.6)",
    )
    parser.add_argument(
        "--require-passing-rate",
        type=float,
        default=1.0,
        help="Minimum per-run pass rate required for success (default: 1.0)",
    )
    return parser.parse_args()


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _latest_run_json(output_dir: Path, previous_set: set[Path]) -> Path | None:
    current = set(output_dir.glob("run_*.json"))
    new_items = sorted(current - previous_set, key=lambda p: p.stat().st_mtime)
    if new_items:
        return new_items[-1]
    return None


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def main() -> int:
    args = _parse_args()
    if args.runs <= 0:
        raise ValueError("--runs must be > 0")
    if not (0.0 <= args.require_winner_rate <= 1.0):
        raise ValueError("--require-winner-rate must be within [0, 1]")
    if not (0.0 <= args.require_passing_rate <= 1.0):
        raise ValueError("--require-passing-rate must be within [0, 1]")

    runner_script = _resolve_path(args.runner_script)
    output_dir = _resolve_path(args.output_dir)
    cases = _resolve_path(args.cases)
    baseline = _resolve_path(args.baseline)

    output_dir.mkdir(parents=True, exist_ok=True)

    run_reports: list[dict[str, Any]] = []

    for idx in range(1, args.runs + 1):
        before = set(output_dir.glob("run_*.json"))

        cmd = [
            sys.executable,
            str(runner_script),
            "--api-base-url",
            args.api_base_url,
            "--cases",
            str(cases),
            "--baseline",
            str(baseline),
            "--output-dir",
            str(output_dir),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--max-retries",
            str(args.max_retries),
            "--retry-backoff-seconds",
            str(args.retry_backoff_seconds),
            "--retry-backoff-multiplier",
            str(args.retry_backoff_multiplier),
            "--max-retry-backoff-seconds",
            str(args.max_retry_backoff_seconds),
        ]

        if args.answer_timeout_seconds is not None:
            cmd.extend(["--answer-timeout-seconds", str(args.answer_timeout_seconds)])
        if args.summary_timeout_seconds is not None:
            cmd.extend(["--summary-timeout-seconds", str(args.summary_timeout_seconds)])
        if args.answer_max_retries is not None:
            cmd.extend(["--answer-max-retries", str(args.answer_max_retries)])
        if args.summary_max_retries is not None:
            cmd.extend(["--summary-max-retries", str(args.summary_max_retries)])
        if args.connect_timeout_seconds is not None:
            cmd.extend(["--connect-timeout-seconds", str(args.connect_timeout_seconds)])
        if args.read_timeout_seconds is not None:
            cmd.extend(["--read-timeout-seconds", str(args.read_timeout_seconds)])
        if args.write_timeout_seconds is not None:
            cmd.extend(["--write-timeout-seconds", str(args.write_timeout_seconds)])
        if args.pool_timeout_seconds is not None:
            cmd.extend(["--pool-timeout-seconds", str(args.pool_timeout_seconds)])

        print(f"[{idx}/{args.runs}] Executing: {' '.join(cmd)}")
        completed = subprocess.run(cmd, cwd=runner_script.parent.parent, check=False)

        run_json = _latest_run_json(output_dir=output_dir, previous_set=before)
        if run_json is None:
            row = {
                "run_index": idx,
                "run_json": None,
                "runner_exit_code": completed.returncode,
                "winner": "unknown",
                "has_gate_regression": True,
                "pass_fail": "fail",
                "overall_score": None,
                "latency_p95_ms": None,
                "eval_source": "runner-error",
            }
            print(f"[{idx}/{args.runs}] No new run artifact produced.")
        else:
            payload = _load_json(run_json)

            compare = payload.get("compare") if isinstance(payload.get("compare"), dict) else {}
            score = payload.get("score") if isinstance(payload.get("score"), dict) else {}

            row = {
                "run_index": idx,
                "run_json": str(run_json),
                "runner_exit_code": completed.returncode,
                "winner": str(compare.get("winner", "unknown")),
                "has_gate_regression": bool(compare.get("has_gate_regression", True)),
                "pass_fail": str(score.get("pass_fail", "unknown")).lower(),
                "overall_score": score.get("overall_score"),
                "latency_p95_ms": payload.get("challenger_metrics", {}).get("latency_p95_ms"),
                "eval_source": payload.get("eval_source"),
            }
        run_reports.append(row)

        if completed.returncode != 0 and args.stop_on_failure:
            print("Stopping early due to runner failure and --stop-on-failure.")
            break

    executed = len(run_reports)
    winner_count = sum(1 for item in run_reports if item["winner"] == "challenger")
    pass_count = sum(1 for item in run_reports if item["pass_fail"] == "pass")
    gate_regression_count = sum(1 for item in run_reports if item["has_gate_regression"])

    overall_scores = [
        float(item["overall_score"])
        for item in run_reports
        if isinstance(item.get("overall_score"), (int, float))
    ]
    latencies = [
        int(item["latency_p95_ms"])
        for item in run_reports
        if isinstance(item.get("latency_p95_ms"), (int, float))
    ]

    winner_rate = (winner_count / executed) if executed else 0.0
    passing_rate = (pass_count / executed) if executed else 0.0

    aggregate = {
        "runs_requested": args.runs,
        "runs_executed": executed,
        "winner_rate": round(winner_rate, 4),
        "passing_rate": round(passing_rate, 4),
        "gate_regression_count": gate_regression_count,
        "overall_score_mean": round(mean(overall_scores), 4) if overall_scores else None,
        "overall_score_std": round(pstdev(overall_scores), 4) if len(overall_scores) > 1 else 0.0,
        "latency_p95_ms_mean": round(mean(latencies), 2) if latencies else None,
        "latency_p95_ms_std": round(pstdev(latencies), 2) if len(latencies) > 1 else 0.0,
        "require_winner_rate": args.require_winner_rate,
        "require_passing_rate": args.require_passing_rate,
        "series_pass": winner_rate >= args.require_winner_rate and passing_rate >= args.require_passing_rate,
        "run_reports": run_reports,
    }

    aggregate_path = output_dir / "series_latest.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")

    print(f"Series aggregate saved: {aggregate_path}")
    print(
        "winner_rate={:.2%}, passing_rate={:.2%}, overall_score_mean={}, latency_p95_ms_mean={}".format(
            winner_rate,
            passing_rate,
            aggregate["overall_score_mean"],
            aggregate["latency_p95_ms_mean"],
        )
    )

    if not aggregate["series_pass"]:
        print("Series gate failed: winner/pass rates below thresholds.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
