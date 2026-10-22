import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  AnswerResponse,
  Citation,
  DocumentSummary,
  IngestionSummary,
  KeywordsResponse,
  RetrievalResponse,
  SummaryResponse,
} from '../models';
import { ApiService } from '../services/api.service';
import { HistoryService } from '../services/history.service';
import { UploadPageComponent } from './upload-page.component';

type Action = 'qa' | 'summary' | 'keywords';

@Component({
  selector: 'app-documents-page',
  imports: [CommonModule, FormsModule, UploadPageComponent],
  templateUrl: './documents-page.component.html',
  styleUrls: ['./shared-page.scss', './documents-page.component.scss'],
})
export class DocumentsPageComponent {
  private readonly api = inject(ApiService);
  private readonly history = inject(HistoryService);

  readonly documents = signal<DocumentSummary[]>([]);
  readonly listLoading = signal(false);
  readonly listError = signal('');

  readonly selected = signal<DocumentSummary | null>(null);
  readonly activeAction = signal<Action | null>(null);

  readonly qaQuestion = signal('');
  readonly qaLoading = signal(false);
  readonly qaError = signal('');
  readonly qaResult = signal<AnswerResponse | null>(null);
  readonly evidence = signal<RetrievalResponse | null>(null);
  readonly evidenceLoading = signal(false);
  readonly evidenceVisible = signal(false);

  readonly summaryLoading = signal(false);
  readonly summaryError = signal('');
  readonly summaryResult = signal<SummaryResponse | null>(null);

  readonly keywordsLoading = signal(false);
  readonly keywordsError = signal('');
  readonly keywordsResult = signal<KeywordsResponse | null>(null);

  constructor() {
    this.loadDocuments();
  }

  loadDocuments(): void {
    this.listLoading.set(true);
    this.listError.set('');
    this.api.listDocuments().subscribe({
      next: (response) => {
        this.documents.set(response.documents ?? []);
        this.listLoading.set(false);
        this.reconcileSelection();
      },
      error: (error) => {
        this.listError.set(this.toErrorMessage(error));
        this.listLoading.set(false);
      },
    });
  }

  onIndexed(summary: IngestionSummary): void {
    this.selected.set(this.summaryToDocument(summary));
    this.activeAction.set(null);
    this.resetActions();
    this.loadDocuments();
  }

  selectDocument(document: DocumentSummary): void {
    this.selected.set(document);
    this.activeAction.set(null);
    this.resetActions();
  }

  selectAction(action: Action): void {
    this.activeAction.set(action);
    this.qaResult.set(null);
    this.qaError.set('');
    this.evidence.set(null);
    this.evidenceVisible.set(false);
    this.summaryResult.set(null);
    this.summaryError.set('');
    this.keywordsResult.set(null);
    this.keywordsError.set('');
  }

  ask(): void {
    const document = this.selected();
    const question = this.qaQuestion().trim();
    if (!document || !question) {
      return;
    }

    this.qaLoading.set(true);
    this.qaError.set('');
    this.qaResult.set(null);
    this.evidence.set(null);
    this.evidenceVisible.set(false);

    const request = { question, top_k: 5, document_id: document.document_id, rerank: true };
    this.api.answer(request).subscribe({
      next: (result) => {
        this.qaResult.set(result);
        this.history.addEntry(this.history.createEntry('answer', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.qaError.set(message);
        this.history.addEntry(this.history.createEntry('answer', request, null, 'error', message));
      },
      complete: () => this.qaLoading.set(false),
    });
  }

  toggleEvidence(): void {
    if (!this.evidenceVisible()) {
      this.evidenceVisible.set(true);
      if (!this.evidence()) {
        this.loadEvidence();
      }
    } else {
      this.evidenceVisible.set(false);
    }
  }

  loadEvidence(): void {
    const document = this.selected();
    const question = this.qaQuestion().trim();
    if (!document || !question) {
      return;
    }

    this.evidenceLoading.set(true);
    this.api.retrieve({ query: question, top_k: 5, document_id: document.document_id, rerank: true }).subscribe({
      next: (result) => {
        this.evidence.set(result);
        this.evidenceLoading.set(false);
      },
      error: (error) => {
        this.qaError.set(this.toErrorMessage(error));
        this.evidenceLoading.set(false);
      },
    });
  }

  generateSummary(): void {
    const document = this.selected();
    if (!document) {
      return;
    }

    this.summaryLoading.set(true);
    this.summaryError.set('');
    this.summaryResult.set(null);

    const request = { document_id: document.document_id, max_chunks: 20 };
    this.api.summary(request).subscribe({
      next: (result) => {
        this.summaryResult.set(result);
        this.history.addEntry(this.history.createEntry('summary', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.summaryError.set(message);
        this.history.addEntry(this.history.createEntry('summary', request, null, 'error', message));
      },
      complete: () => this.summaryLoading.set(false),
    });
  }

  extractKeywords(): void {
    const document = this.selected();
    if (!document) {
      return;
    }

    this.keywordsLoading.set(true);
    this.keywordsError.set('');
    this.keywordsResult.set(null);

    const request = { document_id: document.document_id, limit: 8 };
    this.api.keywords(request).subscribe({
      next: (result) => {
        this.keywordsResult.set(result);
        this.history.addEntry(this.history.createEntry('keywords', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.keywordsError.set(message);
        this.history.addEntry(this.history.createEntry('keywords', request, null, 'error', message));
      },
      complete: () => this.keywordsLoading.set(false),
    });
  }

  metadataLine(document: DocumentSummary): string {
    const parts = [
      document.jurisdiction,
      document.court,
      document.canonical_citation,
      document.decision_date,
      document.practice_area,
    ].filter((value): value is string => Boolean(value));
    return parts.join(' · ');
  }

  citationLabel(citation: Citation): string {
    return citation.id ?? citation.citation_id ?? '';
  }

  private summaryToDocument(summary: IngestionSummary): DocumentSummary {
    return {
      document_id: summary.document_id,
      source_file: summary.source_file,
      document_type: summary.document_type,
      chunk_count: summary.chunks_indexed,
      jurisdiction: summary.metadata?.jurisdiction ?? null,
      court: summary.metadata?.court ?? null,
      canonical_citation: summary.metadata?.canonical_citation ?? null,
      decision_date: summary.metadata?.decision_date ?? null,
      practice_area: summary.metadata?.practice_area ?? null,
    };
  }

  private reconcileSelection(): void {
    const current = this.selected();
    const all = this.documents();
    if (current && all.length > 0 && !all.some((doc) => doc.document_id === current.document_id)) {
      this.selected.set(null);
      this.activeAction.set(null);
    }
  }

  private resetActions(): void {
    this.qaQuestion.set('');
    this.qaResult.set(null);
    this.qaError.set('');
    this.evidence.set(null);
    this.evidenceVisible.set(false);
    this.summaryResult.set(null);
    this.summaryError.set('');
    this.keywordsResult.set(null);
    this.keywordsError.set('');
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
}
