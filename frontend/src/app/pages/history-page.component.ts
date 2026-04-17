import { CommonModule } from '@angular/common';
import { Component, ElementRef, ViewChild, computed, inject, signal } from '@angular/core';

import { RunHistoryEntry } from '../models';
import { HistoryService } from '../services/history.service';

@Component({
  selector: 'app-history-page',
  imports: [CommonModule],
  templateUrl: './history-page.component.html',
  styleUrl: './history-page.component.scss',
})
export class HistoryPageComponent {
  @ViewChild('importFileInput') importFileInput?: ElementRef<HTMLInputElement>;

  private readonly historyService = inject(HistoryService);

  readonly history = this.historyService.history;
  readonly hasHistory = computed(() => this.history().length > 0);
  readonly importMessage = signal('');
  readonly importError = signal('');

  clear(): void {
    this.historyService.clear();
    this.importMessage.set('');
    this.importError.set('');
  }

  exportHistory(): void {
    const payload = this.historyService.exportToJson();
    const blob = new Blob([payload], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `rag-legal-history-${new Date().toISOString().replaceAll(':', '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  triggerImport(): void {
    this.importFileInput?.nativeElement.click();
  }

  async onImportSelected(event: Event): Promise<void> {
    this.importMessage.set('');
    this.importError.set('');

    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const { imported } = this.historyService.importFromJson(text);
      this.importMessage.set(`Imported ${imported} history entries.`);
    } catch (error) {
      this.importError.set(error instanceof Error ? error.message : 'Failed to import history file.');
    } finally {
      input.value = '';
    }
  }

  formatDate(value: string): string {
    return new Date(value).toLocaleString();
  }

  formatJson(value: unknown): string {
    return JSON.stringify(value, null, 2);
  }

  trackByHistoryId(_: number, item: RunHistoryEntry): string {
    return item.id;
  }
}
