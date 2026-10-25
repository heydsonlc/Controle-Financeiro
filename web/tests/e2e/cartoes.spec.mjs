// FIN-CARTOES-1 — cartoes e compras, em tela de celular. Dados FICTICIOS
// (tests/supabase_local.py: semear_contas e semear_cartoes_e2e). Leituras com o usuario A (gestor do
// Pessoal, LEITOR da Empresa); toda escrita com o usuario B no "Perfil B" temporario: cria o proprio
// cartao, grava so em 2031 e o inativa no fim (cartao ativo entraria na geracao dos outros cenarios).
// Pessoal fica no Flask (D5 do FIN-CARTOES-PAGAMENTO-1): nenhuma acao de pagamento na tela dele.
import { expect, test } from '@playwright/test';

import { irPeloMenu, itemDoMenu, trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
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
const textos = async (locator) => (await locator.allTextContents()).map(normal);

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

const SEM_PAGAMENTO = /pagar|pagamento|baixa|estornar|conciliar/i;

test('aba Cartoes a partir de Contas do mes: faturas como na tela de contas, sem pagamento', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/contas.html?mes=2026-11');
    await expect(page.locator('#totais')).toBeVisible();
    await irPeloMenu(page, 'cartoes');
    await page.waitForURL(/cartoes\.html\?mes=2026-11$/);
    await expect(itemDoMenu(page, 'cartoes')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('#totais')).toBeVisible();
    expect(await textos(page.locator('#lista-faturas .conta-nome'))).toEqual(['Cartao Azul', 'Cartao Verde']);
    await expect(fatura(page, 'Cartao Azul').locator('.conta-valor')).toHaveText('R$ 1.320,00');  // = Contas do mes
    await expect(fatura(page, 'Cartao Azul').locator('.situacao')).toHaveText('Aberta');
    await expect(fatura(page, 'Cartao Verde').locator('.conta-valor')).toHaveText('R$ 120,00');
    await expect(fatura(page, 'Cartao Verde').locator('.situacao')).toHaveText('Paga');
    await expect(page.getByRole('button', { name: SEM_PAGAMENTO })).toHaveCount(0);

    const verde = fatura(page, 'Cartao Verde');
    await verde.locator('summary').click();
    await expect(verde.locator('.cartao-compra')).toHaveCount(2);
    await expect(verde.locator('.cartao-compra button')).toHaveCount(0);
    await expect(verde.locator('.despesa-bloqueio').first()).toHaveText(/Fatura paga: para corrigir, estorne o pagamento/);
});

test('cadastro mostra so o final do numero; inativo fora das faturas', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2031-05');
    const antigo = page.locator('#lista-cadastro .conta', { hasText: 'Cartao Antigo' });
    await expect(antigo.locator('.conta-nome')).toHaveText('Cartao Antigo •••• 8888');
    await expect(antigo.locator('.conta-vencimento')).toHaveText('Fecha dia 25 · vence dia 10');
    await expect(antigo.locator('.situacao')).toHaveText('Inativo');
    await expect(fatura(page, 'Cartao Antigo')).toHaveCount(0);
    expect(await page.content()).not.toContain('5555');
});

test('cartao e compra parcelada: cadastro, previa, edicao, exclusao e inativacao', async ({ page }) => {
    await entrar(page, B);
    await abrirMes(page, '2031-05');
    await page.click('#novo-cartao');
    await page.fill('#cartao-nome', 'Cartao Roxo');
    await page.fill('#cartao-fechamento', '3');
    await page.fill('#cartao-vencimento', '12');
    await page.fill('#cartao-limite', '2.500,00');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão cadastrado.');
    const cadastro = () => page.locator('#lista-cadastro .conta', { hasText: 'Cartao Roxo' });
    await expect(cadastro().locator('.conta-vencimento')).toHaveText('Fecha dia 3 · vence dia 12');
    await cadastro().locator('summary').click();
    await cadastro().getByRole('button', { name: 'Editar cartão' }).click();
    await page.fill('#cartao-vencimento', '10');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão atualizado.');
    await expect(cadastro().locator('.conta-vencimento')).toHaveText('Fecha dia 3 · vence dia 10');
    await expect(fatura(page, 'Cartao Roxo').locator('.situacao')).toHaveText('Sem compras');

    await page.click('#nova-compra');
    await page.selectOption('#compra-cartao', { label: 'Cartao Roxo' });
    await page.fill('#compra-descricao', 'Geladeira E2E');
    await page.fill('#compra-valor', '100,00');
    await page.fill('#compra-parcelas', '3');
    await page.fill('#compra-data', '2031-05-12');
    const moradia = await page.locator('#compra-categoria option', { hasText: 'Moradia' }).first().getAttribute('value');
    await page.selectOption('#compra-categoria', moradia);  // no projeto real o nome leva o marcador do seed
    await expect(page.locator('#compra-previa li')).toHaveCount(3);
    expect(await textos(page.locator('#compra-previa li'))).toEqual([
        '1/3 · fatura 05/2031 · R$ 33,34', '2/3 · fatura 06/2031 · R$ 33,33', '3/3 · fatura 07/2031 · R$ 33,33',
    ]);
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Compra registrada em 3 parcelas, a partir da fatura 05/2031.');

    const roxo = fatura(page, 'Cartao Roxo');
    expect(normal(await roxo.locator('.conta-valor').textContent())).toBe('R$ 33,34');
    await expect(roxo.locator('.situacao')).toHaveText('Aberta');
    await expect(roxo.locator('.conta-vencimento')).toHaveText('Vence 10/05/2031');
    await roxo.locator('summary').click();
    const compra = roxo.locator('.cartao-compra', { hasText: 'Geladeira E2E' });
    await expect(compra.locator('.conta-vencimento')).toHaveText(/^12\/05\/2031 · 1\/3 · Moradia/);
    await compra.getByRole('button', { name: 'Editar' }).click();
    await expect(page.locator('#edicao-valor')).toHaveCount(0);  // parcelada: valor e datas nao mudam aqui
    await page.fill('#edicao-descricao', 'Geladeira nova E2E');
    await page.click('#cartao-painel button[type=submit]');
    await expect(page.locator('#acao-resultado')).toHaveText('Compra atualizada.');

    await abrirMes(page, '2031-06');
    const junho = fatura(page, 'Cartao Roxo');
    expect(normal(await junho.locator('.conta-valor').textContent())).toBe('R$ 33,33');
    await junho.locator('summary').click();
    const parcela = junho.locator('.cartao-compra', { hasText: 'Geladeira nova E2E' });
    await expect(parcela.locator('.conta-vencimento')).toHaveText(/2\/3/);
    await parcela.getByRole('button', { name: 'Excluir' }).click();
    await expect(parcela.locator('.despesa-pergunta')).toHaveText('Excluir a compra inteira (3 parcelas)?');
    await parcela.getByRole('button', { name: 'Confirmar exclusão' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('3 parcelas excluídas.');
    expect(normal(await fatura(page, 'Cartao Roxo').locator('.conta-valor').textContent())).toBe('R$ 0,00');

    await cadastro().locator('summary').click();
    await cadastro().getByRole('button', { name: 'Inativar' }).click();
    await cadastro().getByRole('button', { name: 'Confirmar inativação' }).click();
    await expect(page.locator('#acao-resultado')).toHaveText('Cartão inativado.');
    await expect(cadastro().locator('.situacao')).toHaveText('Inativo');
    await expect(fatura(page, 'Cartao Roxo')).toHaveCount(0);
});

test('LEITOR ve faturas e compras sem nenhuma acao', async ({ page }) => {
    await entrar(page, A);
    await abrirMes(page, '2026-11');
    await trocarPerfil(page, 'Empresa');
    await expect(fatura(page, 'Cartao Empresa').locator('.conta-valor')).toHaveText('R$ 250,00');
    await expect(page.locator('#nova-compra')).toHaveCount(0);
    await expect(page.locator('#novo-cartao')).toHaveCount(0);
    const empresa = fatura(page, 'Cartao Empresa');
    await empresa.locator('summary').click();
    await expect(empresa.locator('.cartao-compra')).toHaveCount(1);
    await expect(page.locator('#lista-faturas button, #lista-cadastro button')).toHaveCount(0);
});
