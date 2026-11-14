// FIN-MVP-MOBILE-05 — Nova Despesa mobile (cadastro rapido pelo atalho Despesa). Usuario G, titular do "Perfil G (ficticio)"
// (o mesmo dos Cartoes e das Receitas mobile; gerador NOVO); somente leitura: usuario H. Conta a pagar em 06/2031 e 07/2031
// e compra no cartao (ajuste final) no Nubank Master G em 05 a 12/2031,
// competencias sem outro dado do Perfil G, e e conferido no banco (contas_do_mes, recorrencias_do_perfil), na Lista de
// Despesas mobile e na tela Despesas do desktop no mesmo banco. Dados FICTICIOS; grava so no banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, normal } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MES = '2031-06';
const CELULAR = { width: 390, height: 844 };
const DESKTOP = { width: 1366, height: 900 };
const EVIDENCIAS = process.env.CF_MOBILE05_EVIDENCIAS || '';  // capturas da homologacao (opcional)

test.use({ viewport: CELULAR, isMobile: true, hasTouch: true });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    // A pagina mobile nao tem servidor /api/: as rotas sao atendidas no navegador pelo servico do desktop.
    page.on('request', (req) => { if (new URL(req.url()).pathname.startsWith('/api/')) problemas.push(`pedido a /api/: ${req.url()}`); });
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP, erros de JS ou pedidos a /api/').toEqual([]);
});

async function evidencia(page, nome, inteira = true) {
    if (!EVIDENCIAS) return;
    mkdirSync(EVIDENCIAS, { recursive: true });
    await page.screenshot({ path: path.join(EVIDENCIAS, `${nome}.png`), fullPage: inteira });
}

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/inicio.html**');
}

async function rpc(page, funcao, corpo) {
    const r = await chamarRpc(page, funcao, corpo);
    expect(r.status, `${funcao}: ${JSON.stringify(r.corpo)}`).toBe(200);
    return r.corpo;
}

async function abrirCadastro(page, mes = MES) {
    await page.goto(`/despesa-nova-mobile.html?mes=${mes}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
}

const campo = (page, rotulo) => page.locator('#mob-cadastro .mob-campo', { has: page.locator('xpath=./span[1]', { hasText: new RegExp(`^${rotulo}`) }) });
const controle = (page, rotulo) => campo(page, rotulo).locator('input, select, textarea').first();
const erroDe = (page, rotulo) => campo(page, rotulo).locator('.mob-campo-erro');
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const contasDoMes = (page, mes, nome) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.nome === nome));

async function preencher(page, { nome, valor, categoria = 'Moradia', vencimento, competencia, observacoes }) {
    if (nome !== undefined) await controle(page, 'Descrição').fill(nome);
    if (valor !== undefined) await controle(page, 'Valor').fill(String(valor));
    if (categoria) await controle(page, 'Categoria').selectOption({ label: categoria });
    if (vencimento) await controle(page, 'Vencimento').fill(vencimento);
    if (competencia) await controle(page, 'Competência').fill(competencia);
    if (observacoes) await controle(page, 'Observações').fill(observacoes);
}

async function linhaNaListaMobile(page, mes, nome) {
    await page.goto(`/despesas-mobile.html?mes=${mes}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    const fechados = page.locator('.mob-grupo-cabecalho[aria-expanded="false"]');
    while (await fechados.count()) await fechados.first().click();
    return page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: nome }) });
}

// ---------------------------------------------------------------------------------------------------------------

test('atalho Despesa abre a Nova Despesa na competencia da pagina principal; Lancar continua desabilitado', async ({ page }) => {
    await entrar(page, G);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="despesa"]');
    await expect(atalho).toHaveAttribute('href', `despesa-nova-mobile.html?mes=${MES}`);
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('aria-disabled', 'true');
    await atalho.click();
    await page.waitForURL(`**/despesa-nova-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('h1.mob-titulo')).toHaveText('Nova Despesa');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil G (ficticio)');
    await expect(controle(page, 'Competência')).toHaveValue(MES);
    // Progressivo: so os campos essenciais; a recorrencia abre ao marcar.
    await expect(page.locator('#mob-recorrencia')).toBeHidden();
    await expect(controle(page, 'Categoria').locator('option')).toContainText(['Selecione...', 'Moradia', 'Saude']);
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
    await expect(page.locator('.mob-barra .mob-barra-item')).toHaveText(['Início', 'Lançar', 'Resumo', 'Mais']);
    await evidencia(page, 'formulario-390x844');
});

test('validacoes junto ao campo; erro do banco explicado; cancelar nao grava nada', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Descrição')).toHaveText('Informe a descrição.');
    await expect(erroDe(page, 'Valor')).toHaveText('Informe um valor válido.');
    await expect(erroDe(page, 'Categoria')).toHaveText('Selecione a categoria.');
    await expect(erroDe(page, 'Vencimento')).toHaveText('Informe a data de vencimento.');
    await expect(controle(page, 'Descrição')).toBeFocused();
    await evidencia(page, 'validacoes', false);
    // O banco limita a competencia a 12 meses do vencimento: a explicacao dele aparece junto a Competencia.
    await preencher(page, { nome: 'Conta fora do prazo G', valor: '10', vencimento: '2031-06-10', competencia: '2033-01' });
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Competência')).toContainText('12 meses');
    expect(await contasDoMes(page, '2033-01', 'Conta fora do prazo G')).toEqual([]);
    // Cancelar volta a pagina principal sem gravar.
    await preencher(page, { nome: 'Conta cancelada G', valor: '99.90', vencimento: '2031-06-15', competencia: MES });
    await page.click('#mob-cancelar');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
    expect(await contasDoMes(page, MES, 'Conta cancelada G')).toEqual([]);
});

test('competencia: a da pagina principal; o vencimento leva ao mes anterior (regra do desktop) ate o usuario mudar', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await controle(page, 'Vencimento').fill('2031-07-10');
    await expect(controle(page, 'Competência')).toHaveValue('2031-06');
    await controle(page, 'Vencimento').fill('2031-03-31');  // por mes: fevereiro (o desktop caia em marco nos dias 29 a 31)
    await expect(controle(page, 'Competência')).toHaveValue('2031-02');
    await controle(page, 'Competência').fill('2031-05');
    await controle(page, 'Vencimento').fill('2031-08-05');
    await expect(controle(page, 'Competência')).toHaveValue('2031-05');
});

test('despesa simples: grava uma vez (toque duplo), aparece na competencia na Lista mobile e na tela do desktop', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await preencher(page, { nome: 'Conta de agua G', valor: '87.45', categoria: 'Moradia', vencimento: '2031-07-10',
        observacoes: 'Leitura de junho (ficticia)' });
    await expect(controle(page, 'Competência')).toHaveValue(MES);
    await evidencia(page, 'simples-preenchida', false);
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toBeVisible();
    await expect(page.locator('#mob-confirmacao')).toContainText('“Conta de agua G” cadastrada');
    await expect(page.locator('#mob-confirmacao')).toContainText('Despesa salva na competência 06/2031.');
    await expect(page.locator('#mob-ver-lista')).toHaveAttribute('href', `despesas-mobile.html?mes=${MES}`);
    await evidencia(page, 'confirmacao', false);
    const contas = await contasDoMes(page, MES, 'Conta de agua G');
    expect(contas.map((c) => [Number(c.valor), c.data_vencimento, c.categoria_nome, c.status_pagamento])).toEqual([[87.45, '2031-07-10', 'Moradia', 'Pendente']]);
    // Lista de Despesas mobile (pelo link da confirmacao) e tela Despesas do desktop: a mesma despesa, uma vez.
    await page.click('#mob-ver-lista');
    await page.waitForURL(`**/despesas-mobile.html?mes=${MES}`);
    const linhas = await linhaNaListaMobile(page, MES, 'Conta de agua G');
    await expect(linhas).toHaveCount(1);
    await expect(linhas.locator('.mob-linha-valor')).toHaveText(reais(87.45));
    await page.setViewportSize(DESKTOP);
    await abrirDespesas(page, MES);
    await expect(despesa(page, 'Conta de agua G')).toHaveCount(1);
    expect(normal(await despesa(page, 'Conta de agua G').locator('.despesa-cell-valor').textContent())).toContain('87,45');
    // "Nova despesa" recomeca o formulario vazio, na mesma competencia.
    await page.setViewportSize(CELULAR);
    await abrirCadastro(page);
    await preencher(page, { nome: 'Farmacia G', valor: '23', categoria: 'Saude', vencimento: '2031-06-20', competencia: MES });
    await page.click('#mob-salvar');
    await page.click('#mob-outra');
    await expect(controle(page, 'Descrição')).toHaveValue('');
    await expect(controle(page, 'Competência')).toHaveValue(MES);
    expect((await contasDoMes(page, MES, 'Farmacia G')).length).toBe(1);
});

test('recorrente mensal e semanal: o mesmo mecanismo do desktop (recorrencia gravada; contas geradas ao abrir a competencia)', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await preencher(page, { nome: 'Internet G', valor: '119.90', categoria: 'Moradia', vencimento: '2031-07-15' });
    await page.locator('#mob-cadastro .mob-opcao', { hasText: 'Despesa recorrente' }).locator('input').check();
    await expect(page.locator('#mob-recorrencia')).toBeVisible();
    await expect(campo(page, 'Competência')).toBeHidden();  // na recorrencia, o mes de cada vencimento (banco)
    await expect(campo(page, 'Dia da semana')).toBeHidden();
    await controle(page, 'Pagamento da conta').selectOption('pix');
    await evidencia(page, 'recorrente-mensal', false);
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toContainText('Recorrência cadastrada.');
    await expect(page.locator('#mob-ver-lista')).toHaveAttribute('href', 'despesas-mobile.html?mes=2031-07');
    let recorrencias = (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).filter((r) => r.nome === 'Internet G');
    expect(recorrencias.map((r) => [r.tipo_recorrencia, Number(r.valor), r.data_vencimento, r.meio_pagamento])).toEqual([['mensal', 119.9, '2031-07-15', 'pix']]);
    // A conta nasce quando a competencia e aberta na Lista (o gerador do desktop), uma vez.
    await page.click('#mob-ver-lista');
    const linhas = await linhaNaListaMobile(page, '2031-07', 'Internet G');
    await expect(linhas).toHaveCount(1);
    expect((await contasDoMes(page, '2031-07', 'Internet G')).map((c) => c.data_vencimento)).toEqual(['2031-07-15']);

    // Semanal, a cada 2 semanas, na sexta: semanal_2_5, como o formulario do desktop.
    await abrirCadastro(page);
    await preencher(page, { nome: 'Feira G', valor: '60', categoria: 'Moradia', vencimento: '2031-06-06' });
    await page.locator('#mob-cadastro .mob-opcao', { hasText: 'Despesa recorrente' }).locator('input').check();
    await controle(page, 'Periodicidade').selectOption('semanal');
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Dia da semana')).toHaveText('Selecione o dia da semana.');
    await controle(page, 'Dia da semana').selectOption('5');
    await controle(page, 'Frequência').selectOption('2');
    await evidencia(page, 'recorrente-semanal', false);
    await page.click('#mob-salvar');
    await expect(page.locator('#mob-confirmacao')).toContainText('Recorrência cadastrada.');
    recorrencias = (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).filter((r) => r.nome === 'Feira G');
    expect(recorrencias.map((r) => r.tipo_recorrencia)).toEqual(['semanal_2_5']);
});

test('somente leitura (usuario H): atalho Despesa desabilitado; sem formulario; o banco recusa a gravacao', async ({ page }) => {
    await entrar(page, H);
    // Pagina principal: o atalho de cadastro fica visivel e desabilitado (sem link, mesmo trocando o mes); as consultas seguem.
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="despesa"]');
    await expect(atalho).toHaveAttribute('title', 'Somente leitura neste perfil');  // depois da consulta da permissao
    await expect(atalho).toHaveAttribute('aria-disabled', 'true');
    await expect(atalho).not.toHaveAttribute('href', /./);
    await page.click('#mob-mes-seguinte');
    await expect(atalho).not.toHaveAttribute('href', /./);
    await atalho.click({ force: true });
    await expect(page).toHaveURL(/inicio\.html/);
    for (const modulo of ['receita', 'cartoes', 'resumo']) {
        await expect(page.locator(`.mob-atalho[data-modulo="${modulo}"]`)).toHaveAttribute('href', /mobile\.html\?mes=/);
    }
    await evidencia(page, 'somente-leitura-inicio', false);
    // Acesso direto ao endereco: a pagina explica e nao mostra o formulario.
    await abrirCadastro(page);
    await expect(page.locator('#mob-cadastro')).toContainText('Acesso somente de leitura a este perfil: não é possível cadastrar despesas.');
    await expect(page.locator('#mob-cadastro form')).toHaveCount(0);
    await evidencia(page, 'somente-leitura', false);
    const r = await chamarRpc(page, 'criar_despesa', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(), p_dados: {
        nome: 'Tentativa do leitor H', valor: '10.00', categoria_id: 201, data_vencimento: '2031-06-10', descricao: '' } });
    expect(r.status).not.toBe(200);
    // A compra no cartao tambem: o banco recusa a quem so le.
    const compra = await chamarRpc(page, 'criar_compra', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: (await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G }))[0].id, descricao: 'Tentativa do leitor H', valor: '10.00',
        total_parcelas: 1, data_compra: '2031-06-10', mes_fatura: '2031-06-01', categoria_id: 201 } });
    expect(compra.status).not.toBe(200);
});

// ---------------------------------------------------------------------------------------------------------------
// Ajuste final (Proposta A): "Meio de pagamento" com Conta a pagar ou Cartao de credito (a compra da tela Lancamentos do
// desktop, criar_compra). Cartao "Nubank Master G (ficticio)": fecha dia 15, vence dia 25, fechamento confirmado; fatura
// 09/2031 paga e 12/2031 consolidada (semear_compras_mobile_e2e). Compras em 05 a 12/2031, meses sem outro dado do Master.

const VISA = 'Itau Visa G (ficticio)';
const MASTER = 'Nubank Master G (ficticio)';
const idDoCartao = async (page, nome) => (await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G })).find((c) => c.nome === nome).id;
const comprasDaFatura = (page, cartao, mes, descricao) => rpc(page, 'compras_da_fatura', { p_perfil_id: PERFIL_G, p_cartao_id: cartao, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.descricao === descricao));
const faturaDoMes = (page, cartao, mes) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.grupo === 'FATURA' && c.cartao_id === cartao));

async function compraNoCartao(page, { nome, valor, categoria = 'Moradia', cartao = MASTER, data, parcelas }) {
    await preencher(page, { nome, valor, categoria });
    await controle(page, 'Meio de pagamento').selectOption('cartao');
    await expect(controle(page, 'Cartão').locator('option')).toHaveCount(3);
    await controle(page, 'Cartão').selectOption({ label: cartao });
    await controle(page, 'Data da compra').fill(data);
    await controle(page, 'Data da compra').dispatchEvent('change');
    if (parcelas) await controle(page, 'Parcelas').fill(String(parcelas));
}

test('meio de pagamento: conta a pagar por padrao; no cartao, cartao, data, parcelas e fatura sugerida; recorrencia desabilitada', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    // Logo apos descricao, valor e categoria; "Conta a pagar" mantem o fluxo de antes.
    const ordem = await page.locator('#mob-cadastro form > .mob-campo > span:first-child, #mob-cadastro form > .mob-par .mob-campo > span:first-child')
        .allTextContents();
    expect(ordem.slice(0, 4).map((t) => t.replace(' *', ''))).toEqual(['Descrição', 'Valor', 'Categoria', 'Meio de pagamento']);
    await expect(controle(page, 'Meio de pagamento')).toHaveValue('conta');
    await expect(controle(page, 'Meio de pagamento').locator('option')).toHaveText(['Conta a pagar', 'Cartão de crédito']);
    await expect(controle(page, 'Vencimento')).toBeVisible();
    await expect(page.locator('#mob-cartao')).toBeHidden();
    const marcaRecorrente = page.locator('#mob-cadastro .mob-opcao', { hasText: 'Despesa recorrente' }).locator('input');
    await marcaRecorrente.check();
    await expect(controle(page, 'Pagamento da conta').locator('option')).toHaveText(['Não informado', 'Boleto', 'Débito', 'PIX']);

    // Cartao de credito: vencimento e competencia saem; recorrencia desmarcada e desabilitada, com a orientacao.
    await controle(page, 'Meio de pagamento').selectOption('cartao');
    await expect(page.locator('#mob-cartao')).toBeVisible();
    await expect(controle(page, 'Vencimento')).toBeHidden();
    await expect(marcaRecorrente).not.toBeChecked();
    await expect(marcaRecorrente).toBeDisabled();
    await expect(page.locator('#mob-recorrencia')).toBeHidden();
    await expect(page.locator('#mob-recorrencia-cartao')).toHaveText('O cadastro de despesas recorrentes no cartão de crédito será disponibilizado em uma etapa posterior.');
    await expect(controle(page, 'Cartão').locator('option')).toHaveText(['Selecione...', VISA, MASTER]);
    await expect(controle(page, 'Parcelas')).toHaveValue('1');

    // Fatura sugerida pelo fechamento (07/2031 para 10/07); o mes escolhido pelo usuario prevalece ate "Usar a fatura sugerida".
    await controle(page, 'Cartão').selectOption({ label: MASTER });
    await controle(page, 'Data da compra').fill('2031-07-10');
    await controle(page, 'Data da compra').dispatchEvent('change');
    await expect(controle(page, 'Fatura')).toHaveValue('2031-07');
    await expect(page.locator('#mob-fatura-sugestao')).toHaveText('Sugerida pelo fechamento: fatura 07/2031 (fecha 15/07, vence 25/07).');
    await expect(page.locator('#mob-usar-sugerida')).toBeHidden();
    await controle(page, 'Fatura').fill('2031-08');
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Mês escolhido: 08/2031.');
    await page.click('#mob-usar-sugerida');
    await expect(controle(page, 'Fatura')).toHaveValue('2031-07');
    await evidencia(page, 'cartao-formulario', false);
    // Cartao sem fechamento confirmado: aviso, e o mes volta ao da pagina principal (como no desktop).
    await controle(page, 'Cartão').selectOption({ label: VISA });
    await expect(page.locator('#mob-fatura-sugestao')).toHaveText('Fechamento deste cartão ainda não confirmado: confira o mês da fatura.');
    await expect(controle(page, 'Fatura')).toHaveValue(MES);
    // Validacoes do cartao junto ao campo.
    await controle(page, 'Cartão').selectOption('');
    await controle(page, 'Parcelas').fill('49');
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Descrição')).toHaveText('Informe a descrição.');
    await expect(erroDe(page, 'Cartão')).toHaveText('Selecione o cartão.');
    await expect(erroDe(page, 'Parcelas')).toHaveText('Parcelas: de 1 a 48.');
    // Volta a "Conta a pagar": o fluxo de antes, recorrencia habilitada.
    await controle(page, 'Meio de pagamento').selectOption('conta');
    await expect(controle(page, 'Vencimento')).toBeVisible();
    await expect(page.locator('#mob-cartao')).toBeHidden();
    await expect(marcaRecorrente).toBeEnabled();
    await expect(page.locator('#mob-recorrencia-cartao')).toBeHidden();
});

test('compra a vista no cartao: grava uma vez (toque duplo) na fatura sugerida; aparece no Cartoes mobile e so a fatura na Lista', async ({ page }) => {
    await entrar(page, G);
    const master = await idDoCartao(page, MASTER);
    await abrirCadastro(page);
    await compraNoCartao(page, { nome: 'Tenis G', valor: '250.00', data: '2031-07-10' });
    await expect(controle(page, 'Fatura')).toHaveValue('2031-07');
    await expect(page.locator('#mob-previa-parcelas')).toBeHidden();  // a vista: sem previa
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toContainText('“Tenis G” lançada no cartão');
    await expect(page.locator('#mob-confirmacao')).toContainText(`Compra lançada na fatura 07/2031 do cartão ${MASTER}.`);
    await expect(page.locator('#mob-ver-cartao')).toHaveAttribute('href', `cartoes-mobile.html?mes=2031-07&cartao=${master}`);
    await evidencia(page, 'cartao-confirmacao', false);
    // No banco: uma compra na fatura (toque duplo nao duplica) e nenhuma conta a pagar com o nome da compra.
    const compras = await comprasDaFatura(page, master, '2031-07', 'Tenis G');
    expect(compras.map((c) => [Number(c.valor), c.data_compra, c.numero_parcela, c.total_parcelas])).toEqual([[250, '2031-07-10', 1, 1]]);
    expect(await contasDoMes(page, '2031-07', 'Tenis G')).toEqual([]);
    const fatura = await faturaDoMes(page, master, '2031-07');
    expect(fatura.map((f) => Number(f.valor_executado))).toEqual([250]);
    // Cartoes mobile (pelo link da confirmacao) e Lista de Despesas mobile: a compra na fatura; na lista, so a fatura.
    await page.click('#mob-ver-cartao');
    await page.waitForURL(`**/cartoes-mobile.html?mes=2031-07&cartao=${master}`);
    await expect(page.locator('#mob-lista')).toContainText('Tenis G');
    await expect(page.locator('#mob-cartao')).toHaveValue(String(master));
    await expect(await linhaNaListaMobile(page, '2031-07', 'Tenis G')).toHaveCount(0);
    const faturaNaLista = page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: 'Nubank Master G' }) });
    await expect(faturaNaLista).toHaveCount(1);
    await expect(faturaNaLista.locator('.mob-linha-valor')).toHaveText(reais(250));
});

test('compra parcelada: previa do parcelamento (o plano do banco) e uma parcela em cada fatura', async ({ page }) => {
    await entrar(page, G);
    const master = await idDoCartao(page, MASTER);
    await abrirCadastro(page);
    await compraNoCartao(page, { nome: 'Notebook G', valor: '900.00', data: '2031-05-10', parcelas: 3 });
    await expect(controle(page, 'Fatura')).toHaveValue('2031-05');
    const previa = page.locator('#mob-previa-parcelas');
    await expect(previa.locator('tbody tr')).toHaveCount(3);
    await expect(previa.locator('tbody tr')).toHaveText([/1\/305\/2031R\$\s300,00/, /2\/306\/2031R\$\s300,00/, /3\/307\/2031R\$\s300,00/]);
    await expect(previa.locator('tfoot')).toContainText(reais(900));
    await evidencia(page, 'cartao-parcelada', false);
    await page.click('#mob-salvar');
    await expect(page.locator('#mob-confirmacao')).toContainText(`Compra lançada em 3 parcelas no cartão ${MASTER}: faturas 05/2031 a 07/2031.`);
    for (const [mes, n] of [['2031-05', 1], ['2031-06', 2], ['2031-07', 3]]) {
        const parcela = await comprasDaFatura(page, master, mes, 'Notebook G');
        expect(parcela.map((c) => [Number(c.valor), c.numero_parcela, c.total_parcelas]), mes).toEqual([[300, n, 3]]);
    }
    expect(await contasDoMes(page, '2031-05', 'Notebook G')).toEqual([]);
});

test('fatura paga: a compra vai para a proxima em aberto; fatura consolidada: so com a confirmacao do total', async ({ page }) => {
    await entrar(page, G);
    const master = await idDoCartao(page, MASTER);
    await abrirCadastro(page);
    // 20/08 -> fatura 09/2031, paga: o banco manda a compra para 10/2031 (a proxima em aberto).
    await compraNoCartao(page, { nome: 'Livro G', valor: '60.00', data: '2031-08-20' });
    await expect(controle(page, 'Fatura')).toHaveValue('2031-09');
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Essa fatura já está paga: a compra vai para a próxima em aberto.');
    await page.click('#mob-salvar');
    await expect(page.locator('#mob-confirmacao')).toContainText(`Compra lançada na fatura 10/2031 do cartão ${MASTER}.`);
    expect(await comprasDaFatura(page, master, '2031-09', 'Livro G')).toEqual([]);
    expect((await comprasDaFatura(page, master, '2031-10', 'Livro G')).length).toBe(1);

    // 20/11 -> fatura 12/2031, consolidada (total 200,00): a pergunta do desktop; sem confirmar, nada e gravado.
    await page.click('#mob-outra');
    await compraNoCartao(page, { nome: 'Presente G', valor: '80.00', data: '2031-11-20' });
    await expect(controle(page, 'Fatura')).toHaveValue('2031-12');
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Essa fatura está consolidada: a inclusão pede confirmação.');
    await page.click('#mob-salvar');
    const pergunta = page.locator('#mob-consolidada');
    await expect(pergunta).toContainText(`Incluir na fatura consolidada 12/2031: total ${reais(200)} passa a ${reais(280)} (inclusão de ${reais(80)}).`);
    await evidencia(page, 'cartao-consolidada', false);
    await page.click('#mob-nao-incluir');
    await expect(pergunta).toBeHidden();
    await expect(page.locator('#mob-cadastro form')).toContainText('Compra não salva: a inclusão na fatura consolidada não foi confirmada.');
    expect(await comprasDaFatura(page, master, '2031-12', 'Presente G')).toEqual([]);
    await page.click('#mob-salvar');
    await expect(pergunta).toBeVisible();
    await page.locator('#mob-confirmar-inclusao').dblclick();  // toque duplo: uma compra so
    await expect(page.locator('#mob-confirmacao')).toContainText(`Compra lançada na fatura 12/2031 do cartão ${MASTER}.`);
    expect((await comprasDaFatura(page, master, '2031-12', 'Presente G')).map((c) => Number(c.valor))).toEqual([80]);
});

test('larguras de 320 a 430: sem rolagem horizontal, campos sem sobreposicao (recorrencia semanal aberta)', async ({ page }) => {
    await entrar(page, G);
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        await abrirCadastro(page);
        await page.locator('#mob-cadastro .mob-opcao', { hasText: 'Despesa recorrente' }).locator('input').check();
        await controle(page, 'Periodicidade').selectOption('semanal');
        const medidas = await page.evaluate(() => {
            const caixas = [...document.querySelectorAll('#mob-cadastro .mob-campo')].filter((e) => e.offsetParent)
                .map((e) => e.getBoundingClientRect());
            const sobrepostos = caixas.some((a, i) => caixas.some((b, j) => j > i && a.left < b.right - 0.5 && b.left < a.right - 0.5
                && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
            return {
                rolagem: document.documentElement.scrollWidth > window.innerWidth,
                fora: [...document.querySelectorAll('#mob-cadastro *, .mob-cabecalho *, .mob-barra-item')]
                    .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.left < -0.5 || r.right > window.innerWidth + 0.5); }).length,
                sobrepostos,
            };
        });
        expect(medidas, `largura ${largura}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false });
        if ([320, 430].includes(largura)) await evidencia(page, `formulario-semanal-${largura}`);
    }
});

test('larguras de 320 a 430 no cartao: sem rolagem horizontal, campos sem sobreposicao (previa do parcelamento aberta)', async ({ page }) => {
    await entrar(page, G);
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        await abrirCadastro(page);
        await compraNoCartao(page, { nome: 'Teste de largura G', valor: '1234.56', data: '2031-05-10', parcelas: 12 });
        await expect(page.locator('#mob-previa-parcelas tbody tr')).toHaveCount(12);
        const medidas = await page.evaluate(() => {
            const caixas = [...document.querySelectorAll('#mob-cadastro .mob-campo')].filter((e) => e.offsetParent)
                .map((e) => e.getBoundingClientRect());
            const sobrepostos = caixas.some((a, i) => caixas.some((b, j) => j > i && a.left < b.right - 0.5 && b.left < a.right - 0.5
                && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
            return {
                rolagem: document.documentElement.scrollWidth > window.innerWidth,
                fora: [...document.querySelectorAll('#mob-cadastro *, .mob-cabecalho *, .mob-barra-item')]
                    .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.left < -0.5 || r.right > window.innerWidth + 0.5); }).length,
                sobrepostos,
            };
        });
        expect(medidas, `largura ${largura}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false });
        if ([320, 430].includes(largura)) await evidencia(page, `cartao-parcelado-${largura}`);
    }
});
