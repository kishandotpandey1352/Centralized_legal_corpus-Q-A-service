import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { EvaluationGateDefinition, EvaluationLatest } from '../models';
import { ApiService } from '../services/api.service';

@Component({
  selector: 'app-evaluation-page',
  imports: [CommonModule],
  templateUrl: './evaluation-page.component.html',
  styleUrls: ['./shared-page.scss', './evaluation-page.component.scss'],
})
export class EvaluationPageComponent {
  private readonly api = inject(ApiService);

  readonly latest = signal<EvaluationLatest | null>(null);
  readonly latestLoading = signal(false);
  readonly latestError = signal('');

  constructor() {
    this.loadLatest();
  }

  loadLatest(): void {
    this.latestLoading.set(true);
    this.latestError.set('');
    this.api.latestEvaluation().subscribe({
      next: (result) => {
        this.latest.set(result);
        this.latestLoading.set(false);
      },
      error: () => {
        this.latestError.set('Unable to load the latest evaluation results.');
        this.latestLoading.set(false);
      },
    });
  }

  gateDefinitions(): EvaluationGateDefinition[] {
    return this.latest()?.gate_definitions ?? [];
  }

  metricValue(key: string): number | null | undefined {
    const metrics = this.latest()?.metrics;
    if (!metrics) {
      return null;
    }
    return (metrics as Record<string, number | null | undefined>)[key] ?? null;
  }

  gateStatus(key: string): 'pass' | 'fail' | 'info' {
    const definition = this.gateDefinitions().find((gate) => gate.key === key);
    if (definition?.informational) {
      return 'info';
    }
    const gates = this.latest()?.gates;
    if (!gates || gates[key] === undefined || gates[key] === null) {
      return 'info';
    }
    return gates[key] ? 'pass' : 'fail';
  }

  failedGates(): string[] {
    return this.latest()?.failed_gates ?? [];
  }

  formatMetric(key: string): string {
    const value = this.metricValue(key);
    if (value === null || value === undefined) {
      return '—';
    }
    return key === 'p95_latency_ms' ? `${value} ms` : value.toFixed(2);
  }
}
