// FIN-FIDELIDADE-DESPESAS-1 — tela original de Despesas do Flask (consulta) sobre o Supabase.
// Dados FICTICIOS de tests/supabase_local.py (semear_contas). Valores esperados calculados a mao (os mesmos do
// MOBILE-CONTAS-1); a apresentacao e a do Flask: grupos por origem e tipo, vencimento mais recente primeiro.
import { expect, test } from '@playwright/test';

import {
    abrirDespesas, chamarRpc, despesa, esperarMes, nomes, perfilAtivoId, registrarDialogos, resumo, situacoes,
    textos, trocarCompetencia, valores,
} from './despesas.mjs';
import { itemDoMenu, perfilAtivo, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ID_PERFIL_B = process.env.CF_ID_PERFIL_B || '103';
const ID_FATURA_EMPRESA = process.env.CF_ID_FATURA_EMPRESA || '511';

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (req) => { if (new URL(req.url()).pathname.startsWith('/api/')) problemas.push(`chamada ao Flask: ${req.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/Flask').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

function mesAtual() {
    const [ano, mes] = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date()).split('-');
    return `${ano}-${mes}`;
}

test('login abre Despesas (tela original) no mes atual', async ({ page }) => {
    await entrar(page, A);
    await esperarMes(page, mesAtual());
    await expect(page.locator('.app-topbar-title')).toHaveText('Gerenciamento de Despesas');
    await expect(page.locator('.despesas-summary-cards .summary-card-label'))
        .toHaveText(['Total do mes', 'Pendentes', 'Pagas', 'Vencendo em 7 dias', 'Cartoes / Faturas', 'Saldo do mes']);
    await expect(page.locator('.btn-nova-despesa')).toBeVisible();
    await expect(page.locator('#filtro-forma-pagamento')).toBeVisible();
});

test('novembro (Pessoal): grupos, ordem, situacoes, valores, resumo e geracao', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    expect(await textos(page.locator('.despesas-grupo-titulo')))
        .toEqual(['FATURAS DE CARTÃO DE CRÉDITO', 'DESPESAS RECORRENTES', 'DESPESAS AVULSAS']);
    expect(await nomes(page)).toEqual(['Fatura Cartao Azul - 11/2026', 'Fatura Cartao Verde - 11/2026', 'Aluguel 11/2026',
        'Internet 11/2026', 'Plano de saude 11/2026']);
    expect(await situacoes(page)).toEqual(['Pendente', 'Pago', 'Pendente', 'Pago', 'Pendente']);
    expect(await valores(page)).toEqual(['R$ 1.320,00', 'R$ 120,00', 'R$ 2.000,00', 'R$ 150,50', 'R$ 800,00']);
    expect(await resumo(page)).toEqual({ total: 'R$ 4.390,50', pendentes: 'R$ 4.120,00', pagas: 'R$ 270,50' });
    await expect(page.locator('#total-cartoes')).toHaveText('R$ 1.440,00');
    await expect(page.locator('#summary-cartoes-sub')).toHaveText('2 fatura(s)');
    await expect(despesa(page, 'Plano de saude').locator('.despesa-cell-detalhe')).toHaveText('Parcela 3/12');
    // Painel lateral: composicao do mes (sem faturas) e proximos vencimentos pendentes.
    await expect(page.locator('#categoria-bar-list')).toContainText('Moradia');
    await expect(page.locator('#proximos-vencimentos-list')).toContainText('Aluguel 11/2026');
    // FIN-RECORRENCIA-1: nada a gerar; itens que o motor recusa ficam visiveis (sem acao de gerar).
    await expect(page.locator('#aviso-texto')).toHaveText('3 itens não podem ser gerados.');
    await expect(page.locator('#gerar-contas')).toHaveCount(0);
    await page.locator('#geracao-acoes summary').click();
    expect(await textos(page.locator('#geracao-acoes .geracao-lista li'))).toEqual([
        'Aluguel — Sem valor valido',
        'Cartao Azul · 12/2026 — Cartao sem dia de vencimento configurado',
        'Cartao Verde · 12/2026 — Cartao sem dia de vencimento configurado',
    ]);
});

test('filtros e busca da barra de acoes', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    await page.selectOption('#filtro-status', 'pago');
    expect(await nomes(page)).toEqual(['Fatura Cartao Verde - 11/2026', 'Internet 11/2026']);
    expect(await resumo(page)).toEqual({ total: 'R$ 270,50', pendentes: 'R$ 0,00', pagas: 'R$ 270,50' });
    await page.selectOption('#filtro-status', '');
    await page.selectOption('#filtro-forma-pagamento', 'cartao');
    expect(await nomes(page)).toEqual(['Fatura Cartao Azul - 11/2026', 'Fatura Cartao Verde - 11/2026']);
    await page.selectOption('#filtro-forma-pagamento', 'debito_automatico');
    expect(await nomes(page)).toEqual(['Plano de saude 11/2026']);
    await page.selectOption('#filtro-forma-pagamento', '');
    await page.fill('#filtro-vencimento-ate', '2026-11-20');
    await page.locator('#filtro-vencimento-ate').dispatchEvent('change');
    expect(await nomes(page)).toEqual(['Internet 11/2026', 'Plano de saude 11/2026']);
    await page.fill('#filtro-vencimento-ate', '');
    await page.locator('#filtro-vencimento-ate').dispatchEvent('change');
    await page.fill('#despesas-busca', 'internet');
    expect(await nomes(page)).toEqual(['Internet 11/2026']);
});

test('detalhe da fatura mostra as compras do mes, sem compras de outro mes', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    await despesa(page, 'Fatura Cartao Azul').locator('[data-on-click^="toggleDetalhesFatura"]').click();
    const detalhe = despesa(page, 'Fatura Cartao Azul').locator('.fatura-detalhes');
    await expect(detalhe).toBeVisible();
    await expect(detalhe).toContainText('Compra parcelada');
    await expect(detalhe).not.toContainText('Supermercado dezembro');
});

test('janeiro: atrasada e vencida como pendentes (como no Flask), paga apesar da data passada', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-01');
    expect(await nomes(page)).toEqual(['Fatura Cartao Azul - 01/2026', 'Aluguel 01/2026', 'Internet 01/2026', 'Plano de saude 01/2026']);
    expect(await situacoes(page)).toEqual(['Pago', 'Pendente', 'Pago', 'Pendente']);
    expect(await resumo(page)).toEqual({ total: 'R$ 3.330,50', pendentes: 'R$ 2.680,00', pagas: 'R$ 650,50' });
});

test('competencia: troca pelo filtro, inclusive virada de ano, e fica no endereco e no menu', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-01');
    await trocarCompetencia(page, '2025-12');
    await expect(page).toHaveURL(/mes=2025-12$/);
    await expect(itemDoMenu(page, 'receitas')).toHaveAttribute('href', 'receitas.html?mes=2025-12');
    await trocarCompetencia(page, '2026-11');
    expect(await nomes(page)).toContain('Aluguel 11/2026');
    await itemDoMenu(page, 'receitas').click();
    await page.waitForURL(/receitas\.html\?mes=2026-11$/);
    await itemDoMenu(page, 'despesas').click();
    await esperarMes(page, '2026-11');
});

test('mes sem contas: estado vazio do original e o aviso de geracao quando ha indicio', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-06');
    await expect(page.locator('#despesas-lista .empty-state')).toContainText('Nenhuma despesa encontrada');
    await expect(page.locator('#aviso-geracao')).toBeVisible();
    expect(await resumo(page)).toEqual({ total: 'R$ 0,00', pendentes: 'R$ 0,00', pagas: 'R$ 0,00' });
});

test('perfil Empresa (so leitura): so as contas da Empresa e nenhuma acao de escrita', async ({ page }) => {
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    await trocarPerfil(page, 'Empresa');
    await esperarMes(page, '2026-11');
    expect(await nomes(page)).toEqual(['Fatura Cartao Empresa - 11/2026', 'Contador 11/2026']);
    expect(await resumo(page)).toEqual({ total: 'R$ 1.450,00', pendentes: 'R$ 1.450,00', pagas: 'R$ 0,00' });
    await expect(page.getByText('Internet 11/2026')).toHaveCount(0);  // legado sem perfil e do Pessoal
    await expect(page.locator('.btn-nova-despesa')).toBeHidden();
    await expect(page.locator('#despesas-lista [data-on-click^="editarDespesa"]:visible')).toHaveCount(0);
    await expect(page.locator('#despesas-lista [data-on-click^="marcarComoPago"]:visible')).toHaveCount(0);
    await expect(page.locator('#despesas-lista [data-on-click^="toggleDetalhesFatura"]:visible')).toHaveCount(1);
});

test('usuario B ve so as proprias contas', async ({ page }) => {
    await entrar(page, B);
    await abrirDespesas(page, '2026-11');
    // FIN-RECORRENCIAS-AUTOMATICAS-1: as faturas dos cartoes do Perfil B sao geradas ao abrir o mes (gerador novo).
    expect((await nomes(page)).filter((n) => !n.startsWith('Fatura '))).toEqual(['Aluguel B 11/2026']);
    for (const fatura of (await nomes(page)).filter((n) => n.startsWith('Fatura '))) expect(fatura).toMatch(/^Fatura Cartao (B|Pagamento) - 11\/2026$/);
    for (const nome of ['Aluguel 11/2026', 'Internet 11/2026', 'Contador 11/2026', 'Cartao Azul']) {
        await expect(page.getByText(nome)).toHaveCount(0);
    }
});

test('perfil ou fatura alterados no navegador nao dao acesso a contas de outro perfil', async ({ page }) => {
    await entrar(page, A);
    await page.evaluate((idB) => {
        const usuarioId = JSON.parse(localStorage.getItem('cf-financeiro-auth')).user.id;
        localStorage.setItem(`cf-perfil-ativo:${usuarioId}`, idB);
    }, ID_PERFIL_B);
    await abrirDespesas(page, '2026-11');
    await expect(perfilAtivo(page)).toHaveText('Pessoal');
    await expect(page.getByText('Aluguel B 11/2026')).toHaveCount(0);
    const pessoal = await perfilAtivoId(page);
    expect((await chamarRpc(page, 'contas_do_mes', { p_perfil_id: Number(ID_PERFIL_B), p_mes: '2026-11-01' })).status).toBe(403);
    expect((await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: Number(ID_PERFIL_B), p_cartao_id: 1, p_mes: '2026-11-01' })).status)
        .toBe(403);
    expect((await chamarRpc(page, 'lancamentos_da_fatura', { p_perfil_id: pessoal, p_conta_id: Number(ID_FATURA_EMPRESA) })).status)
        .toBe(403);
});

test('parametro de mes invalido volta para o mes atual', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/contas.html?mes=2026-13');
    await esperarMes(page, mesAtual());
});

test('celular: a pagina nao rola na horizontal e o menu abre a navegacao', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
        baseURL: process.env.CF_WEB_BASE_URL });
    const page = await ctx.newPage();
    registrarDialogos(page);
    await entrar(page, A);
    await abrirDespesas(page, '2026-11');
    const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
    await page.click('.app-menu-button');
    await expect(page.locator('.app-sidebar')).toBeVisible();
    await ctx.close();
});
