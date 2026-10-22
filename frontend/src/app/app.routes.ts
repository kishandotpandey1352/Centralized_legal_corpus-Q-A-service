import { Routes } from '@angular/router';
import { DocumentsPageComponent } from './pages/documents-page.component';
import { EvaluationPageComponent } from './pages/evaluation-page.component';
import { HistoryPageComponent } from './pages/history-page.component';

export const routes: Routes = [
	{ path: '', pathMatch: 'full', redirectTo: 'documents' },
	{ path: 'documents', component: DocumentsPageComponent },
	{ path: 'evaluation', component: EvaluationPageComponent },
	{ path: 'history', component: HistoryPageComponent },
	// Legacy top-level routes redirect to the central documents workspace.
	{ path: 'query', redirectTo: 'documents' },
	{ path: 'answer', redirectTo: 'documents' },
	{ path: 'summary', redirectTo: 'documents' },
	{ path: 'upload', redirectTo: 'documents' },
	{ path: '**', redirectTo: 'documents' },
];
