from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    parser = argparse.ArgumentParser(description="Promote a run's challenger metrics to baseline")
    parser.add_argument("--run-json", required=True, help="Path to run_*.json artifact")
    parser.add_argument(
        "--baseline-file",
        default="../mvp/experiments/baseline_metrics.json",
        help="Path to baseline metrics file",
    )
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="Allow promotion from offline-local runs",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force promotion even if compare checks fail",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate promotion policy and metrics only; do not write baseline file.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object in {path}")
    return payload


def _extract_metrics(run_payload: dict[str, Any]) -> dict[str, Any]:
    challenger = run_payload.get("challenger_metrics")
    if not isinstance(challenger, dict):
        raise ValueError("Run JSON missing challenger_metrics")

    metrics: dict[str, Any] = {}
    for key in REQUIRED_METRICS:
        if key not in challenger:
            raise ValueError(f"Run JSON missing challenger_metrics.{key}")
        metrics[key] = challenger[key]
    return metrics


def _validate_promotion_policy(run_payload: dict[str, Any], allow_offline: bool) -> None:
    eval_source = str(run_payload.get("eval_source", ""))
    if eval_source == "offline-local" and not allow_offline:
        raise ValueError("Refusing baseline promotion from offline-local run. Use --allow-offline to override.")

    compare = run_payload.get("compare")
    if not isinstance(compare, dict):
        raise ValueError("Run JSON missing compare object")

    winner = str(compare.get("winner", ""))
    has_regression = bool(compare.get("has_gate_regression", True))

    score = run_payload.get("score")
    if not isinstance(score, dict):
        raise ValueError("Run JSON missing score object")

    pass_fail = str(score.get("pass_fail", "")).lower()

    if winner != "challenger":
        raise ValueError(f"Promotion blocked: compare winner is '{winner}', not 'challenger'.")
    if has_regression:
        raise ValueError("Promotion blocked: has_gate_regression=true.")
    if pass_fail != "pass":
        raise ValueError(f"Promotion blocked: run score pass_fail='{pass_fail}'.")


def main() -> int:
    args = _parse_args()

    run_path = Path(args.run_json)
    if not run_path.is_absolute():
        run_path = (Path.cwd() / run_path).resolve()

    baseline_path = Path(args.baseline_file)
    if not baseline_path.is_absolute():
        baseline_path = (Path.cwd() / baseline_path).resolve()

    run_payload = _load_json(run_path)

    if not args.force:
        _validate_promotion_policy(run_payload, allow_offline=args.allow_offline)

    promoted_metrics = _extract_metrics(run_payload)

    if args.check_only:
        print(f"Promotion policy check passed for run: {run_path}")
        print("Check-only mode enabled; baseline file was not modified.")
        print("Validated metrics keys: " + ", ".join(REQUIRED_METRICS))
        return 0

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    if baseline_path.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = baseline_path.with_name(f"baseline_metrics.backup_{ts}.json")
        backup_path.write_text(baseline_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup created: {backup_path}")

    baseline_path.write_text(json.dumps(promoted_metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Baseline promoted from run: {run_path}")
    print(f"Updated baseline file: {baseline_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
