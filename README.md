# Centralized Legal Corpus Q&A Service

An evidence-grounded legal-document RAG prototype built as a portfolio project for
technical review. The repository contains a FastAPI backend, an Angular workbench,
a PostgreSQL/pgvector persistence layer, and a repeatable evaluation harness.

> **Scope note:** This is a research and engineering prototype, not legal advice and
> not a production legal-services system.

## What is implemented now

- PDF, DOCX, and TXT ingestion from `data/sample_docs/`
- Text normalization, overlapping chunking, page metadata, and section metadata
- Configurable embeddings:
  - deterministic hashing for lightweight local development and tests
  - `sentence-transformers` with `BAAI/bge-m3` for the configured embedding path
- PostgreSQL + pgvector storage and cosine retrieval
- Optional metadata filters for `source_file` and `document_type`
- Candidate-pool retrieval followed by lexical/vector hybrid reranking
- Grounded answer generation through Ollama, with explicit confidence gates
- Deterministic evidence-direct answers and abstention when evidence is insufficient
- Citation integrity checks that remove unknown inline citation IDs
- Single-document summaries with citation-preserving fallback behavior
- Golden-set evaluation, repeated-run variance checks, trend reports, and promotion checks
- Angular screens for retrieval, answers, summaries, citations, and browser-local run history
- Backend unit/integration tests and Playwright end-to-end workflow coverage

## System architecture

```text
Angular workbench
        |
        v
FastAPI routes
  |       |       |
health  ingest  query/eval
          |       |
          v       v
     Parse/clean  Embed question
          |       |
       Chunk      |
          |       |
          +--> PostgreSQL + pgvector
                    |
             cosine candidate retrieval
                    |
          metadata filters + lexical/vector rerank
                    |
              grounded context assembly
                    |
           evidence-direct / abstain / Ollama
                    |
            citation integrity enforcement
```

### Request paths

| Capability | Endpoint | Behavior |
| --- | --- | --- |
| Health | `GET /health` | Returns a lightweight API health response. |
| Ingestion | `POST /ingest/sample-docs` | Replaces and re-indexes supported files in `data/sample_docs/`. |
| Retrieval | `POST /query/retrieve` | Returns ranked chunks and retrieval metadata. |
| Answer | `POST /query/answer` | Returns a grounded answer, citations, confidence fields, and mode. |
| Summary | `POST /query/summary` | Returns a cited single-document summary. |
| Scoring | `POST /eval/score` | Applies the evaluation rubric to supplied metrics. |
| Comparison | `POST /eval/compare` | Compares baseline and challenger metrics using gate regressions. |

The answer pipeline deliberately distinguishes these modes:

- `evidence-direct`: lexical overlap is strong enough to answer from retrieved evidence.
- `forced-cited`: a configured high-priority phrase is present above its score threshold.
- `low-confidence`: retrieved context is not sufficiently grounded, so the service abstains.
- `llm`: Ollama generated an answer that then passed citation post-processing.
- `fallback`: generation failed while non-strict generation was enabled.
- `no-context`: retrieval returned no usable chunks.

## Repository map

```text
backend/
  app/main.py                  FastAPI application entry point
  app/api/                     health, ingestion, retrieval, and evaluation routes
  app/ingestion/service.py     PDF/DOCX/TXT parsing, normalization, chunking, indexing
  app/retrieval/embeddings.py  hash and sentence-transformers embedding backends
  app/retrieval/service.py     retrieval, reranking, answering, summaries, citations
  app/evaluation/scoring.py    metric formula and pass/fail gates
  scripts/                     live evaluation, trends, and promotion checks
  tests/                       backend regression and integration tests
data/sample_docs/              small local corpus used by the demo and tests
frontend/                      Angular query/answer/summary workbench
infra/db/init/                 PostgreSQL/pgvector schema initialization
mvp/                           golden sets, rubric, and evaluation artifacts
docs/                          development notes
```

## Quick start (Windows)

### 1. Start PostgreSQL and pgvector

From the repository root:

```bat
docker compose -f infra\docker-compose.yml up -d postgres
```

The compose file exposes PostgreSQL on `localhost:5432` and initializes the schema
from `infra/db/init/001_init.sql`.

### 2. Configure the backend

```bat
copy backend\.env.example backend\.env
```

Set the database connection to the local Docker service:

```env
DATABASE_URL=postgresql+psycopg://legal_rag:<password>@localhost:5432/legal_rag
```

For a fast smoke test without downloading an embedding model, set:

```env
EMBEDDING_BACKEND=hash
GENERATION_STRICT=false
```

For the configured external embedding path, use:

```env
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_CACHE_DIR=backend/.model_cache/sentence-transformers
```

If using Ollama generation, ensure the configured model is available locally:

```bat
ollama pull qwen2.5:7b-instruct
```

### 3. Install backend dependencies and run the API

The backend package is imported from its own directory. Run Python and pytest
commands from `backend\`:

```bat
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal, ingest the sample corpus:

```bat
cd backend
.venv\Scripts\activate.bat
curl -X POST http://localhost:8000/ingest/sample-docs
```

### 4. Start the Angular workbench

```bat
cd frontend
npm install
npm start
```

Open `http://localhost:4200`. The Angular development proxy forwards API calls to
`http://localhost:8000`; see [frontend/README.md](frontend/README.md) for frontend
commands and the Playwright setup.

## Example API calls

Use a payload file in Windows Command Prompt to avoid JSON quoting issues:

```bat
echo {"question":"What is the cure period before termination for material breach?","top_k":3} > answer_payload.json
curl -X POST http://localhost:8000/query/answer -H "Content-Type: application/json" --data-binary @answer_payload.json
del answer_payload.json
```

Retrieval supports optional corpus filters:

```json
{
  "query": "material breach cure period",
  "top_k": 5,
  "source_file": "sample_service_agreement.txt",
  "document_type": "txt",
  "rerank": true,
  "candidate_pool_size": 20
}
```

## Evaluation evidence

The repository includes real evaluation artifacts under `mvp/experiments/`. Values
below are reported from those artifacts, not estimated for this README.

### Recorded baseline

Source: [`mvp/experiments/baseline_metrics.json`](mvp/experiments/baseline_metrics.json)

| Metric | Recorded value |
| --- | ---: |
| Faithfulness | 0.9163 |
| Answer correctness | 0.8962 |
| Retrieval recall@5 | 1.0 |
| Abstention accuracy | 0.75 |
| Hallucination rate | 0.0 |
| Invalid citation rate | 0.0 |
| Latency p95 | 2224 ms |

The evaluation implementation and thresholds are defined in
[`mvp/scoring_rubric.md`](mvp/scoring_rubric.md). The recorded trend report also
contains runs with failures and should be read alongside the baseline rather than
treated as a production benchmark.

The latest checked-in release-readiness report records `release_ready: False`,
with `winner_rate: 0.0`, `passing_rate: 0.0`, and mean p95 latency of `88091 ms`.
Those values are retained to make the current limitations visible; they are not
claims about production performance.

## Testing and quality gates

Run backend tests from `backend\`:

```bat
cd backend
.venv\Scripts\activate.bat
python -m pytest tests -q
```

Run the frontend checks:

```bat
cd frontend
npm run build
npm test -- --watch=false
```

The GitHub Actions workflow
[`eval-gates.yml`](.github/workflows/eval-gates.yml) runs repeated smoke checks on
pull requests and repeated full checks on schedule or manual dispatch. Live
evaluation commands require a reachable API and the configured corpus/model
dependencies; no unavailable metric is implied by a green unit-test run.

## Design decisions

- **Hybrid retrieval instead of vector-only retrieval:** legal questions often
  contain exact clause terms, so lexical overlap is combined with vector score.
- **Explicit abstention:** retrieval score alone is not treated as proof. The answer
  path also checks lexical confidence and can return the exact insufficient-evidence
  phrase.
- **Citations as structured output:** citations carry source file, chunk, page, and
  score metadata; inline markers are normalized against the returned citation list.
- **Deterministic fallbacks:** direct evidence answers and structured summaries keep
  local development useful when Ollama is unavailable or strict generation is off.
- **Small-corpus retrieval behavior:** exact scans are preferred for the current
  early-MVP corpus so approximate-index behavior does not hide available evidence.

## Production evolution / future design

These are intentionally not presented as implemented features:

- authentication, authorization, tenant isolation, and document ACL enforcement
- object storage, document versioning, incremental re-indexing, and deletion workflows
- asynchronous ingestion for larger corpora
- sparse retrieval such as BM25 and a learned reranker
- external model serving, prompt/version management, and model safety review
- durable observability, tracing, alerting, and a reviewer-facing evaluation dashboard
- human-graded benchmark expansion and latency measurement under representative load

No production scale, uptime, latency SLO, or legal-accuracy claim is made here.
Where a metric has not been measured in a representative environment, it is **Not
yet measured**.

## Additional documentation

- [Frontend README](frontend/README.md)
- [Evaluation rubric](mvp/scoring_rubric.md)
- [MVP scope notes](mvp/README.md)
- [Development log](docs/development-log.md)
