// FIN-MOB-ABAST-LANCAMENTOS-01 — "Dados do Abastecimento" no formulario de Novo Lancamento: o bloco aparece so com a
// Categoria de Despesa Combustivel, calcula os litros e grava a despesa e o abastecimento juntos; a compra ja lancada recebe o
// abastecimento sem mudar. Usuario E (perfil proprio: dois veiculos e um cartao com dois cartoes fisicos). Dados FICTICIOS;
// grava no banco descartavel.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const E = { email: process.env.CF_EMAIL_E || 'usuario.e@teste.local', senha: process.env.CF_SENHA_E };
const CARTAO = 'Cartao E (ficticio)';

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

const hoje = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());

async function entrar(page) {
    await page.goto('/index.html');
    await page.fill('#email', E.email);
    await page.fill('#senha', E.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function abrirTela(page) {
    await page.goto('/lancamentos.html');
    await expect(page.locator('#filtro-mes')).not.toHaveValue('');
    await expect(page.locator('#lista-lancamentos')).not.toContainText('Carregando');
    await page.fill('#filtro-mes', '');
    await page.locator('#filtro-mes').dispatchEvent('change');
}

async function contexto(page) {
    const perfil = await perfilAtivoId(page);
    const f = (await chamarRpc(page, 'formulario_abastecimento_lancamento', { p_perfil_id: perfil })).corpo;
    const veiculos = Object.fromEntries(f.veiculos.map((v) => [v.nome, v.id]));
    const cartao = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.nome === CARTAO).id;
    return { perfil, combustivel: String(f.categoria_combustivel_id), veiculos, cartao };
}

const linha = (page, texto) => page.locator('#lista-lancamentos .tbl-row', { hasText: texto });
const salvar = (page) => page.locator('#form-lancamento').evaluate((f) => f.requestSubmit());
const opcoes = (page, id) => page.locator(`#${id} option`).allTextContents();

async function compraCombustivel(page, ctx, { descricao, valor }) {
    await page.click('#btn-novo-lancamento');
    await page.selectOption('#lancamento-tipo', 'cartao');
    await page.selectOption('#lancamento-cartao', String(ctx.cartao));
    await expect(page.locator(`#lancamento-categoria-despesa-cartao option[value="${ctx.combustivel}"]`)).toHaveCount(1);
    await page.selectOption('#lancamento-categoria-despesa-cartao', ctx.combustivel);
    await page.fill('#lancamento-descricao', descricao);
    await page.fill('#lancamento-valor', valor);
    await page.fill('#lancamento-data', hoje());
    await page.fill('#lancamento-mes-fatura', hoje().slice(0, 7));
}

test('bloco so com Combustivel: veiculos, combustiveis, cartoes fisicos, litros e dados preservados', async ({ page }) => {
    await entrar(page);
    await abrirTela(page);
    const ctx = await contexto(page);
    await expect(page.locator('#bloco-abastecimento')).toBeHidden();
    await compraCombustivel(page, ctx, { descricao: 'POSTO TELA E', valor: '176' });
    await expect(page.locator('#bloco-abastecimento')).toBeVisible();
    expect(await opcoes(page, 'abast-veiculo')).toEqual(['Só a despesa (sem abastecimento)', 'Flex E (ficticio)', 'Gasolina E (ficticio)']);
    await page.selectOption('#abast-veiculo', String(ctx.veiculos['Flex E (ficticio)']));
    expect(await opcoes(page, 'abast-combustivel')).toEqual(['Gasolina', 'Etanol']);
    await page.selectOption('#abast-veiculo', String(ctx.veiculos['Gasolina E (ficticio)']));
    expect(await opcoes(page, 'abast-combustivel')).toEqual(['Gasolina']);
    await expect(page.locator('#abast-cartao-fisico-grupo')).toBeVisible();
    expect(await opcoes(page, 'abast-cartao-fisico')).toEqual(['Não identificado', 'Adicional E •••• 2222', 'Titular E •••• 1111']);  // ordem do banco (por nome)

    await page.fill('#abast-preco', '4.40');
    await expect(page.locator('#abast-litros')).toHaveText('40,000 L');
    await page.fill('#lancamento-valor', '200');
    await expect(page.locator('#abast-litros')).toHaveText('45,455 L');
    await page.fill('#abast-hodometro', '1000');

    // outra categoria esconde o bloco sem apagar o que foi preenchido
    const outra = await page.locator(`#lancamento-categoria-despesa-cartao option:not([value=""]):not([value="${ctx.combustivel}"])`).first().getAttribute('value');
    await page.selectOption('#lancamento-categoria-despesa-cartao', outra);
    await expect(page.locator('#bloco-abastecimento')).toBeHidden();
    await page.selectOption('#lancamento-categoria-despesa-cartao', ctx.combustivel);
    await expect(page.locator('#bloco-abastecimento')).toBeVisible();
    await expect(page.locator('#abast-hodometro')).toHaveValue('1000');
    await expect(page.locator('#abast-veiculo')).toHaveValue(String(ctx.veiculos['Gasolina E (ficticio)']));

    // celular: o bloco cabe na tela, sem rolagem horizontal
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#bloco-abastecimento').scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    const caixa = await page.locator('#bloco-abastecimento').boundingBox();
    expect(caixa.x >= 0 && caixa.x + caixa.width <= 391).toBe(true);
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.click('.lanc-panel-action[title="Limpar formulario"]');
    await expect(page.locator('#bloco-abastecimento')).toBeHidden();
});

test('compra no cartao com abastecimento: uma compra e um abastecimento vinculados, com o cartao fisico', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page);
    await abrirTela(page);
    const ctx = await contexto(page);
    const flex = ctx.veiculos['Flex E (ficticio)'];
    await compraCombustivel(page, ctx, { descricao: 'POSTO NOVO E', valor: '176' });
    await page.selectOption('#abast-veiculo', String(flex));
    await page.selectOption('#abast-combustivel', 'gasolina');
    await page.fill('#abast-hodometro', '52000');
    await page.fill('#abast-preco', '4.40');
    await page.selectOption('#abast-cartao-fisico', { label: 'Adicional E •••• 2222' });
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Lançamento em cartão salvo com sucesso!');
    await expect(linha(page, 'POSTO NOVO E')).toHaveCount(1);

    const compras = (await chamarRpc(page, 'compras_do_cartao_tela', { p_perfil_id: ctx.perfil, p_cartao_id: ctx.cartao })).corpo
        .filter((c) => c.descricao === 'POSTO NOVO E');
    expect(compras.map((c) => Number(c.valor))).toEqual([176]);
    const historico = (await chamarRpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: ctx.perfil, p_veiculo_id: flex })).corpo.abastecimentos;
    expect(historico.map((a) => [a.lancamento_id, a.situacao_vinculo, a.cartao_final, Number(a.litros), Number(a.hodometro_km)]))
        .toEqual([[compras[0].id, 'VINCULADO', '2222', 40, 52000]]);
});

test('compra ja lancada recebe o abastecimento sem mudar; corrigir a compra aqui e recusado', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page);
    await abrirTela(page);
    const ctx = await contexto(page);
    const carro = ctx.veiculos['Gasolina E (ficticio)'];
    // a compra de Combustivel lancada antes, sem os dados do abastecimento
    const lancada = await chamarRpc(page, 'criar_compra', { p_perfil_id: ctx.perfil, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: ctx.cartao, descricao: 'POSTO EXISTENTE E', valor: '150.00', total_parcelas: 1, data_compra: hoje(),
        mes_fatura: `${hoje().slice(0, 7)}-01`, categoria_id: Number(ctx.combustivel), observacoes: '' } });
    expect(lancada.status).toBe(200);
    await abrirTela(page);
    await linha(page, 'POSTO EXISTENTE E').locator('[data-on-click^="editarLancamento("]').click();
    await expect(page.locator('#lancamento-categoria-despesa-cartao')).toHaveValue(ctx.combustivel);
    await expect(page.locator('#bloco-abastecimento')).toBeVisible();
    await page.selectOption('#abast-veiculo', String(carro));
    await page.fill('#abast-hodometro', '8000');
    await page.fill('#abast-preco', '5');
    await expect(page.locator('#abast-litros')).toHaveText('30,000 L');

    await page.fill('#lancamento-valor', '151');
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toMatch(/só recebe os dados do abastecimento/);
    await page.fill('#lancamento-valor', '150');
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Lançamento em cartão salvo com sucesso!');

    const compra = (await chamarRpc(page, 'compras_do_cartao_tela', { p_perfil_id: ctx.perfil, p_cartao_id: ctx.cartao })).corpo
        .filter((c) => c.descricao === 'POSTO EXISTENTE E');
    expect(compra.map((c) => Number(c.valor))).toEqual([150]);
    const leitura = (await chamarRpc(page, 'abastecimento_do_lancamento', { p_perfil_id: ctx.perfil, p_lancamento_id: compra[0].id, p_conta_id: null })).corpo;
    expect([leitura.abastecimento.veiculo_id, Number(leitura.abastecimento.litros), leitura.abastecimento.situacao_vinculo]).toEqual([carro, 30, 'VINCULADO']);
});

test('despesa direta com abastecimento; trocar a categoria pede a decisao e nao exclui o abastecimento', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page);
    await abrirTela(page);
    const ctx = await contexto(page);
    const flex = ctx.veiculos['Flex E (ficticio)'];
    await page.click('#btn-novo-lancamento');
    await page.selectOption('#lancamento-tipo', 'direto');
    await expect(page.locator(`#lancamento-categoria-geral option[value="${ctx.combustivel}"]`)).toHaveCount(1);
    await page.selectOption('#lancamento-categoria-geral', ctx.combustivel);
    await page.fill('#lancamento-descricao', 'Posto direto E');
    await page.fill('#lancamento-valor', '120');
    await page.fill('#lancamento-data', hoje());
    await page.selectOption('#abast-veiculo', String(flex));
    await page.selectOption('#abast-combustivel', 'etanol');
    await page.fill('#abast-hodometro', '52100');
    await page.fill('#abast-preco', '4');
    await expect(page.locator('#abast-cartao-fisico-grupo')).toBeHidden();
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa direta salva com sucesso!');

    await linha(page, 'Posto direto E').locator('[data-on-click^="editarLancamento("]').click();
    await expect(page.locator('#bloco-abastecimento')).toBeVisible();
    await expect(page.locator('#abast-hodometro')).toHaveValue('52100');
    await expect(page.locator('#abast-aviso')).toContainText('Abastecimento vinculado');
    const outra = await page.locator(`#lancamento-categoria-geral option:not([value=""]):not([value="${ctx.combustivel}"])`).first().getAttribute('value');
    await page.selectOption('#lancamento-categoria-geral', outra);
    await expect(page.locator('#bloco-abastecimento')).toBeHidden();
    await salvar(page);
    await expect.poll(() => dialogos.at(-1)).toBe('Despesa direta atualizada com sucesso!');
    expect(dialogos.at(-3)).toMatch(/deixa de ser Combustível/);
    expect(dialogos.at(-2)).toMatch(/^Desvincular o abastecimento desta despesa\?/);

    const historico = (await chamarRpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: ctx.perfil, p_veiculo_id: flex })).corpo.abastecimentos;
    const direto = historico.find((a) => Number(a.hodometro_km) === 52100);
    expect([direto.situacao_vinculo, direto.conta_id, Number(direto.litros)]).toEqual(['AGUARDANDO', null, 30]);
});

test('Cartoes: mudar o valor da compra vinculada pede confirmacao e desvincula, sem excluir o abastecimento', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page);
    await abrirTela(page);
    const ctx = await contexto(page);
    const compra = (await chamarRpc(page, 'compras_do_cartao_tela', { p_perfil_id: ctx.perfil, p_cartao_id: ctx.cartao })).corpo
        .find((c) => c.descricao === 'POSTO EXISTENTE E');
    const antes = (await chamarRpc(page, 'abastecimento_do_lancamento', { p_perfil_id: ctx.perfil, p_lancamento_id: compra.id, p_conta_id: null })).corpo;
    expect(antes.abastecimento.situacao_vinculo).toBe('VINCULADO');

    await page.goto('/cartoes.html');
    await expect(page.locator('#lista-cartoes .loading')).toHaveCount(0);
    await page.locator('#lista-cartoes .cartao-list-item', { hasText: CARTAO }).click();
    const campo = page.locator('[data-action="alterar-mes-fatura"]');
    await campo.fill(hoje().slice(0, 7));
    await campo.dispatchEvent('change');
    const linhaFatura = page.locator('.fatura-lancamento-row', { hasText: 'POSTO EXISTENTE E' });
    await linhaFatura.locator('[data-action="editar-lancamento"]').click();
    await page.fill('#lancamento-edit-valor', '155');
    await page.click('#form-editar-lancamento button[type=submit]');
    await expect(page.locator('#modal-editar-lancamento')).not.toHaveClass(/open/);
    expect(dialogos.at(-1)).toMatch(/Mudar o valor desvincula o abastecimento/);
    await expect(linhaFatura.locator('.fatura-lancamento-valor')).toHaveText('R$ 155,00');

    const depois = (await chamarRpc(page, 'abastecimento_do_lancamento', { p_perfil_id: ctx.perfil, p_lancamento_id: compra.id, p_conta_id: null })).corpo;
    expect(depois.abastecimento).toBeNull();
    const historico = (await chamarRpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: ctx.perfil, p_veiculo_id: antes.abastecimento.veiculo_id })).corpo.abastecimentos;
    expect(historico.find((a) => a.id === antes.abastecimento.id).situacao_vinculo).toBe('AGUARDANDO');
});
