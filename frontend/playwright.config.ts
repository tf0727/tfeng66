import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', workers: 1, timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:8899', channel: 'msedge', headless: true, screenshot: 'only-on-failure' },
  reporter: [['list'], ['json', { outputFile: 'test-results/report.json' }]],
})
