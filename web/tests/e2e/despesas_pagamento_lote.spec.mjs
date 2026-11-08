// FIN-DESPESAS-PAGAMENTO-LOTE-01 (P20) — pagamento em lote das ocorrencias pendentes de uma recorrencia semanal, com a conta
// bancaria de debito escolhida no modal. Usuario E (perfil proprio): duas recorrencias "Diarista E" de R$ 200 (terca e sexta),
// Pix e sem conta, em 02/2030 (8 ocorrencias); duas pagas uma a uma antes. Dados FICTICIOS; grava no banco descartavel.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const MES = '2030-02';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

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

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', E.email);
    await page.fill('#senha', E.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function diaristas(page, perfil) {
    const r = await chamarRpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${MES}-01` });
    return r.corpo.filter((c) => /^Diarista E - /.test(c.nome)).sort((a, b) => String(a.data_vencimento).localeCompare(String(b.data_vencimento)));
}

async function contaBancaria(page, perfil, nome) {
    const r = await chamarRpc(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' });
    return r.corpo.find((c) => c.nome === nome);
}

const modal = (page) => page.locator('#modal-pagar-lote');
const abrirLote = (page) => despesa(page, 'Diarista E').locator('[data-on-click^="pagarTodasOcorrencias"]').click();

test('modal com a recorrencia, as pendentes, o total e so as contas ativas do perfil; cancelar nao paga', async ({ page }) => {
    await entrar(page);
    await abrirDespesas(page, MES);  // a geracao cria as 8 ocorrencias do mes
    const perfil = await perfilAtivoId(page);
    const todas = await diaristas(page, perfil);
    expect(todas.length).toBe(8);
    // duas pagas uma a uma, pelo pagamento individual
    const contaE = await contaBancaria(page, perfil, 'Conta E (ficticia)');
    for (const c of todas.slice(-2)) {
        const r = await chamarRpc(page, 'pagar_despesa', { p_perfil_id: perfil, p_conta_id: c.id, p_chave: crypto.randomUUID(),
            p_dados: { conta_bancaria_id: contaE.id, data_pagamento: c.data_vencimento, valor_pago: '200.00', valor_devido: '200.00' } });
        expect(r.status).toBe(200);
    }
    await abrirDespesas(page, MES);

    await abrirLote(page);
    await expect(modal(page)).toBeVisible();
    await expect(page.locator('#pagar-lote-nome')).toHaveText('Diarista E');
    await expect(page.locator('#pagar-lote-competencia')).toContainText('2030');
    await expect(page.locator('#pagar-lote-meio')).toHaveText('Pix');
    await expect(page.locator('#pagar-lote-quantidade')).toHaveText('6');
    await expect(page.locator('#pagar-lote-total')).toHaveText('R$ 1.200,00');
    const opcoes = await page.locator('#pagar-lote-conta option').allTextContents();
    expect(opcoes).toEqual(['Selecione...', 'Conta E (ficticia) (Banco ficticio)', 'Conta E2 (ficticia) (Banco ficticio)']);
    // botoes do mesmo tamanho, alinhados
    const [cancelar, confirmar] = await Promise.all([page.locator('#pagar-lote-cancelar').boundingBox(), page.locator('#pagar-lote-confirmar').boundingBox()]);
    expect(Math.abs(cancelar.height - confirmar.height) < 1 && Math.abs(cancelar.y - confirmar.y) < 1).toBe(true);
    expect(Math.abs(cancelar.width - confirmar.width) < 2).toBe(true);

    await page.click('#pagar-lote-cancelar');
    await expect(modal(page)).toBeHidden();
    expect((await diaristas(page, perfil)).filter((c) => c.status_pagamento === 'Pago').length).toBe(2);
});

test('confirmar exige a conta; paga as 6 pendentes na conta escolhida, sem tocar nas pagas nem na recorrencia', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page);
    await abrirDespesas(page, MES);
    const perfil = await perfilAtivoId(page);
    const contaE2 = await contaBancaria(page, perfil, 'Conta E2 (ficticia)');
    const antes = await diaristas(page, perfil);
    const pagasAntes = antes.filter((c) => c.status_pagamento === 'Pago').map((c) => [c.id, c.valor_executado ?? c.valor]);

    await abrirLote(page);
    await page.locator('#form-pagar-lote').evaluate((f) => f.requestSubmit());  // o required do select segura o envio
    expect((await diaristas(page, perfil)).filter((c) => c.status_pagamento === 'Pago').length).toBe(2);
    await page.selectOption('#pagar-lote-conta', String(contaE2.id));
    await page.click('#pagar-lote-confirmar');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('Pagamento em lote concluído');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('6 ocorrência(s) paga(s)');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('R$ 1.200,00');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('Conta E2 (ficticia)');
    await expect(page.locator('#pagar-lote-confirmar')).toBeHidden();
    await page.click('#pagar-lote-cancelar');  // "Fechar"
    await expect(modal(page)).toBeHidden();

    const depois = await diaristas(page, perfil);
    expect(depois.every((c) => c.status_pagamento === 'Pago')).toBe(true);
    expect(depois.filter((c) => pagasAntes.some(([id]) => id === c.id)).map((c) => [c.id, c.valor_executado ?? c.valor])).toEqual(pagasAntes);
    const conta = await contaBancaria(page, perfil, 'Conta E2 (ficticia)');
    expect(Number(conta.saldo_atual) - Number(contaE2.saldo_atual)).toBeCloseTo(-1200, 2);
    const recorrencias = (await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).corpo.filter((r) => r.nome === 'Diarista E');
    expect(recorrencias.map((r) => [r.meio_pagamento, r.conta_bancaria_id ?? null, Number(r.valor)])).toEqual([['pix', null, 200], ['pix', null, 200]]);
    // todas pagas: o botao do lote fica desabilitado
    await abrirDespesas(page, MES);
    await expect(despesa(page, 'Diarista E').locator('[data-on-click^="pagarTodasOcorrencias"]')).toBeDisabled();
});

test('valor alterado com o modal aberto: nada e pago, o motivo aparece e a lista e conferida de novo', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page);
    await abrirDespesas(page, '2030-03');
    const perfil = await perfilAtivoId(page);
    const marco = (await chamarRpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: '2030-03-01' })).corpo
        .filter((c) => /^Diarista E - /.test(c.nome)).sort((a, b) => String(a.data_vencimento).localeCompare(String(b.data_vencimento)));
    expect(marco.length).toBe(9);  // 4 tercas e 5 sextas
    const contaE = (await chamarRpc(page, 'contas_bancarias_tela', { p_perfil_id: perfil, p_status: 'ATIVO' })).corpo.find((c) => c.nome === 'Conta E (ficticia)');
    await abrirLote(page);
    await expect(page.locator('#pagar-lote-quantidade')).toHaveText('9');
    await page.selectOption('#pagar-lote-conta', String(contaE.id));
    // outra aba muda o valor de uma ocorrencia enquanto o modal esta aberto
    const alvo = marco[3];
    const edicao = (await chamarRpc(page, 'despesa_para_edicao', { p_perfil_id: perfil, p_conta_id: alvo.id })).corpo;
    const editada = await chamarRpc(page, 'editar_despesa', { p_perfil_id: perfil, p_conta_id: alvo.id, p_versao: edicao.versao, p_dados: { valor: '230.00' } });
    expect(editada.status).toBe(200);
    await page.click('#pagar-lote-confirmar');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('Nenhuma ocorrência foi paga.');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText(alvo.nome);
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('R$ 230,00');
    await expect(page.locator('#pagar-lote-mensagem')).toContainText('Feche e confira a lista atualizada');
    await expect(page.locator('#pagar-lote-confirmar')).toBeDisabled();
    const depois = (await chamarRpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: '2030-03-01' })).corpo.filter((c) => /^Diarista E - /.test(c.nome));
    expect(depois.filter((c) => c.status_pagamento === 'Pago').length).toBe(0);
    // fechar recarrega a lista: espera a recarga nova, nao a marca da carga anterior
    await page.locator('#despesas-lista').evaluate((el) => { delete el.dataset.competenciaCarregada; });
    await page.click('#pagar-lote-cancelar');
    await expect(page.locator('#despesas-lista')).toHaveAttribute('data-competencia-carregada', '03/2030');
    await abrirLote(page);
    await expect(page.locator('#pagar-lote-total')).toHaveText('R$ 1.830,00');  // 8 x 200 + 230
    await page.click('#pagar-lote-cancelar');
});
