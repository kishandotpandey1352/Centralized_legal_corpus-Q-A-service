import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { ApiService } from '../services/api.service';
import { DocumentsPageComponent } from './documents-page.component';

function buildDocument(overrides: Partial<{ document_id: string; source_file: string; chunk_count: number }> = {}) {
  return {
    document_id: overrides.document_id ?? 'doc-1',
    source_file: overrides.source_file ?? 'case.txt',
    document_type: 'txt',
    title: 'Case',
    chunk_count: overrides.chunk_count ?? 3,
    jurisdiction: 'UK',
    court: null,
    canonical_citation: null,
    decision_date: null,
    practice_area: null,
  };
}

function buildUploadSummary(document_id = 'doc-new') {
  return {
    status: 'indexed',
    document_id,
    source_file: 'new.txt',
    document_type: 'txt',
    chunks_indexed: 2,
    embedding_backend: 'hash',
    embedding_model: 'BAAI/bge-m3',
    metadata: { jurisdiction: null, court: null, canonical_citation: null, decision_date: null, practice_area: null },
    processing_time_ms: 5,
  };
}

describe('DocumentsPageComponent', () => {
  let apiMock: {
    listDocuments: ReturnType<typeof vi.fn>;
    answer: ReturnType<typeof vi.fn>;
    summary: ReturnType<typeof vi.fn>;
    keywords: ReturnType<typeof vi.fn>;
    retrieve: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    apiMock = {
      listDocuments: vi.fn().mockReturnValue(of({ documents: [] })),
      answer: vi.fn(),
      summary: vi.fn(),
      keywords: vi.fn(),
      retrieve: vi.fn(),
    };
    await TestBed.configureTestingModule({
      imports: [DocumentsPageComponent],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiMock },
      ],
    }).compileComponents();
  });

  function createComponent() {
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    return { fixture, component: fixture.componentInstance };
  }

  it('collapses Indexed Documents by default', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument()] }));
    const { fixture, component } = createComponent();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(component.listExpanded()).toBe(false);
    expect(fixture.nativeElement.querySelector('[data-testid="document-title"]')).toBeNull();
  });

  it('expands and collapses the list via the toggle', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument()] }));
    const { fixture, component } = createComponent();
    await fixture.whenStable();
    fixture.detectChanges();

    component.toggleList();
    fixture.detectChanges();
    expect(component.listExpanded()).toBe(true);
    expect(fixture.nativeElement.querySelector('[data-testid="document-title"]')).toBeTruthy();

    component.toggleList();
    fixture.detectChanges();
    expect(component.listExpanded()).toBe(false);
    expect(fixture.nativeElement.querySelector('[data-testid="document-title"]')).toBeNull();
  });

  it('displays the indexed-document count', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument(), buildDocument({ document_id: 'doc-2' })] }));
    const { fixture } = createComponent();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="documents-toggle"]')?.textContent).toContain('Indexed Documents (2)');
  });

  it('selects a document and highlights the row', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument({ document_id: 'doc-1' })] }));
    const { fixture, component } = createComponent();
    await fixture.whenStable();
    component.toggleList();
    fixture.detectChanges();

    const row = fixture.nativeElement.querySelector('[data-testid="document-row"]') as HTMLElement;
    row.click();
    fixture.detectChanges();

    expect(component.selected()?.document_id).toBe('doc-1');
    expect(row.classList.contains('active')).toBe(true);
  });

  it('does not render per-row action buttons', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument()] }));
    const { fixture, component } = createComponent();
    await fixture.whenStable();
    component.toggleList();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="doc-qa-button"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="doc-summary-button"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[data-testid="doc-keywords-button"]')).toBeNull();
  });

  it('disables shared action buttons when no document is selected', async () => {
    const { fixture } = createComponent();
    await fixture.whenStable();
    fixture.detectChanges();

    const qa = fixture.nativeElement.querySelector('[data-testid="action-qa"]') as HTMLButtonElement;
    expect(qa.disabled).toBe(true);
  });

  it('auto-selects the uploaded document and keeps the list collapsed', () => {
    const { component } = createComponent();
    component.listExpanded.set(true);

    component.onIndexed(buildUploadSummary('doc-new'));

    expect(component.selected()?.document_id).toBe('doc-new');
    expect(component.listExpanded()).toBe(false);
  });

  it('extractKeyTopics starts only after explicit click and renders topics as tags', async () => {
    apiMock.keywords.mockReturnValue(of({ document_id: 'doc-42', source_file: 'case.txt', topics: ['procedural fairness', 'unfair dismissal'] }));
    const { fixture, component } = createComponent();
    await fixture.whenStable();

    expect(apiMock.keywords).not.toHaveBeenCalled();

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.selectAction('keywords');
    component.extractKeywords();
    fixture.detectChanges();

    const chips = fixture.nativeElement.querySelectorAll('[data-testid="keywords-list"] .keyword-chip');
    expect(chips.length).toBe(2);
    expect(fixture.nativeElement.querySelector('[data-testid="keywords-list"]')?.textContent).toContain('procedural fairness');
  });

  it('resets the keywords loading state after failure', () => {
    apiMock.keywords.mockReturnValue(throwError(() => ({ status: 0, error: {} })));
    const { component } = createComponent();

    component.selectDocument(buildDocument());
    component.extractKeywords();

    expect(component.keywordsLoading()).toBe(false);
    expect(component.keywordsError()).toBe('Unable to extract key topics. Please try again.');
  });

  it('ask sends document_id to the answer endpoint', () => {
    const { component } = createComponent();
    apiMock.answer.mockReturnValue(of({ answer: 'Answer [C1]', citations: [] }));

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.qaQuestion.set('What is the deadline?');
    component.ask();

    expect(apiMock.answer).toHaveBeenCalledWith({
      question: 'What is the deadline?',
      top_k: 5,
      document_id: 'doc-42',
      rerank: true,
    });
  });

  it('generateSummary sends document_id', () => {
    const { component } = createComponent();
    apiMock.summary.mockReturnValue(of({ source_file: 'case.txt', summary: 'S [C1]', citations: [], used_chunks: 1, mode: 'llm-summary' }));

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.generateSummary();

    expect(apiMock.summary).toHaveBeenCalledWith({ document_id: 'doc-42', max_chunks: 20 });
  });

  it('preserves selected document when switching actions', () => {
    const { component } = createComponent();

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.selectAction('qa');
    component.selectAction('summary');

    expect(component.selected()?.document_id).toBe('doc-42');
    expect(component.activeAction()).toBe('summary');
  });

  it('shows empty state when backend returns zero documents', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [] }));
    const { fixture } = createComponent();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('No indexed documents yet');
    expect(text).not.toContain('Confirm backend is running');
  });

  it('shows a friendly message only on real list failure', async () => {
    apiMock.listDocuments.mockReturnValue(throwError(() => ({ status: 0, error: {} })));
    const { fixture } = createComponent();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Unable to load indexed documents');
    expect(text).not.toContain('Confirm backend is running');
  });
});
