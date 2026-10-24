// FIN-CARTOES-PAGAMENTO-1 — pagar e estornar fatura, em tela de celular. Dados FICTICIOS: toda escrita com o
// usuario B no "Perfil B" temporario (atribuido ao novo aplicativo; conta "Conta Perfil B", saldo inicial 0), num
// cartao criado aqui, so em 05/2034, e inativado no fim (cartao ativo entraria na geracao dos outros cenarios).
// Total, conta, saldo e pagamento vigente sao conferidos no banco; aqui so a tela e o que ela mostra depois.
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

function fatura(page, nome) {
    return page.locator('#lista-faturas .conta', { has: page.locator('.conta-nome', { hasText: nome }) });
}

test('pagar com juros justificados, estornar e pagar de novo: situacao, historico e saldo', async ({ page }) => {
    await entrar(page, B);
    await page.goto('/cartoes.html?mes=2034-05');
    await expect(page.locator('#totais')).toBeVisible();
    await page.click('#novo-cartao');
    await page.fill('#cartao-nome', 'Cartao Pagamento');
    await page.fill('#cartao-fechamento', '3');
    await page.fill('#cartao-vencimento', '12');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão cadastrado.');
    await page.click('#nova-compra');
    await page.selectOption('#compra-cartao', { label: 'Cartao Pagamento' });
    await page.fill('#compra-descricao', 'Compra a pagar E2E');
    await page.fill('#compra-valor', '150,00');
    await page.fill('#compra-data', '2034-05-02');
    await page.fill('#compra-mes', '2034-05');
    const moradia = await page.locator('#compra-categoria option', { hasText: 'Moradia' }).first().getAttribute('value');
    await page.selectOption('#compra-categoria', moradia);
    await expect(page.locator('#compra-previa li')).toHaveCount(1);
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Compra registrada na fatura 05/2034.');

    const item = () => fatura(page, 'Cartao Pagamento');
    await expect(item().locator('.situacao')).toHaveText('Aberta');
    await item().locator('summary').click();
    await item().getByRole('button', { name: 'Pagar fatura' }).click();
    // Preenchido pelo que o sistema conhece: total das compras, data de hoje, conta ativa do perfil.
    await expect(page.locator('#pagamento-valor')).toHaveValue('150,00');
    await expect(page.locator('#pagamento-conta option')).toHaveText([/^Conta Perfil B · saldo R\$\s0,00$/]);
    await expect(page.locator('.pagamento-ajuste')).toBeHidden();
    await page.fill('#pagamento-valor', '155,00');
    await expect(page.locator('.pagamento-ajuste')).toBeVisible();
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#cartao-painel .login-error')).toHaveText('Classifique a diferença e escreva a justificativa.');
    await page.selectOption('#pagamento-tipo', 'JUROS');
    await page.fill('#pagamento-justificativa', 'Pago com atraso');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Fatura paga: R\$\s155,00 debitados de Conta Perfil B\. Saldo da conta: -R\$\s155,00\.$/);
    await expect(item().locator('.situacao')).toHaveText('Paga');
    await expect(page.getByRole('button', { name: 'Pagar fatura' })).toHaveCount(0);

    await item().locator('summary').click();
    await expect(item().locator('.pagamento-linha')).toHaveText([/Pago em \d\d\/\d\d\/\d{4} · R\$\s155,00 · Conta Perfil B · Juros ou encargos: Pago com atraso/]);
    await item().getByRole('button', { name: 'Estornar pagamento' }).click();
    await expect(page.locator('#cartao-painel dl')).toContainText(/R\$\s155,00/);
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#cartao-painel .login-error')).toHaveText('Informe o motivo e a data do estorno.');
    await page.fill('#estorno-motivo', 'Debito em duplicidade no banco');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Pagamento estornado: R\$\s155,00 devolvidos a Conta Perfil B\. Saldo da conta: R\$\s0,00\.$/);
    await expect(item().locator('.situacao')).toHaveText('Aberta');

    // O historico continua consultavel e a fatura pode ser paga de novo (outro pagamento, outra identidade).
    await item().locator('summary').click();
    await expect(item().locator('.pagamento-estornado')).toHaveText([/estornado em \d\d\/\d\d\/\d{4} \(Debito em duplicidade no banco\)$/]);
    await item().getByRole('button', { name: 'Pagar fatura' }).click();
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado'))
        .toHaveText(/^Fatura paga: R\$\s150,00 debitados de Conta Perfil B\. Saldo da conta: -R\$\s150,00\.$/);
    await item().locator('summary').click();
    await expect(item().locator('.pagamento-linha')).toHaveCount(2);  // estornado + vigente
    await expect(item().getByRole('button', { name: 'Estornar pagamento' })).toBeVisible();

    const cadastro = () => page.locator('#lista-cadastro .conta', { hasText: 'Cartao Pagamento' });
    await cadastro().locator('summary').click();
    await cadastro().getByRole('button', { name: 'Inativar' }).click();
    await cadastro().getByRole('button', { name: 'Confirmar inativação' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão inativado.');
});
