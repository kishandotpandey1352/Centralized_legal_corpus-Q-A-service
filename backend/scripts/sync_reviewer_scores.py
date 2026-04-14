from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKSHEET_SCORE_FIELDS = {
    "reviewer_faithfulness": "faithfulness",
    "reviewer_answer_correctness": "answer_correctness",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync reviewer worksheet human scores into golden set safely"
    )
    parser.add_argument(
        "--worksheet",
        default="../mvp/human_scores_reviewer_worksheet.csv",
        help="Path to reviewer worksheet CSV",
    )
    parser.add_argument(
        "--golden-set",
        default="../mvp/golden_set_template.json",
        help="Path to golden set JSON",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. Defaults to --golden-set path.",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow updating only one reviewer score field when the other is blank.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if worksheet has unknown case IDs or metadata mismatches.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to output path. Without this flag, runs in dry-run mode.",
    )
    return parser.parse_args()


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _load_golden_set(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Golden set root must be an object")

    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Golden set must include a 'cases' list")

    by_id: dict[str, dict[str, Any]] = {}
    for idx, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Case at index {idx} must be an object")
        case_id = str(case.get("id", "")).strip()
        if not case_id:
            raise ValueError(f"Case at index {idx} is missing 'id'")
        if case_id in by_id:
            raise ValueError(f"Duplicate case id in golden set: {case_id}")
        by_id[case_id] = case

    return payload, by_id


def _parse_optional_float(value: str, field_name: str, row_num: int) -> float | None:
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        numeric = float(trimmed)
    except ValueError as exc:
        raise ValueError(f"Row {row_num}: {field_name} must be numeric when provided") from exc
    if numeric < 0.0 or numeric > 1.0:
        raise ValueError(f"Row {row_num}: {field_name} must be within [0.0, 1.0]")
    return numeric


def _parse_optional_bool(value: str, field_name: str, row_num: int) -> bool | None:
    trimmed = value.strip().lower()
    if not trimmed:
        return None
    if trimmed in {"true", "1", "yes"}:
        return True
    if trimmed in {"false", "0", "no"}:
        return False
    raise ValueError(f"Row {row_num}: {field_name} must be true/false when provided")


def _metadata_mismatch_reason(
    row: dict[str, str],
    case: dict[str, Any],
    row_num: int,
) -> list[str]:
    mismatches: list[str] = []

    row_kind = row.get("kind", "").strip()
    if row_kind:
        case_kind = str(case.get("kind", "")).strip()
        if case_kind and row_kind != case_kind:
            mismatches.append(
                f"Row {row_num}: kind mismatch (worksheet={row_kind}, golden_set={case_kind})"
            )

    row_category = row.get("category", "").strip()
    if row_category:
        case_category = str(case.get("category", "")).strip()
        if case_category and row_category != case_category:
            mismatches.append(
                f"Row {row_num}: category mismatch (worksheet={row_category}, golden_set={case_category})"
            )

    row_abstain = _parse_optional_bool(
        row.get("should_abstain_expected", ""),
        "should_abstain_expected",
        row_num,
    )
    if row_abstain is not None:
        case_abstain = case.get("should_abstain")
        if isinstance(case_abstain, bool) and row_abstain != case_abstain:
            mismatches.append(
                f"Row {row_num}: should_abstain mismatch (worksheet={row_abstain}, golden_set={case_abstain})"
            )

    return mismatches


def _read_worksheet(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError("Worksheet must include CSV header row")

        required_columns = {"case_id", *WORKSHEET_SCORE_FIELDS.keys()}
        missing = sorted(required_columns.difference(set(reader.fieldnames)))
        if missing:
            raise ValueError("Worksheet missing required columns: " + ", ".join(missing))

        return [dict(row) for row in reader]


def main() -> int:
    args = _parse_args()

    worksheet_path = _resolve_path(args.worksheet)
    golden_set_path = _resolve_path(args.golden_set)
    output_path = _resolve_path(args.output) if args.output else golden_set_path

    golden_payload, cases_by_id = _load_golden_set(golden_set_path)
    worksheet_rows = _read_worksheet(worksheet_path)

    seen_case_ids: set[str] = set()
    unknown_case_ids: list[str] = []
    metadata_warnings: list[str] = []
    updates_applied = 0
    cases_touched = 0
    rows_with_scores = 0

    for row_num, row in enumerate(worksheet_rows, start=2):
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            continue
        if case_id in seen_case_ids:
            raise ValueError(f"Worksheet has duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)

        case = cases_by_id.get(case_id)
        if case is None:
            unknown_case_ids.append(case_id)
            continue

        metadata_mismatches = _metadata_mismatch_reason(row, case, row_num)
        metadata_warnings.extend(metadata_mismatches)

        parsed_scores: dict[str, float] = {}
        for worksheet_field, target_field in WORKSHEET_SCORE_FIELDS.items():
            value = _parse_optional_float(row.get(worksheet_field, ""), worksheet_field, row_num)
            if value is not None:
                parsed_scores[target_field] = value

        if not parsed_scores:
            continue

        if not args.allow_partial and len(parsed_scores) != len(WORKSHEET_SCORE_FIELDS):
            raise ValueError(
                f"Row {row_num}: partial reviewer scores found for case {case_id}. "
                "Provide both reviewer_faithfulness and reviewer_answer_correctness, "
                "or pass --allow-partial."
            )

        rows_with_scores += 1
        human_scores = case.get("human_scores")
        if not isinstance(human_scores, dict):
            human_scores = {}
            case["human_scores"] = human_scores

        changed_this_case = False
        for target_field, new_value in parsed_scores.items():
            old_value = human_scores.get(target_field)
            if old_value != new_value:
                human_scores[target_field] = new_value
                updates_applied += 1
                changed_this_case = True

        if changed_this_case:
            cases_touched += 1

    if unknown_case_ids and args.strict:
        raise ValueError(
            "Worksheet includes unknown case IDs: " + ", ".join(sorted(unknown_case_ids))
        )
    if metadata_warnings and args.strict:
        raise ValueError("Metadata mismatch detected in strict mode:\n" + "\n".join(metadata_warnings))

    print(f"Worksheet rows: {len(worksheet_rows)}")
    print(f"Rows with reviewer scores: {rows_with_scores}")
    print(f"Cases updated: {cases_touched}")
    print(f"Score fields updated: {updates_applied}")

    if unknown_case_ids:
        print("Warning: unknown case IDs skipped: " + ", ".join(sorted(unknown_case_ids)))
    if metadata_warnings:
        print("Warning: metadata mismatches:")
        for warning in metadata_warnings:
            print(f"- {warning}")

    if not args.apply:
        print("Dry-run mode: no files written. Use --apply to persist changes.")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path == golden_set_path and output_path.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = output_path.with_name(f"{output_path.stem}.backup_{ts}{output_path.suffix}")
        backup_path.write_text(golden_set_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup created: {backup_path}")

    output_path.write_text(json.dumps(golden_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Golden set updated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
