// FIN-CARTAO-AGRUPAMENTO-CATEGORIAS-01 — detalhe da fatura na tela original de Despesas agrupa as compras pela
// Categoria do Cartao gravada (compras_da_fatura) e pelo resumo do cartao (fatura_por_categoria), como o Flask.
// Perfil B, cartao criado aqui, em 02/2038; dados FICTICIOS: "Moradia" -> "Mercado B" (limite R$ 300 neste cartao),
// "Saude" sem Categoria do Cartao. Grava so no banco descartavel; o cartao e inativado no fim.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, normal, perfilAtivoId } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Agrupamento (E2E)';
const MERCADO_B = 340;

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
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
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function idDaCategoria(page, nome) {
    const r = await chamarRpc(page, 'categorias_de_despesa', {});
    return r.corpo.find((c) => c.nome === nome).id;
}

const bloco = (detalhe, titulo) => detalhe.locator('.fatura-bloco', { has: detalhe.page().locator('.bloco-titulo', { hasText: titulo }) });

test('detalhe da fatura: parcelada, Categoria do Cartao com limite e Outros, sem perder valor', async ({ page }) => {
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const [moradia, saude] = [await idDaCategoria(page, 'Moradia'), await idDaCategoria(page, 'Saude')];
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 } });
    expect(criado.status).toBe(200);
    const cartao = criado.corpo.cartao_id;
    expect((await chamarRpc(page, 'vincular_limite_cartao', { p_perfil_id: perfil, p_cartao_id: cartao,
        p_dados: { categoria_cartao_id: MERCADO_B, limite_mensal: '300.00' } })).status).toBe(200);
    for (const [descricao, valor, categoria, parcelas] of [['Feira E2E', '120.00', moradia, 1], ['Padaria E2E', '30.00', moradia, 1],
        ['Remedio E2E', '45.00', saude, 1], ['Geladeira E2E', '300.00', moradia, 3]]) {
        const r = await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
            cartao_id: cartao, descricao, valor, total_parcelas: parcelas, data_compra: '2038-02-01', mes_fatura: '2038-02-01',
            categoria_id: categoria } });
        expect(r.status, descricao).toBe(200);
    }
    // A Categoria do Cartao vem da compra gravada (resolvida na gravacao), nao de nova classificacao.
    const lidas = await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2038-02-01' });
    expect(lidas.corpo.map((c) => [c.descricao.replace(/ \(\d+\/\d+\)$/, ''), c.categoria_cartao_id]).sort()).toEqual([
        ['Feira E2E', MERCADO_B], ['Geladeira E2E', MERCADO_B], ['Padaria E2E', MERCADO_B], ['Remedio E2E', null]]);

    await abrirDespesas(page, '2038-02');
    const fatura = despesa(page, `Fatura ${CARTAO} - 02/2038`);
    await fatura.locator('[data-on-click^="toggleDetalhesFatura"]').click();
    const detalhe = fatura.locator('.fatura-detalhes');
    await expect(detalhe.locator('.fatura-container')).toBeVisible();

    // Parcelada (mesmo classificada): so em Compras Parceladas.
    await expect(bloco(detalhe, 'Compras Parceladas').locator('.bloco-subtotal')).toHaveText('R$ 100,00');
    await expect(bloco(detalhe, 'Compras Parceladas')).toContainText('Geladeira E2E');
    await expect(bloco(detalhe, 'Compras Parceladas')).toContainText('01/03');
    await expect(bloco(detalhe, 'Despesas Fixas').locator('.bloco-subtotal')).toHaveText('R$ 0,00');
    // Categoria do Cartao com limite: previsto (limite) e executado (as duas compras a vista).
    const categorias = bloco(detalhe, 'Despesas por Categoria');
    await expect(categorias.locator('.categoria-nome')).toHaveText(['Mercado B']);
    expect(normal(await categorias.locator('.categoria-valor').textContent())).toMatch(/^R\$ 300,00/);
    await expect(categorias.locator('.categoria-indicador')).toHaveText('R$ 150,00');
    await categorias.locator('.categoria-linha').click();
    await expect(categorias.locator('.categoria-detalhes .linha-titulo')).toHaveText(['Feira E2E', 'Padaria E2E']);
    // Sem Categoria do Cartao: Outros.
    await expect(bloco(detalhe, 'Outros Lançamentos').locator('.bloco-subtotal')).toHaveText('R$ 45,00');
    await expect(bloco(detalhe, 'Outros Lançamentos').locator('.linha-titulo')).toHaveText(['Remedio E2E']);
    // Executado = soma das compras do mes (100 + 120 + 30 + 45); previsto pela regra do Flask (limite no lugar do gasto).
    const totais = await detalhe.locator('.fatura-totais .total-valor').allTextContents();
    expect(totais.map(normal)).toEqual(['R$ 445,00', 'R$ 295,00']);

    // Limpeza do cenario: inativa o cartao (compras e faturas continuam registradas).
    const cartoes = await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil });
    const registro = cartoes.corpo.find((c) => c.id === cartao);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao })).status).toBe(200);
});
