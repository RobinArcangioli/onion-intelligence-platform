import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 25_000,
  use: {
    baseURL: 'http://127.0.0.1:8000',
    headless: true,
    screenshot: 'off',
    trace: 'off',
    video: 'off',
  },
  reporter: 'line',
});
