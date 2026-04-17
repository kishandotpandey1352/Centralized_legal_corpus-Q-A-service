import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { CitationInspectorComponent } from '../components/citation-inspector.component';
import { SummaryRequest, SummaryResponse } from '../models';
import { ApiService } from '../services/api.service';
import { HistoryService } from '../services/history.service';

@Component({
  selector: 'app-summary-page',
  imports: [CommonModule, FormsModule, CitationInspectorComponent],
  templateUrl: './summary-page.component.html',
  styleUrl: './shared-page.scss',
})
export class SummaryPageComponent {
  private readonly api = inject(ApiService);
  private readonly history = inject(HistoryService);

  readonly form = signal<SummaryRequest>({
    source_file: 'sample_service_agreement.txt',
    max_chunks: 6,
  });

  readonly loading = signal(false);
  readonly error = signal('');
  readonly result = signal<SummaryResponse | null>(null);

  updateField<K extends keyof SummaryRequest>(key: K, value: SummaryRequest[K]): void {
    this.form.update((current) => ({ ...current, [key]: value }));
  }

  run(): void {
    const request = this.sanitizeRequest(this.form());
    if (!request.source_file) {
      this.error.set('Please enter a source file.');
      return;
    }

    this.loading.set(true);
    this.error.set('');

    this.api.summary(request).subscribe({
      next: (result) => {
        this.result.set(result);
        this.history.addEntry(this.history.createEntry('summary', request, result, 'success'));
      },
      error: (error) => {
        const message = this.toErrorMessage(error);
        this.error.set(message);
        this.history.addEntry(this.history.createEntry('summary', request, null, 'error', message));
      },
      complete: () => {
        this.loading.set(false);
      },
    });
  }

  private sanitizeRequest(value: SummaryRequest): SummaryRequest {
    return {
      ...value,
      source_file: value.source_file.trim(),
    };
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
