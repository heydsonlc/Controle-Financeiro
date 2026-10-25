// FIN-MIGRACAO-FIDELIDADE-FASE-1 — moldura do Flask: barra lateral, barra superior, navegacao, menu no celular,
// itens "Em migracao", Alertas, Ajuda e saida. Dados FICTICIOS (tests/supabase_local.py). So leitura.
import { expect, test } from '@playwright/test';

import { esperarMes } from './despesas.mjs';

import { itemDoMenu, perfilAtivo, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };

const MENU_DO_FLASK = [
    ['Dashboard', ['Dashboard']],
    ['Operação', ['Lançamentos', 'Despesas', 'Recorrencias']],
    ['Gestão Financeira', ['Receitas', 'Cartões', 'Contas Bancárias', 'Financiamentos', 'Patrimônio', 'Documentos Fiscais']],
    ['Cadastros', ['Categorias', 'Mobilidade']],
    ['Ferramentas', ['Importar Cartão']],
    ['Sistema', ['Configurações e Preferências', 'Ajuda e Manual']],
];
const MIGRADAS = [
    ['despesas', 'contas.html', 'Gerenciamento de Despesas'],
    ['recorrencias', 'recorrencias.html', 'Recorrencias'],  // FIN-FIDELIDADE-RECORRENCIAS-1
    ['receitas', 'receitas.html', 'Gerenciamento de Receitas'],
    ['cartoes', 'cartoes.html', 'Cartões'],
    ['importar_cartao', 'importar-cartao.html', 'Importar Cartão'],  // FIN-FIDELIDADE-CARTOES-1
    ['categorias', 'categorias.html', 'Categorias'],
    ['configuracoes', 'configuracoes.html', 'Configurações e Preferências'],
    ['ajuda', 'ajuda.html', 'Central de Ajuda e Manual de Uso'],
];
const EM_MIGRACAO = [
    ['dashboard', 'dashboard.html', 'Dashboard Financeiro'],
    ['lancamentos', 'lancamentos.html', 'Lançamentos'],
    ['contas_bancarias', 'contas-bancarias.html', 'Contas Bancárias'],
    ['financiamentos', 'financiamentos.html', 'Financiamentos'],
    ['patrimonio', 'patrimonio.html', 'Patrimônio'],
    ['imposto_renda', 'documentos-fiscais.html', 'Imposto de Renda'],
    ['veiculos', 'mobilidade.html', 'Mobilidade'],
];

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('requestfailed', (req) => {
        if (req.failure()?.errorText !== 'net::ERR_ABORTED') problemas.push(`requestfailed: ${req.url()} ${req.failure()?.errorText}`);
    });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', A.email);
    await page.fill('#senha', A.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function menu(page) {
    return page.locator('.app-nav-section').evaluateAll((secoes) => secoes.map((secao) => [
        secao.querySelector('.app-nav-section-title').textContent.trim(),
        [...secao.querySelectorAll('.app-nav-text')].map((t) => t.textContent.trim()),
    ]));
}

test.describe('computador', () => {
    test.use({ viewport: { width: 1366, height: 900 } });

    test('menu, secoes, icones e barra superior do Flask; Despesas ativo e perfil padrao no topo', async ({ page }) => {
        await entrar(page);
        expect(await menu(page)).toEqual(MENU_DO_FLASK);
        await expect(page.locator('.app-sidebar .app-icon svg')).toHaveCount(15);
        await expect(page.locator('.app-nav-link.active')).toHaveText(/Despesas/);
        await expect(page.locator('.app-topbar-title')).toHaveText('Gerenciamento de Despesas');
        await expect(perfilAtivo(page)).toHaveText('Pessoal');
        await expect(page.locator('#perfil-financeiro-type')).toHaveText('Pessoal');
        await expect(page.locator('#perfil-financeiro-avatar')).toHaveText('PE');
        await expect(page.locator('.app-topbar a[href="ajuda.html"]')).toBeVisible();
        await expect(page.locator('#app-alertas-button')).toBeVisible();
        await expect(page.locator('#app-logout-button')).toBeVisible();
        // Itens ainda nao migrados ficam visiveis e marcados com discricao.
        for (const [chave] of EM_MIGRACAO) {
            await expect(itemDoMenu(page, chave).locator('.app-nav-status')).toHaveText('Em migração');
        }
        for (const [chave] of MIGRADAS) await expect(itemDoMenu(page, chave).locator('.app-nav-status')).toHaveCount(0);
    });

    test('navegacao pelo menu: cada item abre a sua pagina, ativo e titulo corretos, nunca uma pagina quebrada', async ({ page }) => {
        await entrar(page);
        for (const [chave, arquivo, titulo] of [...MIGRADAS, ...EM_MIGRACAO]) {
            await itemDoMenu(page, chave).click();
            await page.waitForURL(new RegExp(`/${arquivo.replace('.', '\\.')}(\\?|#|$)`));
            await expect(itemDoMenu(page, chave)).toHaveClass(/active/);
            await expect(page.locator('.app-nav-link.active')).toHaveCount(1);
            await expect(page.locator('.app-topbar-title')).toHaveText(titulo);
            await expect(perfilAtivo(page)).toHaveText('Pessoal');
        }
    });

    test('paginas em migracao sao informativas e nao leem dados', async ({ page }) => {
        await entrar(page);
        await page.waitForLoadState('networkidle');  // chamadas da pagina de Contas ja encerradas
        const chamadas = [];
        page.on('request', (req) => { if (/\/rest\/v1\/rpc\//.test(req.url())) chamadas.push(req.url().split('/rpc/')[1]); });
        for (const [, arquivo, titulo] of EM_MIGRACAO) {
            chamadas.length = 0;
            await page.goto(`/${arquivo}`);
            await expect(page.locator('.modulo-em-migracao-titulo')).toHaveText(titulo);
            await expect(page.locator('.modulo-em-migracao-selo')).toHaveText('Em migração');
            await expect(perfilAtivo(page)).toHaveText('Pessoal');
            expect(chamadas).toEqual(['meus_perfis']);  // so o seletor de perfil
        }
    });

    test('perfil escolhido permanece ao navegar pelas paginas', async ({ page }) => {
        await entrar(page);
        await page.goto('/contas.html?mes=2026-11');
        await trocarPerfil(page, 'Empresa');
        await esperarMes(page, '2026-11');
        await expect(page.locator('#despesas-lista .despesa-cell-nome')).toHaveText(['Fatura Cartao Empresa - 11/2026', 'Contador 11/2026']);
        await itemDoMenu(page, 'receitas').click();
        await page.waitForURL(/receitas\.html\?mes=2026-11$/);  // competencia mantida
        await expect(perfilAtivo(page)).toHaveText('Empresa');
        await itemDoMenu(page, 'categorias').click();
        await expect(perfilAtivo(page)).toHaveText('Empresa');
        await expect(page.locator('#contas-corpo tr td:nth-child(2)')).toHaveText(['Conta Empresa (A)']);
        await itemDoMenu(page, 'dashboard').click();
        await expect(perfilAtivo(page)).toHaveText('Empresa');
        await page.click('#perfil-financeiro-trigger');
        await expect(page.locator('.perfil-financeiro-option.active')).toContainText('Empresa');
        await expect(page.locator('.perfil-financeiro-option.active small')).toHaveText('Empresa · somente leitura atual');
        await expect(page.locator('#usuario-email')).toHaveText(`Conectado como ${A.email}`);
        await expect(page.locator('.perfil-financeiro-config')).toHaveAttribute('href', 'configuracoes.html#perfis-financeiros');
    });

    test('Alertas mostra estado informativo; Ajuda abre o manual original', async ({ page }) => {
        await entrar(page);
        await expect(page.locator('#app-alertas-aviso')).toBeHidden();
        await page.click('#app-alertas-button');
        await expect(page.locator('#app-alertas-aviso')).toHaveText('Alertas: em migração para o novo aplicativo.');
        await page.locator('.app-topbar-title').click();
        await expect(page.locator('#app-alertas-aviso')).toBeHidden();
        await page.click('.app-topbar a[href="ajuda.html"]');
        await page.waitForURL('**/ajuda.html');
        await expect(page.locator('#help-article h2, #help-article h3').first()).toBeVisible();
        await expect(page.locator('#help-nav-list button').first()).toBeVisible();
        await page.fill('#help-search-input', 'perfis');
        await expect(page.locator('#help-nav-list')).toContainText('Perfis Financeiros');
    });

    test('sair pela barra superior encerra a sessao em qualquer pagina', async ({ page }) => {
        await entrar(page);
        await page.goto('/importar-cartao.html');
        await page.click('#app-logout-button');
        await page.waitForURL('**/index.html');
        await page.goto('/configuracoes.html');
        await page.waitForURL(/index\.html\?next=configuracoes\.html$/);
    });
});

test.describe('celular', () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    test('botao de menu abre e fecha a barra lateral (fundo, Esc e escolha de item)', async ({ page }) => {
        await entrar(page);
        const barra = page.locator('.app-sidebar');
        const botao = page.locator('.app-menu-button');
        await expect(barra).toBeHidden();
        await expect(botao).toHaveAttribute('aria-expanded', 'false');
        const caixa = await botao.boundingBox();
        expect(caixa.width).toBeGreaterThanOrEqual(40);  // tamanho do Flask
        expect(caixa.height).toBeGreaterThanOrEqual(40);

        await botao.click();
        await expect(barra).toBeVisible();
        await expect(botao).toHaveAttribute('aria-expanded', 'true');
        expect(await menu(page)).toEqual(MENU_DO_FLASK);
        await page.locator('#app-menu-fundo').click({ position: { x: 370, y: 400 } });
        await expect(barra).toBeHidden();

        await botao.click();
        await expect(barra).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(barra).toBeHidden();

        await botao.click();
        await itemDoMenu(page, 'receitas').click();
        await page.waitForURL(/receitas\.html(\?mes=\d{4}-\d{2})?$/);  // Despesas registra a competencia no endereco
        await expect(barra).toBeHidden();
        await expect(page.locator('.app-topbar-title')).toHaveText('Gerenciamento de Receitas');
        const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
        expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
    });

    test('seletor de perfil funciona no celular', async ({ page }) => {
        await entrar(page);
        await page.goto('/contas.html?mes=2026-11');
        await expect(page.locator('#perfil-financeiro-avatar')).toBeVisible();
        await trocarPerfil(page, 'Empresa');
        await esperarMes(page, '2026-11');
        await expect(page.locator('#despesas-lista .despesa-cell-nome')).toHaveText(['Fatura Cartao Empresa - 11/2026', 'Contador 11/2026']);
        const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
        expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
    });
});
