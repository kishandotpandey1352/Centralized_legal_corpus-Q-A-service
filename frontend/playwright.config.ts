import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:4210',
    trace: 'on-first-retry',
  },
  webServer: {
    command: '"C:/Program Files/nodejs/node.exe" ./node_modules/@angular/cli/bin/ng.js serve --host 127.0.0.1 --port 4210 --no-open',
    port: 4210,
    reuseExistingServer: true,
    timeout: 120000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
