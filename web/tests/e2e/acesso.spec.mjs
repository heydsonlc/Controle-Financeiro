// Controle de acesso do primeiro modulo (categorias somente leitura).
// Dados e contas ficticios do ambiente isolado de run_e2e.py.
import { expect, test } from '@playwright/test';

// Contas ficticias: as do ambiente isolado (run_e2e.py) ou as contas de teste do
// projeto real (run_e2e_real.py), sempre vindas do ambiente, nunca do codigo.
const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CATEGORIAS_A = ['Lazer (A)', 'Moradia (A)', 'Transporte (A)'];
const CATEGORIAS_B = ['Educacao (B)', 'Saude (B)'];
const CHAVE_SESSAO = 'cf-financeiro-auth';

// Falha o teste se a pagina violar a CSP real do _headers ou lancar erro de JS.
test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('requestfailed', (req) => {
        // Navegacao interrompida por redirecionamento proprio nao e falha da pagina.
        if (req.failure()?.errorText !== 'net::ERR_ABORTED') problemas.push(`requestfailed: ${req.url()} ${req.failure()?.errorText}`);
    });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/categorias.html');
    await expect(page.locator('#categorias-tabela')).toBeVisible();
}

async function nomesNaTabela(page) {
    return page.locator('#categorias-corpo tr td:nth-child(2)').allTextContents();
}

test('sem sessao: pagina protegida redireciona e nada e consultado', async ({ page }) => {
    const consultasRest = [];
    page.on('request', (req) => { if (req.url().includes('/rest/v1/')) consultasRest.push(new URL(req.url()).pathname); });

    await page.goto('/categorias.html');
    await page.waitForURL(/index\.html\?next=categorias\.html$/);
    await expect(page.locator('#login-form')).toBeVisible();
    expect(consultasRest).toEqual([]);
});

test('credenciais invalidas: mensagem generica e nenhuma sessao gravada', async ({ page }) => {
    await page.goto('/index.html');
    await page.fill('#email', A.email);
    await page.fill('#senha', 'senha-errada');
    await page.click('#login-enviar');
    await expect(page.locator('#login-erro')).toHaveText('E-mail ou senha inválidos.');
    expect(page.url()).toMatch(/index\.html/);
    expect(await page.evaluate((k) => localStorage.getItem(k), CHAVE_SESSAO)).toBeNull();
});

test('usuario A ve somente as proprias categorias', async ({ page }) => {
    await entrar(page, A);
    await expect(page.locator('#usuario-email')).toHaveText(A.email);
    expect(await nomesNaTabela(page)).toEqual(CATEGORIAS_A);
    for (const nome of CATEGORIAS_B) await expect(page.getByText(nome)).toHaveCount(0);
});

test('usuario B ve somente as proprias categorias', async ({ page }) => {
    await entrar(page, B);
    expect(await nomesNaTabela(page)).toEqual(CATEGORIAS_B);
    for (const nome of CATEGORIAS_A) await expect(page.getByText(nome)).toHaveCount(0);
});

test('pagina de categorias nao oferece nenhuma acao de escrita', async ({ page }) => {
    await entrar(page, A);
    await expect(page.locator('form, input, textarea, select')).toHaveCount(0);
    await expect(page.locator('button')).toHaveCount(1);
    await expect(page.locator('button')).toHaveText('Sair');
});

test('sair encerra a sessao e a pagina volta a exigir login', async ({ page }) => {
    await entrar(page, A);
    await page.click('#sair');
    await page.waitForURL('**/index.html');
    expect(await page.evaluate((k) => localStorage.getItem(k), CHAVE_SESSAO)).toBeNull();
    await page.goto('/categorias.html');
    await page.waitForURL(/index\.html/);
});

test('token adulterado no navegador e recusado e nao exibe dados', async ({ page }) => {
    await entrar(page, A);
    await page.evaluate((k) => {
        const sessao = JSON.parse(localStorage.getItem(k));
        const [cabecalho, corpo] = sessao.access_token.split('.');
        const claims = JSON.parse(atob(corpo.replace(/-/g, '+').replace(/_/g, '/')));
        claims.sub = 'bbbbbbbb-0000-4000-8000-00000000000b';
        const forjado = btoa(JSON.stringify(claims)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
        sessao.access_token = `${cabecalho}.${forjado}.assinatura-invalida`;
        sessao.user.id = claims.sub;
        localStorage.setItem(k, JSON.stringify(sessao));
    }, CHAVE_SESSAO);

    await page.goto('/categorias.html');
    await page.waitForURL(/index\.html/);
    for (const nome of [...CATEGORIAS_A, ...CATEGORIAS_B]) await expect(page.getByText(nome)).toHaveCount(0);
});

test('API REST direta pelo navegador: sem token nao le, com token de A nao escreve', async ({ page }) => {
    await page.goto('/index.html');
    const semToken = await page.evaluate(async () => {
        const r = await fetch(`${window.CF_CONFIG.supabaseUrl}/rest/v1/categorias?select=nome`, {
            headers: { apikey: window.CF_CONFIG.supabasePublishableKey, 'Accept-Profile': 'financeiro' },
        });
        return { status: r.status, corpo: await r.text() };
    });
    expect([401, 403]).toContain(semToken.status);
    expect(semToken.corpo).not.toContain('(A)');

    await entrar(page, A);
    const escrita = await page.evaluate(async (k) => {
        const token = JSON.parse(localStorage.getItem(k)).access_token;
        const cabecalhos = {
            apikey: window.CF_CONFIG.supabasePublishableKey,
            Authorization: `Bearer ${token}`,
            'Content-Profile': 'financeiro',
            'Content-Type': 'application/json',
        };
        const base = `${window.CF_CONFIG.supabaseUrl}/rest/v1/categorias`;
        const post = await fetch(base, { method: 'POST', headers: cabecalhos, body: '{"nome":"Injetada"}' });
        const del = await fetch(`${base}?id=gt.0`, { method: 'DELETE', headers: cabecalhos });
        return [post.status, del.status];
    }, CHAVE_SESSAO);
    for (const status of escrita) expect([401, 403]).toContain(status);

    // Depois das tentativas de escrita, os dados de A continuam intactos.
    await page.reload();
    await expect(page.locator('#categorias-corpo tr td:nth-child(2)')).toHaveText(CATEGORIAS_A);
});

test('parametro next nao permite redirecionamento para fora', async ({ page }) => {
    await page.goto('/index.html?next=https://atacante.example/');
    await page.fill('#email', A.email);
    await page.fill('#senha', A.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/categorias.html');
    expect(new URL(page.url()).hostname).toBe('127.0.0.1');
});
