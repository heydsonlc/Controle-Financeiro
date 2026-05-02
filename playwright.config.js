// @ts-check
const { defineConfig, devices } = require('@playwright/test');

const isWindows = process.platform === 'win32';
const flaskServerScript = [
  "from backend.app import create_app",
  "from backend.models import db",
  "app = create_app('testing')",
  "ctx = app.app_context()",
  "ctx.push()",
  "db.create_all()",
  "app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)"
].join('; ');
const pythonCommand = isWindows
  ? `set FLASK_ENV=testing&& set FLASK_DEBUG=0&& venv\\Scripts\\python.exe -c "${flaskServerScript}"`
  : `FLASK_ENV=testing FLASK_DEBUG=0 python -c "${flaskServerScript}"`;

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 45 * 1000,
  expect: {
    timeout: 10 * 1000
  },
  fullyParallel: false,
  reporter: [
    ['list'],
    ['html', { open: 'never' }]
  ],
  use: {
    baseURL: 'http://127.0.0.1:5000',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: {
    command: pythonCommand,
    url: 'http://127.0.0.1:5000/health',
    reuseExistingServer: true,
    timeout: 120 * 1000,
    stdout: 'pipe',
    stderr: 'pipe'
  }
});
