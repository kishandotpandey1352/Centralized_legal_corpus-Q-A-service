import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ApiService } from '../services/api.service';
import { EvaluationPageComponent } from './evaluation-page.component';

const GATE_DEFINITIONS = [
  { key: 'faithfulness', label: 'Faithfulness', threshold: '>= 0.75', informational: false },
  { key: 'answer_correctness', label: 'Answer correctness', threshold: '>= 0.70', informational: false },
  { key: 'recall_at_5', label: 'Recall@5', threshold: '>= 0.65', informational: false },
  { key: 'abstention_accuracy', label: 'Abstention accuracy', threshold: 'Informational', informational: true },
  { key: 'hallucination_rate', label: 'Hallucination rate', threshold: '<= 0.12', informational: false },
  { key: 'invalid_citation_rate', label: 'Invalid citation rate', threshold: '<= 0.10', informational: false },
  { key: 'p95_latency_ms', label: 'p95 latency', threshold: '<= 5000 ms', informational: false },
];

function buildLatest(gates: Record<string, boolean>, status: 'pass' | 'fail', failedGates: string[] = []) {
  return {
    available: true,
    run_id: '20260101_120000_000001',
    mode: 'smoke',
    total_cases: 11,
    metrics: {
      faithfulness: 0.92,
      answer_correctness: 0.89,
      recall_at_5: 1.0,
      abstention_accuracy: 0.73,
      hallucination_rate: 0.0,
      invalid_citation_rate: 0.0,
      p95_latency_ms: 6700,
    },
    overall_score: 0.8587,
    gates,
    gate_definitions: GATE_DEFINITIONS,
    failed_gates: failedGates,
    status,
  };
}

const PASSING_GATES = {
  faithfulness: true,
  answer_correctness: true,
  recall_at_5: true,
  hallucination_rate: true,
  invalid_citation_rate: true,
  p95_latency_ms: true,
};

describe('EvaluationPageComponent', () => {
  let apiMock: { latestEvaluation: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    apiMock = { latestEvaluation: vi.fn().mockReturnValue(of({ available: false })) };
    await TestBed.configureTestingModule({
      imports: [EvaluationPageComponent],
      providers: [provideRouter([]), { provide: ApiService, useValue: apiMock }],
    }).compileComponents();
  });

  it('renders Recall@5 as PASS when the backend reports the gate passed', async () => {
    apiMock.latestEvaluation.mockReturnValue(of(buildLatest(PASSING_GATES, 'pass')));
    const fixture = TestBed.createComponent(EvaluationPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const cell = fixture.nativeElement.querySelector('[data-testid="eval-gate-status-recall_at_5"]');
    expect(cell?.textContent).toContain('PASS');
  });

  it('renders p95 latency as FAIL when the backend reports the gate failed', async () => {
    const gates = { ...PASSING_GATES, p95_latency_ms: false };
    apiMock.latestEvaluation.mockReturnValue(of(buildLatest(gates, 'fail', ['p95 latency'])));
    const fixture = TestBed.createComponent(EvaluationPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const cell = fixture.nativeElement.querySelector('[data-testid="eval-gate-status-p95_latency_ms"]');
    expect(cell?.textContent).toContain('FAIL');
  });

  it('shows FAIL overall even when the composite score is high', async () => {
    const gates = { ...PASSING_GATES, p95_latency_ms: false };
    apiMock.latestEvaluation.mockReturnValue(of(buildLatest(gates, 'fail', ['p95 latency'])));
    const fixture = TestBed.createComponent(EvaluationPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Composite Score: 0.8587');
    expect(text).toContain('FAIL');
  });

  it('shows the failed gate reason', async () => {
    const gates = { ...PASSING_GATES, p95_latency_ms: false };
    apiMock.latestEvaluation.mockReturnValue(of(buildLatest(gates, 'fail', ['p95 latency'])));
    const fixture = TestBed.createComponent(EvaluationPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const reason = fixture.nativeElement.querySelector('[data-testid="eval-failed-gates"]');
    expect(reason?.textContent).toContain('p95 latency');
  });

  it('does not render the manual Compute Score form', async () => {
    apiMock.latestEvaluation.mockReturnValue(of(buildLatest(PASSING_GATES, 'pass')));
    const fixture = TestBed.createComponent(EvaluationPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="eval-run-button"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="eval-advanced-panel"]')).toBeNull();
    expect((fixture.nativeElement.textContent as string)).not.toContain('Compute Score');
  });

  it('shows the empty state when no results are available', async () => {
    apiMock.latestEvaluation.mockReturnValue(of({ available: false }));
    const fixture = TestBed.createComponent(EvaluationPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('No evaluation results are available yet');
  });
});

