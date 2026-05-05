const { test, expect } = require('@playwright/test');
const { attachConsoleErrorTracking } = require('../helpers/console');
const { skipUnlessTestingEnvironment } = require('../helpers/api');
const { makeCategoriaNome } = require('../helpers/test-data');
const { assertModalAberto, assertTextoVisivel } = require('../helpers/assertions');

test.describe('Categorias — fluxo funcional', () => {

  test('[safe] abre modal Nova Categoria ao clicar no botão', async ({ page }) => {
    const consoleErrors = attachConsoleErrorTracking(page, '/categorias');
    await page.goto('/categorias', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-categoria-despesa').click();

    await assertModalAberto(page, '#modal-categoria');
    await expect(page.locator('#nome')).toBeVisible();
    await expect(page.locator('#descricao')).toBeVisible();

    consoleErrors.assertNoCriticalErrors();
  });

  test('[create] cria nova categoria e confirma aparece na lista', async ({ page, request }) => {
    await skipUnlessTestingEnvironment(test, request, 'TEST-2A');

    const consoleErrors = attachConsoleErrorTracking(page, '/categorias');
    const nome = makeCategoriaNome();

    await page.goto('/categorias', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-categoria-despesa').click();
    await assertModalAberto(page, '#modal-categoria');

    await page.locator('#nome').fill(nome);
    await page.locator('#descricao').fill('Categoria criada por teste E2E automatizado');

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#form-categoria button[type="submit"]').click();

    await page.waitForLoadState('networkidle').catch(() => {});

    await assertTextoVisivel(page, nome);
    consoleErrors.assertNoCriticalErrors();
  });

});
