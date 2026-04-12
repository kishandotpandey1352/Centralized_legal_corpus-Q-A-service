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
curl -X POST http://localhost:8000/query/retrieve -H "Content-Type: application/json" --data-binary "{\"query\":\"What is the cure period for material breach?\",\"top_k\":2}"
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
curl -X POST http://localhost:8000/query/retrieve -H "Content-Type: application/json" --data-binary "{\"query\":\"What is the cure period for material breach?\",\"top_k\":2}"
```



