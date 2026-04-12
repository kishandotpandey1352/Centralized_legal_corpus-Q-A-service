# Day 8 README: Evaluation Automation and Regression Gates

This document tracks everything for Day 8: what is implemented, how to run it, what outputs to expect, and what remains.

## Day 8 Goal
Build a repeatable evaluation workflow that can:
1. Run a golden-case suite against live API endpoints.
2. Compute challenger metrics.
3. Score with `POST /eval/score`.
4. Compare with baseline using `POST /eval/compare`.
5. Fail fast on regression gates for CI usage.

## What Was Implemented

### 1. Day 8 checklist in project docs
A Day 8 checklist section was added to the project README to guide execution and tracking.

### 2. Evaluation runner skeleton
Script created at:
- `backend/scripts/eval_runner.py`

Runner responsibilities:
- Load cases from a golden set JSON file.
- Validate case format (`answer` and `summary` case kinds).
- Call:
  - `POST /query/answer`
  - `POST /query/summary`
- Capture per-case details:
  - latency
  - mode
  - used chunks
  - citations
  - invalid citation count
  - abstention behavior
  - HTTP error details (if any)
- Compute proxy challenger metrics.
- Call `POST /eval/score` with challenger metrics.
- Optionally call `POST /eval/compare` using a baseline metrics file.
- Write run artifacts to `mvp/experiments/`:
  - `run_YYYYMMDD_HHMMSS.json`
  - `run_YYYYMMDD_HHMMSS.md`
- Exit with code `1` if compare winner is not `challenger`.

### 3. Golden set template
Template created at:
- `mvp/golden_set_template.json`

Current set size and coverage:
- 24 labeled cases total
- Direct lookup coverage
- Multi-chunk synthesis coverage
- Abstention / insufficient-evidence coverage
- Citation-sensitivity coverage
- Improved summary coverage with multiple `max_chunks` variants

Stronger labels now included per case:
- `should_abstain`
- `expected_mode`
- `min_citations`
- `require_valid_citations`
- `expected_contains_any`
- `expected_not_contains_any`
- `human_scores` (`faithfulness`, `answer_correctness`)

Reviewer worksheet for consistent score updates:
- `mvp/human_scores_reviewer_worksheet.csv`
- Fill `reviewer_faithfulness` and `reviewer_answer_correctness` with values in `[0.0, 1.0]`.
- Keep one row per `case_id` and add rationale in `reviewer_notes`.

### 4. Baseline metrics template
Template created at:
- `mvp/experiments/baseline_metrics.json`

Contains required Day 7 metric fields:
- `faithfulness`
- `answer_correctness`
- `retrieval_recall_at_5`
- `abstention_accuracy`
- `hallucination_rate`
- `invalid_citation_rate`
- `latency_p95_ms`

### 5. Naming cleanup completed
To keep names neutral:
- `backend/scripts/day8_eval_runner.py` -> `backend/scripts/eval_runner.py`
- `mvp/day8_golden_set_template.json` -> `mvp/golden_set_template.json`

## How To Run Day 8 Workflow
From `backend/`:

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json
```

Optional flags:
- `--api-base-url http://localhost:8000`
- `--output-dir <custom path>`
- `--timeout-seconds 90`
- `--offline` for deterministic local simulation when API is unavailable

Repeat-run command used to accumulate artifacts:

```bat
python scripts\eval_runner.py --offline --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json
python scripts\eval_runner.py --offline --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json
```

## Day 8 Command Cookbook

### 1. API health check (PowerShell)
From project root:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8000/health | ConvertTo-Json -Depth 4
```

### 2. Ingest sample docs before evaluation (PowerShell)
From project root:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/ingest/sample-docs | ConvertTo-Json -Depth 6
```

### 3. Run full Day 8 suite against live API (with baseline compare)
From `backend/`:

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json
```

### 4. Run full Day 8 suite in offline deterministic mode
From `backend/`:

```bat
python scripts\eval_runner.py --offline --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json
```

### 5. Repeat runs to accumulate artifacts
From `backend/` (PowerShell loop):

```powershell
1..3 | ForEach-Object { .venv\Scripts\python.exe scripts\eval_runner.py --offline --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json }
```

### 6. Run without baseline comparison (metrics + score only)
From `backend/`:

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json
```

### 7. Run with custom timeout and output directory
From `backend/`:

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json --timeout-seconds 30 --output-dir ..\mvp\experiments
```

### 8. Run targeted test cases only (create mini golden set)
From `backend/` (PowerShell):

```powershell
@'
{
  "cases": [
    {
      "id": "A1-mini",
      "kind": "answer",
      "category": "direct_lookup",
      "question": "What is the cure period for material breach?",
      "top_k": 3,
      "should_abstain": false,
      "expected_mode": "evidence-direct",
      "min_citations": 1,
      "require_valid_citations": true,
      "expected_contains_any": ["cure", "breach"],
      "expected_not_contains_any": ["Insufficient evidence"],
      "human_scores": {"faithfulness": 0.9, "answer_correctness": 0.9},
      "notes": "Mini direct lookup check"
    },
    {
      "id": "S1-mini",
      "kind": "summary",
      "category": "summary_grounded",
      "source_file": "sample_service_agreement.txt",
      "max_chunks": 4,
      "should_abstain": false,
      "expected_mode": "llm-summary",
      "min_citations": 1,
      "require_valid_citations": true,
      "expected_contains_any": ["[C1]"],
      "expected_not_contains_any": ["Insufficient evidence"],
      "human_scores": {"faithfulness": 0.88, "answer_correctness": 0.84},
      "notes": "Mini summary check"
    }
  ]
}
'@ | Set-Content -Path ..\mvp\golden_set_mini.json

.venv\Scripts\python.exe scripts\eval_runner.py --cases ..\mvp\golden_set_mini.json --baseline ..\mvp\experiments\baseline_metrics.json
```

### 9. Verify artifacts generated
From project root (PowerShell):

```powershell
Get-ChildItem .\mvp\experiments\run_*.json | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
Get-ChildItem .\mvp\experiments\run_*.md | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
```

### 10. Quick check latest run summary
From project root (PowerShell):

```powershell
$latest = Get-ChildItem .\mvp\experiments\run_*.md | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $latest.FullName
```

## Expected Outputs
Saved in `mvp/experiments/`:
- JSON run artifact: `run_*.json`
- Markdown run summary: `run_*.md`

Run behavior:
- If baseline compare is provided and winner is not `challenger`, script exits non-zero for CI gating.
- Baseline compare is consistently run against `mvp/experiments/baseline_metrics.json` in Day 8 runs.

## Golden Set Case Schema
Each case supports:

### Answer case
```json
{
  "id": "A1",
  "kind": "answer",
  "question": "What is the cure period for material breach?",
  "top_k": 3,
  "should_abstain": false,
  "notes": "Direct factual lookup"
}
```

### Summary case
```json
{
  "id": "S1",
  "kind": "summary",
  "source_file": "sample_service_agreement.txt",
  "max_chunks": 6,
  "should_abstain": false,
  "notes": "Grounded summary sanity check"
}
```

## Day 8 Remaining Plan
1. Continue refining case prompts and labels against live API behavior (not only offline simulation).
2. Replace remaining proxy-only components with more human-graded judgments.
3. Add reviewer workflow for periodic updates to `human_scores`.
4. Track metric trend quality across runs, not only pass/fail gate outcomes.

## Day 8 Execution Log
Recent repeat runs created artifacts in `mvp/experiments/`:
- `run_20260412_142649_945398.json`
- `run_20260412_142649_945398.md`
- `run_20260412_142656_682701.json`
- `run_20260412_142656_682701.md`

Validated per-run logging fields:
- case-level latency (`latency_ms`)
- mode (`mode`)
- citation counts and validity (`citation_count`, `invalid_citation_count`)
- abstention behavior (`checks.abstention_match`, plus aggregate abstention accuracy)

## Day 8 Definition Of Done
1. One command runs the full suite and produces artifacts.
2. Challenger metrics are scored and compared against baseline.
3. Regression gate behavior works for CI.
4. Golden set has enough coverage to detect quality shifts.
