// FIN-CARTOES-MULTIPLOS-01 — contrato com varios cartoes vinculados e fatura unica, pelas telas originais: os cartoes
// (fisico cancelado, virtual ativo) cadastrados no detalhe do contrato em Cartoes; a fatura do Nubank em PDF FICTICIO (com o
// final de cada compra) importada com o cartao de origem; a linha sem cartao no documento fica sem cartao identificado;
// a fatura por cartao soma o valor a pagar. So o usuario B, no "Perfil B", num contrato criado aqui, em 06/2035; o
// contrato e inativado no fim.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { gerarPdf } from '../pdf-ficticio.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CONTRATO = 'Contrato Multiplo E2E';

test.use({ viewport: { width: 1600, height: 900 } });

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

const detalhe = (page) => page.locator('#cartao-detalhe');
const linhaVinculado = (page, final) => page.locator('.cartoes-vinculados-card .fatura-table-row', { hasText: `•••• ${final}` });

async function abrirContrato(page, mes) {
    await page.goto('/cartoes.html');
    await expect(page.locator('#lista-cartoes .loading')).toHaveCount(0);
    await page.locator('#lista-cartoes .cartao-list-item', { hasText: CONTRATO }).click();
    await expect(detalhe(page).locator('.cartao-detail-header h2')).toHaveText(CONTRATO);
    if (mes) {
        const campo = page.locator('[data-action="alterar-mes-fatura"]');
        await campo.fill(mes);
        await campo.dispatchEvent('change');
        await expect(page.locator('.fatura-card-header p')).toHaveText(`Consumo agrupado por Categoria do Cartão em ${mes}.`);
    }
}

async function salvarVinculado(page, campos) {
    if (campos.nome) await page.fill('#vinculado-nome', campos.nome);
    if (campos.final) await page.fill('#vinculado-final', campos.final);
    if (campos.tipo) await page.selectOption('#vinculado-tipo', campos.tipo);
    if (campos.portador) await page.fill('#vinculado-portador', campos.portador);
    if (campos.situacao) await page.selectOption('#vinculado-situacao', campos.situacao);
    if (campos.cancelamento) await page.fill('#vinculado-cancelamento', campos.cancelamento);
    await page.locator('#form-cartao-vinculado button[type="submit"]').click();
    await expect(page.locator('#modal-cartao-vinculado')).not.toHaveClass(/open/);
}

// Fatura do Nubank FICTICIA (layout real: data, final do cartao, descricao, valor; credito com sinal)
function faturaNubankFicticia() {
    return gerarPdf([
        [[[40, 'TITULAR FICTICIO']], [[40, 'FATURA 08 JUN 2035']], [[40, 'Total a pagar R$ 113,70']], [[40, 'Nu Pagamentos S.A.']]],
        [[[40, 'FATURA 08 JUN 2035']], [[40, 'TRANSAÇÕES DE 29 ABR A 29 MAI']],
            [[40, '02 MAI'], [90, '**** 1111'], [150, 'Padaria Fisico E2E'], [400, 'R$ 9,00']],
            [[40, '03 MAI'], [90, '**** 2222'], [150, 'Loja Virtual E2E'], [400, 'R$ 35,70']],
            [[40, '04 MAI'], [150, 'Plano Celular E2E'], [400, 'R$ 70,00']],
            [[40, '05 MAI'], [150, 'Credito Ajuste E2E'], [400, '-R$ 1,00']]],
    ]);
}

test('contrato com cartoes vinculados: cadastro, importacao com o cartao de origem e fatura por cartao', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const moradia = (await chamarRpc(page, 'categorias_de_despesa', {})).corpo.find((c) => c.nome.startsWith('Moradia')).id;
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CONTRATO, dia_fechamento: 3, dia_vencimento: 8 } });
    expect(criado.status).toBe(200);
    const contrato = criado.corpo.cartao_id;

    // Cartoes do contrato, no detalhe (modal compacto): fisico e virtual; o fisico cancelado continua no historico
    await abrirContrato(page);
    await expect(page.locator('.cartoes-vinculados-card')).toContainText('Nenhum cartão vinculado');
    await page.locator('[data-action="novo-vinculado"]').click();
    await salvarVinculado(page, { nome: 'Fisico titular', final: '1111', tipo: 'FISICO', portador: 'Titular' });
    await page.locator('[data-action="novo-vinculado"]').click();
    await salvarVinculado(page, { nome: 'Virtual compras', final: '2222', tipo: 'VIRTUAL' });
    await linhaVinculado(page, '1111').locator('[data-action="editar-vinculado"]').click();
    await expect(page.locator('#vinculado-final')).toHaveValue('1111');
    await salvarVinculado(page, { situacao: 'CANCELADO', cancelamento: '2035-05-20' });
    await expect(linhaVinculado(page, '1111')).toContainText('Cancelado');
    await expect(linhaVinculado(page, '2222')).toContainText('Ativo');

    // Importacao do PDF: o cartao de origem pelo final; o que o documento nao diz fica sem cartao identificado
    await page.goto('/importar-cartao.html');
    await expect(page.locator('#cartaoSelect option', { hasText: CONTRATO })).toHaveCount(1);
    await page.selectOption('#cartaoSelect', { label: CONTRATO });
    await page.fill('#competenciaInput', '06/2035');
    await page.locator('#competenciaInput').dispatchEvent('input');
    await page.locator('#csvFile').setInputFiles({ name: 'Nubank_2035-06-08.pdf', mimeType: 'application/pdf', buffer: faturaNubankFicticia() });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('PDF analisado com sucesso.');
    await page.click('#btnStep4');
    const linha = (texto) => page.locator('#editorPrePersistencia tr', { hasText: texto });
    const seletor = (texto) => linha(texto).locator('select[aria-label="Cartão de origem"]');
    await expect(seletor('Padaria Fisico E2E').locator('option:checked')).toHaveText('•••• 1111 · físico (cancelado) (arquivo)');
    await expect(seletor('Loja Virtual E2E').locator('option:checked')).toHaveText('•••• 2222 · virtual (arquivo)');
    await expect(seletor('Plano Celular E2E').locator('option:checked')).toHaveText('Cartão não identificado');
    for (const texto of ['Padaria Fisico E2E', 'Loja Virtual E2E', 'Plano Celular E2E']) {
        await linha(texto).locator('.import-category-cell select').selectOption(String(moradia));
    }
    await expect(page.locator('#btnImportar')).toContainText('(4)');
    await page.click('#btnImportar');
    await expect(page.locator('#resultadoContainer')).toContainText('Importação concluída.');
    expect(dialogos.find((d) => d.startsWith('Confirmar importacao'))).toBeTruthy();

    // Cartoes: a fatura unica por cartao (o que nao tem cartao identificado a parte) e a soma igual ao total
    const resumo = (await chamarRpc(page, 'fatura_por_categoria', { p_perfil_id: perfil, p_cartao_id: contrato, p_mes: '2035-06-01' })).corpo;
    expect(resumo.por_cartao.map((c) => [c.final, Number(c.total)])).toEqual([['2222', 35.7], ['1111', 9], [null, 69]]);
    expect(Number(resumo.total_fatura)).toBeCloseTo(113.7, 2);
    await abrirContrato(page, '2035-06');
    const porCartao = page.locator('.fatura-por-cartao .fatura-table-row');
    await expect(porCartao).toHaveCount(3);
    await expect(porCartao.nth(2)).toContainText('Sem cartão identificado');
    await expect(page.locator('.fatura-lancamento-row', { hasText: 'Loja Virtual E2E' })).toContainText('•••• 2222');
    await porCartao.nth(1).locator('[data-action="ver-lancamentos-fatura"]').click();
    await expect(page.locator('.fatura-lancamento-row')).toHaveCount(1);
    await expect(page.locator('.fatura-lancamento-row')).toContainText('Padaria Fisico E2E');

    // Limpeza do cenario: o contrato inativado (compras, cartoes e faturas continuam registrados)
    const registro = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.id === contrato);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: contrato, p_versao: registro.versao })).status).toBe(200);
});
