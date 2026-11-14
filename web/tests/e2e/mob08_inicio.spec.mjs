// FIN-MVP-MOB-08 — pagina principal mobile. Ambiente isolado de run_e2e.py, conta ficticia A; nenhum dado e gravado.
// Celular: o login leva a inicio.html; atalhos e barra (so Inicio navega); competencia local; sem rolagem horizontal.
// Tablet e desktop: o login segue levando a contas.html. Destino pedido (?next=) e acesso sem sessao inalterados.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const EVIDENCIAS = process.env.CF_MOB08_EVIDENCIAS || '';
const CELULAR = { width: 390, height: 844 };
const ATALHOS = ['Receita', 'Despesa', 'Lançamento', 'Resumo', 'Pagamentos', 'Recorrências', 'Cartões', 'Contas'];

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    const dados = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => {
        const caminho = new URL(r.url()).pathname;
        if (caminho.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`);
        if (caminho.startsWith('/rest/v1') && /inicio\.html/.test(page.url())) dados.push(`${r.method()} ${caminho}`);
    });
    testInfo.problemas = problemas;
    testInfo.dados = dados;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
    expect(testInfo.dados, 'a pagina principal mobile nao le nem grava dados financeiros').toEqual([]);
});

async function entrar(page, url = '/index.html') {
    await page.goto(url);
    await page.fill('#email', A.email);
    await page.fill('#senha', A.senha);
    await page.click('#login-enviar');
}

function mesAtual(delta = 0) {
    const partes = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit' }).formatToParts(new Date());
    const [ano, mes] = ['year', 'month'].map((t) => Number(partes.find((p) => p.type === t).value));
    const d = new Date(Date.UTC(ano, mes - 1 + delta, 1));
    const chave = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
    const curto = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'][d.getUTCMonth()];
    return { chave, rotulo: `${curto}/${d.getUTCFullYear()}` };  // formato do mockup: "Nov/2026"
}

async function evidencia(page, nome) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`), fullPage: true });
}

test('sem sessao, inicio.html leva ao login e volta para ela', async ({ page }) => {
    await page.setViewportSize(CELULAR);
    await page.goto('/inicio.html');
    await page.waitForURL(/index\.html\?next=inicio\.html$/);
    await page.fill('#email', A.email);
    await page.fill('#senha', A.senha);
    await page.click('#login-enviar');
    await page.waitForURL(/\/inicio\.html\?mes=\d{4}-\d{2}$/);
});

// FIN-MVP-MOB-01: so o Resumo (atalho e barra) ficou habilitado, para a Lista de Despesas mobile; os demais seguem desabilitados.
// FIN-MVP-MOBILE-03: Cartoes tambem habilitado (Cartoes mobile); os demais seguem desabilitados.
// FIN-MVP-MOBILE-04: Receita tambem habilitado (Receitas mobile).
test('celular: login leva a pagina principal mobile, com so Resumo, Cartoes e Receita habilitados entre os atalhos e Inicio ativo', async ({ page }) => {
    await page.setViewportSize(CELULAR);
    await entrar(page);
    await page.waitForURL(/\/inicio\.html\?mes=\d{4}-\d{2}$/);
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('.mob-titulo')).toHaveText('Financeiro');
    await expect(page.locator('.mob-notificacoes')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#mob-competencia')).toHaveText(mesAtual().rotulo);

    const atalhos = page.locator('.mob-grade .mob-atalho');
    await expect(atalhos.locator('.mob-atalho-nome')).toHaveText(ATALHOS);
    for (let i = 0; i < ATALHOS.length; i += 1) {
        await expect(atalhos.nth(i)).toBeVisible();
        const destino = { Resumo: 'despesas-mobile.html', Cartões: 'cartoes-mobile.html', Receita: 'receitas-mobile.html' }[ATALHOS[i]];
        if (destino) {
            await expect(atalhos.nth(i)).not.toHaveAttribute('aria-disabled', 'true');
            await expect(atalhos.nth(i)).toHaveAttribute('href', `${destino}?mes=${mesAtual().chave}`);
            continue;
        }
        await expect(atalhos.nth(i)).toHaveAttribute('aria-disabled', 'true');
        await expect(atalhos.nth(i)).not.toHaveAttribute('href', /.*/);
    }
    // ajustes da homologacao: botoes mais baixos (80 px) e menos espaco entre a competencia e a grade (12 px)
    const medidas = await page.evaluate(() => ({
        altura: Math.round(document.querySelector('.mob-atalho').getBoundingClientRect().height),
        espaco: Math.round(document.querySelector('.mob-grade').getBoundingClientRect().top - document.querySelector('.mob-competencia').getBoundingClientRect().bottom),
    }));
    expect(medidas).toEqual({ altura: 80, espaco: 12 });
    // 2 colunas x 4 linhas
    const caixas = await atalhos.evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top)]; }));
    expect(new Set(caixas.map(([x]) => x)).size).toBe(2);
    expect(new Set(caixas.map(([, y]) => y)).size).toBe(4);

    const antes = page.url();
    // desabilitados: o clique (forcado, como o toque) nao navega
    await atalhos.nth(1).click({ force: true });
    await page.locator('.mob-barra-item').nth(1).click({ force: true });
    await page.locator('.mob-notificacoes').click({ force: true });
    expect(page.url()).toBe(antes);

    const barra = page.locator('.mob-barra .mob-barra-item');
    await expect(barra).toHaveText(['Início', 'Lançar', 'Resumo', 'Mais']);
    await expect(barra.nth(0)).toHaveAttribute('href', `inicio.html?mes=${mesAtual().chave}`);
    await expect(barra.nth(0)).toHaveAttribute('aria-current', 'page');
    await expect(barra.nth(3)).toHaveAttribute('aria-haspopup', 'menu');
    await expect(barra.nth(1)).toHaveAttribute('aria-disabled', 'true');
    await expect(barra.nth(1)).not.toHaveAttribute('href', /.*/);
    await expect(barra.nth(2)).not.toHaveAttribute('aria-disabled', 'true');
    await expect(barra.nth(2)).toHaveAttribute('href', `despesas-mobile.html?mes=${mesAtual().chave}`);
    const corInicio = await barra.nth(0).evaluate((e) => getComputedStyle(e).color);
    expect(corInicio).toBe('rgb(29, 29, 31)');  // preto do menu lateral do desktop (#1d1d1f)
    await evidencia(page, 'celular-390x844');
});

test('celular: competencia navega entre meses so na interface', async ({ page }) => {
    await page.setViewportSize(CELULAR);
    await entrar(page);
    await page.waitForURL(/\/inicio\.html/);
    await page.click('#mob-mes-seguinte');
    await expect(page.locator('#mob-competencia')).toHaveText(mesAtual(1).rotulo);
    await expect(page).toHaveURL(new RegExp(`mes=${mesAtual(1).chave}$`));
    await page.click('#mob-mes-anterior');
    await page.click('#mob-mes-anterior');
    await expect(page.locator('#mob-competencia')).toHaveText(mesAtual(-1).rotulo);
    await page.reload();
    await expect(page.locator('#mob-competencia')).toHaveText(mesAtual(-1).rotulo);  // atualizar a pagina mantem o mes
    await page.click('.mob-barra-item.ativo');  // Inicio recarrega a pagina principal mantendo o mes escolhido
    await page.waitForURL(new RegExp(`inicio\\.html\\?mes=${mesAtual(-1).chave}$`));
    await expect(page.locator('#mob-competencia')).toHaveText(mesAtual(-1).rotulo);
    await page.goto('/inicio.html?mes=2026-13');
    await expect(page.locator('#mob-competencia')).toHaveText(mesAtual().rotulo);  // mes invalido: competencia atual
});

test('celular: Mais abre o menu com Sair, que encerra a sessao', async ({ page }) => {
    await page.setViewportSize(CELULAR);
    await entrar(page);
    await page.waitForURL(/\/inicio\.html/);
    const menu = page.locator('#mob-menu-mais');
    await expect(menu).toBeHidden();
    await page.click('#mob-mais');
    await expect(menu).toBeVisible();
    await expect(page.locator('#mob-mais')).toHaveAttribute('aria-expanded', 'true');
    await evidencia(page, 'celular-390x844-mais');
    await page.keyboard.press('Escape');  // Esc fecha
    await expect(menu).toBeHidden();
    await page.click('#mob-mais');
    await page.click('.mob-titulo');  // toque fora fecha
    await expect(menu).toBeHidden();
    await page.click('#mob-mais');
    await page.click('#mob-sair');
    await page.waitForURL(/\/index\.html$/);
    expect(await page.evaluate(() => localStorage.getItem('cf-financeiro-auth'))).toBeNull();
    await page.goto('/inicio.html');
    await page.waitForURL(/index\.html\?next=inicio\.html$/);  // sem sessao, volta a exigir login
});

test('celular: sem rolagem horizontal nem corte nas larguras moveis', async ({ page }) => {
    await page.setViewportSize(CELULAR);
    await entrar(page);
    await page.waitForURL(/\/inicio\.html/);
    for (const [largura, altura] of [[320, 568], [360, 740], [375, 667], [390, 844], [412, 915], [430, 932]]) {
        await page.setViewportSize({ width: largura, height: altura });
        const medida = await page.evaluate(() => {
            const dentro = (e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 0.5; };
            const barra = document.querySelector('.mob-barra').getBoundingClientRect();
            window.scrollTo(0, document.documentElement.scrollHeight);
            const ultima = [...document.querySelectorAll('.mob-atalho')].at(-1).getBoundingClientRect();
            const topoBarra = document.querySelector('.mob-barra').getBoundingClientRect().top;
            const cortados = [...document.querySelectorAll('.mob-atalho-nome, .mob-barra-item span, .mob-competencia-mes, .mob-titulo')]
                .filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent);
            window.scrollTo(0, 0);
            return {
                rolagem: document.documentElement.scrollWidth - window.innerWidth,
                foraDaTela: [...document.querySelectorAll('.mob-cabecalho, .mob-competencia, .mob-atalho, .mob-barra-item')].filter((e) => !dentro(e)).length,
                barraNoRodape: Math.round(barra.bottom) === window.innerHeight,
                ultimaLinhaVisivel: ultima.bottom <= topoBarra + 0.5,
                cortados,
            };
        });
        expect(medida, `${largura}x${altura}`).toEqual({ rolagem: 0, foraDaTela: 0, barraNoRodape: true, ultimaLinhaVisivel: true, cortados: [] });
        if (largura === 360 || largura === 320) await evidencia(page, `celular-${largura}x${altura}`);
    }
});

test('celular: destino pedido continua valendo e o login com sessao vai para a pagina mobile', async ({ page }) => {
    await page.setViewportSize(CELULAR);
    await entrar(page, '/index.html?next=receitas.html');
    await page.waitForURL('**/receitas.html');
    await page.goto('/index.html');
    await page.waitForURL(/\/inicio\.html/);
});

for (const [nome, tamanho] of [['tablet', { width: 820, height: 1180 }], ['desktop', { width: 1366, height: 900 }]]) {
    test(`${nome}: login segue levando a Despesas (contas.html) com a moldura do desktop`, async ({ page }) => {
        await page.setViewportSize(tamanho);
        await entrar(page);
        await page.waitForURL('**/contas.html');
        await expect(page.locator('#app-sidebar')).toBeAttached();
        await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', /\d{2}\/\d{4}/);
        if (nome === 'desktop') await evidencia(page, 'desktop-1366x900-contas');
        // a pagina mobile aberta direto no desktop fica centrada, sem quebrar
        await page.goto('/inicio.html');
        await expect(page.locator('.mob-grade .mob-atalho')).toHaveCount(8);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBe(0);
        if (nome === 'desktop') await evidencia(page, 'desktop-1366x900-inicio');
    });
}
