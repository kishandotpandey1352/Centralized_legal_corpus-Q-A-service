import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { CitationInspectorComponent } from '../components/citation-inspector.component';
import { AnswerRequest, AnswerResponse } from '../models';
import { ApiService } from '../services/api.service';
import { HistoryService } from '../services/history.service';

@Component({
  selector: 'app-answer-page',
  imports: [CommonModule, FormsModule, CitationInspectorComponent],
  templateUrl: './answer-page.component.html',
  styleUrl: './shared-page.scss',
})
export class AnswerPageComponent {
  private readonly api = inject(ApiService);
  private readonly history = inject(HistoryService);

  readonly form = signal<AnswerRequest>({
    question: '',
    top_k: 5,
    rerank: true,
    candidate_pool_size: 20,
    source_file: '',
    document_type: '',
  });

  readonly loading = signal(false);
  readonly error = signal('');
  readonly result = signal<AnswerResponse | null>(null);

  updateField<K extends keyof AnswerRequest>(key: K, value: AnswerRequest[K]): void {
    this.form.update((current) => ({ ...current, [key]: value }));
  }

  run(): void {
    const request = this.sanitizeRequest(this.form());
    if (!request.question) {
      this.error.set('Please enter a question.');
      return;
    }

    this.loading.set(true);
    this.error.set('');

    this.api.answer(request).subscribe({
      next: (result) => {
        this.result.set(result);
        this.history.addEntry(this.history.createEntry('answer', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.error.set(message);
        this.history.addEntry(this.history.createEntry('answer', request, null, 'error', message));
      },
      complete: () => {
        this.loading.set(false);
      },
    });
  }

  private sanitizeRequest(value: AnswerRequest): AnswerRequest {
    return {
      ...value,
      question: value.question.trim(),
      source_file: this.cleanOptionalText(value.source_file),
      document_type: this.cleanOptionalText(value.document_type),
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
}
