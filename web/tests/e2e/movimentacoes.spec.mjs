// FIN-MOVIMENTACOES-1 — pagar e estornar despesa comum, receber (parcial e acima do previsto) e estornar receita, e
// os movimentos do mes, em tela de celular. Dados FICTICIOS: toda escrita com o usuario B no "Perfil B" temporario
// (atribuido ao novo aplicativo; "Conta Perfil B", saldo inicial 0), so em 03/2035. Valor devido, o que falta,
// saldo e operacao vigente sao conferidos no banco; aqui so a tela e o que ela mostra depois.
import { expect, test } from '@playwright/test';

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

const despesa = (page, nome) => page.locator('#lista-despesas .conta', { has: page.locator('.conta-nome', { hasText: nome }) });
const previsao = (page, nome) => page.locator('#lista-receitas .conta[data-receita-id^="PREVISAO-"]',
    { has: page.locator('.conta-nome', { hasText: nome }) });

test('despesa: pagar com juros justificados, estornar; movimentos e saldo do mes', async ({ page }) => {
    await entrar(page, B);
    await page.goto('/contas.html?mes=2035-03');
    await expect(page.locator('#totais')).toBeVisible();
    await page.click('#nova-despesa');
    await page.fill('#despesa-nome', 'Internet E2E');
    await page.fill('#despesa-valor', '120,00');
    const moradia = await page.locator('#despesa-categoria option', { hasText: 'Moradia' }).first().getAttribute('value');
    await page.selectOption('#despesa-categoria', moradia);
    await page.fill('#despesa-vencimento', '2035-03-10');
    await page.locator('#despesa-vencimento').dispatchEvent('change');
    await page.locator('#despesa-painel').getByRole('button', { name: 'Salvar' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Despesa salva na competência 03/2035.');
    await expect(despesa(page, 'Internet E2E').locator('.situacao')).toHaveText('Pendente');

    await despesa(page, 'Internet E2E').locator('summary').click();
    await despesa(page, 'Internet E2E').getByRole('button', { name: 'Pagar' }).click();
    await expect(page.locator('#pagamento-valor')).toHaveValue('120,00');  // o devido, vindo do banco
    await expect(page.locator('#pagamento-conta option')).toHaveText([/^Conta Perfil B · saldo R\$\s0,00$/]);
    await expect(page.locator('#despesa-painel .pagamento-ajuste')).toBeHidden();
    await page.fill('#pagamento-data', '2035-03-12');
    await page.fill('#pagamento-valor', '125,00');
    await expect(page.locator('#despesa-painel .pagamento-ajuste')).toBeVisible();
    await page.locator('#despesa-painel button[type=submit]').click();
    await expect(page.locator('#despesa-painel .login-error')).toHaveText('Classifique a diferença e escreva a justificativa.');
    await page.selectOption('#pagamento-tipo', 'JUROS');
    await page.fill('#pagamento-justificativa', 'Multa por atraso');
    await page.locator('#despesa-painel button[type=submit]').click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Despesa paga: R\$\s125,00 debitados de Conta Perfil B\. Saldo da conta: -R\$\s125,00\.$/);
    await expect(despesa(page, 'Internet E2E').locator('.situacao')).toHaveText('Paga');

    // Movimentos do mes: o debito, ligado a despesa, e o saldo da conta pelos movimentos.
    const movimentos = page.locator('#lista-movimentos .movimento');
    await expect(movimentos).toHaveCount(1);
    await expect(movimentos.first()).toContainText('Internet E2E');
    await expect(movimentos.first()).toContainText('Pagamento de despesa · Conta Perfil B');
    await expect(movimentos.first().locator('.conta-valor')).toHaveText(/^−\sR\$\s125,00$/);
    await expect(page.locator('#saldos-contas .saldo-conta', { hasText: 'Conta Perfil B' })).toContainText(/-R\$\s125,00/);

    await despesa(page, 'Internet E2E').locator('summary').click();
    await expect(despesa(page, 'Internet E2E').locator('.pagamento-linha'))
        .toHaveText([/^Pago em 12\/03\/2035 · R\$\s125,00 · Conta Perfil B · Juros ou multa: Multa por atraso$/]);
    await despesa(page, 'Internet E2E').getByRole('button', { name: 'Estornar pagamento' }).click();
    await page.locator('#despesa-painel button[type=submit]').click();
    await expect(page.locator('#despesa-painel .login-error')).toHaveText('Informe o motivo e a data do estorno.');
    await page.fill('#estorno-motivo', 'Debito em duplicidade');
    await page.fill('#estorno-data-estorno', '2035-03-14');
    await page.locator('#despesa-painel button[type=submit]').click();
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Pagamento estornado: R\$\s125,00 devolvidos a Conta Perfil B\. Saldo da conta: R\$\s0,00\.$/);
    await expect(despesa(page, 'Internet E2E').locator('.situacao')).toHaveText('Pendente');
    await expect(despesa(page, 'Internet E2E').locator('.conta-valor')).toHaveText(/120,00/);  // volta ao devido
    await expect(movimentos).toHaveCount(2);
    await expect(movimentos.nth(1)).toContainText('Estorno de despesa · Conta Perfil B');
    await expect(movimentos.nth(1).locator('.conta-valor')).toHaveText(/^\+\sR\$\s125,00$/);
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

    await page.goto('/contas.html?mes=2035-03');
    const movimentos = page.locator('#lista-movimentos .movimento');
    await expect(movimentos.filter({ hasText: '· Recebimento ·' })).toHaveCount(2);
    await expect(movimentos.filter({ hasText: 'Estorno de recebimento ·' })).toHaveCount(2);
});
