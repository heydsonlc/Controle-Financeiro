/**
 * Asserções reutilizáveis para testes E2E funcionais.
 */

const { expect } = require('@playwright/test');

/**
 * Verifica que um modal está visível na página.
 * @param {import('@playwright/test').Page} page
 * @param {string} selector - ex: '#modal-categoria'
 */
async function assertModalAberto(page, selector) {
  const modal = page.locator(selector);
  await expect(modal).toBeVisible({ timeout: 5000 });
}

/**
 * Verifica que um texto está visível em algum lugar na página.
 * @param {import('@playwright/test').Page} page
 * @param {string} texto
 */
async function assertTextoVisivel(page, texto) {
  await expect(page.getByText(texto, { exact: false })).toBeVisible({ timeout: 5000 });
}

module.exports = { assertModalAberto, assertTextoVisivel };
