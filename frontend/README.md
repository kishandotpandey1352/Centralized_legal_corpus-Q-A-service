# RAG Legal Frontend MVP

Angular frontend for the RAG Legal backend.

Implemented panels:
- Query retrieval
- Answer with citations
- Summary view
- Run history panel (browser local storage)

## Prerequisites

1. Node.js 20+ installed.
2. Backend API running on http://localhost:8000.

## Install

From this folder:

```bat
npm install
```

## Run in development

```bat
npm start
```

Open:

- http://localhost:4200

The Angular dev server uses proxy settings in proxy.conf.json, so calls to /query, /summary, /eval, and /ingest are forwarded to http://localhost:8000.

## Build

```bat
npm run build
```

Build output:

- dist/rag-legal-frontend

## Notes

- Run history is local to the browser and intentionally independent from backend experiment artifacts.
- If you just installed Node and commands are not found, close and reopen the terminal.
