const { test, expect } = require('@playwright/test');
const { attachConsoleErrorTracking } = require('./helpers/console');
const { smokeRoutes, diagnosticRoutes } = require('./helpers/routes');

test.describe('Smoke HTML routes', () => {
  for (const route of smokeRoutes) {
    test(`${route.label} (${route.path}) carrega sem erro critico`, async ({ page }) => {
      const consoleErrors = attachConsoleErrorTracking(page, route.path);

      const response = await page.goto(route.path, {
        waitUntil: 'domcontentloaded'
      });

      expect(response, `sem resposta HTTP para ${route.path}`).not.toBeNull();
      expect(response.status(), `status HTTP de ${route.path}`).toBe(200);
      expect(response.status(), `${route.path} nao deve retornar 500`).toBeLessThan(500);

      await expect(page.locator('body')).toBeVisible();

      const structuralSelector = 'main, .container, .dashboard-container, .page-container, .app-container, h1, h2';
      await expect(page.locator(structuralSelector).first()).toBeVisible();

      await page.waitForLoadState('networkidle').catch(() => {});
      consoleErrors.assertNoCriticalErrors();
    });
  }
});

test.describe('Rotas diagnosticas conhecidas', () => {
  for (const route of diagnosticRoutes) {
    test.skip(`${route.label} (${route.path}) - ${route.reason}`, async () => {});
  }
});
