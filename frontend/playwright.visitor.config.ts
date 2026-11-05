import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e',testMatch:'visitor.spec.ts',workers:1,retries:0,timeout:25000,
  use:{baseURL:'http://127.0.0.1:8010',headless:true,screenshot:'off',trace:'off',video:'off'},
  webServer:{command:`${process.env.OIP_E2E_PYTHON || 'python3'} ../scripts/serve-visitor-demo.py`,
    url:'http://127.0.0.1:8010/api/health',reuseExistingServer:false,timeout:20000},
  reporter:'line',
});
