from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trend diagnostics from eval run artifacts")
    parser.add_argument(
        "--runs-dir",
        default="../mvp/experiments",
        help="Directory containing run_*.json artifacts",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of latest runs to include (default: 20)",
    )
    parser.add_argument(
        "--output-json",
        default="trend_latest.json",
        help="Trend summary JSON filename (written inside runs-dir)",
    )
    parser.add_argument(
        "--output-md",
        default="trend_latest.md",
        help="Trend summary Markdown filename (written inside runs-dir)",
    )
    return parser.parse_args()


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload in {path}")
    return payload


def _safe_float(value: Any) -> float | None:
    if isinstance(value, (float, int)):
        return float(value)
    return None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, (float, int)):
        return int(value)
    return None


def _extract_run_point(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    metrics = payload.get("challenger_metrics") if isinstance(payload.get("challenger_metrics"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    run_analytics = payload.get("run_analytics") if isinstance(payload.get("run_analytics"), dict) else {}

    return {
        "run_id": payload.get("run_id"),
        "run_file": str(path),
        "eval_source": payload.get("eval_source"),
        "pass_fail": score.get("pass_fail"),
        "overall_score": _safe_float(score.get("overall_score")),
        "latency_p95_ms": _safe_int(metrics.get("latency_p95_ms")),
        "invalid_citation_rate": _safe_float(metrics.get("invalid_citation_rate")),
        "abstention_accuracy": _safe_float(metrics.get("abstention_accuracy")),
        "failed_cases": _safe_int(summary.get("failed_cases")),
        "success_rate": _safe_float(run_analytics.get("success_rate")),
        "top_non_pass_issues": (
            run_analytics.get("failure_taxonomy", {}).get("top_non_pass_issues", [])
            if isinstance(run_analytics.get("failure_taxonomy"), dict)
            else []
        ),
    }


def _delta(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(float(current) - float(previous), 4)


def _window_mean(points: list[dict[str, Any]], key: str, window: int) -> float | None:
    values = [point[key] for point in points[-window:] if isinstance(point.get(key), (float, int))]
    if not values:
        return None
    return round(float(mean(values)), 4)


def _aggregate_issue_counts(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for point in points:
        issues = point.get("top_non_pass_issues")
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            name = str(issue.get("issue") or "").strip()
            count = issue.get("count")
            if not name or not isinstance(count, (int, float)):
                continue
            counts[name] = counts.get(name, 0) + int(count)

    return [
        {"issue": issue, "count": count}
        for issue, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    ]


def _build_trend_report(points: list[dict[str, Any]]) -> dict[str, Any]:
    latest = points[-1] if points else None
    previous = points[-2] if len(points) > 1 else None

    pass_count = sum(1 for point in points if str(point.get("pass_fail", "")).lower() == "pass")
    fail_count = sum(1 for point in points if str(point.get("pass_fail", "")).lower() == "fail")

    trend = {
        "run_count": len(points),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate": round((pass_count / len(points)) if points else 0.0, 4),
        "latest_run_id": latest.get("run_id") if latest else None,
        "latest": {
            "overall_score": latest.get("overall_score") if latest else None,
            "latency_p95_ms": latest.get("latency_p95_ms") if latest else None,
            "invalid_citation_rate": latest.get("invalid_citation_rate") if latest else None,
            "abstention_accuracy": latest.get("abstention_accuracy") if latest else None,
            "failed_cases": latest.get("failed_cases") if latest else None,
        },
        "deltas_vs_previous": {
            "overall_score": _delta(
                latest.get("overall_score") if latest else None,
                previous.get("overall_score") if previous else None,
            ),
            "latency_p95_ms": _delta(
                latest.get("latency_p95_ms") if latest else None,
                previous.get("latency_p95_ms") if previous else None,
            ),
            "invalid_citation_rate": _delta(
                latest.get("invalid_citation_rate") if latest else None,
                previous.get("invalid_citation_rate") if previous else None,
            ),
            "abstention_accuracy": _delta(
                latest.get("abstention_accuracy") if latest else None,
                previous.get("abstention_accuracy") if previous else None,
            ),
        },
        "moving_averages": {
            "overall_score_last_5": _window_mean(points, "overall_score", 5),
            "latency_p95_ms_last_5": _window_mean(points, "latency_p95_ms", 5),
            "invalid_citation_rate_last_5": _window_mean(points, "invalid_citation_rate", 5),
            "abstention_accuracy_last_5": _window_mean(points, "abstention_accuracy", 5),
        },
        "top_failure_issues": _aggregate_issue_counts(points)[:10],
        "series": points,
    }
    return trend


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Eval Trend Report",
        "",
        f"- runs: {report.get('run_count')}",
        f"- pass_rate: {report.get('pass_rate')}",
        f"- latest_run_id: {report.get('latest_run_id')}",
        "",
        "## Latest",
        "",
    ]

    latest = report.get("latest") if isinstance(report.get("latest"), dict) else {}
    for key in ("overall_score", "latency_p95_ms", "invalid_citation_rate", "abstention_accuracy", "failed_cases"):
        lines.append(f"- {key}: {latest.get(key)}")

    lines.extend(["", "## Deltas vs Previous", ""])
    deltas = report.get("deltas_vs_previous") if isinstance(report.get("deltas_vs_previous"), dict) else {}
    for key, value in deltas.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Moving Averages", ""])
    moving = report.get("moving_averages") if isinstance(report.get("moving_averages"), dict) else {}
    for key, value in moving.items():
        lines.append(f"- {key}: {value}")

    top_issues = report.get("top_failure_issues") if isinstance(report.get("top_failure_issues"), list) else []
    if top_issues:
        lines.extend(["", "## Top Failure Issues", ""])
        for item in top_issues:
            if isinstance(item, dict):
                lines.append(f"- {item.get('issue')}: {item.get('count')}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    if args.limit <= 0:
        raise ValueError("--limit must be > 0")

    runs_dir = _resolve_path(args.runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_files = sorted(runs_dir.glob("run_*.json"), key=lambda p: p.stat().st_mtime)
    selected = run_files[-args.limit :]

    points: list[dict[str, Any]] = []
    for run_file in selected:
        payload = _load_json(run_file)
        points.append(_extract_run_point(run_file, payload))

    report = _build_trend_report(points)

    output_json = runs_dir / args.output_json
    output_md = runs_dir / args.output_md

    output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_markdown(output_md, report)

    print(f"Trend report saved: {output_json}")
    print(f"Trend summary saved: {output_md}")
    print(f"Runs analyzed: {report.get('run_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
