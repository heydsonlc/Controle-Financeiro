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

  test('[create] cria nova fonte de receita (não-recorrente) e confirma aparece na lista', async ({ page, request }) => {
    await skipUnlessTestingEnvironment(test, request, 'TEST-2A');

    const consoleErrors = attachConsoleErrorTracking(page, '/receitas');
    const nome = makeFonteNome();

    await page.goto('/receitas', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-nova-receita').click();
    await assertModalAberto(page, '#modal-fonte');

    await page.locator('#fonte-nome').fill(nome);
    await page.locator('#fonte-tipo').selectOption('RENDA_EXTRA');

    // #fonte-recorrente vem checked por padrão — desmarcar para não gerar orçamentos automáticos
    const recorrente = page.locator('#fonte-recorrente');
    if (await recorrente.isChecked()) {
      await recorrente.uncheck();
    }

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#form-fonte button[type="submit"]').click();

    await page.waitForLoadState('networkidle').catch(() => {});

    await assertTextoVisivel(page, nome);
    consoleErrors.assertNoCriticalErrors();
  });

});
