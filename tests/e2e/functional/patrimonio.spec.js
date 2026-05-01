const { test, expect } = require('@playwright/test');
const { attachConsoleErrorTracking } = require('../helpers/console');
const { skipUnlessTestingEnvironment } = require('../helpers/api');
const { makeCaixinhaNome } = require('../helpers/test-data');
const { assertModalAberto, assertTextoVisivel } = require('../helpers/assertions');

test.describe('Patrimonio - fluxo funcional', () => {

  test('abre modal Nova Caixinha ao clicar no botao', async ({ page }) => {
    const consoleErrors = attachConsoleErrorTracking(page, '/patrimonio');
    await page.goto('/patrimonio', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-caixinha').click();

    await assertModalAberto(page, '#modal-conta');
    await expect(page.locator('#conta-nome')).toBeVisible();
    await expect(page.locator('#conta-tipo')).toBeVisible();
    await expect(page.locator('#conta-saldo-inicial')).toBeVisible();

    consoleErrors.assertNoCriticalErrors();
  });

  test('cria nova caixinha e confirma aparece na lista', async ({ page, request }) => {
    await skipUnlessTestingEnvironment(test, request, 'TEST-2B');

    const consoleErrors = attachConsoleErrorTracking(page, '/patrimonio');
    const nome = makeCaixinhaNome();

    await page.goto('/patrimonio', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-caixinha').click();
    await assertModalAberto(page, '#modal-conta');

    await page.locator('#conta-nome').fill(nome);
    await page.locator('#conta-tipo').selectOption('Reserva');
    await page.locator('#conta-saldo-inicial').fill('0');
    await page.locator('#conta-obs').fill('Caixinha criada por teste E2E automatizado');

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#form-conta button[type="submit"]').click();

    await page.waitForLoadState('networkidle').catch(() => {});

    await assertTextoVisivel(page, nome);
    consoleErrors.assertNoCriticalErrors();
  });

});
