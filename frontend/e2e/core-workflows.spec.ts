import { expect, test } from '@playwright/test';

const documents = [
  {
    document_id: 'doc-1',
    source_file: 'Hawthorne Analytics v Mercer.pdf',
    document_type: 'pdf',
    title: 'Hawthorne Analytics v Mercer',
    chunk_count: 23,
    jurisdiction: 'UK',
    court: 'Employment Tribunal',
    canonical_citation: null,
    decision_date: null,
    practice_area: null,
  },
];

test('documents workspace shows upload section and indexed documents', async ({ page }) => {
  await page.route('**/documents', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ documents }),
    });
  });

  await page.goto('/documents');

  await expect(page.getByTestId('upload-file-input')).toBeVisible();
  await expect(page.getByTestId('document-title')).toContainText('Hawthorne Analytics v Mercer.pdf');
});

test('documents workspace runs Q&A, summary and keywords for the selected document', async ({ page }) => {
  await page.route('**/documents', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ documents }) });
  });

  await page.route('**/query/answer', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        answer: 'The dismissal was procedurally unfair. [C1]',
        citations: [
          {
            id: 'C1',
            source_file: 'Hawthorne Analytics v Mercer.pdf',
            chunk_index: 0,
            page_range: '4',
            section_title: 'Procedural Fairness',
          },
        ],
        mode: 'evidence-direct',
      }),
    });
  });

  await page.route('**/query/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source_file: 'Hawthorne Analytics v Mercer.pdf',
        summary: '1. Unfair dismissal findings. [C1]',
        citations: [{ id: 'C1', source_file: 'Hawthorne Analytics v Mercer.pdf', chunk_index: 0 }],
        used_chunks: 1,
        mode: 'llm-summary',
      }),
    });
  });

  await page.route('**/query/keywords', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        document_id: 'doc-1',
        source_file: 'Hawthorne Analytics v Mercer.pdf',
        keywords: ['unfair dismissal', 'procedural fairness'],
      }),
    });
  });

  await page.goto('/documents');

  await page.getByTestId('doc-qa-button').first().click();
  await page.getByTestId('qa-input').fill('Why was the dismissal unfair?');
  await page.getByTestId('qa-run-button').click();
  await expect(page.getByTestId('qa-answer')).toContainText('procedurally unfair');
  await expect(page.getByTestId('qa-sources')).toContainText('C1');

  await page.getByTestId('action-summary').click();
  await page.getByTestId('summary-run-button').click();
  await expect(page.getByTestId('summary-text')).toContainText('Unfair dismissal');

  await page.getByTestId('action-keywords').click();
  await page.getByTestId('keywords-run-button').click();
  await expect(page.getByTestId('keywords-list')).toContainText('unfair dismissal');
});

test('history route supports import and export json', async ({ page }) => {
  await page.goto('/history');

  const importPayload = JSON.stringify([
    {
      id: 'imported-1',
      type: 'answer',
      timestamp: new Date().toISOString(),
      status: 'success',
      request: { question: 'x', document_id: 'doc-1', top_k: 5 },
      response: { answer: 'Imported answer [C1]', citations: [] },
    },
  ]);

  await page.getByTestId('history-import-input').setInputFiles({
    name: 'history.json',
    mimeType: 'application/json',
    buffer: Buffer.from(importPayload),
  });

  await expect(page.getByText('Imported 1 history entries.')).toBeVisible();
  await expect(page.getByTestId('history-list')).toContainText('Answer');

  const downloadPromise = page.waitForEvent('download');
  await page.getByTestId('history-export-button').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('rag-legal-history-');
});
