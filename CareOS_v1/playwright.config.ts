import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60000,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'on-first-retry' },
  webServer: [
    {
      command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: 'backend',
      env: { APP_ENV: 'test', DATABASE_URL: 'sqlite+aiosqlite:///./careos-e2e.db' },
      url: 'http://127.0.0.1:8000/api/v1/health',
      reuseExistingServer: true,
    },
    { command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], launchOptions: { args: ['--disable-gpu'] } } }],
})
