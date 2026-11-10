// FIN-MVP-LANCAMENTOS-03, parte A — abastecimento x compra: a importacao sugere o abastecimento compativel e so vincula o
// confirmado; a Mobilidade vincula e desvincula a compra pela lista de abastecimentos. Usuario E (perfil proprio: dois
// veiculos e o Cartao E). Dados FICTICIOS; grava no banco descartavel.
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
// A — abastecimento x compra importada
// ---------------------------------------------------------------------------------------------------------------------

test('importacao sugere o abastecimento e so vincula o confirmado, sem outra compra', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await page.setViewportSize({ width: 1600, height: 900 });
    await entrar(page);
    const ctx = await contexto(page);
    const id = await abastecer(page, ctx, 123.45);
    const mes = hoje().slice(0, 7);
    await page.goto('/importar-cartao.html');
    await expect(page.locator('#cartaoSelect option', { hasText: CARTAO })).toHaveCount(1);
    await page.selectOption('#cartaoSelect', { label: CARTAO });
    await page.fill('#competenciaInput', `${mes.slice(5, 7)}/${mes.slice(0, 4)}`);
    await page.locator('#competenciaInput').dispatchEvent('input');
    const csv = ['date,title,amount', `${hoje()},POSTO IMPORTADO L03,123.45`, `${hoje()},PADARIA IMPORT L03,9.90`].join('\n');
    await page.locator('#csvFile').setInputFiles({ name: 'fatura-l03.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('CSV analisado com sucesso.');
    await page.click('#btnStep4');
    const posto = page.locator('#editorPrePersistencia tr', { hasText: 'POSTO IMPORTADO L03' });
    const sugestao = posto.locator('.import-abast.sugerida');
    await expect(sugestao).toContainText(`Vincular ao abastecimento: ${VEICULO}`);
    await expect(sugestao.locator('input')).not.toBeChecked();  // nunca marcado sozinho
    await expect(page.locator('#editorPrePersistencia tr', { hasText: 'PADARIA IMPORT L03' }).locator('.import-abast')).toHaveCount(0);
    await sugestao.locator('input').check();
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/l03_importacao_sugestao.png` });
    for (const texto of ['POSTO IMPORTADO L03', 'PADARIA IMPORT L03']) {
        await page.locator('#editorPrePersistencia tr', { hasText: texto }).locator('.import-category-cell select').selectOption(String(ctx.categoria));
    }
    await page.click('#btnImportar');
    await expect(page.locator('#resultadoContainer')).toContainText('Importação concluída.');
    const importadas = await compras(page, ctx, 'POSTO IMPORTADO L03');
    expect(importadas.map((c) => Number(c.valor))).toEqual([123.45]);  // uma compra so
    const a = await abastecimento(page, ctx, id);
    expect([a.lancamento_id, a.situacao_vinculo]).toEqual([importadas[0].id, 'VINCULADO']);
    expect(dialogos.some((d) => /Erro/.test(d))).toBe(false);
});

test('Mobilidade: vincular a compra ao abastecimento e desvincular', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await page.setViewportSize({ width: 1366, height: 768 });
    await entrar(page);
    const ctx = await contexto(page);
    const id = await abastecer(page, ctx, 87.65);
    const criada = await chamarRpc(page, 'criar_compra', { p_perfil_id: ctx.perfil, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: ctx.cartao, descricao: 'POSTO MANUAL L03', valor: '87.65', total_parcelas: 1, data_compra: hoje(),
        mes_fatura: `${hoje().slice(0, 7)}-01`, categoria_id: ctx.categoria } });
    expect(criada.status, JSON.stringify(criada.corpo)).toBe(200);
    await page.goto('/mobilidade.html');
    await page.locator('#tab-configuracao').click();
    await page.locator(`#conf-veiculos-lista [data-on-click="abrirHistoricoAbastecimentos(${ctx.veiculo})"]`).click();
    const linha = page.locator('#abast-historico-lista tr', { hasText: '87,65' });
    await expect(linha).toContainText('Aguardando compra');
    await linha.locator('[title="Vincular compra"]').click();
    const modal = page.locator('#modal-vinculo-abastecimento');
    await expect(modal).toBeVisible();
    await expect(modal.locator('#vinculo-abast-lista')).toContainText('POSTO MANUAL L03');
    await expect(modal.locator('input[name="vinculo-abast-candidata"]')).toHaveCount(1);
    await expect(modal.locator('#vinculo-abast-confirmar')).toBeEnabled();
    await page.waitForTimeout(400);  // fim da animacao de abertura do modal (so para a evidencia)
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/l03_mobilidade_vincular_1366.png` });
    await modal.locator('#vinculo-abast-confirmar').click();
    await expect(modal).toBeHidden();
    await expect(linha).toContainText('POSTO MANUAL L03');
    expect((await abastecimento(page, ctx, id)).situacao_vinculo).toBe('VINCULADO');
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/l03_mobilidade_vinculada_1366.png` });
    await linha.locator('[title="Desvincular compra"]').click();
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Desvincular a compra/);
    await expect(linha).toContainText('Aguardando compra');
    expect((await abastecimento(page, ctx, id)).situacao_vinculo).toBe('AGUARDANDO');
    expect((await compras(page, ctx, 'POSTO MANUAL L03')).length).toBe(1);  // a compra continua
});
