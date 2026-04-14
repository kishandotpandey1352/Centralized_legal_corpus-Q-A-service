# RAG Legal Project

Day 1 setup is complete for the backend skeleton, dependencies, local pgvector database, and one sample legal file.

## Project Layout
- `backend/` FastAPI service skeleton
- `infra/` Docker resources for PostgreSQL + pgvector
- `data/sample_docs/` initial legal test document
- `mvp/` planning and evaluation templates

## Day 1 Quick Start

### 1. Start PostgreSQL with pgvector
From project root:

```bat
cd infra
docker compose up -d
```

### 2. Setup backend virtual environment
From project root:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### 3. Configure environment
From `backend/`, copy `.env.example` to `.env`.

```bat
copy .env.example .env
```

### 4. Run API
From `backend/`:

```bat
uvicorn app.main:app --reload --port 8000
```

### 5. Verify health
Open in browser or curl:
- `http://localhost:8000/`
- `http://localhost:8000/health`

### 6. Run Day 2 sample ingestion
From `backend/`:

```bat
curl -X POST http://localhost:8000/ingest/sample-docs
```

Expected response includes:
- `documents_ingested`
- `chunks_ingested`
- `files`

### 7. Run Day 3 retrieval
From `backend/`:

```bat
echo {"query":"What is the cure period for material breach?","top_k":2} > retrieve_payload.json
curl -X POST http://localhost:8000/query/retrieve -H "Content-Type: application/json" --data-binary @retrieve_payload.json
del retrieve_payload.json
```

Expected response includes:
- `query`
- `top_k`
- `results` (with `source_file`, `chunk_text`, and `score`)

## What is included today
- FastAPI app with root and health routes
- Python dependency manifest
- PostgreSQL + pgvector docker compose
- SQL init script with `documents` and `chunks` tables
- One sample legal agreement text file

## Day 2 target
Implement the first ingest path:
1. Read file from `data/sample_docs/`
2. Parse and normalize text
3. Chunk with metadata
4. Insert chunk rows into PostgreSQL

## Post command test:
curl -s -X POST http://127.0.0.1:8000/ingest/sample-docs | python -m json.tool


## output:
{
    "sample_docs_path": "C:\\Users\\kisha\\projects\\RAG_legal\\data\\sample_docs",
    "documents_ingested": 1,
    "chunks_ingested": 2,
    "files": [
        "sample_service_agreement.txt"
    ]
}

## Day 3 status
Implemented:
1. Embedding generation during ingestion
2. Embedding persistence to `chunks.embedding` (pgvector)
3. Retrieval endpoint `POST /query/retrieve` with top-k results and chunk citations

Notes:
- External embeddings are enabled with `EMBEDDING_BACKEND=sentence-transformers`.
- The configured model is `BAAI/bge-m3`.
- Model files are stored in project cache path `backend/.model_cache/sentence-transformers`.

## Day 4 setup (external open-source LLM)

### 1. Install and run Ollama
Start Ollama and pull the configured model:

```bat
ollama pull qwen2.5:7b-instruct
ollama list
```

### 2. Configure generation in backend env
From `backend/.env`, keep these values:

```env
OLLAMA_BASE_URL=http://localhost:11434
GENERATION_BACKEND=ollama
GENERATION_MODEL=qwen2.5:7b-instruct
GENERATION_STRICT=true
```

`GENERATION_STRICT=true` means `/query/answer` will fail with an error if Ollama/model is unavailable, instead of silently falling back.

### 3. Ask grounded questions with citations

```bat
echo {"question":"What is the cure period for material breach?","top_k":2} > answer_payload.json
curl -X POST http://localhost:8000/query/answer -H "Content-Type: application/json" --data-binary @answer_payload.json
del answer_payload.json
```

## Day 5 setup (document summary endpoint)

### 1. Generate a grounded summary for one document

```bat
echo {"source_file":"sample_service_agreement.txt","max_chunks":6} > summary_payload.json
curl -X POST http://localhost:8000/query/summary -H "Content-Type: application/json" --data-binary @summary_payload.json
del summary_payload.json
```

Expected response includes:
- `source_file`
- `summary`
- `citations`
- `used_chunks`
- `mode`

## Day 6 status (summary generation hardening)

Implemented:
1. Summary post-processing that removes incomplete trailing fragments and ensures the text ends with proper punctuation.
2. Summary-specific formatting cleanup so output is prose-style (no leading `-` bullet prefixes).
3. Non-null summary citation scores (`score: 1.0`) for source-file grounded summary chunks.

Summary generation logic:
1. `POST /query/summary` loads chunks by exact `source_file` and `chunk_index` order.
2. Context chunks are converted to citation objects (`C1`, `C2`, ...).
3. LLM prompt is built with grounded chunk context and citation IDs.
4. If LLM call succeeds: mode is `llm-summary`.
5. If strict mode is disabled and LLM fails: deterministic fallback summary is returned with citations.
6. Final summary text is polished using summary-specific cleanup before response serialization.

Day 6 problems encountered and fixes:
1. Problem: summary ended abruptly (for example trailing fragment like `- Con [C1] [C2]`).
2. Root cause: generic answer cleaner was reused for summaries and did not handle summary-tail fragments well.
3. Fix: introduced a dedicated summary polishing path that trims incomplete tails, normalizes punctuation, and preserves citations.

4. Problem: summary citation `score` appeared as `null`.
5. Root cause: summary uses source-file selection (not vector similarity), so score field was left unset.
6. Fix: set summary citation score to `1.0` to represent exact source-file grounded selection.

7. Problem: summary output returned as hyphen-prefixed list (`- ... - ...`).
8. Root cause: LLM frequently emitted bullet-style format.
9. Fix: summary polisher now removes bullet prefixes and returns a clean prose paragraph while keeping citations.

10. Problem: live API sometimes still returned old formatting after code update.
11. Root cause: running `uvicorn` process had stale code loaded.
12. Fix: restart backend server after updates (`uvicorn app.main:app --reload --port 8000`).

## Day 7 status (evaluation and experiment scoring)

Implemented:
1. Evaluation scoring endpoint `POST /eval/score` using rubric metrics from `mvp/scoring_rubric.md`.
2. Experiment comparison endpoint `POST /eval/compare` using improvement and gate-regression rules.
3. Pass/fail gate checks and latency penalty logic included in API response.

Day 7 evaluation logic:
1. Input metrics: `faithfulness`, `answer_correctness`, `retrieval_recall_at_5`, `abstention_accuracy`, `hallucination_rate`, `invalid_citation_rate`, `latency_p95_ms`.
2. `overall_score` formula:
    - `0.40*faithfulness + 0.30*answer_correctness + 0.20*retrieval_recall_at_5 + 0.10*abstention_accuracy - 0.10*hallucination_rate - 0.05*invalid_citation_rate - latency_penalty`
3. Latency penalty:
    - `0.00` if `latency_p95_ms <= 3000`
    - `0.02` if `3000 < latency_p95_ms <= 5000`
    - `0.05` if `latency_p95_ms > 5000`
4. Pass/fail gates:
    - `faithfulness >= 0.75`
    - `answer_correctness >= 0.70`
    - `retrieval_recall_at_5 >= 0.65`
    - `hallucination_rate <= 0.12`
    - `invalid_citation_rate <= 0.10`
    - `latency_p95_ms <= 5000`
5. Compare decision rule:
    - Challenger wins if `overall_score` improves by at least `0.02` and no pass gate regresses from pass to fail.
    - If score delta is within `0.02`, lower latency and lower hallucination are used as tie-breakers.

Run Day 7 scoring (from `backend/`):

```bat
echo {"faithfulness":0.79,"answer_correctness":0.75,"retrieval_recall_at_5":0.72,"abstention_accuracy":0.86,"hallucination_rate":0.09,"invalid_citation_rate":0.07,"latency_p95_ms":3200} > eval_score_payload.json
curl -X POST http://localhost:8000/eval/score -H "Content-Type: application/json" --data-binary @eval_score_payload.json
del eval_score_payload.json
```

Run Day 7 experiment comparison (from `backend/`):

```bat
echo {"baseline":{"faithfulness":0.78,"answer_correctness":0.73,"retrieval_recall_at_5":0.70,"abstention_accuracy":0.84,"hallucination_rate":0.10,"invalid_citation_rate":0.08,"latency_p95_ms":3400},"challenger":{"faithfulness":0.81,"answer_correctness":0.76,"retrieval_recall_at_5":0.73,"abstention_accuracy":0.86,"hallucination_rate":0.08,"invalid_citation_rate":0.06,"latency_p95_ms":3200}} > eval_compare_payload.json
curl -X POST http://localhost:8000/eval/compare -H "Content-Type: application/json" --data-binary @eval_compare_payload.json
del eval_compare_payload.json
```

Day 7 problems encountered and fixes:
1. Problem: score interpretations differed between runs.
2. Root cause: formula and pass/fail gates were applied manually and inconsistently.
3. Fix: centralized formula, latency penalty, and gates into one reusable evaluation module and API endpoints.

4. Problem: comparison decisions were ambiguous for close runs.
5. Root cause: no deterministic tie-break behavior for near-equal scores.
6. Fix: implemented explicit tie-break rules using lower latency and lower hallucination.

## Day 8 checklist (evaluation automation and regression gates)

- [ ] Create a golden evaluation set at `mvp/golden_set_template.json` with at least 20 cases.
- [ ] Cover four case categories: direct lookup, multi-chunk synthesis, abstention/insufficient-evidence, and citation-sensitivity checks.
- [ ] Label each case with `kind` (`answer` or `summary`) and `should_abstain` where applicable.
- [ ] Run the new runner script against the live API and save artifacts to `mvp/experiments/`.
- [ ] Verify each run records: per-case latency, mode, citations, and abstention behavior.
- [ ] Compute challenger metrics and score via `POST /eval/score`.
- [ ] Compare challenger against a baseline metric set via `POST /eval/compare`.
- [ ] Gate regressions: fail the run when compare winner is not `challenger`.
- [ ] Add one markdown run summary for human review and one JSON artifact for machine use.
- [ ] Re-run once after any prompt/threshold/config changes and append the new run artifact.

Run Day 8 runner skeleton (from `backend/`):

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json
```

Outputs:
- JSON run report under `mvp/experiments/run_*.json`
- Markdown summary under `mvp/experiments/run_*.md`
- Exit code `1` when regression gate fails (for CI use)

## Day 9 status (live-run stability + smoke suite + baseline promotion)

Implemented:
1. Runner stability controls in `backend/scripts/eval_runner.py`:
    - `--answer-timeout-seconds`
    - `--summary-timeout-seconds`
    - `--max-retries`
2. Fast smoke evaluation suite in `mvp/golden_set_smoke.json`.
3. Full evaluation suite in `mvp/golden_set_template.json`.
4. Baseline promotion helper in `backend/scripts/promote_baseline.py`.
5. Repeated-run orchestrator in `backend/scripts/eval_series.py` for variance-aware confidence checks.
6. CI workflow in `.github/workflows/eval-gates.yml` for automated smoke/full gates and promotion-policy validation.

### Why CI pipeline was implemented

The CI pipeline was added to make evaluation decisions reliable and repeatable:
1. Prevent manual mistakes and inconsistent promotion decisions.
2. Detect quality regressions early (before merging/deploying).
3. Measure run-to-run variance instead of trusting a single run.
4. Enforce Day 9 policy gates automatically (winner/regression/pass checks).

### How CI pipeline is implemented

Workflow file:
- `.github/workflows/eval-gates.yml`

Execution flow:
1. Install backend dependencies.
2. Run repeated smoke evaluations with strict thresholds.
3. Run repeated full evaluations with stricter thresholds.
4. Find latest full run artifact.
5. Validate promotion policy in non-destructive mode using `--check-only`.
6. Upload run artifacts for audit/review.

### What the CI pipeline is used for

Use this pipeline as an automatic release gate:
1. Confirms challenger quality is stable across repeated runs.
2. Confirms pass/fail gates are not regressing.
3. Ensures baseline promotion policy is met before any manual promotion step.
4. Produces artifacts (`run_*.json`, `run_*.md`, `series_latest.json`) for auditability.

Run Day 9 smoke suite (from `backend/`):

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_smoke.json --baseline ..\mvp\experiments\baseline_metrics.json --answer-timeout-seconds 20 --summary-timeout-seconds 40 --max-retries 1
```

Run Day 9 full suite with separate answer/summary timeouts (from `backend/`):

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json --answer-timeout-seconds 25 --summary-timeout-seconds 90 --max-retries 2
```

Promote challenger to baseline after compare checks pass (from `backend/`):

```bat
python scripts\promote_baseline.py --run-json ..\mvp\experiments\run_20260412_142535_167754.json
```

Optional promotion flags:
- `--allow-offline` to permit promotion from offline-local runs.
- `--force` to bypass policy checks (not recommended).

Recommended promotion flow (smoke -> full -> promote):

```bat
REM 1) Fast smoke validation
python scripts\eval_runner.py --cases ..\mvp\golden_set_smoke.json --baseline ..\mvp\experiments\baseline_metrics.json --answer-timeout-seconds 20 --summary-timeout-seconds 40 --max-retries 1

REM 2) Full evaluation validation
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json --answer-timeout-seconds 25 --summary-timeout-seconds 90 --max-retries 2

REM 3) Promote only after full run passes and challenger wins
python scripts\promote_baseline.py --run-json ..\mvp\experiments\run_YYYYMMDD_HHMMSS_xxxxxx.json
```

### Repeated live runs (variance confidence)

Run repeated smoke evaluations and require a minimum challenger win/pass rate:

```bat
python scripts\eval_series.py --api-base-url http://localhost:8000 --cases ..\mvp\golden_set_smoke.json --baseline ..\mvp\experiments\baseline_metrics.json --runs 5 --answer-timeout-seconds 20 --summary-timeout-seconds 40 --max-retries 1 --stop-on-failure --require-winner-rate 0.60 --require-passing-rate 1.00
```

Run repeated full evaluations:

```bat
python scripts\eval_series.py --api-base-url http://localhost:8000 --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json --runs 3 --answer-timeout-seconds 25 --summary-timeout-seconds 90 --max-retries 2 --stop-on-failure --require-winner-rate 0.70 --require-passing-rate 1.00
```

The series command writes an aggregate report to:
- `mvp/experiments/series_latest.json`

### CI automation (smoke/full + promotion policy)

GitHub Actions workflow:
- `.github/workflows/eval-gates.yml`

What it does:
1. Repeats smoke runs with winner/pass thresholds.
2. Repeats full runs with winner/pass thresholds.
3. Locates latest full run artifact.
4. Enforces promotion policy in non-destructive mode via:

```bat
python scripts\promote_baseline.py --run-json <latest_run_json> --check-only
```

Policy check validates winner/regression/pass criteria without modifying baseline metrics.

Current strict CI thresholds:
1. Smoke: `winner_rate >= 0.60`, `passing_rate = 1.00`, fail-fast enabled.
2. Full: `winner_rate >= 0.70`, `passing_rate = 1.00`, fail-fast enabled.

## Day 10 status (live-run stability hardening)

Implemented:
1. Retry behavior hardening in `backend/scripts/eval_runner.py`:
    - Retry only transient transport failures and retryable HTTP status codes (`429`, `500`, `502`, `503`, `504`).
    - Exponential retry backoff controls.
2. Separate runtime controls for answer vs summary runs:
    - `--answer-timeout-seconds`, `--summary-timeout-seconds`
    - `--answer-max-retries`, `--summary-max-retries`
3. Structured HTTP timeout controls:
    - `--connect-timeout-seconds`, `--read-timeout-seconds`, `--write-timeout-seconds`, `--pool-timeout-seconds`
4. Runtime-control snapshot persisted in each run artifact under `runtime_controls` for debugging and reproducibility.

Run Day 10 hardened smoke validation (from `backend/`):

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_smoke.json --baseline ..\mvp\experiments\baseline_metrics.json --answer-timeout-seconds 20 --summary-timeout-seconds 45 --answer-max-retries 2 --summary-max-retries 1 --connect-timeout-seconds 5 --read-timeout-seconds 45 --write-timeout-seconds 10 --pool-timeout-seconds 10 --retry-backoff-seconds 0.5 --retry-backoff-multiplier 2.0 --max-retry-backoff-seconds 4
```

Run Day 10 hardened full validation (from `backend/`):

```bat
python scripts\eval_runner.py --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json --answer-timeout-seconds 25 --summary-timeout-seconds 90 --answer-max-retries 2 --summary-max-retries 2 --connect-timeout-seconds 5 --read-timeout-seconds 90 --write-timeout-seconds 15 --pool-timeout-seconds 15 --retry-backoff-seconds 0.5 --retry-backoff-multiplier 2.0 --max-retry-backoff-seconds 5
```

Run repeated Day 10 stability series (from `backend/`):

```bat
python scripts\eval_series.py --api-base-url http://localhost:8000 --cases ..\mvp\golden_set_smoke.json --baseline ..\mvp\experiments\baseline_metrics.json --runs 5 --answer-timeout-seconds 20 --summary-timeout-seconds 45 --answer-max-retries 2 --summary-max-retries 1 --connect-timeout-seconds 5 --read-timeout-seconds 45 --write-timeout-seconds 10 --pool-timeout-seconds 10 --retry-backoff-seconds 0.5 --retry-backoff-multiplier 2.0 --max-retry-backoff-seconds 4 --stop-on-failure --require-winner-rate 0.60 --require-passing-rate 1.00
```

## Day 11 status (smoke vs full evaluation suites)

Implemented:
1. Fast PR smoke suite in `.github/workflows/eval-gates.yml`:
    - Trigger: `pull_request` (main/develop, scoped paths)
    - Runs smoke-only repeated checks
    - Stores artifacts under `mvp/experiments/pr_smoke`
2. Full nightly suite in `.github/workflows/eval-gates.yml`:
    - Trigger: nightly `schedule` (`0 2 * * *`)
    - Runs full repeated checks
    - Enforces promotion policy in non-destructive mode (`--check-only`)
    - Stores artifacts under `mvp/experiments/nightly_full`
3. Manual dispatch now supports suite selection:
    - `suite=smoke` | `suite=full` | `suite=both`

Why this split helps:
1. PR feedback remains fast and practical (smoke coverage).
2. Nightly run keeps deep coverage without slowing developer iteration.
3. Promotion-policy checks stay tied to full-suite evidence.

How to run equivalent local checks:

Fast smoke (PR-like):

```bat
python scripts\eval_series.py --api-base-url http://localhost:8000 --cases ..\mvp\golden_set_smoke.json --baseline ..\mvp\experiments\baseline_metrics.json --output-dir ..\mvp\experiments\pr_smoke --runs 2 --answer-timeout-seconds 20 --summary-timeout-seconds 40 --max-retries 1 --stop-on-failure --require-winner-rate 0.60 --require-passing-rate 1.00
```

Full nightly-like:

```bat
python scripts\eval_series.py --api-base-url http://localhost:8000 --cases ..\mvp\golden_set_template.json --baseline ..\mvp\experiments\baseline_metrics.json --output-dir ..\mvp\experiments\nightly_full --runs 2 --answer-timeout-seconds 25 --summary-timeout-seconds 90 --max-retries 2 --stop-on-failure --require-winner-rate 0.70 --require-passing-rate 1.00
```

Nightly promotion-policy validation (non-destructive):

```bat
python scripts\promote_baseline.py --run-json ..\mvp\experiments\nightly_full\run_YYYYMMDD_HHMMSS_xxxxxx.json --check-only
```

## Day 12 status (baseline promotion workflow)

Implemented:
1. Strict promotion criteria in `backend/scripts/promote_baseline.py`:
    - Candidate run must pass normal promotion policy (`winner=challenger`, `has_gate_regression=false`, `pass_fail=pass`).
    - Require consecutive live runs (`eval_source=api`) with no gate regression.
    - Selected run must be the latest run artifact in the checked run directory.
2. CI automation updated in `.github/workflows/eval-gates.yml`:
    - Nightly full-suite policy check now enforces `--require-consecutive-live-runs 2` on `mvp/experiments/nightly_full`.

Day 12 strict promotion criteria (default strict mode):
1. Run-level policy pass for candidate run.
2. Consecutive live runs requirement is met.
3. Every run in required streak has:
    - `eval_source=api`
    - `compare.winner=challenger`
    - `compare.has_gate_regression=false`
    - `score.pass_fail=pass`

Validate policy without updating baseline (recommended first):

```bat
python scripts\promote_baseline.py --run-json ..\mvp\experiments\nightly_full\run_YYYYMMDD_HHMMSS_xxxxxx.json --runs-dir ..\mvp\experiments\nightly_full --require-consecutive-live-runs 2 --check-only
```

Promote baseline only after policy check passes:

```bat
python scripts\promote_baseline.py --run-json ..\mvp\experiments\nightly_full\run_YYYYMMDD_HHMMSS_xxxxxx.json --runs-dir ..\mvp\experiments\nightly_full --require-consecutive-live-runs 2
```

Optional override flags:
1. `--allow-offline` to allow offline run source (not recommended for strict live policy).
2. `--force` to bypass checks (emergency use only).

## Day 13 status (reviewer score sync automation)

Implemented:
1. Safe sync script `backend/scripts/sync_reviewer_scores.py` to import reviewer worksheet scores into golden set.
2. Validation safeguards:
    - case ID matching against golden set
    - duplicate worksheet case ID detection
    - numeric score validation in range `[0.0, 1.0]`
    - optional strict mode for unknown IDs and metadata mismatches
3. Safety controls:
    - default dry-run mode (no writes)
    - explicit `--apply` required for file updates
    - automatic backup when updating in place

Worksheet source:
- `mvp/human_scores_reviewer_worksheet.csv`

Golden set target:
- `mvp/golden_set_template.json`

Run Day 13 sync dry-run (recommended first):

```bat
python scripts\sync_reviewer_scores.py --worksheet ..\mvp\human_scores_reviewer_worksheet.csv --golden-set ..\mvp\golden_set_template.json
```

Apply Day 13 sync in place (with automatic backup):

```bat
python scripts\sync_reviewer_scores.py --worksheet ..\mvp\human_scores_reviewer_worksheet.csv --golden-set ..\mvp\golden_set_template.json --apply
```

Strict policy sync (fail on unknown IDs/metadata mismatch):

```bat
python scripts\sync_reviewer_scores.py --worksheet ..\mvp\human_scores_reviewer_worksheet.csv --golden-set ..\mvp\golden_set_template.json --strict --apply
```

Optional flags:
1. `--allow-partial` to allow updating only one reviewer score field in a row.
2. `--output <path>` to write to a separate JSON file instead of in-place update.

## External embedding model setup (download + usage)

### 1. Configure environment
From `backend/.env`, keep these values:

```env
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_CACHE_DIR=backend/.model_cache/sentence-transformers
```

### 2. Download model into project folder
From project root:

```bat
cd backend
.venv\Scripts\activate.bat
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', cache_folder='C:/Users/kisha/projects/RAG_legal/backend/.model_cache/sentence-transformers'); print('model-ready')"
```

Wait for `model-ready` before closing terminal.

### 3. Verify model files exist

```bat
dir C:\Users\kisha\projects\RAG_legal\backend\.model_cache\sentence-transformers\models--BAAI--bge-m3\snapshots
```

### 4. Re-embed chunks using external model
Restart API (if already running), then run ingestion again:

```bat
curl -X POST http://localhost:8000/ingest/sample-docs
```

### 5. Test retrieval

```bat
echo {"query":"What is the cure period for material breach?","top_k":2} > retrieve_payload.json
curl -X POST http://localhost:8000/query/retrieve -H "Content-Type: application/json" --data-binary @retrieve_payload.json
del retrieve_payload.json
```

## More query examples (cmd)

### Answer example: material breach

```bat
echo {"question":"In the ingested legal documents, what is the cure period before termination for material breach?","top_k":3} > answer_payload.json
curl -X POST http://localhost:8000/query/answer -H "Content-Type: application/json" --data-binary @answer_payload.json
del answer_payload.json
```

### Retrieval example: Time Extension Request

```bat
echo {"query":"Which document discusses Time Extension Request and what is being requested?","top_k":3} > retrieve_payload.json
curl -X POST http://localhost:8000/query/retrieve -H "Content-Type: application/json" --data-binary @retrieve_payload.json
del retrieve_payload.json
```

### Answer example: Texas case issue

```bat
echo {"question":"What legal issue is central in texas_department_of_public_safety_v._robert_christopher_callaway.pdf?","top_k":3} > answer_payload.json
curl -X POST http://localhost:8000/query/answer -H "Content-Type: application/json" --data-binary @answer_payload.json
del answer_payload.json
```

## Known issues and probable solutions

### 1. Sometimes answer says "Insufficient evidence" even when relevant text exists
- Why it happens: vector similarity can retrieve semantically nearby but not lexically grounded chunks.
- Solution implemented: calibrated confidence uses both vector score and lexical overlap (`top_score`, `raw_top_score`, `lexical_confidence`).
- Config knobs: `QA_MIN_RETRIEVAL_SCORE`, `QA_MIN_LEXICAL_OVERLAP`, `QA_DIRECT_ANSWER_MIN_OVERLAP`.

### 2. Answers can be truncated (broken sentence endings)
- Why it happens: PDF chunk boundaries can split sentences.
- Solution implemented: direct-answer mode prefers best full sentence and trims trailing incomplete fragments.
- Additional mitigation: adjacent chunk stitching for top result when generating evidence-direct answers.

### 3. Person/profile style questions may return quote fragments instead of concise summaries
- Why it happens: direct quote extraction can be too literal for "Tell me about X" prompts.
- Solution implemented: question-aware direct-answer formatting for person-style prompts using evidence-first summary with citations.

### 4. Wrong document can rank high for generic legal terms
- Why it happens: corpus contains mixed legal domains and shared terminology.
- Solution direction: add metadata filters (`source_file`, `document_type`) and optional reranking stage in future iteration.

## Response troubleshooting log (issues encountered + fixes applied)

### Quick tuning checklist

| Symptom | Env key to tune | Recommended value range | Effect |
|---|---|---|---|
| Too many `Insufficient evidence` responses | `QA_MIN_RETRIEVAL_SCORE` | `0.25` to `0.40` | Lower value makes answering easier; higher value is stricter. |
| Good vector hits but still low confidence | `QA_MIN_LEXICAL_OVERLAP` | `0.10` to `0.30` | Lower value tolerates weaker keyword overlap. |
| Direct evidence answers rarely trigger | `QA_DIRECT_ANSWER_MIN_OVERLAP` | `0.30` to `0.60` | Lower value triggers direct cited answers more often. |
| Forced keyword answer not triggering | `QA_FORCE_MIN_SCORE` | `0.35` to `0.55` | Lower value allows keyword force mode at lower confidence. |
| Need different forced trigger phrase | `QA_FORCE_KEYWORD` | Any domain phrase | Example: `material breach`, `time extension request`. |
| LLM errors should not block response | `GENERATION_STRICT` | `false` or `true` | `false` enables fallback response path; `true` fails fast on LLM errors. |
| LLM timing out on long context | `GENERATION_TIMEOUT_SECONDS` | `30` to `120` | Higher value allows slower model responses. |

### A. `curl` JSON parse errors in cmd
- Symptom: `json_invalid`, `Could not resolve host`, unmatched braces.
- Root cause: inline JSON quoting in Windows cmd breaks easily.
- Fix applied:
1. Use payload file pattern (`echo ... > payload.json` + `--data-binary @payload.json`).
2. Updated all README examples to use `echo/curl/del` command blocks.

### B. Dependency installation failed on Windows/Python 3.14
- Symptom: `pymupdf` metadata generation failed, Visual Studio not found.
- Root cause: pinned versions lacked compatible wheels for current Python version.
- Fix applied:
1. Upgraded pins in `backend/requirements.txt`:
2. `pymupdf` -> `1.27.2.2`
3. `psycopg[binary]` -> `3.3.3`
4. `tiktoken` -> `0.12.0`

### C. API startup failed due to env validation errors
- Symptom: Pydantic `extra_forbidden` for `OLLAMA_BASE_URL`, `EMBEDDING_MODEL`, `GENERATION_MODEL`.
- Root cause: `.env` keys not defined in `Settings` model.
- Fix applied:
1. Added missing fields in `backend/app/core/config.py`.
2. Added missing `backend/.env.example` file to match README setup.

### D. External embedding model not loading initially
- Symptom: model downloads interrupted, fallback behavior inconsistent.
- Root cause: large downloads and cache path transitions.
- Fix applied:
1. Configured explicit project cache path (`EMBEDDING_CACHE_DIR`).
2. Standardized embedding backend and model settings in `.env` and `.env.example`.
3. Added download/verify steps in README.

### E. Retrieval returned empty results with available rows
- Symptom: `results: []` even when chunks existed.
- Root cause: ANN/plan behavior on very small dataset.
- Fix applied:
1. Retrieval query tuning for reliable small-corpus behavior (`SET LOCAL` planner/ivfflat settings).

### F. Answers returned `Insufficient evidence` despite moderate vector score
- Symptom: answer refused while `raw_top_score` looked decent.
- Root cause: vector score alone was overconfident on semantically similar but lexically mismatched chunks.
- Fix applied:
1. Added lexical overlap confidence.
2. Added calibrated score fields in response:
3. `top_score` (calibrated), `raw_top_score`, `lexical_confidence`.
4. Added confidence gates via env thresholds.

### G. Truncated answer tails (for example ending with `where he`)
- Symptom: broken sentence endings in direct answers.
- Root cause: chunk boundaries and noisy PDF extraction text.
- Fix applied:
1. Added adjacent chunk stitching for top retrieved context.
2. Added sentence cleanup and final answer polish pass.
3. Added citation-preserving post-processing.

### H. Person-style questions produced quote fragments
- Symptom: weak framing for prompts like `Tell me about ...`.
- Root cause: literal sentence extraction without question intent shaping.
- Fix applied:
1. Added person-question formatting in direct answer path (`From the retrieved record, ... [C1]`).

### I. Tests not aligned with actual corpus/doc patterns
- Symptom: tests were mostly synthetic and did not reflect sample document set.
- Fix applied:
1. Updated prompt tests with corpus-style metadata/content.
2. Added corpus-based tests tied to files in `data/sample_docs`.
3. Added `/query/answer` integration test using TestClient and citation-structure assertions.

