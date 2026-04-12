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

