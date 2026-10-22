import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

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

  it('loads and displays indexed documents', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument()] }));
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const title = fixture.nativeElement.querySelector('[data-testid="document-title"]');
    expect(title?.textContent).toContain('case.txt');
  });

  it('shows action tabs after selecting a document', async () => {
    apiMock.listDocuments.mockReturnValue(of({ documents: [buildDocument()] }));
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    fixture.componentInstance.selectDocument(buildDocument());
    fixture.componentInstance.selectAction('qa');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[data-testid="qa-panel"]')).toBeTruthy();
  });

  it('ask sends document_id to the answer endpoint', () => {
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    const component = fixture.componentInstance;
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
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    const component = fixture.componentInstance;
    apiMock.summary.mockReturnValue(of({ source_file: 'case.txt', summary: 'S [C1]', citations: [], used_chunks: 1, mode: 'llm-summary' }));

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.generateSummary();

    expect(apiMock.summary).toHaveBeenCalledWith({ document_id: 'doc-42', max_chunks: 20 });
  });

  it('extractKeywords sends document_id', () => {
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    const component = fixture.componentInstance;
    apiMock.keywords.mockReturnValue(of({ document_id: 'doc-42', source_file: 'case.txt', keywords: ['k'] }));

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.extractKeywords();

    expect(apiMock.keywords).toHaveBeenCalledWith({ document_id: 'doc-42', limit: 8 });
  });

  it('preserves selected document when switching actions', () => {
    const fixture = TestBed.createComponent(DocumentsPageComponent);
    const component = fixture.componentInstance;

    component.selectDocument(buildDocument({ document_id: 'doc-42' }));
    component.selectAction('qa');
    component.selectAction('summary');

    expect(component.selected()?.document_id).toBe('doc-42');
    expect(component.activeAction()).toBe('summary');
  });
});
