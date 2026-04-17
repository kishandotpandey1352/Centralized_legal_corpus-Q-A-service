import { CommonModule } from '@angular/common';
import { Component, computed, input, signal } from '@angular/core';

import { Citation } from '../models';

@Component({
  selector: 'app-citation-inspector',
  imports: [CommonModule],
  templateUrl: './citation-inspector.component.html',
  styleUrl: './citation-inspector.component.scss',
})
export class CitationInspectorComponent {
  readonly citations = input<Citation[]>([]);
  readonly selectedIndex = signal(0);

  readonly selectedCitation = computed(() => {
    const all = this.citations();
    if (!all.length) {
      return null;
    }
    const safeIndex = Math.min(this.selectedIndex(), all.length - 1);
    return all[safeIndex] ?? null;
  });

  select(index: number): void {
    this.selectedIndex.set(index);
  }
}
