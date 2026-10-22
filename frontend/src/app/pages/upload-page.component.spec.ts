import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';

import { IngestionSummary } from '../models';
import { ApiService } from '../services/api.service';
import { UploadPageComponent } from './upload-page.component';

function buildSummary(): IngestionSummary {
  return {
    status: 'indexed',
    document_id: 'doc-1',
    source_file: 'case.txt',
    document_type: 'txt',
    chunks_indexed: 3,
    embedding_backend: 'hash',
    embedding_model: 'BAAI/bge-m3',
    metadata: {
      jurisdiction: 'UK',
      court: 'Supreme Court',
      canonical_citation: '[2024] UKSC 1',
      decision_date: '2024-01-15',
      practice_area: 'public law',
    },
    processing_time_ms: 12,
  };
}

function selectEvent(fileName: string, type = 'text/plain'): Event {
  const file = new File(['content'], fileName, { type });
  return { target: { files: [file], value: '' } } as unknown as Event;
}

describe('UploadPageComponent', () => {
  let apiMock: { uploadDocument: ReturnType<typeof vi.fn> };
  let component: UploadPageComponent;

  beforeEach(async () => {
    apiMock = { uploadDocument: vi.fn() };
    await TestBed.configureTestingModule({
      imports: [UploadPageComponent],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiMock },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(UploadPageComponent);
    component = fixture.componentInstance;
  });

  it('rejects unsupported extensions with a friendly message', () => {
    component.onFileSelected(selectEvent('malware.exe', 'application/octet-stream'));

    expect(component.file()).toBeNull();
    expect(component.error()).toBe('Only PDF, DOCX and TXT files are supported.');
  });

  it('accepts supported files and exposes their name, size and type', () => {
    component.onFileSelected(selectEvent('case.pdf', 'application/pdf'));

    expect(component.file()?.name).toBe('case.pdf');
    expect(component.file()?.size).toBeGreaterThan(0);
    expect(component.fileTypeLabel(component.file()!)).toBe('application/pdf');
    expect(component.error()).toBe('');
  });

  it('submits the file and sanitized optional metadata to the API', () => {
    apiMock.uploadDocument.mockReturnValue(of(buildSummary()));

    component.onFileSelected(selectEvent('case.txt'));
    component.updateField('jurisdiction', ' UK ');
    component.updateField('court', '');
    component.updateField('decision_date', '2024-01-15');
    component.run();

    expect(apiMock.uploadDocument).toHaveBeenCalledTimes(1);
    const [file, metadata] = apiMock.uploadDocument.mock.calls[0];
    expect(file.name).toBe('case.txt');
    expect(metadata).toEqual({
      jurisdiction: 'UK',
      decision_date: '2024-01-15',
    });
  });

  it('shows the success response after upload', () => {
    const summary = buildSummary();
    apiMock.uploadDocument.mockReturnValue(of(summary));

    component.onFileSelected(selectEvent('case.txt'));
    component.run();

    expect(component.result()).toEqual(summary);
    expect(component.error()).toBe('');
    expect(component.loading()).toBe(false);
  });

  it('keeps the loading state active while processing and disables the button', () => {
    const subject = new Subject<IngestionSummary>();
    apiMock.uploadDocument.mockReturnValue(subject);

    const fixture = TestBed.createComponent(UploadPageComponent);
    const instance = fixture.componentInstance;
    instance.onFileSelected(selectEvent('case.txt'));
    fixture.detectChanges();

    instance.run();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('[data-testid="upload-run-button"]') as HTMLButtonElement;
    expect(instance.loading()).toBe(true);
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('Uploading and indexing');

    subject.next(buildSummary());
    subject.complete();
    fixture.detectChanges();

    expect(instance.loading()).toBe(false);
  });

  it('maps a 413 response to a friendly message', () => {
    apiMock.uploadDocument.mockReturnValue(throwError(() => ({ status: 413, error: { detail: 'raw' } })));

    component.onFileSelected(selectEvent('case.txt'));
    component.run();

    expect(component.error()).toBe('The selected file is too large.');
  });

  it('maps a 415 response to a friendly message', () => {
    apiMock.uploadDocument.mockReturnValue(throwError(() => ({ status: 415, error: { detail: 'raw' } })));

    component.onFileSelected(selectEvent('case.txt'));
    component.run();

    expect(component.error()).toBe('Only PDF, DOCX and TXT files are supported.');
  });

  it('maps a 500 response to a backend failure message without details', () => {
    apiMock.uploadDocument.mockReturnValue(throwError(() => ({ status: 500, error: { detail: 'stack' } })));

    component.onFileSelected(selectEvent('case.txt'));
    component.run();

    expect(component.error()).toBe('The document could not be indexed. Please try again or inspect the backend logs.');
    expect(component.error()).not.toContain('stack');
  });
});
