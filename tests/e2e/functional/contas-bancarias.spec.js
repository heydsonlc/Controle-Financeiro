const { test, expect } = require('@playwright/test');
const { attachConsoleErrorTracking } = require('../helpers/console');
const { skipUnlessTestingEnvironment } = require('../helpers/api');
const { makeContaNome } = require('../helpers/test-data');
const { assertModalAberto, assertTextoVisivel } = require('../helpers/assertions');

test.describe('Contas Bancárias — fluxo funcional', () => {

  test('[safe] abre modal Nova Conta ao clicar no botão', async ({ page }) => {
    const consoleErrors = attachConsoleErrorTracking(page, '/contas-bancarias');
    await page.goto('/contas-bancarias', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-conta').click();

    await assertModalAberto(page, '#modal-conta');
    await expect(page.locator('#conta-nome')).toBeVisible();
    await expect(page.locator('#conta-instituicao')).toBeVisible();
    await expect(page.locator('#conta-tipo')).toBeVisible();

    consoleErrors.assertNoCriticalErrors();
  });

  test('[create] cria nova conta bancária e confirma aparece na lista', async ({ page, request }) => {
    await skipUnlessTestingEnvironment(test, request, 'TEST-2A');

    const consoleErrors = attachConsoleErrorTracking(page, '/contas-bancarias');
    const nome = makeContaNome();

    await page.goto('/contas-bancarias', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-conta').click();
    await assertModalAberto(page, '#modal-conta');

    await page.locator('#conta-nome').fill(nome);
    await page.locator('#conta-instituicao').selectOption('Nubank');
    await page.locator('#conta-tipo').selectOption('Carteira Digital');

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#form-conta button[type="submit"]').click();

    await page.waitForLoadState('networkidle').catch(() => {});

    await assertTextoVisivel(page, nome);
    consoleErrors.assertNoCriticalErrors();
  });

});
