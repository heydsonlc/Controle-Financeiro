// FIN-FIDELIDADE-MOVIMENTACOES-1 — tela original de Contas Bancarias do Flask (frontend/templates/contas_bancarias.html)
// sobre o Supabase. Escrita so com o usuario B no "Perfil B" (escritor do novo aplicativo no E2E), em contas criadas
// aqui e inativadas no fim. Usuario A: Pessoal (ainda no Flask: movimento recusado) e Empresa (so leitor).
import { expect, test } from '@playwright/test';

import { registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const ORIGEM = 'Conta E2E Origem';
const DESTINO = 'Conta E2E Destino';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
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

async function abrirTela(page) {
    await page.goto('/contas-bancarias.html');
    await expect(page.locator('#contas-lista .conta-row').first()).toBeVisible();
}

const linha = (page, nome) => page.locator('#contas-lista .conta-row', { hasText: nome });
const toast = (page) => page.locator('#contas-toast');

async function criarConta(page, nome, saldoInicial) {
    await page.click('#btn-nova-conta');
    await page.fill('#conta-nome', nome);
    await page.selectOption('#conta-instituicao', 'Inter');
    await page.selectOption('#conta-tipo', 'Conta Corrente');
    await page.fill('#conta-saldo-inicial', saldoInicial);
    await page.click('#form-conta button[type=submit]');
    await expect(toast(page)).toContainText('Conta criada com sucesso');
    await expect(linha(page, nome)).toBeVisible();
}

test('cadastro, transferencia, ajuste, extrato e conferencia como no Flask', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    await abrirTela(page);
    await expect(linha(page, 'Conta Perfil B')).toBeVisible();

    await criarConta(page, ORIGEM, '1.000,00');
    await criarConta(page, DESTINO, '0,00');
    await expect(linha(page, ORIGEM)).toContainText('R$ 1.000,00');

    // Transferencia: debito na origem e credito no destino (nao e receita nem despesa).
    await linha(page, ORIGEM).locator('[title="Transferir"]').click();
    await page.selectOption('#transfer-destino-id', { label: `${DESTINO} - Inter` });
    await page.fill('#transfer-valor', '250,00');
    await page.click('#form-transferencia button[type=submit]');
    await expect(toast(page)).toContainText('Transferência realizada');
    await expect(linha(page, ORIGEM)).toContainText('R$ 750,00');
    await expect(linha(page, DESTINO)).toContainText('R$ 250,00');

    // Saldo inicial nao muda depois de movimentos (o Flask manda usar o ajuste).
    await linha(page, ORIGEM).locator('[title="Editar"]').click();
    await expect(page.locator('#conta-nome')).toHaveValue(ORIGEM);
    await page.fill('#conta-saldo-inicial', '2.000,00');
    await page.click('#form-conta button[type=submit]');
    await expect(toast(page)).toContainText('Nao e permitido alterar saldo inicial apos existirem movimentos');
    await page.locator('#modal-conta').getByRole('button', { name: /Cancelar/ }).first().click();

    // Ajuste pelo saldo desejado: AJUSTE de credito de R$ 50,00.
    await linha(page, ORIGEM).locator('[title="Ajustar saldo"]').click();
    await page.fill('#ajuste-novo-saldo', '800,00');
    await page.fill('#ajuste-descricao', 'Conferido com o extrato (E2E)');
    await page.click('#form-ajuste button[type=submit]');
    await expect(page.locator('#modal-extrato')).toBeVisible();
    await expect(page.locator('#extrato-saldo')).toHaveText(/R\$\s800,00/);
    const extrato = page.locator('#extrato-lista');
    await expect(extrato.locator('.contas-movimento')).toHaveCount(2);
    await expect(extrato.locator('.contas-movimento').first()).toContainText('Conferido com o extrato (E2E)');
    await expect(extrato.locator('.contas-movimento').first()).toContainText('AJUSTE');
    await expect(extrato.locator('.contas-movimento').nth(1)).toContainText('TRANSFERENCIA');
    await expect(extrato.locator('.contas-movimento').nth(1)).toContainText(/-\sR\$\s250,00/);
    // So o ajuste tem editar e excluir.
    await expect(extrato.locator('.contas-movimento-actions')).toHaveCount(1);

    // Editar o ajuste (R$ 60,00) e depois exclui-lo: saldo volta a R$ 750,00.
    await extrato.locator('[title="Editar ajuste"]').click();
    await page.fill('#ajuste-valor', '60,00');
    await page.click('#form-ajuste button[type=submit]');
    await expect(page.locator('#extrato-saldo')).toHaveText(/R\$\s810,00/);
    await extrato.locator('[title="Excluir ajuste"]').click();
    await expect(page.locator('#extrato-saldo')).toHaveText(/R\$\s750,00/);
    expect(dialogos).toContain('Excluir este ajuste?');
    await expect(extrato.locator('.contas-movimento')).toHaveCount(1);
    await page.locator('#modal-extrato').getByRole('button', { name: 'Fechar' }).first().click();

    // Conferencia (so leitura).
    await linha(page, ORIGEM).locator('[title="Conferir saldo"]').click();
    await expect(page.locator('#conferencia-corpo')).toContainText('Status: Consistente');
    await expect(page.locator('#conferencia-corpo')).toContainText(/R\$\s750,00/);
    await page.locator('#modal-conferencia-saldo').getByRole('button', { name: 'Fechar' }).first().click();

    // Inativar e reativar (historico e saldo preservados); no fim, as duas ficam inativas.
    for (const nome of [ORIGEM, DESTINO]) {
        await linha(page, nome).locator('[title="Inativar"]').click();
        await page.click('#modal-confirmar .contas-danger-btn');
        await expect(toast(page)).toContainText('Conta inativada com sucesso');
    }
    await page.selectOption('#filtro-status', 'INATIVO');
    await expect(linha(page, ORIGEM)).toContainText('R$ 750,00');
    await linha(page, DESTINO).locator('[title="Ativar"]').click();
    await expect(toast(page)).toContainText('Conta reativada com sucesso');
    await page.selectOption('#filtro-status', 'TODAS');
    await linha(page, DESTINO).locator('[title="Inativar"]').click();
    await page.click('#modal-confirmar .contas-danger-btn');
    await expect(toast(page)).toContainText('Conta inativada com sucesso');
});

test('perfil ainda no Flask: movimento recusado sem gravar; leitor sem acoes de escrita', async ({ page }) => {
    await entrar(page, A);
    await abrirTela(page);
    const conta = linha(page, 'Conta Pessoal (A)');
    const antes = await conta.textContent();
    await conta.locator('[title="Ajustar saldo"]').click();
    await page.fill('#ajuste-novo-saldo', '12.345,00');
    await page.click('#form-ajuste button[type=submit]');
    await expect(toast(page)).toContainText('ainda são feitas pelo sistema atual (Flask)');
    await page.locator('#modal-ajuste').getByRole('button', { name: 'Fechar' }).first().click();
    await page.reload();
    await expect(linha(page, 'Conta Pessoal (A)')).toHaveText(antes);

    await trocarPerfil(page, 'Empresa');
    await abrirTela(page);
    await expect(linha(page, 'Conta Empresa (A)')).toBeVisible();
    await expect(page.locator('#btn-nova-conta')).toBeHidden();
    await expect(linha(page, 'Conta Empresa (A)').locator('[title="Editar"]')).toBeHidden();
    await expect(linha(page, 'Conta Empresa (A)').locator('[title="Extrato"]')).toBeVisible();
    await linha(page, 'Conta Empresa (A)').locator('[title="Conferir saldo"]').click();
    await expect(page.locator('#conferencia-corpo')).toContainText('Status:');
});
