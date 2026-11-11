// FIN-CARTOES-EXECUTADO-01 — fatura so com despesas fixas previstas (como o Visa de 12/2026): o executado consolidado as
// inclui; o previsto soma o limite da categoria sem contar a fixa duas vezes; Despesas e Dashboard com o mesmo valor; no
// pagamento, o executado consolidado e o valor sugerido (identificado, com a parte prevista) e o banco pode cobrar menos
// (fixa ainda nao cobrada), com a diferenca classificada e justificada, sem marcar nada como nao cobrado.
// Perfil B, cartao criado aqui, em 05/2038; dados FICTICIOS; o pagamento e estornado e recorrencias e cartao inativados no
// fim. O nome do arquivo o poe depois de contas.spec (que confere as faturas do Perfil B em 11/2026), como fatura_agrupamento.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const EVIDENCIAS = process.env.CF_EVIDENCIAS_DIR;
const CARTAO = 'Cartao Executado (E2E)';
const MERCADO_B = 340;

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (/Ponte CSP|Adaptador:/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
});

async function rpcOk(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

test('fatura so com fixas previstas: executado consolidado, Dashboard igual e banco cobrando menos', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await page.goto('/index.html');
    await page.fill('#email', B.email);
    await page.fill('#senha', B.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
    const perfil = await perfilAtivoId(page);
    const moradia = (await rpcOk(page, 'categorias_de_despesa', {})).find((c) => c.nome === 'Moradia').id;
    const cartao = (await rpcOk(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 } })).cartao_id;
    await rpcOk(page, 'vincular_limite_cartao', { p_perfil_id: perfil, p_cartao_id: cartao,
        p_dados: { categoria_cartao_id: MERCADO_B, limite_mensal: '400.00' } });
    const recorrencias = [];
    for (const [nome, valor] of [['Netflix E2E', '59.90'], ['Claude E2E', '109.90'], ['Apple One E2E', '59.90'], ['ChatGPT E2E', '99.90']]) {
        recorrencias.push((await rpcOk(page, 'criar_recorrencia_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
            nome, valor, categoria_id: moradia, data_vencimento: '2038-05-05', cartao_id: cartao, tipo_recorrencia: 'mensal', descricao: '' } })).item_id);
    }

    await abrirDespesas(page, '2038-05');  // gera as 4 previsoes de 05/2038
    const fatura = despesa(page, `Fatura ${CARTAO} - 05/2038`);
    await expect(fatura.locator('.despesa-cell-valor')).toHaveText(/R\$ 729,60/);  // 329,60 fixas + 400 do limite
    await fatura.locator('[data-on-click^="toggleDetalhesFatura"]').click();
    // previsto | executado consolidado (antes: R$ 0,00)
    await expect(fatura.locator('.fatura-detalhes .fatura-totais .total-valor')).toHaveText([/R\$\s729,60/, /R\$\s329,60/]);

    // Dashboard: a fatura em aberto pelo mesmo valor de Despesas
    const painel = await rpcOk(page, 'dashboard_resumo_tela', { p_perfil_id: perfil, p_mes_referencia: '2038-05' });
    const doMes = (await rpcOk(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: '2038-05-01' }))
        .filter((c) => c.grupo === 'FATURA' && c.status_pagamento !== 'Pago');
    const somaDespesas = doMes.reduce((s, c) => s + Math.round(Number(c.valor) * 100), 0) / 100;
    expect(Number(JSON.stringify(painel).match(/"faturas_em_aberto":\{[^}]*"valor":([\d.]+)/)[1])).toBe(somaDespesas);

    // Pagamento: valor sugerido identificado, com a parte prevista; o banco cobrou so 3 (Claude nao veio)
    await fatura.locator('[data-on-click^="marcarComoPago"]').click();
    await expect(page.locator('#modal-pagar')).toBeVisible();
    await expect(page.locator('.aviso-fatura-cartao')).toContainText('Executado consolidado');
    await expect(page.locator('.aviso-fatura-cartao .cf-fatura-consolidado')).toContainText('Inclui R$ 329,60 de despesas fixas previstas');
    await expect(page.locator('input[name="tipo-pagamento"][value="total"]').locator('xpath=ancestor::label').locator('span'))
        .toHaveText(/Executado consolidado \(valor sugerido\): R\$\s329,60/);
    if (EVIDENCIAS) await page.screenshot({ path: `${EVIDENCIAS}/cartoes_executado_pagamento_1366.png` });
    await page.locator('input[name="tipo-pagamento"][value="parcial"]').check();
    await page.fill('#pagar-valor-pago', '219.70');
    await page.locator('#pagar-valor-pago').dispatchEvent('input');
    await page.locator('#pagar-valor-pago').dispatchEvent('change');
    await expect(page.locator('#pagar-ajuste')).toBeVisible();
    await page.selectOption('#pagar-ajuste-tipo', 'AJUSTE');
    await expect(page.locator('#pagar-ajuste-tipo option:checked')).toHaveText('Valor cobrado pelo banco diferente do consolidado');
    await page.fill('#pagar-ajuste-justificativa', 'Claude nao veio nesta fatura do banco');
    const contas = await rpcOk(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' });
    const select = page.locator('#pagar-conta-bancaria');
    if (await select.isVisible()) await select.selectOption(String(contas[0].id));
    await page.locator('#form-pagar button[type="submit"]').click();
    await expect.poll(() => dialogos.at(-1)).toMatch(/^Fatura paga: R\$\s219,70 debitados/);

    const faturaId = doMes.find((c) => c.nome === `Fatura ${CARTAO} - 05/2038`).id;
    const dados = await rpcOk(page, 'dados_pagamento_fatura', { p_perfil_id: perfil, p_fatura_id: faturaId });
    const pagamento = dados.pagamentos.find((p) => p.vigente);
    expect([Number(pagamento.valor_pago), Number(pagamento.valor_executado), pagamento.tipo_ajuste, pagamento.justificativa])
        .toEqual([219.7, 329.6, 'AJUSTE', 'Claude nao veio nesta fatura do banco']);
    const fixas = (await rpcOk(page, 'lancamentos_fatura_por_categoria', { p_perfil_id: perfil, p_cartao_id: cartao,
        p_mes: '2038-05-01', p_filtro: 'despesas_fixas' })).lancamentos;
    expect(fixas.map((l) => l.situacao_ocorrencia).sort()).toEqual(['PAGA', 'PAGA', 'PAGA', 'PAGA']);  // nenhuma "nao cobrada"

    // Limpeza: estorna o pagamento (a conta volta ao saldo), inativa as recorrencias (nada a gerar para os outros specs)
    // e o cartao.
    await rpcOk(page, 'estornar_pagamento_fatura', { p_perfil_id: perfil, p_fatura_id: faturaId, p_movimento_id: pagamento.movimento_id,
        p_dados: { motivo: 'Limpeza do E2E', data_estorno: '2038-05-31' }, p_chave: crypto.randomUUID() });
    for (const id of recorrencias) {
        const versao = (await rpcOk(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).find((r) => r.id === id).versao;
        await rpcOk(page, 'definir_situacao_recorrencia_cartao', { p_perfil_id: perfil, p_item_id: id, p_versao: versao, p_ativo: false });
    }
    const registro = (await rpcOk(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).find((c) => c.id === cartao);
    await rpcOk(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao });
});
