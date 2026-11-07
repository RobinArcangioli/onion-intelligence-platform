import { defineConfig } from '@playwright/test';

const modes: Record<string, { testMatch: string; flag: string }> = {
  visitor: { testMatch: 'visitor.spec.ts', flag: '' },
  simulation: { testMatch: 'simulation.spec.ts', flag: '--simulation' },
  acceptance: { testMatch: 'collection-acceptance.spec.ts', flag: '--acceptance' },
};
const modeName = process.env.OIP_E2E_MODE ?? 'visitor';
if (!Object.hasOwn(modes, modeName)) throw new Error('Unknown OIP browser fixture mode');
const mode = modes[modeName];
const baseURL = 'http://127.0.0.1:8000';

export default defineConfig({
  testDir: './e2e', testMatch: mode.testMatch, workers: 1, retries: 0, timeout: 45_000,
  use: {
    baseURL, actionTimeout: 10_000, timezoneId: 'UTC', headless: true, screenshot: 'off',
    trace: 'off', video: 'off', serviceWorkers: 'block',
  },
  webServer: {
    command: '"${OIP_E2E_PYTHON:-python3}" ../scripts/serve-visitor-demo.py ' + mode.flag,
    url: `${baseURL}/api/health`, reuseExistingServer: false, timeout: 20_000,
  },
  reporter: 'line',
});
