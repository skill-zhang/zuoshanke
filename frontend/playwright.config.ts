import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 2,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:9002',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'cd .. && bash run-tests.sh server',
    port: 9002,
    reuseExistingServer: !process.env.CI,
  },
});
