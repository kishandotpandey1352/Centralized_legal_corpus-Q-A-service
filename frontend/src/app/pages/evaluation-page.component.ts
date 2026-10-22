import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { EvaluationMetrics, EvaluationScoreResponse } from '../models';
import { ApiService } from '../services/api.service';

@Component({
  selector: 'app-evaluation-page',
  imports: [CommonModule, FormsModule],
  templateUrl: './evaluation-page.component.html',
  styleUrls: ['./shared-page.scss', './evaluation-page.component.scss'],
})
export class EvaluationPageComponent {
  private readonly api = inject(ApiService);

  readonly gates = [
    { label: 'Faithfulness', threshold: '≥ 0.75', key: 'faithfulness' },
    { label: 'Answer correctness', threshold: '≥ 0.70', key: 'answer_correctness' },
    { label: 'Recall@5', threshold: '≥ 0.65', key: 'retrieval_recall_at_5' },
    { label: 'Hallucination rate', threshold: '≤ 0.12', key: 'hallucination_rate' },
    { label: 'Invalid citation rate', threshold: '≤ 0.10', key: 'invalid_citation_rate' },
    { label: 'p95 latency', threshold: '≤ 5000 ms', key: 'latency_p95_ms' },
  ];

  readonly metrics = signal<EvaluationMetrics>({
    faithfulness: 0.85,
    answer_correctness: 0.8,
    retrieval_recall_at_5: 0.7,
    abstention_accuracy: 0.9,
    hallucination_rate: 0.05,
    invalid_citation_rate: 0.03,
    latency_p95_ms: 1800,
  });

  readonly loading = signal(false);
  readonly error = signal('');
  readonly result = signal<EvaluationScoreResponse | null>(null);

  updateMetric<K extends keyof EvaluationMetrics>(key: K, value: number): void {
    this.metrics.update((current) => ({ ...current, [key]: value }));
  }

  run(): void {
    this.loading.set(true);
    this.error.set('');
    this.result.set(null);

    this.api.scoreExperiment(this.metrics()).subscribe({
      next: (score) => {
        this.result.set(score);
      },
      error: (error) => {
        this.error.set(this.toErrorMessage(error));
      },
      complete: () => {
        this.loading.set(false);
      },
    });
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
