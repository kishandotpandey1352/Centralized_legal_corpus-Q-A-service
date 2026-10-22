import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AnswerRequest,
  AnswerResponse,
  DocumentListResponse,
  DocumentMetadataInput,
  EvaluationLatest,
  IngestionSummary,
  KeywordsRequest,
  KeywordsResponse,
  RetrievalRequest,
  RetrievalResponse,
  SummaryRequest,
  SummaryResponse,
} from '../models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  listDocuments(): Observable<DocumentListResponse> {
    return this.http.get<DocumentListResponse>('/documents');
  }

  retrieve(payload: RetrievalRequest): Observable<RetrievalResponse> {
    return this.http.post<RetrievalResponse>('/query/retrieve', payload);
  }

  answer(payload: AnswerRequest): Observable<AnswerResponse> {
    return this.http.post<AnswerResponse>('/query/answer', payload);
  }

  summary(payload: SummaryRequest): Observable<SummaryResponse> {
    return this.http.post<SummaryResponse>('/query/summary', payload);
  }

  keywords(payload: KeywordsRequest): Observable<KeywordsResponse> {
    return this.http.post<KeywordsResponse>('/query/keywords', payload);
  }

  latestEvaluation(): Observable<EvaluationLatest> {
    return this.http.get<EvaluationLatest>('/eval/latest');
  }

  uploadDocument(file: File, metadata: DocumentMetadataInput = {}): Observable<IngestionSummary> {
    const formData = new FormData();
    formData.append('file', file, file.name);

    const fields: (keyof DocumentMetadataInput)[] = [
      'jurisdiction',
      'court',
      'canonical_citation',
      'decision_date',
      'practice_area',
    ];
    for (const field of fields) {
      const value = metadata[field];
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        formData.append(field, String(value).trim());
      }
    }

    return this.http.post<IngestionSummary>('/ingest/upload', formData);
  }
}
