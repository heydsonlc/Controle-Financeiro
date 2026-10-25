// FIN-MOVIMENTACOES-1 — pagar e estornar despesa comum, receber (parcial e acima do previsto) e estornar receita, e
// os movimentos do mes, em tela de celular. Dados FICTICIOS: toda escrita com o usuario B no "Perfil B" temporario
// (atribuido ao novo aplicativo; "Conta Perfil B", saldo inicial 0), so em 03/2035. Valor devido, o que falta,
// saldo e operacao vigente sao conferidos no banco; aqui so a tela e o que ela mostra depois.
import { expect, test } from '@playwright/test';

import {
    abrirDespesas, abrirPagamento, chamarRpc, despesa, estornar, pagar, perfilAtivoId, preencherDespesa, registrarDialogos,
    salvarDespesa,
} from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
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
}

const previsao = (page, nome) => page.locator('#lista-receitas .conta[data-receita-id^="PREVISAO-"]',
    { has: page.locator('.conta-nome', { hasText: nome }) });

// FIN-FIDELIDADE-DESPESAS-1: a despesa e paga e estornada pelos modais originais da tela de Despesas do Flask. Os
// movimentos e o saldo (que a tela original nao lista; ficam em Contas Bancarias) sao conferidos pela funcao de leitura.
async function movimentosDoMes(page, mes) {
    return (await chamarRpc(page, 'movimentos_do_mes', { p_perfil_id: await perfilAtivoId(page), p_mes: `${mes}-01` })).corpo;
}

test.describe('tela original de Despesas (computador)', () => {
    test.use({ viewport: { width: 1366, height: 900 }, isMobile: false, hasTouch: false });

test('despesa: pagar com juros justificados, estornar; movimentos e saldo do mes', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirDespesas(page, '2035-03');
    await page.click('.btn-nova-despesa');
    await preencherDespesa(page, { nome: 'Internet E2E', valor: '120', categoria: 'Moradia', vencimento: '2035-03-10',
        competencia: '2035-03' });
    await salvarDespesa(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa salva na competência 03/2035.');
    await expect(despesa(page, 'Internet E2E').locator('.status-badge')).toHaveText('Pendente');

    await abrirPagamento(page, 'Internet E2E');
    await expect(page.locator('#form-pagar label', { hasText: 'Valor Total' })).toContainText('R$ 120,00');  // rotulo que o original reescreve
    await expect(page.locator('#pagar-conta-bancaria option')).toHaveText(['Selecione...', 'Conta Perfil B (Banco ficticio)']);
    await expect(page.locator('#pagar-ajuste')).toBeHidden();
    await page.locator('#modal-pagar [data-on-click="fecharModalPagar()"]').first().click();
    await pagar(page, 'Internet E2E', { data: '2035-03-12', valor: '125' });  // diferenca sem classificar
    await expect.poll(() => dialogos.at(-1)).toBe('Classifique a diferença e escreva a justificativa.');
    await expect(page.locator('#pagar-ajuste')).toBeVisible();
    await expect(page.locator('#pagar-ajuste-tipo option')).toHaveText(['Selecione...', 'Juros ou multa', 'Ajuste de quitação integral']);
    await page.selectOption('#pagar-ajuste-tipo', 'JUROS');
    await page.fill('#pagar-ajuste-justificativa', 'Multa por atraso');
    await page.click('#form-pagar button[type=submit]');
    await expect.poll(() => dialogos.at(-1))
        .toMatch(/^Despesa paga: R\$\s125,00 debitados de Conta Perfil B\. Saldo da conta: -R\$\s125,00\.$/);
    await expect(despesa(page, 'Internet E2E').locator('.status-badge')).toHaveText('Pago');
    let mov = await movimentosDoMes(page, '2035-03');
    expect(mov.movimentos.map((m) => [m.tipo, Number(m.valor), m.referencia])).toEqual([['DEBITO', 125, 'Internet E2E']]);
    expect(Number(mov.contas.find((c) => c.nome === 'Conta Perfil B').saldo)).toBe(-125);

    const antes = dialogos.length;
    await estornar(page, 'Internet E2E', '');  // sem motivo: o campo obrigatorio do modal original impede o envio
    await expect(page.locator('#modal-estorno')).toBeVisible();
    expect(dialogos.length).toBe(antes);
    await page.fill('#estorno-data', '2035-03-14');
    await page.fill('#estorno-motivo', 'Debito em duplicidade');
    await page.click('#form-estorno button[type=submit]');
    await expect.poll(() => dialogos.at(-1)).toBe('Pagamento estornado com sucesso.');
    await expect(despesa(page, 'Internet E2E').locator('.status-badge')).toHaveText('Pendente');
    await expect(despesa(page, 'Internet E2E').locator('.despesa-cell-valor')).toHaveText('R$ 120,00');  // volta ao devido
    mov = await movimentosDoMes(page, '2035-03');
    expect(mov.movimentos.map((m) => [m.tipo, Number(m.valor)])).toEqual([['DEBITO', 125], ['CREDITO', 125]]);
    expect(Number(mov.contas.find((c) => c.nome === 'Conta Perfil B').saldo)).toBe(0);
});
});

test('receita: receber parcial, receber acima do que falta com justificativa, estornar um recebimento', async ({ page }) => {
    await entrar(page, B);
    await page.goto('/receitas.html?mes=2035-03');
    await page.click('#nova-receita');
    await page.fill('#receita-nome', 'Freela E2E');
    await page.selectOption('#receita-tipo', 'RENDA_EXTRA');
    await page.fill('#receita-data', '2035-03-15');
    await page.fill('#receita-valor', '1.000,00');
    await page.locator('#receita-painel').getByRole('button', { name: 'Salvar' }).click();
    const item = () => previsao(page, 'Freela E2E');
    await expect(item().locator('.situacao')).toHaveText('Prevista');

    await item().locator('summary').click();
    await item().getByRole('button', { name: 'Receber' }).click();
    await expect(page.locator('#recebimento-valor')).toHaveValue('1000,00');  // o que falta, vindo do banco
    await page.fill('#recebimento-data', '2035-03-15');
    await page.fill('#recebimento-valor', '400,00');
    await expect(page.locator('#receita-painel .pagamento-ajuste')).toBeHidden();  // menor: parcial, sem justificativa
    await expect(page.locator('#receita-painel')).toContainText('recebimento parcial');
    await page.locator('#receita-painel button[type=submit]').click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Recebido: R\$\s400,00 creditados em Conta Perfil B\. Saldo da conta: R\$\s400,00\.$/);
    await expect(item().locator('.situacao')).toHaveText('Parcial');

    await item().locator('summary').click();
    await item().getByRole('button', { name: 'Receber' }).click();
    await expect(page.locator('#recebimento-valor')).toHaveValue('600,00');
    await page.fill('#recebimento-data', '2035-03-20');
    await page.fill('#recebimento-valor', '700,00');
    await page.locator('#receita-painel button[type=submit]').click();
    await expect(page.locator('#receita-painel .login-error')).toHaveText('Escreva a justificativa.');
    await page.fill('#recebimento-justificativa', 'Bonus junto com o pagamento');
    await page.locator('#receita-painel button[type=submit]').click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Recebido: R\$\s700,00 creditados em Conta Perfil B\. Saldo da conta: R\$\s1\.100,00\.$/);
    await expect(item().locator('.situacao')).toHaveText('Recebida');

    await item().locator('summary').click();
    await expect(item().locator('.pagamento-linha')).toHaveCount(2);
    await item().getByRole('button', { name: 'Estornar recebimento' }).first().click();
    await page.fill('#estorno-motivo', 'Credito devolvido');
    await page.fill('#estorno-data-estorno', '2035-03-21');
    await page.locator('#receita-painel button[type=submit]').click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Recebimento estornado: R\$\s400,00 debitados de Conta Perfil B\. Saldo da conta: R\$\s700,00\.$/);
    await expect(item().locator('.situacao')).toHaveText('Parcial');  // 700 de 1.000 (o estornado nao conta)

    // Estorna tambem o outro: cada recebimento tem o seu estorno, e a conta volta ao saldo de partida (os specs
    // seguintes usam a mesma conta).
    await item().locator('summary').click();
    await expect(item().getByRole('button', { name: 'Estornar recebimento' })).toHaveCount(1);
    await item().getByRole('button', { name: 'Estornar recebimento' }).click();
    await page.fill('#estorno-motivo', 'Valor recebido por engano');
    await page.fill('#estorno-data-estorno', '2035-03-22');
    await page.locator('#receita-painel button[type=submit]').click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Recebimento estornado: R\$\s700,00 debitados de Conta Perfil B\. Saldo da conta: R\$\s0,00\.$/);
    await expect(item().locator('.situacao')).toHaveText('Prevista');

    const mov = await movimentosDoMes(page, '2035-03');
    const daReceita = mov.movimentos.filter((m) => m.referencia === 'Freela E2E');
    expect(daReceita.filter((m) => m.tipo === 'CREDITO' && !m.estorno_de)).toHaveLength(2);  // recebimentos
    expect(daReceita.filter((m) => m.tipo === 'DEBITO' && m.estorno_de)).toHaveLength(2);    // estornos
});
