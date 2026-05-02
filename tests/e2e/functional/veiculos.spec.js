const { test, expect } = require('@playwright/test');
const { attachConsoleErrorTracking } = require('../helpers/console');
const { skipUnlessTestingEnvironment } = require('../helpers/api');
const { makeVeiculoNome } = require('../helpers/test-data');
const { assertModalAberto, assertTextoVisivel } = require('../helpers/assertions');

test.describe('Veiculos - fluxo funcional', () => {

  test('[safe] abre modal Novo Veiculo ao clicar no botao', async ({ page }) => {
    const consoleErrors = attachConsoleErrorTracking(page, '/veiculos');
    await page.goto('/veiculos', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-novo-veiculo').click();

    await assertModalAberto(page, '#modal-veiculo');
    await expect(page.locator('#nome')).toBeVisible();
    await expect(page.locator('#tipo')).toBeVisible();
    await expect(page.locator('#combustivel')).toBeVisible();
    await expect(page.locator('#autonomia_km_l')).toBeVisible();

    consoleErrors.assertNoCriticalErrors();
  });

  test('[create] cria novo veiculo simulado e confirma aparece na lista', async ({ page, request }) => {
    await skipUnlessTestingEnvironment(test, request, 'TEST-2B');

    const consoleErrors = attachConsoleErrorTracking(page, '/veiculos');
    const nome = makeVeiculoNome();

    await page.goto('/veiculos', { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});

    await page.locator('#btn-novo-veiculo').click();
    await assertModalAberto(page, '#modal-veiculo');

    await page.locator('#nome').fill(nome);
    await page.locator('#tipo').selectOption('carro');
    await page.locator('#combustivel').selectOption('gasolina');
    await page.locator('#autonomia_km_l').fill('12');
    await page.locator('#status').selectOption('SIMULADO');

    page.on('dialog', async (dialog) => {
      await dialog.accept();
    });

    await page.locator('#form-veiculo button[type="submit"]').click();

    await page.waitForLoadState('networkidle').catch(() => {});

    await assertTextoVisivel(page, nome);
    consoleErrors.assertNoCriticalErrors();
  });

});
