// FIN-CONTRATOS-2 — parcela de financiamento paga e estornada pelo caminho real (tela original de Despesas), no
// "Perfil B" (atribuido ao novo aplicativo). Dados FICTICIOS (tests/supabase_local.py: semear_financiamento_e2e):
// contrato SAC de 3 parcelas, parcela 1 paga, despesas das parcelas ligadas (como o Flask cria). Toda operacao e
// desfeita no fim (pagamentos estornados: a conta volta ao saldo de partida para os specs seguintes).
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, estornar, pagar, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CONTRATO = 'Financiamento E2E (ficticio)';
const PARCELA_2 = `${CONTRATO} - parcela 2/3`;

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/')) problemas.push(`rede /api/: ${r.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS/chamadas ao Flask').toEqual([]);
});

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function contrato(page) {
    const perfil = await perfilAtivoId(page);
    const lista = (await chamarRpc(page, 'financiamentos_tela', { p_perfil_id: perfil, p_ativo: null })).corpo;
    const id = (lista.data || lista).find((f) => f.nome === CONTRATO).id;
    const det = (await chamarRpc(page, 'financiamento_tela', { p_perfil_id: perfil, p_financiamento_id: id })).corpo;
    const dados = det.data || det;
    return { saldo: Number(dados.saldo_devedor_atual), parcelas: (dados.parcelas || []).map((p) => [p.numero_parcela, p.status]) };
}

test('parcela paga e estornada em Despesas: parcela e saldo devedor acompanham; de novo, o ciclo se repete', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirDespesas(page, '2033-03');
    expect(await contrato(page)).toEqual({ saldo: 2000, parcelas: [[1, 'pago'], [2, 'pendente'], [3, 'pendente']] });

    for (const [data, motivo] of [['2033-03-10', 'Debito em duplicidade'], ['2033-03-15', 'Valor errado']]) {
        await pagar(page, PARCELA_2, { data });
        await expect.poll(() => dialogos.at(-1)).toMatch(/^Despesa paga: R\$\s1\.0\d\d,\d\d debitados de Conta Perfil B/);
        await expect(despesa(page, PARCELA_2).locator('.status-badge')).toHaveText('Pago');
        expect(await contrato(page)).toEqual({ saldo: 1000, parcelas: [[1, 'pago'], [2, 'pago'], [3, 'pendente']] });

        await estornar(page, PARCELA_2, motivo, data);
        await expect.poll(() => dialogos.at(-1)).toBe('Pagamento estornado com sucesso.');
        await expect(despesa(page, PARCELA_2).locator('.status-badge')).toHaveText('Pendente');
        expect(await contrato(page)).toEqual({ saldo: 2000, parcelas: [[1, 'pago'], [2, 'pendente'], [3, 'pendente']] });
    }
});

test('estorno so a partir da parcela paga mais recente; tela de Financiamentos orienta para Despesas', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    const PARCELA_3 = `${CONTRATO} - parcela 3/3`;
    await entrar(page, B);
    await abrirDespesas(page, '2033-03');
    await pagar(page, PARCELA_2, { data: '2033-03-10' });
    await expect(despesa(page, PARCELA_2).locator('.status-badge')).toHaveText('Pago');
    await abrirDespesas(page, '2033-04');
    await pagar(page, PARCELA_3, { data: '2033-04-10' });
    await expect(despesa(page, PARCELA_3).locator('.status-badge')).toHaveText('Pago');
    expect(await contrato(page)).toEqual({ saldo: 0, parcelas: [[1, 'pago'], [2, 'pago'], [3, 'pago']] });

    // Estornar a 2 com a 3 paga: recusado, nada muda (a cadeia do saldo devedor se preserva).
    await abrirDespesas(page, '2033-03');
    await estornar(page, PARCELA_2, 'Tentativa fora de ordem', '2033-04-11');
    await expect.poll(() => dialogos.at(-1)).toMatch(/Existe uma parcela paga mais recente \(numero 3\)/);
    await page.locator('#modal-estorno [data-on-click^="fecharModalEstorno"]').first().click().catch(() => {});
    expect(await contrato(page)).toEqual({ saldo: 0, parcelas: [[1, 'pago'], [2, 'pago'], [3, 'pago']] });

    // A tela de Financiamentos (pagar/estornar parcela direto) orienta para Despesas, como o Flask; nada e gravado.
    await page.goto('/financiamentos.html');
    await page.waitForLoadState('networkidle');
    const r = await page.evaluate(async () => (await fetch('/api/financiamentos/parcelas/1/pagar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).json());
    expect(r.success).toBe(false);
    expect(r.error).toContain('Use o fluxo de Despesas');

    // Limpeza na ordem certa (3, depois 2): volta ao estado inicial e ao saldo da conta.
    await abrirDespesas(page, '2033-04');
    await estornar(page, PARCELA_3, 'Limpeza do E2E', '2033-04-12');
    await expect.poll(() => dialogos.at(-1)).toBe('Pagamento estornado com sucesso.');
    await abrirDespesas(page, '2033-03');
    await estornar(page, PARCELA_2, 'Limpeza do E2E', '2033-04-12');
    await expect.poll(() => dialogos.at(-1)).toBe('Pagamento estornado com sucesso.');
    expect(await contrato(page)).toEqual({ saldo: 2000, parcelas: [[1, 'pago'], [2, 'pendente'], [3, 'pendente']] });
});
