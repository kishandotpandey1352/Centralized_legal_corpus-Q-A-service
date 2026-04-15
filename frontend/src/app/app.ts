import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AnswerRequest,
  AnswerResponse,
  Citation,
  RetrievalRequest,
  RetrievalResponse,
  RunHistoryEntry,
  SummaryRequest,
  SummaryResponse,
} from './models';
import { ApiService } from './services/api.service';

type ViewTab = 'query' | 'answer' | 'summary' | 'history';

const HISTORY_STORAGE_KEY = 'rag-legal-mvp-history';

function createEntry(
  type: RunHistoryEntry['type'],
  request: unknown,
  response: unknown,
  status: 'success' | 'error',
  message?: string,
): RunHistoryEntry {
  return {
    id: `${Date.now()}-${Math.floor(Math.random() * 100000)}`,
    type,
    timestamp: new Date().toISOString(),
    status,
    message,
    request,
    response,
  };
}

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly api = inject(ApiService);

  readonly tabs: ViewTab[] = ['query', 'answer', 'summary', 'history'];
  readonly activeTab = signal<ViewTab>('query');

  readonly queryForm = signal<RetrievalRequest>({
    query: '',
    top_k: 5,
    rerank: true,
    candidate_pool_size: 20,
    source_file: '',
    document_type: '',
  });

  readonly answerForm = signal<AnswerRequest>({
    question: '',
    top_k: 5,
    rerank: true,
    candidate_pool_size: 20,
    source_file: '',
    document_type: '',
  });

  readonly summaryForm = signal<SummaryRequest>({
    source_file: 'sample_service_agreement.txt',
    max_chunks: 6,
  });

  readonly loadingQuery = signal(false);
  readonly loadingAnswer = signal(false);
  readonly loadingSummary = signal(false);

  readonly queryError = signal('');
  readonly answerError = signal('');
  readonly summaryError = signal('');

  readonly queryResult = signal<RetrievalResponse | null>(null);
  readonly answerResult = signal<AnswerResponse | null>(null);
  readonly summaryResult = signal<SummaryResponse | null>(null);

  readonly history = signal<RunHistoryEntry[]>(this.loadHistory());
  readonly hasHistory = computed(() => this.history().length > 0);

  setTab(tab: ViewTab): void {
    this.activeTab.set(tab);
  }

  updateQueryField<K extends keyof RetrievalRequest>(key: K, value: RetrievalRequest[K]): void {
    this.queryForm.update((current) => ({ ...current, [key]: value }));
  }

  updateAnswerField<K extends keyof AnswerRequest>(key: K, value: AnswerRequest[K]): void {
    this.answerForm.update((current) => ({ ...current, [key]: value }));
  }

  updateSummaryField<K extends keyof SummaryRequest>(key: K, value: SummaryRequest[K]): void {
    this.summaryForm.update((current) => ({ ...current, [key]: value }));
  }

  runQuery(): void {
    const request = this.sanitizeRetrievalRequest(this.queryForm());
    if (!request.query) {
      this.queryError.set('Please enter a query.');
      return;
    }

    this.loadingQuery.set(true);
    this.queryError.set('');

    this.api.retrieve(request).subscribe({
      next: (result) => {
        this.queryResult.set(result);
        this.pushHistory(createEntry('query', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.queryError.set(message);
        this.pushHistory(createEntry('query', request, null, 'error', message));
      },
      complete: () => {
        this.loadingQuery.set(false);
      },
    });
  }

  runAnswer(): void {
    const request = this.sanitizeAnswerRequest(this.answerForm());
    if (!request.question) {
      this.answerError.set('Please enter a question.');
      return;
    }

    this.loadingAnswer.set(true);
    this.answerError.set('');

    this.api.answer(request).subscribe({
      next: (result) => {
        this.answerResult.set(result);
        this.pushHistory(createEntry('answer', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.answerError.set(message);
        this.pushHistory(createEntry('answer', request, null, 'error', message));
      },
      complete: () => {
        this.loadingAnswer.set(false);
      },
    });
  }

  runSummary(): void {
    const request = this.sanitizeSummaryRequest(this.summaryForm());
    if (!request.source_file) {
      this.summaryError.set('Please enter a source file.');
      return;
    }

    this.loadingSummary.set(true);
    this.summaryError.set('');

    this.api.summary(request).subscribe({
      next: (result) => {
        this.summaryResult.set(result);
        this.pushHistory(createEntry('summary', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.summaryError.set(message);
        this.pushHistory(createEntry('summary', request, null, 'error', message));
      },
      complete: () => {
        this.loadingSummary.set(false);
      },
    });
  }

  clearHistory(): void {
    this.history.set([]);
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  }

  trackByHistoryId(_: number, item: RunHistoryEntry): string {
    return item.id;
  }

  formatDate(value: string): string {
    return new Date(value).toLocaleString();
  }

  formatJson(value: unknown): string {
    return JSON.stringify(value, null, 2);
  }

  citationsForAnswer(): Citation[] {
    return this.answerResult()?.citations ?? [];
  }

  citationsForSummary(): Citation[] {
    return this.summaryResult()?.citations ?? [];
  }

  private sanitizeRetrievalRequest(value: RetrievalRequest): RetrievalRequest {
    return {
      ...value,
      query: value.query.trim(),
      source_file: this.cleanOptionalText(value.source_file),
      document_type: this.cleanOptionalText(value.document_type),
    };
  }

  private sanitizeAnswerRequest(value: AnswerRequest): AnswerRequest {
    return {
      ...value,
      question: value.question.trim(),
      source_file: this.cleanOptionalText(value.source_file),
      document_type: this.cleanOptionalText(value.document_type),
    };
  }

  private sanitizeSummaryRequest(value: SummaryRequest): SummaryRequest {
    return {
      ...value,
      source_file: value.source_file.trim(),
    };
  }

  private cleanOptionalText(value: string | undefined): string | undefined {
    if (!value) {
      return undefined;
    }
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
  }

  private toErrorMessage(error: unknown): string {
    if (typeof error === 'object' && error !== null && 'error' in error) {
      const payload = (error as { error?: unknown }).error;
      if (typeof payload === 'string') {
        return payload;
      }
      if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
        return String((payload as { detail?: unknown }).detail ?? 'Request failed');
      }
    }
    return 'Request failed. Confirm backend is running on http://localhost:8000.';
  }

  private loadHistory(): RunHistoryEntry[] {
    try {
      const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed as RunHistoryEntry[];
    } catch {
      return [];
    }
  }

  private pushHistory(entry: RunHistoryEntry): void {
    const next = [entry, ...this.history()].slice(0, 60);
    this.history.set(next);
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
  }
}
