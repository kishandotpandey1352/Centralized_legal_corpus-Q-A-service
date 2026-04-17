import { Routes } from '@angular/router';
import { AnswerPageComponent } from './pages/answer-page.component';
import { HistoryPageComponent } from './pages/history-page.component';
import { QueryPageComponent } from './pages/query-page.component';
import { SummaryPageComponent } from './pages/summary-page.component';

export const routes: Routes = [
	{ path: '', pathMatch: 'full', redirectTo: 'query' },
	{ path: 'query', component: QueryPageComponent },
	{ path: 'answer', component: AnswerPageComponent },
	{ path: 'summary', component: SummaryPageComponent },
	{ path: 'history', component: HistoryPageComponent },
	{ path: '**', redirectTo: 'query' },
];
