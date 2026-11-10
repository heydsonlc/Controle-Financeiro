// FIN-MVP-LANCAMENTOS-03, parte B (P14) — previa das parcelas no Novo Lancamento: a tabela acompanha valor e parcelas, nao
// grava nada e e exatamente o que fica gravado. Usuario E (Cartao E). Dados FICTICIOS; grava no banco descartavel.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const CARTAO = 'Cartao E (ficticio)';
const VEICULO = 'Gasolina E (ficticio)';
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (pedido) => { if (/\/api\//.test(new URL(pedido.url()).pathname)) problemas.push(`rede /api/: ${pedido.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamada ao Flask').toEqual([]);
});

const hoje = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const moeda = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const normal = (t) => String(t || '').replace(/\s+/g, ' ').trim();

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', E.email);
    await page.fill('#senha', E.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function contexto(page) {
    const perfil = await perfilAtivoId(page);
    const cartao = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.nome === CARTAO).id;
    const f = (await chamarRpc(page, 'formulario_abastecimento_lancamento', { p_perfil_id: perfil })).corpo;
    const veiculo = f.veiculos.find((v) => v.nome === VEICULO).id;
    const categorias = (await chamarRpc(page, 'categorias_de_despesa', {})).corpo;
    const categoria = categorias.find((c) => String(c.id) !== String(f.categoria_combustivel_id)).id;
    return { perfil, cartao, veiculo, categoria };
}

async function abastecer(page, ctx, valor) {
    const hist = (await chamarRpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: ctx.perfil, p_veiculo_id: ctx.veiculo })).corpo.abastecimentos;
    const km = Math.max(1000, ...hist.filter((a) => !a.anulado).map((a) => Number(a.hodometro_km))) + 500;
    const r = await chamarRpc(page, 'registrar_abastecimento', { p_perfil_id: ctx.perfil, p_chave: crypto.randomUUID(), p_dados: {
        veiculo_id: ctx.veiculo, data_abastecimento: hoje(), hodometro_km: km, combustivel: 'gasolina', preco_litro: 5,
        valor_total: valor, meio_pagamento: 'cartao', cartao_id: ctx.cartao } });
    expect(r.status, JSON.stringify(r.corpo)).toBe(200);
    return r.corpo.abastecimento.id;
}

const abastecimento = async (page, ctx, id) => (await chamarRpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: ctx.perfil, p_veiculo_id: ctx.veiculo }))
    .corpo.abastecimentos.find((a) => a.id === id);
const compras = async (page, ctx, prefixo) => (await chamarRpc(page, 'compras_do_cartao_tela', { p_perfil_id: ctx.perfil, p_cartao_id: ctx.cartao }))
    .corpo.filter((c) => String(c.descricao || '').startsWith(prefixo));

// ---------------------------------------------------------------------------------------------------------------------
// B — P14: previa das parcelas
// ---------------------------------------------------------------------------------------------------------------------

for (const largura of [1366, 1920]) {
    test(`P14: previa acompanha os campos, nao grava e e o que fica gravado (${largura})`, async ({ page }) => {
        const dialogos = registrarDialogos(page);
        await page.setViewportSize({ width: largura, height: largura === 1366 ? 768 : 1080 });
        await entrar(page);
        const ctx = await contexto(page);
        const nome = `NOTEBOOK P14 ${largura}`;
        await page.goto('/lancamentos.html');
        await expect(page.locator('#lista-lancamentos')).not.toContainText('Carregando');
        await page.click('#btn-novo-lancamento');
        await page.selectOption('#lancamento-tipo', 'cartao');
        await page.selectOption('#lancamento-cartao', String(ctx.cartao));
        await page.selectOption('#lancamento-categoria-despesa-cartao', String(ctx.categoria));
        await page.fill('#lancamento-descricao', nome);
        await page.fill('#lancamento-data', hoje());
        await page.fill('#lancamento-mes-fatura', hoje().slice(0, 7));
        await page.fill('#lancamento-valor', '100');
        const previa = page.locator('#lancamento-previa-parcelas');
        await expect(previa).toBeHidden();  // a vista: sem previa
        await page.fill('#lancamento-parcelas', '3');
        await expect(previa.locator('tbody tr')).toHaveCount(3);
        const valores = (await previa.locator('tbody td:nth-child(3)').allTextContents()).map(normal);
        expect([...valores].sort()).toEqual([moeda(33.33), moeda(33.33), moeda(33.34)].sort());
        await expect(previa.locator('tfoot')).toContainText(moeda(100));
        await page.fill('#lancamento-parcelas', '12');
        await expect(previa.locator('tbody tr')).toHaveCount(12);
        expect((await previa.locator('.lanc-previa-rolagem').boundingBox()).height).toBeLessThanOrEqual(170);  // rolagem limitada
        await page.fill('#lancamento-valor', '500');
        await page.fill('#lancamento-parcelas', '4');
        await expect(previa.locator('tbody tr')).toHaveCount(4);
        await expect(previa.locator('tfoot')).toContainText(moeda(500));
        await previa.scrollIntoViewIfNeeded();
        if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/p14_previa_${largura}.png` });
        await page.fill('#lancamento-parcelas', '1');
        await expect(previa).toBeHidden();

        // Cancelar (limpar o formulario) nao grava nada
        await page.click('.lanc-panel-action[title="Limpar formulario"]');
        expect(await compras(page, ctx, nome)).toEqual([]);

        // Confirmar: as parcelas gravadas sao as da previa
        await page.click('#btn-novo-lancamento');
        await page.selectOption('#lancamento-tipo', 'cartao');
        await page.selectOption('#lancamento-cartao', String(ctx.cartao));
        await page.selectOption('#lancamento-categoria-despesa-cartao', String(ctx.categoria));
        await page.fill('#lancamento-descricao', nome);
        await page.fill('#lancamento-data', hoje());
        await page.fill('#lancamento-mes-fatura', hoje().slice(0, 7));
        await page.fill('#lancamento-valor', '500');
        await page.fill('#lancamento-parcelas', '4');
        await expect(previa.locator('tbody tr')).toHaveCount(4);
        const vistas = (await previa.locator('tbody tr').allTextContents()).map(normal);
        await page.locator('#form-lancamento').evaluate((f) => f.requestSubmit());
        await expect.poll(() => dialogos.at(-1)).toBe('Lançamento em cartão salvo com sucesso!');
        const gravadas = (await compras(page, ctx, nome)).sort((a, b) => a.numero_parcela - b.numero_parcela)
            .map((c) => normal(`${c.numero_parcela}/${c.total_parcelas}${String(c.mes_fatura).slice(5, 7)}/${String(c.mes_fatura).slice(0, 4)}${moeda(c.valor)}`));
        expect(gravadas).toEqual(vistas.map((v) => v.replace(/ \*/, '')));
    });
}
