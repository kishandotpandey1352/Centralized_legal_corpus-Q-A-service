import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AnswerRequest,
  AnswerResponse,
  RetrievalRequest,
  RetrievalResponse,
  SummaryRequest,
  SummaryResponse,
} from '../models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  retrieve(payload: RetrievalRequest): Observable<RetrievalResponse> {
    return this.http.post<RetrievalResponse>('/query/retrieve', payload);
  }

  answer(payload: AnswerRequest): Observable<AnswerResponse> {
    return this.http.post<AnswerResponse>('/query/answer', payload);
  }

  summary(payload: SummaryRequest): Observable<SummaryResponse> {
    return this.http.post<SummaryResponse>('/query/summary', payload);
  }
}
