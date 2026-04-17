import { Injectable, signal } from '@angular/core';

import { RunHistoryEntry } from '../models';

const HISTORY_STORAGE_KEY = 'rag-legal-mvp-history';
const MAX_HISTORY_ENTRIES = 120;

@Injectable({ providedIn: 'root' })
export class HistoryService {
  readonly history = signal<RunHistoryEntry[]>(this.loadHistory());

  addEntry(entry: RunHistoryEntry): void {
    const next = [entry, ...this.history()].slice(0, MAX_HISTORY_ENTRIES);
    this.history.set(next);
    this.persist(next);
  }

  clear(): void {
    this.history.set([]);
    localStorage.removeItem(HISTORY_STORAGE_KEY);
  }

  exportToJson(): string {
    return JSON.stringify(this.history(), null, 2);
  }

  importFromJson(raw: string): { imported: number } {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      throw new Error('Invalid file format. Expected an array of history entries.');
    }

    const cleaned: RunHistoryEntry[] = parsed
      .map((item) => this.toValidEntry(item))
      .filter((item): item is RunHistoryEntry => item !== null)
      .slice(0, MAX_HISTORY_ENTRIES);

    this.history.set(cleaned);
    this.persist(cleaned);
    return { imported: cleaned.length };
  }

  createEntry(
    type: RunHistoryEntry['type'],
    request: unknown,
    response: unknown,
    status: RunHistoryEntry['status'],
    message?: string,
  ): RunHistoryEntry {
    return {
      id: `${Date.now()}-${Math.floor(Math.random() * 100000)}`,
      type,
      timestamp: new Date().toISOString(),
      status,
      message,
      request,
      response,
    };
  }

  private loadHistory(): RunHistoryEntry[] {
    try {
      const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed
        .map((item) => this.toValidEntry(item))
        .filter((item): item is RunHistoryEntry => item !== null)
        .slice(0, MAX_HISTORY_ENTRIES);
    } catch {
      return [];
    }
  }

  private persist(history: RunHistoryEntry[]): void {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
  }

  private toValidEntry(value: unknown): RunHistoryEntry | null {
    if (!value || typeof value !== 'object') {
      return null;
    }
    const item = value as Partial<RunHistoryEntry>;
    if (!item.id || !item.timestamp || !item.type || !item.status) {
      return null;
    }

    if (item.type !== 'query' && item.type !== 'answer' && item.type !== 'summary') {
      return null;
    }
    if (item.status !== 'success' && item.status !== 'error') {
      return null;
    }

    return {
      id: String(item.id),
      timestamp: String(item.timestamp),
      type: item.type,
      status: item.status,
      message: item.message ? String(item.message) : undefined,
      request: item.request,
      response: item.response,
    };
  }
}
