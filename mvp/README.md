# Legal RAG MVP

## Goal
Build a minimal retrieval-augmented generation pipeline for legal documents that can ingest files, retrieve grounded passages, and answer questions with citations.

## MVP Scope

### Inputs
- PDF
- DOCX
- TXT

### Core capabilities
- Parse documents into text
- Split text into chunks with overlap
- Attach metadata per chunk
- Build a vector index
- Answer queries with cited sources
- Generate a single-document summary

### Out of scope for MVP
- Sparse retrieval / BM25
- Hybrid reranking
- ACL enforcement
- Multi-document synthesis
- Async ingestion queue
- Versioning and incremental reindexing
- Eval dashboards and guardrails

## Recommended MVP Architecture
1. Ingestion layer
- File upload or local folder ingest
- Format-specific parsers
- Normalization and cleanup

2. Chunking layer
- Chunk by heading/paragraph when possible
- Fallback to token-based chunking
- Preserve page numbers, section names, and source file metadata

3. Index layer
- Vector embeddings for chunks
- Persistent index storage
- Metadata store for document and chunk provenance

4. Retrieval and answer layer
- Top-k semantic retrieval
- Context assembly with citations
- Prompt that requires grounded answers only

5. Summary layer
- Document summary endpoint
- Optional section-level summary for long files

## Suggested MVP Workflow
1. Ingest one legal document.
2. Parse and chunk it.
3. Store chunk metadata and embeddings.
4. Ask a question against the document.
5. Return an answer with citations to chunk/page references.
6. Produce a short summary of the document.

## Data Model
Each chunk should store:
- document_id
- source_file
- document_type
- page_range
- section_title
- chunk_id
- chunk_text
- chunk_index
- created_at

## Definition of Done for MVP
- A user can upload or point to a legal document and have it indexed.
- A user can ask a question and receive a grounded answer with citations.
- A user can request a concise summary of a single document.
- The pipeline works on PDF, DOCX, and TXT inputs.
- Basic logging exists for ingest, retrieval, and answer generation.

## Practical Build Phases

### Phase 1: MVP
Estimated time: 2-3 weeks
- Ingest PDF, DOCX, TXT
- Parse, chunk, and capture metadata
- Build vector search and basic query flow
- Return citations with answers
- Add single-document summary

Deliverable:
- One working end-to-end path from file upload to cited answer.

### Phase 2: Production Retrieval
- Add BM25 sparse index
- Add hybrid retrieval and reranking
- Add metadata filters and ACL filtering
- Add multi-document summary

### Phase 3: Reliability and Scale
- Add async ingestion queue
- Add incremental reindexing and versioning
- Add evaluation harness and dashboards
- Add prompt hardening and guardrails

## Suggested Next Steps
1. Choose the stack for the MVP.
2. Decide where documents will be stored.
3. Pick an embedding model and vector database.
4. Create the ingest and query service skeleton.
5. Add a small test corpus of legal documents.
