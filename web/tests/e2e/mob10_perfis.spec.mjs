// FIN-MVP-MOBILE-10 — alternancia de perfis na pagina principal mobile (inicio.html): icone de usuario ao lado do sino que
// abre o menu dos perfis do usuario (meus_perfis) e grava a escolha como o seletor do desktop (perfil.js). Usuario A (varios
// perfis ficticios) e usuario G (um perfil). So leitura: nenhum dado financeiro e gravado.
import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const A = { id: 'aaaaaaaa-0000-4000-8000-00000000000a', email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP ou erros de JS').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/inicio.html**');
    await expect(page.locator('#mob-perfis')).toHaveAttribute('aria-label', /Perfil financeiro: /);
}

const menu = (page) => page.locator('#mob-menu-perfis');
const itens = (page) => menu(page).locator('.mob-menu-item');

test('icone ao lado do sino, do mesmo tamanho; o restante do cabecalho e da pagina como antes', async ({ page }) => {
    await entrar(page, A);
    const perfis = page.locator('#mob-perfis');
    const sino = page.locator('.mob-notificacoes');
    await expect(perfis).toBeVisible();
    const [p, s] = [await perfis.boundingBox(), await sino.boundingBox()];
    expect([Math.round(p.width), Math.round(p.height)]).toEqual([Math.round(s.width), Math.round(s.height)]);
    expect(p.x + p.width).toBeLessThanOrEqual(s.x + 1);  // a esquerda do sino
    expect(Math.abs(p.y - s.y)).toBeLessThanOrEqual(1);
    await expect(sino).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('h1.mob-titulo')).toHaveText('Financeiro');
    await expect(page.locator('.mob-grade .mob-atalho')).toHaveCount(8);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

test('menu com os perfis do usuario e o ativo marcado; trocar recarrega e vale para as paginas mobile', async ({ page }) => {
    await entrar(page, A);
    const meus = (await chamarRpc(page, 'meus_perfis', {})).corpo;
    expect(meus.length).toBeGreaterThan(1);
    await expect(menu(page)).toBeHidden();
    await page.click('#mob-perfis');
    await expect(menu(page)).toBeVisible();
    await expect(page.locator('#mob-perfis')).toHaveAttribute('aria-expanded', 'true');
    await expect(itens(page)).toHaveText(meus.map((m) => m.nome));
    await expect(menu(page).locator('[aria-checked="true"]')).toHaveCount(1);
    const ativo = await menu(page).locator('[aria-checked="true"]').innerText();
    // Esc e toque fora fecham sem trocar
    await page.keyboard.press('Escape');
    await expect(menu(page)).toBeHidden();
    await page.click('#mob-perfis');
    await page.locator('h1.mob-titulo').click();
    await expect(menu(page)).toBeHidden();
    // Escolher outro: grava como o desktop e recarrega na mesma competencia
    const outro = meus.find((m) => m.nome !== ativo);
    await page.click('#mob-mes-seguinte');
    const mes = new URL(page.url()).searchParams.get('mes');
    await page.click('#mob-perfis');
    await Promise.all([page.waitForEvent('load'), itens(page).filter({ hasText: outro.nome }).first().click()]);
    await expect(page.locator('#mob-perfis')).toHaveAttribute('aria-label', `Perfil financeiro: ${outro.nome}. Trocar perfil`);
    expect(new URL(page.url()).searchParams.get('mes')).toBe(mes);
    expect(await page.evaluate((id) => localStorage.getItem(`cf-perfil-ativo:${id}`), A.id)).toBe(String(outro.id));
    await page.click('#mob-perfis');
    await expect(menu(page).locator('[aria-checked="true"]')).toHaveText(outro.nome);
    // As paginas mobile abrem no perfil escolhido (a mesma escolha do desktop)
    await page.goto('/despesas-mobile.html');
    await expect(page.locator('#mob-perfil')).toHaveText(outro.nome);
    // Voltar ao perfil anterior pelo mesmo menu
    await page.goto('/inicio.html');
    await page.click('#mob-perfis');
    await Promise.all([page.waitForEvent('load'), itens(page).filter({ hasText: ativo }).first().click()]);
    await expect(page.locator('#mob-perfis')).toHaveAttribute('aria-label', `Perfil financeiro: ${ativo}. Trocar perfil`);
});

test('um perfil so: o menu mostra o perfil marcado; escolher o mesmo so fecha', async ({ page }) => {
    await entrar(page, G);
    await page.click('#mob-perfis');
    await expect(itens(page)).toHaveCount(1);
    await expect(itens(page)).toHaveAttribute('aria-checked', 'true');
    const antes = page.url();
    await itens(page).click();
    await expect(menu(page)).toBeHidden();
    expect(page.url()).toBe(antes);
});

for (const largura of [320, 430]) {
    test(`responsividade ${largura} px: icone, sino e menu cabem na tela`, async ({ page }) => {
        await page.setViewportSize({ width: largura, height: 800 });
        await entrar(page, A);
        const titulo = await page.locator('h1.mob-titulo').boundingBox();
        expect(titulo.x + titulo.width).toBeLessThanOrEqual((await page.locator('#mob-perfis').boundingBox()).x);  // sem sobrepor o titulo
        await page.click('#mob-perfis');
        const caixa = await menu(page).boundingBox();
        expect(caixa.x).toBeGreaterThanOrEqual(0);
        expect(caixa.x + caixa.width).toBeLessThanOrEqual(largura);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    });
}
