export interface RetrievalRequest {
  query: string;
  top_k: number;
  source_file?: string;
  document_id?: string;
  document_type?: string;
  jurisdiction?: string;
  court?: string;
  canonical_citation?: string;
  decision_date?: string;
  practice_area?: string;
  rerank: boolean;
  candidate_pool_size?: number;
}

export interface AnswerRequest {
  question: string;
  top_k: number;
  source_file?: string;
  document_id?: string;
  document_type?: string;
  jurisdiction?: string;
  court?: string;
  canonical_citation?: string;
  decision_date?: string;
  practice_area?: string;
  rerank: boolean;
  candidate_pool_size?: number;
}

export interface SummaryRequest {
  source_file?: string;
  document_id?: string;
  max_chunks: number;
}

export interface KeywordsRequest {
  document_id: string;
  limit?: number;
}

export interface DocumentMetadataInput {
  jurisdiction?: string;
  court?: string;
  canonical_citation?: string;
  decision_date?: string;
  practice_area?: string;
}

export interface IngestionMetadata {
  jurisdiction?: string | null;
  court?: string | null;
  canonical_citation?: string | null;
  decision_date?: string | null;
  practice_area?: string | null;
}

export interface IngestionSummary {
  status: string;
  document_id: string;
  source_file: string;
  document_type: string;
  chunks_indexed: number;
  embedding_backend: string;
  embedding_model: string;
  metadata: IngestionMetadata;
  processing_time_ms?: number | null;
}

export interface DocumentSummary {
  document_id: string;
  source_file: string;
  document_type: string;
  title?: string | null;
  chunk_count: number;
  jurisdiction?: string | null;
  court?: string | null;
  canonical_citation?: string | null;
  decision_date?: string | null;
  practice_area?: string | null;
}

export interface DocumentListResponse {
  documents: DocumentSummary[];
}

export interface KeywordsResponse {
  document_id: string;
  source_file: string;
  keywords: string[];
}

export interface RetrievedChunk {
  chunk_id?: string;
  document_id?: string;
  source_file: string;
  document_type?: string;
  chunk_index: number;
  chunk_text: string;
  page_range?: string | null;
  section_title?: string | null;
  score: number;
  vector_score?: number | null;
  lexical_score?: number | null;
  hybrid_score?: number | null;
}

export interface Citation {
  id?: string;
  citation_id?: string;
  document_id?: string;
  source_file?: string;
  chunk_id?: string;
  chunk_index?: number;
  chunk_text?: string;
  page_range?: string | null;
  section_title?: string | null;
  jurisdiction?: string | null;
  court?: string | null;
  canonical_citation?: string | null;
  decision_date?: string | null;
  practice_area?: string | null;
  score?: number | null;
}

export interface RetrievalResponse {
  query: string;
  top_k: number;
  results: RetrievedChunk[];
}

export interface AnswerResponse {
  question?: string;
  answer: string;
  citations: Citation[];
  mode?: string;
}

export interface SummaryResponse {
  source_file: string;
  document_id?: string | null;
  summary: string;
  citations: Citation[];
  used_chunks: number;
  mode: string;
}

export interface EvaluationMetrics {
  faithfulness: number;
  answer_correctness: number;
  retrieval_recall_at_5: number;
  abstention_accuracy: number;
  hallucination_rate: number;
  invalid_citation_rate: number;
  latency_p95_ms: number;
}

export interface EvaluationScoreResponse {
  overall_score: number;
  latency_penalty: number;
  gates: Record<string, boolean>;
  pass_fail: 'pass' | 'fail';
}

export interface RunHistoryEntry {
  id: string;
  type: 'query' | 'answer' | 'summary' | 'keywords';
  timestamp: string;
  status: 'success' | 'error';
  message?: string;
  request: unknown;
  response: unknown;
}
