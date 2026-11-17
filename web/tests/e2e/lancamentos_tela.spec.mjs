// FIN-FIDELIDADE-MOVIMENTACOES-1 — tela original de Lancamentos do Flask (frontend/templates/lancamentos.html) sobre o
// Supabase. Escrita so com o usuario B no "Perfil B", num cartao criado aqui (inativado no fim), em 02/2034. Leitor:
// usuario A no perfil Empresa.
import { expect, test } from '@playwright/test';

import * as cad from './cadastro.mjs';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Lancamentos E2E';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to|Ponte CSP/i.test(msg.text())) problemas.push(msg.text());
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
    await page.goto('/lancamentos.html');
    await expect(page.locator('#filtro-mes')).not.toHaveValue('');  // inicializarFiltros ja rodou
    await expect(page.locator('#lista-lancamentos')).not.toContainText('Carregando');
    // Todos os meses (o Flask abre no mes atual).
    await page.fill('#filtro-mes', '');
    await page.locator('#filtro-mes').dispatchEvent('change');
}

const linha = (page, texto) => page.locator('#lista-lancamentos .tbl-row', { hasText: texto });

// FIN-MVP-CADASTRO-UNIFICADO-01: o painel "Novo lancamento" oferece a escolha do tipo; Despesa direta e Compra no cartao
// abrem o modal unico (cadastro.mjs); o formulario original fica para abastecimento, entrada/credito e edicao.
async function novo(page, tipo) {
    await page.click('#btn-novo-lancamento');
    await expect(page.locator('#cf-lanc-escolha')).toBeVisible();
    await expect(page.locator('#form-lancamento')).toBeHidden();
    await page.click(tipo === 'cartao' ? '#cf-lanc-cartao' : '#cf-lanc-despesa');
    await cad.esperarModal(page, tipo === 'cartao' ? 'compra' : 'direta');
}

async function salvar(page) {
    await page.locator('#form-lancamento').evaluate((f) => f.requestSubmit());
}

test('despesa direta, compra no cartao, recusas e exclusoes como no Flask', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 },
        p_chave: crypto.randomUUID() });
    expect(criado.status).toBe(200);
    await abrirTela(page);

    // Despesa direta (pendente), pelo modal unico. A competencia continua a da tela Lancamentos: o mes da propria data,
    // mostrada no modal e sem ajuste manual (a regra de Despesas, mes anterior ao vencimento, nao vale aqui).
    await novo(page, 'direto');
    await expect(page.locator('#cad-modal .mob-campo', { has: page.locator('#cad-vencimento') })).toContainText('Data *');
    await cad.preencherCadastro(page, { nome: 'Padaria Lanc E2E', valor: '23.40', vencimento: '2034-02-05' });
    await expect(page.locator('#cad-competencia-texto')).toHaveText('Competência: fevereiro/2034');
    await expect(page.locator('#cad-alterar-competencia')).toBeHidden();
    await expect(cad.modal(page)).not.toContainText(/já foi paga|Data de pagamento/i);  // "paga" na criacao nao existe mais
    await page.locator('#cad-salvar').dblclick();
    await expect(cad.confirmacao(page)).toContainText('“Padaria Lanc E2E” cadastrada como pendente');
    await expect(cad.confirmacao(page)).toContainText('Despesa salva na competência 02/2034.');
    await page.click('#cad-concluir');
    await expect(cad.modal(page)).toHaveCount(0);
    await expect(page).toHaveURL(/lancamentos\.html/);  // volta a origem
    await page.fill('#filtro-mes', '');
    await page.locator('#filtro-mes').dispatchEvent('change');
    await expect(linha(page, 'Padaria Lanc E2E')).toHaveCount(1);  // toque duplo: uma despesa so
    const doMes = async (mes) => (await chamarRpc(page, 'contas_do_mes', { p_perfil_id: perfil, p_mes: `${mes}-01` })).corpo
        .filter((c) => c.nome === 'Padaria Lanc E2E').map((c) => c.status_pagamento);
    expect(await doMes('2034-02')).toEqual(['Pendente']);
    expect(await doMes('2034-01')).toEqual([]);

    // Um so caminho: o formulario do painel nao cria mais despesa nem compra comum (so com abastecimento); pedir por
    // ele, mesmo "paga", e recusado sem gravar.
    const recusa = await page.evaluate(async () => (await fetch('/api/despesas', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: 'Paga Lanc E2E', valor: 10, categoria_id: 1, data_vencimento: '2034-02-06', pago: true }) })).json());
    expect(recusa.success).toBe(false);
    await expect.poll(() => dialogos.join('|')).toContain('Use a ação de pagamento em Despesas');
    const comum = await page.evaluate(async () => (await fetch('/api/despesas', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: 'Paga Lanc E2E', valor: 10, categoria_id: 1, data_vencimento: '2034-02-06' }) })).json());
    expect(comum.success).toBe(false);
    await expect.poll(() => dialogos.join('|')).toContain('Por este formulário só se lança despesa ou compra com abastecimento');
    const despesas = await chamarRpc(page, 'despesas_diretas_tela', { p_perfil_id: perfil });
    expect(despesas.corpo.filter((d) => d.nome === 'Paga Lanc E2E')).toEqual([]);

    // Compra parcelada no cartao (3 parcelas a partir de 02/2034), pelo modal unico.
    await page.reload();
    await abrirTela(page);
    await novo(page, 'cartao');
    await cad.preencherCadastro(page, { cartao: CARTAO, nome: 'Fone Lanc E2E', valor: '90', data: '2034-02-05', fatura: '2034-02', parcelas: 3 });
    expect(await cad.salvarCadastro(page)).toContain(`Compra lançada em 3 parcelas no cartão ${CARTAO}`);
    await page.fill('#filtro-mes', '');
    await page.locator('#filtro-mes').dispatchEvent('change');
    await expect(linha(page, 'Fone Lanc E2E')).toHaveCount(3);

    // Editar compra aqui gravaria uma compra nova (defeito do Flask): recusado, nada gravado.
    await linha(page, 'Fone Lanc E2E').first().locator('[title="Editar"]').click();
    await expect(page.locator('#lancamento-descricao')).toHaveValue('Fone Lanc E2E');
    await expect(page.locator('#lancamento-mes-fatura')).toHaveValue('2034-04');
    await page.waitForTimeout(600);  // a edicao do Flask repreenche cartao e categorias em setTimeout encadeados
    await page.selectOption('#lancamento-categoria-despesa-cartao', { index: 1 });  // o formulario exige (como no Flask)
    await salvar(page);
    await expect.poll(() => dialogos.join('|')).toContain('use a tela Cartões');
    const cartao = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.nome === CARTAO);
    const compras = await chamarRpc(page, 'compras_do_cartao_tela', { p_perfil_id: perfil, p_cartao_id: cartao.id });
    expect(compras.corpo.length).toBe(3);

    // Excluir a compra (parcelas em fatura aberta) e a despesa direta.
    await page.reload();
    await abrirTela(page);
    await linha(page, 'Fone Lanc E2E').first().locator('[title="Excluir"]').click();
    await expect(linha(page, 'Fone Lanc E2E')).toHaveCount(0);
    expect(dialogos.join('|')).toContain('Esta compra é parcelada (3 parcelas)');
    await linha(page, 'Padaria Lanc E2E').locator('[title="Excluir"]').click();
    await expect(linha(page, 'Padaria Lanc E2E')).toHaveCount(0);

    const versao = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.nome === CARTAO).versao;
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao.id, p_versao: versao })).status).toBe(200);
});

test('leitor ve os lancamentos sem acoes de escrita', async ({ page }) => {
    await entrar(page, A);
    await trocarPerfil(page, 'Empresa');
    await abrirTela(page);
    await expect(page.locator('#btn-novo-lancamento')).toBeHidden();
    await expect(page.locator('#lista-lancamentos [data-on-click^="excluirLancamento("]:visible')).toHaveCount(0);
});
