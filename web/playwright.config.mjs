// E2E do frontend estatico (CF-SUPABASE-REFACTOR-1). Executar via
// tests/e2e/run_e2e.py, que sobe o ambiente isolado e define CF_WEB_BASE_URL.
import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.CF_WEB_BASE_URL;
if (!baseURL) {
    throw new Error('CF_WEB_BASE_URL ausente: rode web/tests/e2e/run_e2e.py');
}

export default defineConfig({
    testDir: './tests/e2e',
    timeout: 30 * 1000,
    expect: { timeout: 10 * 1000 },
    fullyParallel: false,
    workers: 1,
    retries: 0,
    reporter: [['list']],
    outputDir: '../test-results/web',
    use: {
        baseURL,
        trace: 'retain-on-failure',
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
