# RAG Legal Frontend Documentation

This file is the dedicated frontend guide for the Angular MVP in this repository.

## Scope

Frontend stack:
- Angular 21 (standalone app)
- TypeScript + SCSS
- Angular HttpClient for backend integration
- Angular dev proxy for local API calls

Frontend location:
- frontend/

## MVP Features Implemented

1. Query retrieval panel
- Sends `POST /query/retrieve`
- Displays retrieved chunks with source, chunk index, and score
- Supports filters: `source_file`, `document_type`
- Supports rerank controls: `rerank`, `candidate_pool_size`

2. Answer with citations panel
- Sends `POST /query/answer`
- Displays answer text and citation list
- Supports same retrieval filters/rerank controls

3. Summary view panel
- Sends `POST /query/summary`
- Displays summary text, mode, used chunks, and citations

4. Run-history panel
- Stores local run entries in browser localStorage
- Records request, response, timestamp, and success/error status
- Supports clearing history

## Why The App Has Four Tabs

The frontend is organized as a focused legal-RAG workbench. Each tab exists to separate a different workflow, reduce confusion, and make debugging easier.

1. Query tab (retrieval inspection)
- Purpose: inspect retrieval quality before generation.
- Why it exists: helps verify that relevant chunks are being fetched and ranked correctly.
- What it is best for: checking scores, source files, chunk coverage, and rerank/filter effects.

2. Answer tab (grounded QA)
- Purpose: answer user questions with evidence citations.
- Why it exists: question answering is a different workflow from retrieval inspection and needs a dedicated result format.
- What it is best for: user-facing legal Q&A with citation-backed responses.

3. Summary tab (document synthesis)
- Purpose: generate grounded summaries for a selected document.
- Why it exists: summary prompts and outputs are document-centric and differ from question-centric answering.
- What it is best for: fast review of a source file's key points with citations and mode visibility.

4. History tab (traceability)
- Purpose: keep a local record of prior runs.
- Why it exists: supports reproducibility, quick comparisons, and troubleshooting without re-running every request.
- What it is best for: reviewing request/response pairs, timing context, and success/failure patterns.

## Frontend Folder Structure

- frontend/package.json: npm scripts and dependencies
- frontend/angular.json: Angular build/serve configuration
- frontend/proxy.conf.json: local proxy mapping to backend
- frontend/src/main.ts: application bootstrap
- frontend/src/styles.scss: global typography/base styles
- frontend/src/app/app.ts: page state, actions, API calls, local history
- frontend/src/app/app.html: UI layout and panel templates
- frontend/src/app/app.scss: component-scoped visual design and responsive styles
- frontend/src/app/models.ts: request/response TypeScript interfaces
- frontend/src/app/services/api.service.ts: backend HTTP service layer
- frontend/src/app/app.config.ts: app providers (`provideHttpClient`, router)

## Prerequisites

1. Backend API running on `http://localhost:8000`
2. Node.js installed (20+ recommended)

## Install and Run

From project root:

```bat
cd frontend
npm install
npm start
```

If PowerShell execution policy blocks `npm`, use:

```bat
cd frontend
C:\Program Files\nodejs\npm.cmd install
C:\Program Files\nodejs\npm.cmd start
```

App URL:
- `http://localhost:4200`

## Build

```bat
cd frontend
npm run build
```

Production output:
- `frontend/dist/rag-legal-frontend`

## How Backend Integration Works

The frontend uses relative API paths such as:
- `/query/retrieve`
- `/query/answer`
- `/query/summary`

During local development, Angular proxy (`frontend/proxy.conf.json`) forwards these paths to `http://localhost:8000`.

Configured proxy prefixes:
- `/query`
- `/eval`
- `/health`
- `/ingest`

This avoids CORS issues during local development.

## Request/Response Contracts Used by UI

### Query
Request shape:
- `query: string`
- `top_k: number`
- `source_file?: string`
- `document_type?: string`
- `rerank: boolean`
- `candidate_pool_size?: number`

Response fields consumed:
- `query`
- `top_k`
- `results[]` with `source_file`, `chunk_index`, `chunk_text`, `score`

### Answer
Request shape:
- `question: string`
- `top_k: number`
- `source_file?: string`
- `document_type?: string`
- `rerank: boolean`
- `candidate_pool_size?: number`

Response fields consumed:
- `answer`
- `citations[]` with `citation_id`, `source_file`, `chunk_index`, `chunk_text`, `score?`
- optional `mode`

### Summary
Request shape:
- `source_file: string`
- `max_chunks: number`

Response fields consumed:
- `source_file`
- `summary`
- `citations[]`
- `used_chunks`
- `mode`

## Frontend State and Behavior

State management approach:
- Angular signals (`signal`, `computed`) in `App` component

Input handling:
- Form values are sanitized before submission
- Empty optional fields (`source_file`, `document_type`) are removed from payloads

Error handling:
- API errors surface via panel-specific error text
- If backend is unreachable, UI shows fallback connection message

History behavior:
- Key: `rag-legal-mvp-history`
- Max kept entries: 60 (newest first)
- Data persisted per browser profile

## UX and Design Notes

- Single-page tabbed workbench (`query`, `answer`, `summary`, `history`)
- Responsive layout for desktop and mobile
- Purposeful typography and non-default visual theme
- Lightweight reveal animation for panel transitions

## Testing and Validation

Frontend checks completed:
- `npm run build` passed
- Unit test scaffold retained and updated for new heading

To run tests:

```bat
cd frontend
npm test
```

## Troubleshooting

1. `node`, `npm`, or `npx` not recognized
- Close and reopen terminal after Node installation
- Verify installation path is in `PATH`
- Use direct executable path (`npm.cmd`) if needed

2. `npm.ps1 cannot be loaded because running scripts is disabled`
- Use `npm.cmd` instead of `npm` in PowerShell

3. Frontend loads but requests fail
- Confirm backend is running on `http://localhost:8000`
- Confirm proxy file exists at `frontend/proxy.conf.json`
- Restart Angular dev server after proxy/config changes

4. Stale UI behavior during development
- Stop and restart `npm start`
- Hard refresh browser

## Current Limitations

- Run-history is local only (not synchronized with backend experiment artifacts)
- No auth/session model yet
- No pagination/virtualization for very large result sets
- No dedicated route-level pages; MVP is a single workbench view

## Recommended Next Frontend Iterations

1. Add document picker and metadata dropdowns from backend-provided options
2. Add run export/import for local history (JSON)
3. Add side-by-side citation inspector for answer/summary
4. Add route-based screens (`/query`, `/answer`, `/summary`, `/history`)
5. Add E2E tests for core workflows
