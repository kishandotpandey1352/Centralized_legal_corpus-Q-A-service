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
- Displays answer text and side-by-side citation inspector
- Supports same retrieval filters/rerank controls

3. Summary view panel
- Sends `POST /query/summary`
- Displays summary text, mode, used chunks, and side-by-side citation inspector

4. Run-history panel
- Stores local run entries in browser localStorage
- Records request, response, timestamp, and success/error status
- Supports clear, JSON export, and JSON import with validation

5. E2E testing for core workflows
- Playwright test suite for query, answer, summary, and history flows
- Uses mocked API responses for deterministic frontend validation

## Frontend Folder Structure

- frontend/package.json: npm scripts and dependencies
- frontend/angular.json: Angular build/serve configuration
- frontend/proxy.conf.json: local proxy mapping to backend
- frontend/src/main.ts: application bootstrap
- frontend/src/styles.scss: global typography/base styles
- frontend/src/app/app.ts: routed shell component
- frontend/src/app/app.html: shell nav + router outlet
- frontend/src/app/app.scss: shell-level visual styles
- frontend/src/app/app.routes.ts: route definitions (`/query`, `/answer`, `/summary`, `/history`)
- frontend/src/app/models.ts: request/response TypeScript interfaces
- frontend/src/app/services/api.service.ts: backend HTTP service layer
- frontend/src/app/services/history.service.ts: history persistence + export/import
- frontend/src/app/components/citation-inspector.component.*: citation selection and detail panel
- frontend/src/app/pages/*: route-level page components and templates
- frontend/src/app/app.config.ts: app providers (`provideHttpClient`, router)
- frontend/playwright.config.ts: E2E runner configuration
- frontend/e2e/core-workflows.spec.ts: core user journey tests

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
- `/query/retrieve`
- `/query/answer`
- `/query/summary`
- `/eval`
- `/health`
- `/ingest`

This avoids CORS issues during local development and prevents collision with the frontend route `/query`.

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
- Angular signals (`signal`, `computed`) in route components and shared services

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

## Iteration 2, 3, 4, 5: Reason and Implementation

### 2) Answer with side-by-side citation inspector

Reason of implementation:
- Inline citation IDs (`[C1]`, `[C2]`) are useful but too slow for legal review when users must scan a long list.
- A side-by-side inspector shortens verification time by keeping answer text and citation detail visible together.

How it works:
- Answer requests run through `ApiService.answer()` from the `/answer` page.
- Returned citations are passed into a reusable inspector component.
- Users click citation pills to focus one citation and view source/chunk/body in a dedicated detail panel.

How it is implemented:
- `frontend/src/app/pages/answer-page.component.ts` handles request lifecycle, validation, loading, error, and history write.
- `frontend/src/app/pages/answer-page.component.html` renders left answer surface + right citation inspector.
- `frontend/src/app/components/citation-inspector.component.ts` keeps selected citation state and renders details.

### 3) Summary with side-by-side citation inspector

Reason of implementation:
- Summary without inspectable evidence reduces trust for legal users.
- Reusing the same inspector interaction as answer keeps mental model consistent and lowers training cost.

How it works:
- Summary page calls `ApiService.summary()` with source file and max chunks.
- Response summary/meta render in one pane while citations render in inspector pane.
- Citation selection updates the right-side detail view in-place.

How it is implemented:
- `frontend/src/app/pages/summary-page.component.ts` manages summary request state and error handling.
- `frontend/src/app/pages/summary-page.component.html` reuses the same inspector component used by answer flow.
- Shared visual layout is reused through `frontend/src/app/pages/shared-page.scss`.

### 4) Run-history with clear/export/import

Reason of implementation:
- Early MVP evaluations need quick reproducibility and shareability without backend schema changes.
- Local export/import enables reviewer handoff and run replay while backend remains unchanged.

How it works:
- Every query/answer/summary execution writes a normalized history entry.
- History persists to localStorage and is shown on `/history`.
- Users can clear all entries, export current list to JSON, and import JSON back with validation/sanitization.

How it is implemented:
- `frontend/src/app/services/history.service.ts` owns history state, storage sync, entry factory, JSON export/import.
- `frontend/src/app/pages/history-page.component.ts` handles file input, import feedback, export download, and clear action.
- `frontend/src/app/pages/history-page.component.html` provides history list UI with request/response details.

### 5) E2E tests for core workflows

Reason of implementation:
- Route/page refactor added moving parts (routing, shared components, local persistence) that unit tests alone do not fully cover.
- E2E tests catch integration regressions in real browser behavior for critical user journeys.

How it works:
- Playwright starts frontend app, runs browser tests, and mocks API endpoints at network layer.
- Tests validate query retrieval rendering, answer/summary citation interaction, and history export/import behavior.

How it is implemented:
- `frontend/playwright.config.ts` configures browser project, base URL, and Angular dev server startup for tests.
- `frontend/e2e/core-workflows.spec.ts` contains three core tests:
	- query flow renders retrieval results
	- answer + summary flows render citation inspector behavior
	- history flow validates export and import paths
- `frontend/package.json` adds scripts: `npm run e2e`, `npm run e2e:headed`

## UX and Design Notes

- Single-page tabbed workbench (`query`, `answer`, `summary`, `history`)
- Responsive layout for desktop and mobile
- Purposeful typography and non-default visual theme
- Lightweight reveal animation for panel transitions

## Testing and Validation

Frontend checks completed:
- `npm run build` passed
- `npm run e2e` passed (3 tests)
- Unit test scaffold retained and updated for new heading

To run tests:

```bat
cd frontend
npm test
npm run e2e
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

## Recommended Next Frontend Iterations

1. Add document picker and metadata dropdowns from backend-provided options
2. Add route guards and unsaved-form prompts for long legal drafting sessions
3. Add optional server-backed history syncing for team review workflows
4. Add visual diff view between two history runs for regression triage
5. Add CI pipeline step to run Playwright E2E on pull requests
