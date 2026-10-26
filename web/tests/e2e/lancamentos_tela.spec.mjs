// FIN-FIDELIDADE-MOVIMENTACOES-1 — tela original de Lancamentos do Flask (frontend/templates/lancamentos.html) sobre o
// Supabase. Escrita so com o usuario B no "Perfil B", num cartao criado aqui (inativado no fim), em 02/2034. Leitor:
// usuario A no perfil Empresa.
import { expect, test } from '@playwright/test';

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

async function novo(page, tipo) {
    await page.click('#btn-novo-lancamento');
    await page.selectOption('#lancamento-tipo', tipo);
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

    // Despesa direta (pendente).
    await novo(page, 'direto');
    await page.fill('#lancamento-descricao', 'Padaria Lanc E2E');
    await page.fill('#lancamento-valor', '23.40');
    await page.fill('#lancamento-data', '2034-02-05');
    await page.selectOption('#lancamento-categoria-geral', { index: 1 });
    await salvar(page);
    await expect.poll(() => dialogos.join('|')).toContain('Despesa direta salva com sucesso!');
    await page.fill('#filtro-mes', '');
    await page.locator('#filtro-mes').dispatchEvent('change');
    await expect(linha(page, 'Padaria Lanc E2E')).toBeVisible();

    // "Paga" na criacao: recusada com o motivo (pagar escolhe a conta e registra o movimento); nada gravado.
    await novo(page, 'direto');
    await page.fill('#lancamento-descricao', 'Paga Lanc E2E');
    await page.fill('#lancamento-valor', '10');
    await page.fill('#lancamento-data', '2034-02-06');
    await page.selectOption('#lancamento-categoria-geral', { index: 1 });
    await page.check('#lancamento-pago');
    await salvar(page);
    await expect.poll(() => dialogos.join('|')).toContain('Use a ação de pagamento em Despesas');
    const despesas = await chamarRpc(page, 'despesas_diretas_tela', { p_perfil_id: perfil });
    expect(despesas.corpo.filter((d) => d.nome === 'Paga Lanc E2E')).toEqual([]);

    // Compra parcelada no cartao (3 parcelas a partir de 02/2034).
    await page.reload();
    await abrirTela(page);
    await novo(page, 'cartao');
    await page.selectOption('#lancamento-cartao', { label: CARTAO });
    await page.selectOption('#lancamento-categoria-despesa-cartao', { index: 1 });
    await page.fill('#lancamento-descricao', 'Fone Lanc E2E');
    await page.fill('#lancamento-valor', '90');
    await page.fill('#lancamento-data', '2034-02-05');
    await page.fill('#lancamento-mes-fatura', '2034-02');
    await page.fill('#lancamento-parcelas', '3');
    await salvar(page);
    await expect.poll(() => dialogos.join('|')).toContain('Lançamento em cartão salvo com sucesso!');
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
