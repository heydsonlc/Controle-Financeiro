// FIN-MVP-MOBILE-06 — Registrar Lancamento mobile (atalho Lancamento e Lancar da barra). Usuario G, titular do "Perfil G
// (ficticio)" (o mesmo dos Cartoes, Receitas e Nova Despesa mobile); somente leitura: usuario H. Competencia 01/2032 e cartao
// "Nubank Master G" (fecha 15, vence 25, fechamento confirmado) para receita, despesa e compra; "Reserva G" (segunda conta)
// para a transferencia; "Flex G" (veiculo flex, sem abastecimentos) para o abastecimento, com a data de hoje (o banco recusa
// data futura). Tudo conferido no banco (funcoes de leitura do desktop) e nas telas mobile. Dados FICTICIOS; grava so no
// banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import * as cad from './cadastro.mjs';

import { chamarRpc } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MES = '2032-01';
const MASTER = 'Nubank Master G (ficticio)';
const CONTA_G = 'Conta G (ficticia)';
const RESERVA_G = 'Reserva G (ficticia)';
const VEICULO = 'Flex G (ficticio)';
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const CELULAR = { width: 390, height: 844 };
const EVIDENCIAS = process.env.CF_MOBILE06_EVIDENCIAS || '';  // capturas da homologacao (opcional)

test.use({ viewport: CELULAR, isMobile: true, hasTouch: true });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    // A pagina mobile nao tem servidor /api/: as rotas sao atendidas no navegador pelos servicos do desktop.
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

async function abrirLancamento(page, tipo = null, mes = MES) {
    await page.goto(`/lancamento-mobile.html?mes=${mes}${tipo ? `&tipo=${tipo}` : ''}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
}

async function escolher(page, tipo) {
    await page.click(`.mob-tipo[data-tipo="${tipo}"]`);
    await expect(page.locator(`.mob-tipo[data-tipo="${tipo}"]`)).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
}

const campo = (page, rotulo) => page.locator('#mob-cadastro .mob-campo', { has: page.locator('xpath=./span[1]', { hasText: new RegExp(`^${rotulo}`) }) });
const controle = (page, rotulo) => campo(page, rotulo).locator('input, select, textarea, output').first();
const erroDe = (page, rotulo) => campo(page, rotulo).locator('.mob-campo-erro');
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const confirmacao = (page) => page.locator('#mob-confirmacao');
const idDoCartao = async (page, nome) => (await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G })).find((c) => c.nome === nome).id;
const comprasDaFatura = (page, cartao, mes, descricao) => rpc(page, 'compras_da_fatura', { p_perfil_id: PERFIL_G, p_cartao_id: cartao, p_mes: `${mes}-01` })
    .then((l) => l.filter((c) => c.descricao === descricao));
const contasDoMes = (page, mes, nome) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` }).then((l) => l.filter((c) => c.nome === nome));
const contas = (page) => rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' });
const veiculoG = async (page) => (await rpc(page, 'formulario_abastecimento_lancamento', { p_perfil_id: PERFIL_G })).veiculos.find((v) => v.nome === VEICULO);
const abastecimentos = async (page) => (await rpc(page, 'abastecimentos_veiculo_tela', { p_perfil_id: PERFIL_G, p_veiculo_id: (await veiculoG(page)).id })).abastecimentos;

// ---------------------------------------------------------------------------------------------------------------

test('atalho Lancamento e Lancar da barra abrem a mesma pagina, na competencia; seletor compacto; nenhuma operacao aberta', async ({ page }) => {
    await entrar(page, G);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="lancamento"]');
    const lancar = page.locator('.mob-barra-item[data-modulo="lancar"]');
    await expect(atalho).toHaveAttribute('href', `lancamento-mobile.html?mes=${MES}`);
    await expect(lancar).toHaveAttribute('href', `lancamento-mobile.html?mes=${MES}`);
    await atalho.click();
    await page.waitForURL(`**/lancamento-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('h1.mob-titulo')).toHaveText('Registrar Lançamento');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil G (ficticio)');
    await expect(page.locator('.mob-tipo')).toHaveText(['Receita', 'Despesa', 'Compra no cartão', 'Transferência', 'Abastecimento']);
    await expect(page.locator('.mob-tipo[aria-pressed="true"]')).toHaveCount(0);
    await expect(page.locator('#mob-cadastro')).toHaveText('Escolha o tipo de lançamento.');
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
    await evidencia(page, 'abertura');
    // O Lancar da barra das outras paginas mobile leva a mesma pagina, com a competencia aberta.
    await page.goto(`/despesas-mobile.html?mes=${MES}`);
    await page.locator('.mob-barra-item[data-modulo="lancar"]').click();
    await page.waitForURL(`**/lancamento-mobile.html?mes=${MES}`);
    await expect(page.locator('.mob-tipo')).toHaveCount(5);
});

test('receita: o formulario das Receitas mobile; nasce prevista na competencia, sem recebimento', async ({ page }) => {
    await entrar(page, G);
    await abrirLancamento(page);
    await escolher(page, 'receita');
    await expect(page.locator('#mob-cadastro')).toContainText('Competência Jan/2032: a receita nasce prevista neste mês');
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Nome' }).locator('input').fill('Bonus G');
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Tipo' }).locator('select').selectOption({ index: 1 });
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Valor base mensal' }).locator('input').fill('350,00');
    await page.locator('#mob-cadastro .mob-opcao', { hasText: 'Receita recorrente' }).locator('input').uncheck();
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Conta bancária' }).locator('select').selectOption({ label: `${CONTA_G} (Banco ficticio)` });
    await evidencia(page, 'receita', false);
    await page.locator('#mob-cadastro button[type="submit"]').dblclick();
    await expect(confirmacao(page)).toContainText('“Bonus G” cadastrada');
    await expect(confirmacao(page)).toContainText('O recebimento é registrado em Receitas → Receber');
    await expect(page.locator('#mob-ver-receitas')).toHaveAttribute('href', `receitas-mobile.html?mes=${MES}`);
    // No banco: uma fonte e uma previsao de 01/2032 com R$ 350,00, nenhum recebimento.
    const fontes = (await rpc(page, 'receitas_fontes_tela', { p_perfil_id: PERFIL_G })).filter((f) => f.nome === 'Bonus G');
    expect(fontes.length).toBe(1);
    const previsoes = (await rpc(page, 'receitas_orcamentos_tela', { p_perfil_id: PERFIL_G, p_ano: 2032 }))
        .filter((o) => o.item_receita_id === fontes[0].id);
    expect(previsoes.map((o) => [o.mes_referencia.slice(0, 7), Number(o.valor_esperado ?? o.valor_previsto ?? o.valor)])).toEqual([['2032-01', 350]]);
    // Receitas mobile: a receita prevista, a receber.
    await page.click('#mob-ver-receitas');
    await page.waitForURL(`**/receitas-mobile.html?mes=${MES}`);
    const linha = page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: 'Bonus G' }) });
    await expect(linha).toHaveCount(1);
    await expect(linha).not.toContainText('Recebida');
});

// FIN-MVP-CADASTRO-UNIFICADO-01: Despesa e Compra no cartao abrem o modal unico (o mesmo de Despesas e Recorrencias), ja no
// tipo escolhido na tela; ao fechar, volta-se a escolha do tipo desta pagina, na mesma competencia.
test('despesa e compra no cartao: o modal unico, ja no tipo escolhido; sem duplicidade; fechar volta a escolha do tipo', async ({ page }) => {
    await entrar(page, G);
    const master = await idDoCartao(page, MASTER);
    await abrirLancamento(page);
    await escolher(page, 'despesa');
    await cad.esperarModal(page, 'direta');
    await expect(page.locator('#cad-competencia-texto')).toHaveText('Competência: janeiro/2032');
    await cad.preencherCadastro(page, { nome: 'Fibra G (lancamento)', valor: '99.90', categoria: 'Moradia', vencimento: '2032-02-10' });
    await expect(page.locator('#cad-competencia-texto')).toHaveText('Competência: janeiro/2032');  // regra do desktop: mes anterior ao vencimento
    await page.locator('#cad-salvar').dblclick();
    await expect(cad.confirmacao(page)).toContainText('“Fibra G (lancamento)” cadastrada como pendente');
    expect((await contasDoMes(page, MES, 'Fibra G (lancamento)')).map((c) => [Number(c.valor), c.status_pagamento])).toEqual([[99.9, 'Pendente']]);
    // "Novo cadastro" recomeca a mesma operacao, vazia; "Concluir" volta a escolha do tipo (a origem), na mesma competencia.
    await page.click('#cad-novo');
    await expect(page.locator('#cad-nome')).toHaveValue('');
    await expect(page.locator('#cad-tipo')).toHaveValue('DESPESA_DIRETA');
    await cad.fecharCadastro(page);
    await expect(page).toHaveURL(new RegExp(`lancamento-mobile\\.html\\?mes=${MES}$`));
    await expect(page.locator('.mob-tipo[aria-pressed="true"]')).toHaveCount(0);
    await expect(page.locator('#mob-cadastro')).toContainText('Escolha o tipo de lançamento.');

    // Compra no cartao: o mesmo modal, ja em "Compra no cartao"; parcelada, com a previa do banco.
    await escolher(page, 'cartao');
    await cad.esperarModal(page, 'compra');
    await cad.preencherCadastro(page, { nome: 'Fone G', valor: '300.00', categoria: 'Moradia', cartao: MASTER, data: '2032-01-05', parcelas: 2 });
    await expect(page.locator('#cad-mes-fatura')).toHaveValue('2032-01');
    await expect(page.locator('#mob-previa-parcelas tbody tr')).toHaveText([/1\/201\/2032R\$\s150,00/, /2\/202\/2032R\$\s150,00/]);
    await evidencia(page, 'compra-cartao', false);
    await page.locator('#cad-salvar').dblclick();
    await expect(cad.confirmacao(page)).toContainText(`Compra lançada em 2 parcelas no cartão ${MASTER}: faturas 01/2032 a 02/2032.`);
    await expect(page.locator('#cad-ver-registro')).toHaveAttribute('href', `cartoes-mobile.html?mes=2032-01&cartao=${master}`);
    for (const [mes, n] of [['2032-01', 1], ['2032-02', 2]]) {
        expect((await comprasDaFatura(page, master, mes, 'Fone G')).map((c) => [Number(c.valor), c.numero_parcela]), mes).toEqual([[150, n]]);
    }
    expect(await contasDoMes(page, MES, 'Fone G')).toEqual([]);  // so a compra, na fatura: nenhuma conta a pagar
    await page.click('#cad-ver-registro');
    await page.waitForURL(`**/cartoes-mobile.html?mes=2032-01&cartao=${master}`);
    await expect(page.locator('#mob-lista')).toContainText('Fone G');
});

test('transferencia: movimentos pareados e saldos pelos movimentos; destino sem a origem; duplo toque grava uma', async ({ page }) => {
    await entrar(page, G);
    const antes = await contas(page);
    const origem = antes.find((c) => c.nome === CONTA_G);
    const destino = antes.find((c) => c.nome === RESERVA_G);
    await abrirLancamento(page);
    await escolher(page, 'transferencia');
    await controle(page, 'Conta de origem').selectOption(String(origem.id));
    // O destino nao oferece a propria origem.
    await expect(controle(page, 'Conta de destino').locator('option')).toHaveText(['Selecione...', `${RESERVA_G} · ${reais(destino.saldo_atual)}`]);
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Conta de destino')).toHaveText('Selecione a conta de destino.');
    await expect(erroDe(page, 'Valor')).toHaveText('Informe um valor maior que zero.');
    await controle(page, 'Conta de destino').selectOption(String(destino.id));
    await controle(page, 'Valor').fill('123.45');
    await expect(controle(page, 'Data')).toHaveValue(HOJE);
    await evidencia(page, 'transferencia', false);
    await page.locator('#mob-salvar').dblclick();
    await expect(confirmacao(page)).toContainText('Transferência realizada');
    await expect(confirmacao(page)).toContainText(`${reais(123.45)} de ${CONTA_G} para ${RESERVA_G}`);
    const depois = await contas(page);
    const saldo = (lista, id) => Math.round(Number(lista.find((c) => c.id === id).saldo_atual) * 100);
    expect(saldo(depois, origem.id) - saldo(antes, origem.id)).toBe(-12345);
    expect(saldo(depois, destino.id) - saldo(antes, destino.id)).toBe(12345);
    await expect(confirmacao(page)).toContainText(`${RESERVA_G} ${reais(saldo(depois, destino.id) / 100)}`);
    // Um movimento de entrada no destino (o duplo toque nao duplicou).
    const extrato = await rpc(page, 'extrato_conta_bancaria', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: destino.id, p_inicio: null,
        p_fim: null, p_limite: 200, p_incluir_saldo: false });
    expect(extrato.filter((mv) => Math.round(Number(mv.valor) * 100) === 12345).length).toBe(1);
});

test('abastecimento: veiculo, combustivel do cadastro e litros; conta a pagar e compra a vista no cartao, vinculados a Mobilidade', async ({ page }) => {
    await entrar(page, G);
    const master = await idDoCartao(page, MASTER);
    await abrirLancamento(page);
    await escolher(page, 'abastecimento');
    // Um veiculo so: ja escolhido; flex: gasolina ou etanol; descricao sugerida; data de hoje.
    await expect(controle(page, 'Veículo').locator('option:checked')).toHaveText(VEICULO);
    await expect(controle(page, 'Combustível').locator('option')).toHaveText(['Gasolina', 'Etanol']);
    await expect(controle(page, 'Descrição')).toHaveValue(`Abastecimento ${VEICULO}`);
    await expect(controle(page, 'Data')).toHaveValue(HOJE);
    await expect(controle(page, 'Meio de pagamento')).toHaveValue('conta');
    await expect(page.locator('#mob-nota-conta')).toContainText('(mês da data)');
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Hodômetro')).toHaveText('Informe o hodômetro.');
    await expect(erroDe(page, 'Preço por litro')).toHaveText('Informe o preço por litro.');
    await expect(erroDe(page, 'Valor total')).toHaveText('Informe o valor total.');
    // Hodometros a partir da ultima leitura do veiculo (outro spec pode ter registrado um abastecimento antes).
    const km0 = Number((await veiculoG(page)).ultimo_hodometro || 0);
    const antesDeste = (await abastecimentos(page)).length;
    await controle(page, 'Hodômetro').fill(String(km0 + 10000));
    await controle(page, 'Combustível').selectOption('etanol');
    await controle(page, 'Preço por litro').fill('5.899');
    await controle(page, 'Valor total').fill('200');
    await expect(page.locator('#mob-litros')).toHaveText('33,904 L');  // 200 / 5,899, como o desktop mostra
    await evidencia(page, 'abastecimento-conta', false);
    await page.locator('#mob-salvar').dblclick();
    await expect(confirmacao(page)).toContainText(`“Abastecimento ${VEICULO}” registrado`);
    await expect(confirmacao(page)).toContainText('33,904 L de Etanol');  // os litros gravados pelo banco
    await expect(page.locator('#mob-ver-lista')).toHaveAttribute('href', `despesas-mobile.html?mes=${HOJE.slice(0, 7)}`);
    // No banco: um abastecimento vinculado a uma conta a pagar de R$ 200 (categoria Combustivel, competencia do mes da data).
    let lista = (await abastecimentos(page)).filter((a) => Number(a.hodometro_km) === km0 + 10000);
    expect(lista.map((a) => [Number(a.valor_total), Number(a.hodometro_km), a.combustivel, Boolean(a.conta_id), Boolean(a.lancamento_id)]))
        .toEqual([[200, km0 + 10000, 'etanol', true, false]]);
    const conta = await contasDoMes(page, HOJE.slice(0, 7), `Abastecimento ${VEICULO}`);
    expect(conta.map((c) => [Number(c.valor), c.categoria_nome, c.data_vencimento])).toEqual([[200, 'Combustível', HOJE]]);

    // Compra a vista no cartao (sem parcelas), com a fatura sugerida; o abastecimento fica vinculado a compra.
    await page.click('#mob-outra');
    await controle(page, 'Hodômetro').fill(String(km0 + 9000));
    await controle(page, 'Preço por litro').fill('5.799');
    await controle(page, 'Valor total').fill('150');
    await controle(page, 'Meio de pagamento').selectOption('cartao');
    await controle(page, 'Cartão').selectOption({ label: MASTER });
    await expect(page.locator('#mob-fatura-sugestao')).toContainText('Sugerida pelo fechamento');
    await expect(campo(page, 'Parcelas')).toHaveCount(0);  // abastecimento: compra a vista
    const fatura = await controle(page, 'Fatura').inputValue();
    // Hodometro menor que a ultima leitura: o banco recusa (regra da Mobilidade), junto ao campo; nada e gravado.
    await page.click('#mob-salvar');
    await expect(erroDe(page, 'Hodômetro')).toContainText('Hodômetro menor que a leitura');
    expect((await abastecimentos(page)).length).toBe(antesDeste + 1);
    await controle(page, 'Hodômetro').fill(String(km0 + 10350));
    await evidencia(page, 'abastecimento-cartao', false);
    await page.locator('#mob-salvar').dblclick();
    await expect(confirmacao(page)).toContainText(`Compra lançada na fatura ${fatura.slice(5, 7)}/${fatura.slice(0, 4)} do cartão ${MASTER}.`);
    await expect(confirmacao(page)).toContainText('Abastecimento registrado no veículo');
    lista = await abastecimentos(page);
    expect(lista.length).toBe(antesDeste + 2);
    const doCartao = lista.find((a) => Number(a.hodometro_km) === km0 + 10350);
    expect([Number(doCartao.valor_total), Boolean(doCartao.lancamento_id), Boolean(doCartao.conta_id)]).toEqual([150, true, false]);
    expect((await comprasDaFatura(page, master, fatura, `Abastecimento ${VEICULO}`)).map((c) => [Number(c.valor), c.total_parcelas]))
        .toEqual([[150, 1]]);
});

test('trocar de operacao com dados preenchidos pede confirmacao; cancelar e sair sem salvar nao gravam', async ({ page }) => {
    await entrar(page, G);
    await abrirLancamento(page, 'despesa');
    // FIN-MVP-CADASTRO-UNIFICADO-01: na despesa, a troca de tipo e dentro do modal; com algo so da despesa direta ja
    // preenchido, o modal pergunta. "Manter" continua na despesa, com o que foi preenchido.
    await cad.preencherCadastro(page, { nome: 'Rascunho G', valor: '10', categoria: 'Moradia', vencimento: '2032-02-10' });
    await page.selectOption('#cad-tipo', 'DESPESA_RECORRENTE');
    await expect(page.locator('#cad-troca')).toContainText('Trocar para “Despesa recorrente” descarta o que só existe em “Despesa direta”');
    await page.click('#cad-troca-manter');
    await expect(page.locator('#cad-tipo')).toHaveValue('DESPESA_DIRETA');
    await expect(page.locator('#cad-nome')).toHaveValue('Rascunho G');
    await expect(page.locator('#cad-vencimento')).toHaveValue('2032-02-10');
    // Cancelar o cadastro: nada e gravado e volta-se a escolha do tipo; a transferencia abre sem os valores da despesa.
    await cad.fecharCadastro(page);
    await escolher(page, 'transferencia');
    await expect(campo(page, 'Conta de origem')).toBeVisible();
    await expect(controle(page, 'Valor')).toHaveValue('');
    // Sair com dados: o navegador pergunta (recusar mantem a pagina); Cancelar e intencional e nao pergunta.
    await controle(page, 'Valor').fill('10');
    let perguntou = false;
    page.once('dialog', (d) => { perguntou = d.type() === 'beforeunload'; d.dismiss(); });
    await page.click('#mob-voltar');
    await expect.poll(() => perguntou).toBe(true);
    await expect(page).toHaveURL(/lancamento-mobile\.html/);
    await page.click('#mob-cancelar');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
    expect(await contasDoMes(page, MES, 'Rascunho G')).toEqual([]);
});

test('somente leitura (usuario H): Lancamento e Lancar desabilitados; sem operacoes; o banco recusa', async ({ page }) => {
    await entrar(page, H);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="lancamento"]');
    const lancar = page.locator('.mob-barra-item[data-modulo="lancar"]');
    await expect(atalho).toHaveAttribute('title', 'Somente leitura neste perfil');  // depois da consulta da permissao
    for (const item of [atalho, lancar]) {
        await expect(item).toHaveAttribute('aria-disabled', 'true');
        await expect(item).not.toHaveAttribute('href', /./);
    }
    await lancar.click({ force: true });
    await expect(page).toHaveURL(/inicio\.html/);
    // Nas outras paginas mobile o Lancar tambem fica desabilitado.
    await page.goto(`/receitas-mobile.html?mes=${MES}`);
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('title', 'Somente leitura neste perfil');
    // Acesso direto ao endereco: sem operacoes.
    await abrirLancamento(page, 'transferencia');
    await expect(page.locator('#mob-cadastro')).toContainText('Acesso somente de leitura a este perfil: não é possível registrar lançamentos.');
    await expect(page.locator('#mob-tipos')).toBeHidden();
    await expect(page.locator('#mob-cadastro form')).toHaveCount(0);
    await evidencia(page, 'somente-leitura', false);
    const lidas = await contas(page);
    const transferir = await chamarRpc(page, 'transferir_entre_contas', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(), p_dados: {
        conta_origem_id: lidas[0].id, conta_destino_id: lidas[1].id, valor: 1, data_movimento: HOJE, descricao: 'Tentativa do leitor H' } });
    expect(transferir.status).not.toBe(200);
    const abastecer = await chamarRpc(page, 'salvar_lancamento_abastecimento', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(), p_dados: {
        lancamento: { tipo: 'despesa', dados: { nome: 'Tentativa do leitor H', valor: '10.00', categoria_id: 201, data_vencimento: HOJE } },
        abastecimento: { veiculo_id: (await veiculoG(page)).id, combustivel: 'etanol', hodometro_km: 20000, preco_litro: 5 } } });
    expect(abastecer.status).not.toBe(200);
});

test('larguras de 320 a 430: sem rolagem horizontal nem campos sobrepostos em cada operacao', async ({ page }) => {
    page.on('dialog', (d) => d.accept());  // trocar de pagina com o formulario preenchido: o navegador pergunta
    await entrar(page, G);
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        for (const tipo of ['receita', 'despesa', 'cartao', 'transferencia', 'abastecimento']) {
            await abrirLancamento(page, tipo);
            // Despesa e Compra no cartao: o modal unico, medido no lugar do formulario da pagina.
            if (tipo === 'despesa') await cad.esperarModal(page, 'direta');
            if (tipo === 'cartao') {
                await cad.preencherCadastro(page, { valor: '1234.56', categoria: false, cartao: MASTER, parcelas: 3 });
                await expect(page.locator('#mob-previa-parcelas tbody tr')).toHaveCount(3);
            }
            if (tipo === 'abastecimento') {
                await controle(page, 'Meio de pagamento').selectOption('cartao');
                await controle(page, 'Cartão').selectOption({ label: MASTER });
            }
            const medidas = await page.evaluate(() => {
                const noModal = Boolean(document.querySelector('#cad-modal'));
                const caixas = [...document.querySelectorAll(noModal ? '#cad-modal .mob-campo' : '#mob-cadastro .mob-campo, .mob-tipo')].filter((e) => e.offsetParent)
                    .map((e) => e.getBoundingClientRect());
                const sobrepostos = caixas.some((a, i) => caixas.some((b, j) => j > i && a.left < b.right - 0.5 && b.left < a.right - 0.5
                    && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5));
                return {
                    rolagem: document.documentElement.scrollWidth > window.innerWidth,
                    fora: [...document.querySelectorAll(noModal ? '#cad-modal *' : '#mob-cadastro *, #mob-tipos *, .mob-cabecalho *, .mob-barra-item')]
                        .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.left < -0.5 || r.right > window.innerWidth + 0.5); }).length,
                    sobrepostos,
                };
            });
            expect(medidas, `${tipo} em ${largura}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false });
            if ([320, 430].includes(largura)) await evidencia(page, `${tipo}-${largura}`);
        }
    }
});
