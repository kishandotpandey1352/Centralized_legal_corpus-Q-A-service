import { expect, test } from '@playwright/test';

test('query route executes and displays results', async ({ page }) => {
  await page.route('**/query/retrieve', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'material breach',
        top_k: 2,
        results: [
          {
            chunk_id: 'chunk-1',
            source_file: 'sample_service_agreement.txt',
            chunk_index: 0,
            chunk_text: 'A 30-day cure period applies before termination. ',
            score: 0.88,
          },
        ],
      }),
    });
  });

  await page.goto('/query');
  await page.getByTestId('query-input').fill('What is cure period?');
  await page.getByTestId('query-run-button').click();

  await expect(page.getByTestId('query-result-block')).toBeVisible();
  await expect(page.getByText('sample_service_agreement.txt')).toBeVisible();
  await expect(page.getByText('30-day cure period')).toBeVisible();
});

test('answer and summary routes render side-by-side citation inspector', async ({ page }) => {
  await page.route('**/query/answer', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        answer: 'The agreement requires a cure period before termination. [C1] [C2]',
        citations: [
          {
            citation_id: 'C1',
            source_file: 'sample_service_agreement.txt',
            chunk_index: 0,
            chunk_text: 'Material breach requires written notice. ',
          },
          {
            citation_id: 'C2',
            source_file: 'sample_service_agreement.txt',
            chunk_index: 1,
            chunk_text: 'Termination occurs if not cured within 30 days. ',
          },
        ],
      }),
    });
  });

  await page.route('**/query/summary', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        source_file: 'sample_service_agreement.txt',
        summary: '1. Notice required for breach. [C1] 2. Cure period is 30 days. [C2]',
        mode: 'llm-summary',
        used_chunks: 2,
        citations: [
          {
            citation_id: 'C1',
            source_file: 'sample_service_agreement.txt',
            chunk_index: 0,
            chunk_text: 'Notice obligation details.',
          },
          {
            citation_id: 'C2',
            source_file: 'sample_service_agreement.txt',
            chunk_index: 1,
            chunk_text: 'Thirty day cure period details.',
          },
        ],
      }),
    });
  });

  await page.goto('/answer');
  await page.getByTestId('answer-input').fill('What happens before termination?');
  await page.getByTestId('answer-run-button').click();
  await expect(page.getByTestId('answer-text')).toContainText('cure period before termination');
  await expect(page.getByTestId('citation-inspector')).toBeVisible();
  await page.getByTestId('citation-pill-1').click();
  await expect(page.getByTestId('citation-detail')).toContainText('30 days');

  await page.goto('/summary');
  await page.getByTestId('summary-source-input').fill('sample_service_agreement.txt');
  await page.getByTestId('summary-run-button').click();
  await expect(page.getByTestId('summary-text')).toContainText('Cure period is 30 days');
  await expect(page.getByTestId('citation-inspector')).toBeVisible();
});

test('history route supports export and import json', async ({ page }) => {
  await page.route('**/query/retrieve', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ query: 'x', top_k: 1, results: [] }),
    });
  });

  await page.goto('/query');
  await page.getByTestId('query-input').fill('seed history');
  await page.getByTestId('query-run-button').click();

  await page.goto('/history');
  await expect(page.getByTestId('history-list')).toContainText('Query');

  const downloadPromise = page.waitForEvent('download');
  await page.getByTestId('history-export-button').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('rag-legal-history-');

  const importPayload = JSON.stringify([
    {
      id: 'imported-1',
      type: 'summary',
      timestamp: new Date().toISOString(),
      status: 'success',
      request: { source_file: 'sample_service_agreement.txt', max_chunks: 6 },
      response: { summary: 'Imported summary', citations: [] },
    },
  ]);

  await page.getByTestId('history-import-input').setInputFiles({
    name: 'history.json',
    mimeType: 'application/json',
    buffer: Buffer.from(importPayload),
  });

  await expect(page.getByText('Imported 1 history entries.')).toBeVisible();
  await expect(page.getByTestId('history-list')).toContainText('Summary');
});
