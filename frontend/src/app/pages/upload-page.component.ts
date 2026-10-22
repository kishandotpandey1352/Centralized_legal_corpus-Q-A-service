import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DocumentMetadataInput, IngestionSummary } from '../models';
import { ApiService } from '../services/api.service';

const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.txt'];

@Component({
  selector: 'app-upload-page',
  imports: [CommonModule, FormsModule],
  templateUrl: './upload-page.component.html',
  styleUrls: ['./shared-page.scss', './upload-page.component.scss'],
})
export class UploadPageComponent {
  private readonly api = inject(ApiService);

  @Output() indexed = new EventEmitter<IngestionSummary>();

  readonly file = signal<File | null>(null);
  readonly dragActive = signal(false);
  readonly metadata = signal<DocumentMetadataInput>({
    jurisdiction: '',
    court: '',
    canonical_citation: '',
    decision_date: '',
    practice_area: '',
  });

  readonly loading = signal(false);
  readonly error = signal('');
  readonly result = signal<IngestionSummary | null>(null);

  updateField<K extends keyof DocumentMetadataInput>(key: K, value: DocumentMetadataInput[K]): void {
    this.metadata.update((current) => ({ ...current, [key]: value }));
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectFile(input.files?.[0] ?? null);
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragActive.set(false);
    this.selectFile(event.dataTransfer?.files?.[0] ?? null);
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  fileTypeLabel(file: File): string {
    if (file.type) {
      return file.type;
    }
    const extension = file.name.split('.').pop()?.toUpperCase();
    return extension ? `${extension} document` : 'Document';
  }

  run(): void {
    const selectedFile = this.file();
    if (!selectedFile) {
      this.error.set('Please select a document to upload.');
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.result.set(null);

    this.api.uploadDocument(selectedFile, this.sanitizeMetadata(this.metadata())).subscribe({
      next: (result) => {
        this.result.set(result);
        this.indexed.emit(result);
      },
      error: (error) => {
        this.error.set(this.toErrorMessage(error));
        this.loading.set(false);
      },
      complete: () => {
        this.loading.set(false);
      },
    });
  }

  private selectFile(file: File | null): void {
    this.result.set(null);
    this.error.set('');

    if (!file) {
      return;
    }

    const name = file.name.toLowerCase();
    if (!SUPPORTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
      this.file.set(null);
      this.error.set('Only PDF, DOCX and TXT files are supported.');
      return;
    }

    this.file.set(file);
  }

  private sanitizeMetadata(value: DocumentMetadataInput): DocumentMetadataInput {
    const cleaned: DocumentMetadataInput = {};
    for (const key of Object.keys(value) as (keyof DocumentMetadataInput)[]) {
      const raw = value[key];
      if (typeof raw === 'string' && raw.trim() !== '') {
        cleaned[key] = raw.trim();
      }
    }
    return cleaned;
  }

  private toErrorMessage(error: unknown): string {
    const status = (error as { status?: number })?.status;

    if (status === 413) {
      return 'The selected file is too large.';
    }
    if (status === 415) {
      return 'Only PDF, DOCX and TXT files are supported.';
    }
    if (status === 500) {
      return 'The document could not be indexed. Please try again or inspect the backend logs.';
    }

    const payload = (error as { error?: unknown })?.error;
    if (typeof payload === 'string') {
      return payload;
    }
    if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
      return String((payload as { detail?: unknown }).detail ?? 'Request failed');
    }
    return 'Upload failed. Confirm backend is running on http://localhost:8000.';
  }
}
