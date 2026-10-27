// FIN-FINANCIAMENTOS-MOTOR-1 — tela original de Financiamentos com o motor SAC/TR no Supabase (migration
// 20261123090000), no "Perfil B" (novo aplicativo): cadastro pelo formulario original, parcelas e despesas geradas,
// amortizacao pelo modal original, exclusao segura (recusada com execucao financeira; aceita sem). Dados FICTICIOS; TR
// ficticia de 2034-2035 (tests/supabase_local.py).
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const NOME = 'Financiamento Motor E2E (ficticio)';
const NOME_2 = 'Financiamento Motor E2E 2 (ficticio)';

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (pedido) => { if (/\/api\//.test(new URL(pedido.url()).pathname)) problemas.push(`rede /api/: ${pedido.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamada ao Flask').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function contrato(page, perfil, nome = NOME) {
    const lista = (await chamarRpc(page, 'financiamentos_tela', { p_perfil_id: perfil, p_ativo: null })).corpo;
    return lista.find((f) => f.nome === nome);
}

async function chamarApi(page, metodo, rota, corpo) {
    return page.evaluate(async ({ metodo, rota, corpo }) => (await fetch(rota, {
        method: metodo, headers: { 'Content-Type': 'application/json' }, body: corpo ? JSON.stringify(corpo) : undefined,
    })).json(), { metodo, rota, corpo });
}

test('cadastro SAC/TR, amortizacao e exclusao segura pela tela original', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await page.goto('/financiamentos.html');
    await expect(page.locator('.fin-aviso-fase')).toContainText('SAC/TR da Caixa, SAC, PRICE e SIMPLES');
    const perfil = await perfilAtivoId(page);

    // Cadastro pelo formulario original (seguro fixo, taxa administrativa, TR).
    await page.getByRole('button', { name: 'Novo financiamento' }).first().click();
    await page.fill('#fin-nome', NOME);
    await page.selectOption('#fin-produto', { index: 1 });
    await page.selectOption('#fin-finalidade', { index: 1 });
    await page.fill('#fin-valor', '15.000,00');
    await page.fill('#fin-saldo-inicial', '12.000,00');
    await page.fill('#fin-prazo', '12');
    await page.fill('#fin-taxa', '9,38');
    await page.fill('#fin-data-contrato', '2034-01-10');
    await page.selectOption('#fin-seguro-modo', 'fixo');
    await page.fill('#fin-seguro', '20,00');
    await page.fill('#fin-taxa-adm', '25,00');
    await page.selectOption('#fin-indexador', 'TR');
    await page.fill('#fin-data-primeira', '2034-02-10');
    await page.selectOption('#fin-dia-vencimento', '10');
    await page.getByRole('button', { name: 'Salvar financiamento' }).click();
    const linha = page.locator('#financiamentos-lista .fin-contract-row', { hasText: NOME });
    await expect(linha).toBeVisible();
    const criado = await contrato(page, perfil);
    expect(criado.total_parcelas).toBe(12);
    const detalhe = (await chamarRpc(page, 'financiamento_tela', { p_perfil_id: perfil, p_financiamento_id: criado.id })).corpo;
    const p1 = detalhe.parcelas.find((p) => p.numero_parcela === 1);
    expect(p1.valor_juros).toBeCloseTo((12000 * 1.001 * 0.0938) / 12, 2);  // saldo corrigido pela TR x nominal/12
    expect(p1.valor_seguro).toBe(20);
    expect(p1.valor_taxa_adm).toBe(25);

    // Amortizacao pelo modal original: reduz a prestacao; saldo devedor atual = financiado - amortizado.
    await linha.locator('[title="Amortizar"]').click();
    await page.fill('#amort-data', '2034-01-15');
    await page.fill('#amort-valor', '2.000,00');
    await page.selectOption('#amort-tipo', 'reduzir_parcela');
    await page.getByRole('button', { name: 'Registrar amortização' }).click();
    await expect(page.locator('#modal-amortizacao')).toBeHidden();
    await expect.poll(async () => (await contrato(page, perfil)).saldo_devedor_atual).toBe(10000);
    const depois = (await chamarRpc(page, 'financiamento_tela', { p_perfil_id: perfil, p_financiamento_id: criado.id })).corpo;
    expect(depois.parcelas.find((p) => p.numero_parcela === 1).valor_previsto_total).toBeLessThan(p1.valor_previsto_total);

    // Edicao com execucao: estrutural recusada; nome aceito. Vigencia nova e simulacao de quitacao (so leitura).
    const estrutural = await chamarApi(page, 'PUT', `/api/financiamentos/${criado.id}`, { valor_financiado: 9000 });
    expect(estrutural).toEqual({ success: false, error: expect.stringContaining('dados estruturais') });
    const renomeado = await chamarApi(page, 'PUT', `/api/financiamentos/${criado.id}`, { nome: `${NOME} renomeado` });
    expect(renomeado.success).toBe(true);
    await chamarApi(page, 'PUT', `/api/financiamentos/${criado.id}`, { nome: NOME });
    const vigencia = await chamarApi(page, 'POST', `/api/financiamentos/${criado.id}/vigencias-seguro`, { competencia_inicio: '2034-06', valor_mensal: 22 });
    expect(vigencia.success).toBe(true);
    expect(vigencia.data.parcelas_atualizadas).toBeGreaterThan(0);
    const antesQuit = await contrato(page, perfil);
    const quitacao = await chamarApi(page, 'POST', `/api/financiamentos/${criado.id}/simular-quitacao`, { data_quitacao: '2034-05-20' });
    expect(quitacao.success).toBe(true);
    expect(quitacao.data.modo_calculo).toBe('SAC+TR');
    expect(quitacao.data.saldo_devedor_estimado).toBeCloseTo(10000 * 1.001, 2);
    expect(await contrato(page, perfil)).toEqual(antesQuit);

    // Exclusao: com amortizacao (execucao financeira) e recusada; nada sai.
    const recusa = await chamarApi(page, 'DELETE', `/api/financiamentos/${criado.id}`);
    expect(recusa).toEqual({ success: false, error: expect.stringContaining('Nao e possivel excluir') });
    expect((await contrato(page, perfil)).total_parcelas).toBe(12);

    // Sem execucao financeira: excluido com as despesas das parcelas.
    const outro = await chamarApi(page, 'POST', '/api/financiamentos', {
        nome: NOME_2, sistema_amortizacao: 'SAC', indexador_saldo: 'TR', valor_financiado: 5000, prazo_total_meses: 6,
        taxa_juros_nominal_anual: 9, data_contrato: '2034-03-01', data_primeira_parcela: '2034-04-01', seguro_modo: 'fixo',
        vigencias_seguro: [{ competencia_inicio: '2034-04-01', valor_mensal: 10 }],
    });
    expect(outro.success).toBe(true);
    const removido = await chamarApi(page, 'DELETE', `/api/financiamentos/${outro.data.id}`);
    expect(removido.success).toBe(true);
    expect(await contrato(page, perfil, NOME_2)).toBeUndefined();
});
