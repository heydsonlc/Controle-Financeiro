// FIN-CARTOES-FECHAMENTO-1 — fatura sugerida pelo fechamento, escolha manual e fatura consolidada, em tela de
// celular. Toda escrita com o usuario B no "Perfil B" temporario: cria o proprio cartao, grava so em 2031/2032
// e o inativa no fim. A consolidacao usa o gancho do harness local (o novo aplicativo nao consolida faturas),
// por isso o cenario so roda no banco descartavel (CF_E2E_LOCAL).
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

const normal = (texto) => (texto || '').replace(/\s+/g, ' ').trim();

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
}

async function abrirMes(page, mes) {
    await page.goto(`/cartoes.html?mes=${mes}`);
    await expect(page.locator('#totais')).toBeVisible();
}

function fatura(page, nome) {
    return page.locator('#lista-faturas .conta', { has: page.locator('.conta-nome', { hasText: nome }) });
}

async function categoriaMoradia(page) {
    const valor = await page.locator('#compra-categoria option', { hasText: 'Moradia' }).first().getAttribute('value');
    await page.selectOption('#compra-categoria', valor);
}

test('fechamento confirmado sugere a fatura; manual prevalece; consolidada so com confirmacao', async ({ page }) => {
    test.skip(!process.env.CF_E2E_LOCAL, 'a consolidacao usa o gancho do harness local');
    await entrar(page, B);
    await abrirMes(page, '2032-01');

    // Cadastro: regra do dia e confirmacao explicitas; mudar um dia pede nova confirmacao.
    await page.click('#novo-cartao');
    await page.fill('#cartao-nome', 'Cartao Lilas');
    await page.fill('#cartao-fechamento', '25');
    await page.fill('#cartao-vencimento', '5');
    await expect(page.locator('#cartao-regra')).toHaveValue('PROXIMO');
    await page.check('#cartao-confirmado');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão cadastrado.');
    const cadastro = () => page.locator('#lista-cadastro .conta', { hasText: 'Cartao Lilas' });
    await expect(cadastro().locator('.conta-vencimento')).toHaveText('Fecha dia 25 · vence dia 5');
    await expect(cadastro().locator('.cartao-aviso')).toHaveCount(0);
    await cadastro().locator('summary').click();
    await expect(cadastro().locator('.conta-detalhe')).toContainText('Vai para a próxima fatura');
    await cadastro().getByRole('button', { name: 'Editar cartão' }).click();
    await expect(page.locator('#cartao-confirmado')).toBeChecked();
    await page.fill('#cartao-vencimento', '6');
    await page.locator('#cartao-vencimento').blur();
    await expect(page.locator('#cartao-confirmado')).not.toBeChecked();
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão atualizado.');
    await expect(cadastro().locator('.cartao-aviso')).toHaveText('Fechamento a confirmar');
    await cadastro().locator('summary').click();
    await cadastro().getByRole('button', { name: 'Editar cartão' }).click();
    await page.fill('#cartao-vencimento', '5');
    await page.locator('#cartao-vencimento').blur();
    await page.check('#cartao-confirmado');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão atualizado.');
    await expect(cadastro().locator('.cartao-aviso')).toHaveCount(0);

    // Sugestao: antes, no dia (padrao: proxima) e depois do fechamento; recalculada ao trocar a data.
    await page.click('#nova-compra');
    await page.selectOption('#compra-cartao', { label: 'Cartao Lilas' });
    await page.fill('#compra-data', '2031-11-24');
    await expect(page.locator('#compra-mes')).toHaveValue('2031-12');
    await expect(page.locator('#compra-sugestao')).toHaveText('Sugerida pelo fechamento: fatura 12/2031 (fecha 25/11, vence 05/12).');
    await page.fill('#compra-data', '2031-11-25');
    await expect(page.locator('#compra-mes')).toHaveValue('2032-01');
    await page.fill('#compra-data', '2031-11-26');
    await expect(page.locator('#compra-mes')).toHaveValue('2032-01');
    await expect(page.locator('#compra-sugestao')).toHaveText('Sugerida pelo fechamento: fatura 01/2032 (fecha 25/12, vence 05/01).');

    // Escolha manual nunca e sobrescrita; "Usar a sugerida" volta a sugestao.
    await page.fill('#compra-mes', '2032-02');
    await page.fill('#compra-data', '2031-11-24');
    await expect(page.locator('#compra-sugestao')).toContainText('fatura 12/2031');
    await expect(page.locator('#compra-mes')).toHaveValue('2032-02');
    await expect(page.locator('#compra-sugestao')).toContainText('Mês escolhido: 02/2032.');
    await page.fill('#compra-data', '2031-11-26');
    await expect(page.locator('#compra-sugestao')).toContainText('fatura 01/2032');
    await page.click('#compra-usar-sugerida');
    await expect(page.locator('#compra-mes')).toHaveValue('2032-01');
    await expect(page.locator('#compra-usar-sugerida')).toBeHidden();

    await page.fill('#compra-descricao', 'Mesa E2E');
    await page.fill('#compra-valor', '100,00');
    await categoriaMoradia(page);
    await expect(page.locator('#compra-previa li')).toHaveText(['1/1 · fatura 01/2032 · R$ 100,00']);
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Compra registrada na fatura 01/2032.');

    // Fatura consolidada (gancho local, como a consolidacao do Flask): inclusao so com a caixa marcada.
    const consolidacao = await page.request.post('/__e2e__/consolidar', {
        data: { cartao: 'Cartao Lilas', competencia: '2032-01-01' },
    });
    expect(consolidacao.status()).toBe(200);
    await abrirMes(page, '2032-01');
    await expect(fatura(page, 'Cartao Lilas').locator('.situacao')).toHaveText('Fechada');

    await page.click('#nova-compra');
    await page.selectOption('#compra-cartao', { label: 'Cartao Lilas' });
    await page.fill('#compra-data', '2031-11-27');
    await expect(page.locator('#compra-sugestao')).toContainText('Essa fatura está consolidada: a inclusão pede confirmação.');
    await page.fill('#compra-descricao', 'Cadeira E2E');
    await page.fill('#compra-valor', '10,00');
    await categoriaMoradia(page);
    await expect(page.locator('#compra-previa li')).toHaveText(['1/1 · fatura 01/2032 · R$ 10,00 (fatura consolidada)']);
    const caixa = page.locator('#compra-previa input[type=checkbox]');
    await expect(caixa).toHaveCount(1);
    expect(normal(await page.locator('#compra-previa .form-check').textContent()))
        .toBe('Incluir na fatura consolidada 01/2032: total R$ 100,00 passa a R$ 110,00 (inclusão de R$ 10,00).');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#cartao-painel .login-error')).toHaveText('Confirme a inclusão na fatura consolidada ou escolha outro mês da fatura.');
    await caixa.check();
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Compra registrada na fatura 01/2032.');
    const lilas = fatura(page, 'Cartao Lilas');
    await expect(lilas.locator('.situacao')).toHaveText('Fechada');
    await lilas.locator('summary').click();
    await expect(lilas.locator('.cartao-compra')).toHaveCount(2);
    await expect(lilas.locator('.conta-detalhe').first()).toContainText('R$ 110,00');

    // Limpeza do cenario: o cartao deixa de receber compras (compras e faturas continuam registradas).
    await cadastro().locator('summary').click();
    await cadastro().getByRole('button', { name: 'Inativar' }).click();
    await cadastro().getByRole('button', { name: 'Confirmar inativação' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão inativado.');
});
