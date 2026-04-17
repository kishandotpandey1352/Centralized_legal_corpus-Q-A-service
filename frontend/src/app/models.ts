export interface RetrievalRequest {
  query: string;
  top_k: number;
  source_file?: string;
  document_type?: string;
  rerank: boolean;
  candidate_pool_size?: number;
}

export interface AnswerRequest {
  question: string;
  top_k: number;
  source_file?: string;
  document_type?: string;
  rerank: boolean;
  candidate_pool_size?: number;
}

export interface SummaryRequest {
  source_file: string;
  max_chunks: number;
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
}

export interface Citation {
  citation_id: string;
  source_file: string;
  chunk_index: number;
  chunk_text: string;
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
  summary: string;
  citations: Citation[];
  used_chunks: number;
  mode: string;
}

export interface RunHistoryEntry {
  id: string;
  type: 'query' | 'answer' | 'summary';
  timestamp: string;
  status: 'success' | 'error';
  message?: string;
  request: unknown;
  response: unknown;
}
