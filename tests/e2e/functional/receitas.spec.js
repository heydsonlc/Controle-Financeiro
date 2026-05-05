const { test, expect } = require('@playwright/test');
const { attachConsoleErrorTracking } = require('../helpers/console');
const { skipUnlessTestingEnvironment } = require('../helpers/api');
const { makeFonteNome } = require('../helpers/test-data');
const { assertModalAberto, assertTextoVisivel } = require('../helpers/assertions');

test.describe('Receitas — fluxo funcional (Fonte)', () => {

  test('[safe] abre modal Nova Fonte ao clicar no botão', async ({ page }) => {
    const consoleErrors = attachConsoleErrorTracking(page, '/receitas');
    await page.goto('/receitas', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-receita').click();

    await assertModalAberto(page, '#modal-fonte');
    await expect(page.locator('#fonte-nome')).toBeVisible();
    await expect(page.locator('#fonte-tipo')).toBeVisible();

    consoleErrors.assertNoCriticalErrors();
  });

  test('[create] cria nova fonte de receita recorrente e confirma aparece na lista', async ({ page, request }) => {
    await skipUnlessTestingEnvironment(test, request, 'TEST-2A');

    const consoleErrors = attachConsoleErrorTracking(page, '/receitas');
    const nome = makeFonteNome();

    await page.goto('/receitas', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-receita').click();
    await assertModalAberto(page, '#modal-fonte');

    await page.locator('#fonte-nome').fill(nome);
    await page.locator('#fonte-tipo').selectOption('RENDA_EXTRA');
    await page.locator('#fonte-valor-base').fill('500,00');
    await page.locator('#fonte-dia-pagamento').selectOption('5');

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#form-fonte button[type="submit"]').click();

    await page.waitForLoadState('networkidle').catch(() => {});

    await assertTextoVisivel(page, nome);
    consoleErrors.assertNoCriticalErrors();
  });

});
