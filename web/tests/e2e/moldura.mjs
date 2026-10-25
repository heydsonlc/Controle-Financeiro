// FIN-MIGRACAO-FIDELIDADE-FASE-1 — apoio dos specs: seletor de perfil e menu da moldura do Flask.
import { expect } from '@playwright/test';

// Troca pelo seletor do topo, como o usuario: abre o menu, escolhe o perfil e a pagina recarrega.
export async function trocarPerfil(page, nome) {
    await page.click('#perfil-financeiro-trigger');
    const opcao = page.locator('#perfil-financeiro-options .perfil-financeiro-option')
        .filter({ has: page.locator('strong', { hasText: new RegExp(`^${nome.replace(/[()]/g, '\\$&')}$`) }) });
    await Promise.all([page.waitForEvent('load'), opcao.click()]);
    await expect(page.locator('#perfil-financeiro-name')).toHaveText(nome);
}

export const nomesDosPerfis = (page) => page.locator('#perfil-financeiro-options .perfil-financeiro-option strong');
export const perfilAtivo = (page) => page.locator('#perfil-financeiro-name');
export const itemDoMenu = (page, chave) => page.locator(`.app-sidebar a.app-nav-link[data-pagina="${chave}"]`);

// Navega pelo menu como o usuario: no celular, abre antes a barra lateral pelo botao de menu.
export async function irPeloMenu(page, chave) {
    if (!(await page.locator('.app-sidebar').isVisible())) await page.click('.app-menu-button');
    await itemDoMenu(page, chave).click();
}
