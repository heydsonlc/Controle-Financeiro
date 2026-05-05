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
  const matches = page.getByText(texto, { exact: false });
  await expect.poll(async () => {
    const total = await matches.count();
    for (let index = 0; index < total; index += 1) {
      if (await matches.nth(index).isVisible().catch(() => false)) {
        return true;
      }
    }
    return false;
  }, { timeout: 5000 }).toBe(true);
}

module.exports = { assertModalAberto, assertTextoVisivel };
