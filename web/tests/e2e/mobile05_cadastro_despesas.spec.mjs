// FIN-MVP-MOBILE-05 — Nova Despesa mobile (cadastro rapido pelo atalho Despesa). Usuario G, titular do "Perfil G (ficticio)"
// (o mesmo dos Cartoes e das Receitas mobile; gerador NOVO); somente leitura: usuario H. Conta a pagar em 06/2031 e 07/2031
// e compra no cartao (ajuste final) no Nubank Master G em 05 a 12/2031,
// competencias sem outro dado do Perfil G, e e conferido no banco (contas_do_mes, recorrencias_do_perfil), na Lista de
// Despesas mobile e na tela Despesas do desktop no mesmo banco. Dados FICTICIOS; grava so no banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, normal } from './despesas.mjs';
import { confirmacao, escolherTipo, esperarModal, mensagem, modal, preencherCadastro, salvarCadastro } from './cadastro.mjs';

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

// FIN-MVP-CADASTRO-UNIFICADO-01: a pagina abre o modal unico (o mesmo de Despesas, Lancamentos e Recorrencias), ja em
// "Despesa direta"; cancelar ou concluir volta a pagina principal, na competencia de origem.
async function abrirCadastro(page, mes = MES) {
    await page.goto(`/despesa-nova-mobile.html?mes=${mes}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await esperarModal(page, 'direta');
}

const campo = (page, rotulo) => page.locator('#cad-modal .mob-campo', { has: page.locator('xpath=./span[1]', { hasText: new RegExp(`^${rotulo}`) }) });
const controle = (page, rotulo) => campo(page, rotulo).locator('input, select, textarea').first();
const erroDe = (page, rotulo) => campo(page, rotulo).locator('.mob-campo-erro');
const competencia = (page) => page.locator('#cad-competencia-texto');
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const contasDoMes = (page, mes, nome) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.nome === nome));

const preencher = (page, { categoria = 'Moradia', ...d }) => preencherCadastro(page, { categoria, ...d });

async function linhaNaListaMobile(page, mes, nome) {
    await page.goto(`/despesas-mobile.html?mes=${mes}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    const fechados = page.locator('.mob-grupo-cabecalho[aria-expanded="false"]');
    while (await fechados.count()) await fechados.first().click();
    return page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: nome }) });
}

// ---------------------------------------------------------------------------------------------------------------

test('atalho Despesa abre o modal unico em Despesa direta, na competencia da pagina principal; Lancar abre o Registrar Lancamento', async ({ page }) => {
    await entrar(page, G);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="despesa"]');
    await expect(atalho).toHaveAttribute('href', `despesa-nova-mobile.html?mes=${MES}`);
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('href', `lancamento-mobile.html?mes=${MES}`);  // FIN-MVP-MOBILE-06
    await atalho.click();
    await page.waitForURL(`**/despesa-nova-mobile.html?mes=${MES}`);
    await esperarModal(page, 'direta');
    await expect(page.locator('#cad-titulo')).toHaveText('Nova despesa');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil G (ficticio)');
    await expect(competencia(page)).toHaveText('Competência: junho/2031');
    // Os quatro tipos de operacao no seletor; so os campos da despesa direta aparecem.
    await expect(page.locator('#cad-tipo option')).toHaveText(['Despesa direta', 'Compra no cartão', 'Despesa recorrente', 'Consórcio']);
    await expect(page.locator('#cad-campos .mob-campo:visible > span:first-child')).toHaveText(['Nome *', 'Categoria *', 'Valor *', 'Data de vencimento *']);
    await expect(modal(page)).not.toContainText(/já foi paga|Data de pagamento/i);
    await expect(controle(page, 'Categoria').locator('option')).toContainText(['Selecione uma categoria...', 'Moradia', 'Saude']);
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
    await evidencia(page, 'formulario-390x844');
});

test('validacoes junto ao campo; erro do banco explicado; cancelar nao grava nada e volta a origem', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await page.click('#cad-salvar');
    await expect(erroDe(page, 'Nome')).toHaveText('Informe o nome.');
    await expect(erroDe(page, 'Valor')).toHaveText('Informe um valor válido.');
    await expect(erroDe(page, 'Categoria')).toHaveText('Selecione a categoria.');
    await expect(erroDe(page, 'Data de vencimento')).toHaveText('Informe a data de vencimento.');
    await expect(controle(page, 'Nome')).toBeFocused();
    await evidencia(page, 'validacoes', false);
    // O banco limita a competencia a 12 meses do vencimento: a explicacao dele aparece junto a Competencia.
    await preencher(page, { nome: 'Conta fora do prazo G', valor: '10', vencimento: '2031-06-10', competencia: '2033-01' });
    await page.click('#cad-salvar');
    await expect(erroDe(page, 'Competência')).toContainText('12 meses');
    expect(await contasDoMes(page, '2033-01', 'Conta fora do prazo G')).toEqual([]);
    // Cancelar volta a pagina principal (a origem), na mesma competencia, sem gravar.
    await preencher(page, { nome: 'Conta cancelada G', valor: '99.90', vencimento: '2031-06-15', competencia: MES });
    await page.click('#cad-cancelar');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
    expect(await contasDoMes(page, MES, 'Conta cancelada G')).toEqual([]);
});

test('competencia: a da pagina principal; o vencimento leva ao mes anterior (regra do desktop) ate o usuario mudar', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await expect(competencia(page)).toHaveText('Competência: junho/2031');
    await preencherCadastro(page, { categoria: false, vencimento: '2031-07-10' });
    await expect(competencia(page)).toHaveText('Competência: junho/2031');
    await preencherCadastro(page, { categoria: false, vencimento: '2031-03-31' });  // por mes: fevereiro (o desktop caia em marco nos dias 29 a 31)
    await expect(competencia(page)).toHaveText('Competência: fevereiro/2031');
    // A alteracao manual continua possivel (acao discreta) e deixa de acompanhar o vencimento.
    await expect(page.locator('#cad-competencia')).toBeHidden();
    await preencherCadastro(page, { categoria: false, competencia: '2031-05' });
    await expect(page.locator('#cad-competencia')).toBeVisible();
    await preencherCadastro(page, { categoria: false, vencimento: '2031-08-05' });
    await expect(page.locator('#cad-competencia')).toHaveValue('2031-05');
    await expect(competencia(page)).toHaveText('Competência: maio/2031');
});

test('despesa direta: grava uma vez (toque duplo), pendente, aparece na competencia na Lista mobile e na tela do desktop', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await preencher(page, { nome: 'Conta de agua G', valor: '87.45', categoria: 'Moradia', vencimento: '2031-07-10',
        observacoes: 'Leitura de junho (ficticia)' });
    await expect(competencia(page)).toHaveText('Competência: junho/2031');
    await evidencia(page, 'simples-preenchida', false);
    await page.locator('#cad-salvar').dblclick();
    await expect(confirmacao(page)).toBeVisible();
    await expect(confirmacao(page)).toContainText('“Conta de agua G” cadastrada como pendente');
    await expect(confirmacao(page)).toContainText('Despesa salva na competência 06/2031.');
    await expect(page.locator('#cad-ver-registro')).toHaveAttribute('href', `despesas-mobile.html?mes=${MES}`);
    await evidencia(page, 'confirmacao', false);
    // Pendente, sem pagamento nem movimento bancario: o pagamento e outra operacao.
    const contas = await contasDoMes(page, MES, 'Conta de agua G');
    expect(contas.map((c) => [Number(c.valor), c.data_vencimento, c.categoria_nome, c.status_pagamento, c.data_pagamento || null]))
        .toEqual([[87.45, '2031-07-10', 'Moradia', 'Pendente', null]]);
    const movimentos = await rpc(page, 'movimentos_do_mes', { p_perfil_id: PERFIL_G, p_mes: '2031-07-01' });
    expect((movimentos.movimentos || []).filter((m) => m.referencia === 'Conta de agua G')).toEqual([]);
    // Lista de Despesas mobile (pelo link da confirmacao) e tela Despesas do desktop: a mesma despesa, uma vez.
    await page.click('#cad-ver-registro');
    await page.waitForURL(`**/despesas-mobile.html?mes=${MES}`);
    const linhas = await linhaNaListaMobile(page, MES, 'Conta de agua G');
    await expect(linhas).toHaveCount(1);
    await expect(linhas.locator('.mob-linha-valor')).toHaveText(reais(87.45));
    await page.setViewportSize(DESKTOP);
    await abrirDespesas(page, MES);
    await expect(despesa(page, 'Conta de agua G')).toHaveCount(1);
    expect(normal(await despesa(page, 'Conta de agua G').locator('.despesa-cell-valor').textContent())).toContain('87,45');
    // "Novo cadastro" recomeca em branco, no mesmo tipo e na mesma competencia; "Concluir" volta a pagina principal.
    await page.setViewportSize(CELULAR);
    await abrirCadastro(page);
    await preencher(page, { nome: 'Farmacia G', valor: '23', categoria: 'Saude', vencimento: '2031-06-20', competencia: MES });
    await salvarCadastro(page, { concluir: false });
    await page.click('#cad-novo');
    await esperarModal(page, 'direta');
    await expect(controle(page, 'Nome')).toHaveValue('');
    await expect(competencia(page)).toHaveText('Competência: junho/2031');
    expect((await contasDoMes(page, MES, 'Farmacia G')).length).toBe(1);
    await preencher(page, { nome: 'Padaria G', valor: '12', categoria: 'Saude', vencimento: '2031-06-22', competencia: MES });
    await salvarCadastro(page, { concluir: false });
    await page.click('#cad-concluir');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
});

test('recorrente mensal e a cada 2 semanas: o servico de Recorrencias (recorrencia gravada; contas geradas ao abrir a competencia)', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await preencher(page, { tipo: 'recorrente', nome: 'Internet G', valor: '119.90', categoria: 'Moradia', inicio: '2031-07-15', meio: 'pix' });
    await expect(campo(page, 'Dia da semana')).toBeHidden();
    await expect(page.locator('#cad-vencimento')).toHaveCount(0);  // nada do tipo anterior fica no formulario
    await evidencia(page, 'recorrente-mensal', false);
    await page.locator('#cad-salvar').dblclick();
    await expect(confirmacao(page)).toContainText('Recorrência “Internet G” cadastrada');
    await expect(page.locator('#cad-ver-registro')).toHaveAttribute('href', 'recorrencias-mobile.html');
    let recorrencias = (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).filter((r) => r.nome === 'Internet G');
    expect(recorrencias.map((r) => [r.tipo_recorrencia, Number(r.valor), r.data_vencimento, r.meio_pagamento, r.ativo]))
        .toEqual([['mensal', 119.9, '2031-07-15', 'pix', true]]);
    // A conta nasce quando a competencia e aberta na Lista (o gerador do desktop), uma vez.
    const linhas = await linhaNaListaMobile(page, '2031-07', 'Internet G');
    await expect(linhas).toHaveCount(1);
    expect((await contasDoMes(page, '2031-07', 'Internet G')).map((c) => c.data_vencimento)).toEqual(['2031-07-15']);

    // A cada 2 semanas, na sexta: semanal_2_5, como o formulario do desktop.
    await abrirCadastro(page);
    await preencher(page, { tipo: 'recorrente', nome: 'Feira G', valor: '60', categoria: 'Moradia', inicio: '2031-06-06', frequencia: 'quinzenal' });
    await page.click('#cad-salvar');
    await expect(erroDe(page, 'Dia da semana')).toHaveText('Selecione o dia da semana.');
    await preencherCadastro(page, { categoria: false, dia: 5 });
    await evidencia(page, 'recorrente-semanal', false);
    await salvarCadastro(page, { concluir: false });
    recorrencias = (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).filter((r) => r.nome === 'Feira G');
    expect(recorrencias.map((r) => r.tipo_recorrencia)).toEqual(['semanal_2_5']);
});

test('recorrencia no cartao pelo celular: mensal ou anual, pelo servico de Recorrencias; semanal e quinzenal nao sao oferecidas', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await preencher(page, { tipo: 'recorrente', nome: 'Clube de assinatura G', valor: '39.90', categoria: 'Moradia', inicio: '2032-02-12', meio: 'cartao', cartao: MASTER });
    await expect(page.locator('#cad-frequencia option[value="semanal"]')).toHaveJSProperty('disabled', true);
    await expect(page.locator('#cad-frequencia option[value="quinzenal"]')).toHaveJSProperty('disabled', true);
    await expect(campo(page, 'Pagamento da conta')).toContainText('No cartão de crédito: frequência mensal ou anual.');
    await expect(page.locator('#cad-categoria-cartao')).toContainText('Categoria do cartão');
    await evidencia(page, 'recorrente-cartao', false);
    await salvarCadastro(page, { concluir: false });
    const master = await idDoCartao(page, MASTER);
    const gravada = (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).filter((r) => r.nome === 'Clube de assinatura G');
    expect(gravada.map((r) => [r.tipo_recorrencia, r.meio_pagamento, r.cartao_id])).toEqual([['mensal', 'cartao', master]]);
    // E o contrario: com a frequencia semanal, o cartao nao e oferecido.
    await page.click('#cad-novo');
    await preencherCadastro(page, { categoria: false, frequencia: 'semanal' });
    await expect(page.locator('#cad-meio-pagamento option[value="cartao"]')).toHaveJSProperty('disabled', true);
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
    // Acesso direto ao endereco: a pagina explica e nao abre o cadastro.
    await page.goto(`/despesa-nova-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('#mob-cadastro')).toContainText('Acesso somente de leitura a este perfil: não é possível cadastrar despesas.');
    await expect(modal(page)).toHaveCount(0);
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
// Compra no cartao (a compra da tela Lancamentos do desktop, criar_compra). Cartao "Nubank Master G (ficticio)": fecha dia
// 15, vence dia 25, fechamento confirmado; fatura 09/2031 paga e 12/2031 consolidada (semear_compras_mobile_e2e). Compras
// em 05 a 12/2031, meses sem outro dado do Master.

const VISA = 'Itau Visa G (ficticio)';
const MASTER = 'Nubank Master G (ficticio)';
const idDoCartao = async (page, nome) => (await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G })).find((c) => c.nome === nome).id;
const comprasDaFatura = (page, cartao, mes, descricao) => rpc(page, 'compras_da_fatura', { p_perfil_id: PERFIL_G, p_cartao_id: cartao, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.descricao === descricao));
const faturaDoMes = (page, cartao, mes) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.grupo === 'FATURA' && c.cartao_id === cartao));

const compraNoCartao = (page, { categoria = 'Moradia', cartao = MASTER, ...d }) => preencherCadastro(page, { tipo: 'compra', categoria, cartao, ...d });

test('tipo de operacao: despesa direta por padrao; na compra, cartao, data, parcelas e fatura sugerida; troca de tipo sem dado residual', async ({ page }) => {
    await entrar(page, G);
    await abrirCadastro(page);
    await expect(page.locator('#cad-tipo')).toHaveValue('DESPESA_DIRETA');
    await expect(controle(page, 'Data de vencimento')).toBeVisible();
    await expect(page.locator('#cad-cartao')).toHaveCount(0);
    // Trocar com algo preenchido so da despesa direta: o modal pergunta; "Manter" nao muda nada.
    await preencherCadastro(page, { nome: 'Compra G', valor: '50', categoria: 'Moradia', vencimento: '2031-07-10' });
    await page.selectOption('#cad-tipo', 'COMPRA_CARTAO');
    await expect(page.locator('#cad-troca')).toContainText('descarta o que só existe em “Despesa direta”: Data de vencimento.');
    await page.click('#cad-troca-manter');
    await expect(page.locator('#cad-tipo')).toHaveValue('DESPESA_DIRETA');
    await expect(page.locator('#cad-vencimento')).toHaveValue('2031-07-10');
    await escolherTipo(page, 'compra');
    // Nome, valor e categoria seguem; vencimento e competencia saem do formulario (nao viajam ocultos).
    await expect(page.locator('#cad-nome')).toHaveValue('Compra G');
    await expect(page.locator('#cad-valor')).toHaveValue('50');
    await expect(page.locator('#cad-categoria option:checked')).toHaveText('Moradia');
    await expect(page.locator('#cad-vencimento, #cad-competencia')).toHaveCount(0);
    await expect(page.locator('#cad-campos .mob-campo:visible > span:first-child'))
        .toHaveText(['Cartão de crédito *', 'Categoria *', 'Descrição *', 'Valor *', 'Data da compra *', 'Parcelas', 'Mês da fatura *']);
    await expect(controle(page, 'Cartão de crédito').locator('option')).toHaveText(['Selecione...', VISA, MASTER]);
    await expect(controle(page, 'Parcelas')).toHaveValue('1');

    // Fatura sugerida pelo fechamento (07/2031 para 10/07); o mes escolhido pelo usuario prevalece ate "Usar a fatura sugerida".
    await compraNoCartao(page, { categoria: false, data: '2031-07-10' });
    await expect(controle(page, 'Mês da fatura')).toHaveValue('2031-07');
    await expect(page.locator('#mob-fatura-sugestao')).toHaveText('Sugerida pelo fechamento: fatura 07/2031 (fecha 15/07, vence 25/07).');
    await expect(page.locator('#mob-usar-sugerida')).toBeHidden();
    await controle(page, 'Mês da fatura').fill('2031-08');
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Mês escolhido: 08/2031.');
    await page.click('#mob-usar-sugerida');
    await expect(controle(page, 'Mês da fatura')).toHaveValue('2031-07');
    await evidencia(page, 'cartao-formulario', false);
    // Cartao sem fechamento confirmado: aviso, e o mes volta ao da pagina principal (como no desktop).
    await controle(page, 'Cartão de crédito').selectOption({ label: VISA });
    await expect(page.locator('#mob-fatura-sugestao')).toHaveText('Fechamento deste cartão ainda não confirmado: confira o mês da fatura.');
    await expect(controle(page, 'Mês da fatura')).toHaveValue(MES);
    // Validacoes do cartao junto ao campo.
    await controle(page, 'Cartão de crédito').selectOption('');
    await controle(page, 'Parcelas').fill('49');
    await page.fill('#cad-nome', '');
    await page.click('#cad-salvar');
    await expect(erroDe(page, 'Descrição')).toHaveText('Informe a descrição.');
    await expect(erroDe(page, 'Cartão de crédito')).toHaveText('Selecione o cartão.');
    await expect(erroDe(page, 'Parcelas')).toHaveText('Parcelas: de 1 a 48.');
    // Volta a despesa direta: os campos dela, em branco (sem o vencimento de antes).
    await escolherTipo(page, 'direta');
    await expect(page.locator('#cad-vencimento')).toHaveValue('');
    await expect(page.locator('#cad-cartao')).toHaveCount(0);
});

test('compra a vista no cartao: grava uma vez (toque duplo) na fatura sugerida; aparece no Cartoes mobile e so a fatura na Lista', async ({ page }) => {
    await entrar(page, G);
    const master = await idDoCartao(page, MASTER);
    await abrirCadastro(page);
    await compraNoCartao(page, { nome: 'Tenis G', valor: '250.00', data: '2031-07-10' });
    await expect(controle(page, 'Mês da fatura')).toHaveValue('2031-07');
    await expect(page.locator('#mob-previa-parcelas')).toBeHidden();  // a vista: sem previa
    await page.locator('#cad-salvar').dblclick();
    await expect(confirmacao(page)).toContainText('“Tenis G” lançada no cartão');
    await expect(confirmacao(page)).toContainText(`Compra lançada na fatura 07/2031 do cartão ${MASTER}.`);
    await expect(page.locator('#cad-ver-registro')).toHaveAttribute('href', `cartoes-mobile.html?mes=2031-07&cartao=${master}`);
    await evidencia(page, 'cartao-confirmacao', false);
    // No banco: uma compra na fatura (toque duplo nao duplica) e nenhuma conta a pagar com o nome da compra.
    const compras = await comprasDaFatura(page, master, '2031-07', 'Tenis G');
    expect(compras.map((c) => [Number(c.valor), c.data_compra, c.numero_parcela, c.total_parcelas])).toEqual([[250, '2031-07-10', 1, 1]]);
    expect(await contasDoMes(page, '2031-07', 'Tenis G')).toEqual([]);
    const fatura = await faturaDoMes(page, master, '2031-07');
    expect(fatura.map((f) => Number(f.valor_executado))).toEqual([250]);
    // Cartoes mobile (pelo link da confirmacao) e Lista de Despesas mobile: a compra na fatura; na lista, so a fatura.
    await page.click('#cad-ver-registro');
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
    await expect(controle(page, 'Mês da fatura')).toHaveValue('2031-05');
    const previa = page.locator('#mob-previa-parcelas');
    await expect(previa.locator('tbody tr')).toHaveCount(3);
    await expect(previa.locator('tbody tr')).toHaveText([/1\/305\/2031R\$\s300,00/, /2\/306\/2031R\$\s300,00/, /3\/307\/2031R\$\s300,00/]);
    await expect(previa.locator('tfoot')).toContainText(reais(900));
    await evidencia(page, 'cartao-parcelada', false);
    await page.click('#cad-salvar');
    await expect(confirmacao(page)).toContainText(`Compra lançada em 3 parcelas no cartão ${MASTER}: faturas 05/2031 a 07/2031.`);
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
    await expect(controle(page, 'Mês da fatura')).toHaveValue('2031-09');
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Essa fatura já está paga: a compra vai para a próxima em aberto.');
    await page.click('#cad-salvar');
    await expect(confirmacao(page)).toContainText(`Compra lançada na fatura 10/2031 do cartão ${MASTER}.`);
    expect(await comprasDaFatura(page, master, '2031-09', 'Livro G')).toEqual([]);
    expect((await comprasDaFatura(page, master, '2031-10', 'Livro G')).length).toBe(1);

    // 20/11 -> fatura 12/2031, consolidada (total 200,00): a pergunta do desktop; sem confirmar, nada e gravado.
    await page.click('#cad-novo');
    await compraNoCartao(page, { nome: 'Presente G', valor: '80.00', data: '2031-11-20' });
    await expect(controle(page, 'Mês da fatura')).toHaveValue('2031-12');
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Essa fatura está consolidada: a inclusão pede confirmação.');
    await page.click('#cad-salvar');
    const pergunta = page.locator('#cad-consolidada');
    await expect(pergunta).toContainText(`Incluir na fatura consolidada 12/2031: total ${reais(200)} passa a ${reais(280)} (inclusão de ${reais(80)}).`);
    await evidencia(page, 'cartao-consolidada', false);
    await page.click('#mob-nao-incluir');
    await expect(pergunta).toBeHidden();
    await expect(mensagem(page)).toHaveText('Compra não salva: a inclusão na fatura consolidada não foi confirmada.');
    expect(await comprasDaFatura(page, master, '2031-12', 'Presente G')).toEqual([]);
    await page.click('#cad-salvar');
    await expect(pergunta).toBeVisible();
    await page.locator('#mob-confirmar-inclusao').dblclick();  // toque duplo: uma compra so
    await expect(confirmacao(page)).toContainText(`Compra lançada na fatura 12/2031 do cartão ${MASTER}.`);
    expect((await comprasDaFatura(page, master, '2031-12', 'Presente G')).map((c) => Number(c.valor))).toEqual([80]);
});

// Sem rolagem horizontal, campos sem sobreposicao, cabecalho e rodape fixos e visiveis (a rolagem e so a do corpo).
async function medir(page) {
    return page.evaluate(() => {
        const caixas = [...document.querySelectorAll('#cad-modal .mob-campo')].filter((e) => e.offsetParent)
            .map((e) => e.getBoundingClientRect());
        const sobrepostos = caixas.some((a, i) => caixas.some((b, j) => j > i && a.left < b.right - 0.5 && b.left < a.right - 0.5
            && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
        const corpo = document.querySelector('.cad-corpo');
        const rodape = document.querySelector('.cad-rodape').getBoundingClientRect();
        const cabecalho = document.querySelector('.cad-cabecalho').getBoundingClientRect();
        return {
            rolagem: document.documentElement.scrollWidth > window.innerWidth || corpo.scrollWidth > corpo.clientWidth + 1,
            fora: [...document.querySelectorAll('#cad-modal *')]
                .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.left < -0.5 || r.right > window.innerWidth + 0.5); }).length,
            sobrepostos,
            fixos: cabecalho.top >= -0.5 && rodape.bottom <= window.innerHeight + 0.5,
        };
    });
}

test('larguras de 320 a 430: sem rolagem horizontal, campos sem sobreposicao, cabecalho e rodape fixos (os quatro tipos)', async ({ page }) => {
    await entrar(page, G);
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        await abrirCadastro(page);
        for (const tipo of ['direta', 'recorrente', 'consorcio']) {
            await escolherTipo(page, tipo);
            if (tipo === 'recorrente') await page.selectOption('#cad-frequencia', 'semanal');
            if (tipo === 'consorcio') await page.selectOption('#cad-tipo-reajuste', 'percentual');
            expect(await medir(page), `largura ${largura}, ${tipo}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false, fixos: true });
            if ([320, 430].includes(largura)) await evidencia(page, `modal-${tipo}-${largura}`);
        }
    }
});

test('larguras de 320 a 430 no cartao: sem rolagem horizontal, campos sem sobreposicao (previa do parcelamento aberta)', async ({ page }) => {
    await entrar(page, G);
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        await abrirCadastro(page);
        await compraNoCartao(page, { nome: 'Teste de largura G', valor: '1234.56', data: '2031-05-10', parcelas: 12 });
        await expect(page.locator('#mob-previa-parcelas tbody tr')).toHaveCount(12);
        expect(await medir(page), `largura ${largura}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false, fixos: true });
        if ([320, 430].includes(largura)) await evidencia(page, `cartao-parcelado-${largura}`);
    }
});
