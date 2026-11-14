// FIN-MVP-MOBILE-04 — Receitas mobile. Usuario G, titular do "Perfil G (ficticio)" (o mesmo dos Cartoes mobile; gerador NOVO),
// com receitas gravadas pelas funcoes oficiais (tests/supabase_local.py: semear_receitas_mobile_e2e): no mes atual, "Salario G"
// (o do mes anterior atrasado), "Aluguel Sala G" parcial, "Gratificacao G" recebida e "Rendimento G" previsto; em 04/2031, as
// mesmas fontes (salario de 03 atrasado). Somente leitura: usuario H, leitor do Perfil G. A lista e os totais sao comparados com
// a tela de Receitas do desktop no mesmo banco; recebimentos, estornos e cadastros sao conferidos no banco (recebimentos,
// movimento e saldo). Dados FICTICIOS; grava so no banco descartavel.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc, normal } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MES = '2031-04';
const CELULAR = { width: 390, height: 844 };
const DESKTOP = { width: 1366, height: 900 };
const EVIDENCIAS = process.env.CF_MOBILE04_EVIDENCIAS || '';  // capturas da homologacao (opcional)
const SALARIO = 'Salario G (ficticio)';
const ALUGUEL = 'Aluguel Sala G (ficticio)';
const RENDIMENTO = 'Rendimento G (ficticio)';
const GRATIFICACAO = 'Gratificacao G (ficticio)';
const FREELANCE = 'Freelance G (ficticio)';

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

function mesAtual() {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit' }).format(new Date()).slice(0, 7);
}

async function esperarLista(page, mes) {
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', mes);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}

async function abrirReceitas(page, mes = MES) {
    await page.goto(`/receitas-mobile.html?mes=${mes}`);
    await esperarLista(page, mes);
}

const linha = (page, nome, onde = '#mob-lista') => page.locator(`${onde} .mob-linha`, { has: page.locator('.mob-linha-nome', { hasText: nome }) }).first();
const folha = (page) => page.locator('#mob-folha');
const botaoFolha = (page, texto) => folha(page).locator('.mob-botao', { hasText: texto });
const aviso = (page) => page.locator('#mob-aviso');
const total = (page, chave) => page.locator(`#mob-resumo [data-total="${chave}"] dd`);
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const campoFolha = (page, rotulo) => folha(page).locator('.mob-campo', { hasText: rotulo }).locator('input, select, textarea').first();
const detalhe = (page, rotulo) => folha(page).locator('.mob-detalhes dt', { hasText: new RegExp(`^${rotulo}$`) }).locator('xpath=following-sibling::dd[1]');

// Linhas da lista do mes: [nome, valor, legenda]
const linhasMobile = (page, onde = '#mob-lista') => page.$$eval(`${onde} .mob-linha`, (els) => els.map((e) => [
    e.querySelector('.mob-linha-nome').textContent.trim(), e.querySelector('.mob-linha-valor').textContent.replace(/\s+/g, ' ').trim(),
    e.querySelector('.mob-linha-data').textContent.trim()]));

async function abrirDetalhes(page, nome, onde = '#mob-lista') {
    await linha(page, nome, onde).click();
    await expect(folha(page)).toBeVisible();
    await expect(page.locator('#mob-folha-titulo')).toHaveText(nome);
}

async function totais(page) {
    return { previsto: normal(await total(page, 'previsto').textContent()), recebido: normal(await total(page, 'recebido').textContent()),
        pendente: normal(await total(page, 'pendente').textContent()) };
}

const contaG = async (page) => (await rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' }))
    .find((c) => c.nome === 'Conta G (ficticia)');

async function previsao(page, nome, competencia) {
    const fontes = await rpc(page, 'receitas_fontes_tela', { p_perfil_id: PERFIL_G });
    const fonte = fontes.find((f) => f.nome === nome);
    const orcamentos = await rpc(page, 'receitas_orcamentos_tela', { p_perfil_id: PERFIL_G, p_ano: Number(competencia.slice(0, 4)) });
    return orcamentos.find((o) => o.item_receita_id === fonte.id && o.mes_referencia.startsWith(competencia));
}

// ---------------------------------------------------------------------------------------------------------------

test('atalho Receita da pagina principal abre as Receitas mobile na competencia; Inicio volta com o mesmo mes', async ({ page }) => {
    await entrar(page, G);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="receita"]');
    await expect(atalho).toHaveAttribute('href', `receitas-mobile.html?mes=${MES}`);
    await expect(atalho).not.toHaveAttribute('aria-disabled', 'true');
    await atalho.click();
    await page.waitForURL(`**/receitas-mobile.html?mes=${MES}`);
    await esperarLista(page, MES);
    await expect(page.locator('h1.mob-titulo')).toHaveText('Receitas');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil G (ficticio)');
    await expect(page.locator('#mob-competencia')).toHaveText('Abr/2031');
    await expect(page.locator('#mob-nova')).toBeVisible();
    // A barra continua a aprovada (nenhum item novo); Inicio e Voltar levam a competencia.
    await expect(page.locator('.mob-barra .mob-barra-item')).toHaveText(['Início', 'Lançar', 'Resumo', 'Mais']);
    await expect(page.locator('.mob-barra-item[data-inicio]')).toHaveAttribute('href', `inicio.html?mes=${MES}`);
    await page.click('#mob-mes-seguinte');
    await esperarLista(page, '2031-05');
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', 'inicio.html?mes=2031-05');
    await page.click('#mob-mes-anterior');
    await esperarLista(page, MES);
    await page.click('#mob-voltar');
    await page.waitForURL(`**/inicio.html?mes=${MES}`);
});

test('lista do mes, ordem, legendas e totais; atrasadas recolhidas; tudo igual a tela de Receitas do desktop (mes atual)', async ({ page }) => {
    await entrar(page, G);
    await abrirReceitas(page);
    // A ordem do desktop: previstas, parciais e recebidas; depois competencia e nome.
    expect(await linhasMobile(page)).toEqual([
        [RENDIMENTO, reais(45.3), 'Prev. 01/04'],
        [SALARIO, reais(6500), 'Prev. 05/04'],
        [ALUGUEL, reais(1200), 'Prev. 10/04 · parcial'],
        [GRATIFICACAO, reais(800), 'Receb. 12/04 · recebida'],
    ]);
    await expect(linha(page, GRATIFICACAO)).toHaveClass(/recebida/);
    expect(await totais(page)).toEqual({ previsto: reais(8545.3), recebido: reais(1300), pendente: reais(7245.3) });
    // Atrasadas: bloco recolhido, com a quantidade e o que falta receber; abre e mostra a competencia na legenda.
    const atrasadas = page.locator('#mob-atrasadas .mob-grupo-cabecalho');
    await expect(atrasadas).toHaveAttribute('aria-expanded', 'false');
    await expect(atrasadas.locator('.mob-grupo-rotulo')).toHaveText('Receitas atrasadas (1)');
    await expect(atrasadas.locator('.mob-grupo-total')).toHaveText(reais(6500));
    await expect(page.locator('#mob-grupo-atrasadas')).toBeHidden();
    await evidencia(page, 'lista-390x844');
    await atrasadas.click();
    expect(await linhasMobile(page, '#mob-atrasadas')).toEqual([[SALARIO, reais(6500), 'Mar/2031 · Prev. 05/03']]);
    await evidencia(page, 'atrasadas-abertas-390x844');

    // Mes atual (o desktop nao seleciona 2031 no filtro de ano): mobile e desktop com os mesmos numeros e linhas.
    const mes = mesAtual();
    await abrirReceitas(page, mes);
    const mobile = { totais: await totais(page), linhas: (await linhasMobile(page)).map((l) => l[0]) };
    expect(mobile.linhas.sort()).toEqual([ALUGUEL, GRATIFICACAO, RENDIMENTO, SALARIO]);
    await page.setViewportSize(DESKTOP);
    await page.goto('/receitas.html');
    await expect(page.locator('#mes-lista .receitas-loading')).toHaveCount(0);
    await expect(page.locator('#mes-lista .receita-row')).toHaveCount(4);
    expect(normal(await page.locator('#total-previsto').textContent())).toBe(mobile.totais.previsto);
    expect(normal(await page.locator('#total-realizado').textContent())).toBe(mobile.totais.recebido);
    const nomesDesktop = (await page.locator('#mes-lista .receita-source strong').allTextContents()).map(normal);
    expect(nomesDesktop.sort()).toEqual(mobile.linhas.sort());
    // Pendente: a conta do painel "Recebimentos pendentes" do desktop (o que falta das previstas e parciais).
    expect(mobile.totais.pendente).toBe(reais(6500 + 45.3 + 700));
});

test('detalhe da receita: informacoes do desktop e so as acoes possiveis para cada situacao', async ({ page }) => {
    await entrar(page, G);
    await abrirReceitas(page);
    await abrirDetalhes(page, SALARIO);
    await expect(folha(page).locator('.mob-folha-valor')).toHaveText(reais(6500));
    await expect(detalhe(page, 'Descrição')).toHaveText('Salario mensal ficticio');
    await expect(detalhe(page, 'Tipo')).toHaveText('Salário Fixo');
    await expect(detalhe(page, 'Competência')).toHaveText('Abr/2031');
    await expect(detalhe(page, 'Data prevista')).toHaveText('05/04/2031');
    await expect(detalhe(page, 'Valor previsto')).toHaveText(reais(6500));
    await expect(detalhe(page, 'Falta receber')).toHaveText(reais(6500));
    await expect(detalhe(page, 'Conta bancária')).toHaveText('Conta G (ficticia)');
    await expect(detalhe(page, 'Recorrência')).toHaveText('Mensal (recorrente)');
    await expect(detalhe(page, 'Situação')).toHaveText('Prevista');
    await expect(folha(page).locator('.mob-botao')).toHaveText(['Receber', 'Editar', 'Cancelar previsão']);
    await evidencia(page, 'detalhe-prevista', false);
    await page.click('#mob-folha-fechar');

    await abrirDetalhes(page, ALUGUEL);
    await expect(detalhe(page, 'Situação')).toHaveText('Parcialmente recebida');
    await expect(detalhe(page, 'Valor recebido')).toHaveText(reais(500));
    await expect(detalhe(page, 'Falta receber')).toHaveText(reais(700));
    await expect(detalhe(page, 'Recebimento')).toHaveText('10/04/2031');
    // Parcial: sem cancelar (o banco recusa a previsao com recebimento) e sem estorno (o desktop so oferece na realizada).
    await expect(folha(page).locator('.mob-botao')).toHaveText(['Receber', 'Editar']);
    await page.click('#mob-folha-fechar');

    await abrirDetalhes(page, GRATIFICACAO);
    await expect(detalhe(page, 'Situação')).toHaveText('Recebida');
    await expect(detalhe(page, 'Recorrência')).toHaveText('Não recorrente');
    await expect(folha(page).locator('.mob-botao')).toHaveText(['Editar', 'Estornar']);
    await evidencia(page, 'detalhe-recebida', false);
});

test('receber: conta, valor e data; credito na conta; toque duplo nao duplica; acima do que falta exige justificativa', async ({ page }) => {
    await entrar(page, G);
    const saldoAntes = Number((await contaG(page)).saldo_atual);
    await abrirReceitas(page);
    await abrirDetalhes(page, SALARIO);
    await botaoFolha(page, 'Receber').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText(`Receber: ${SALARIO}`);
    await expect(campoFolha(page, 'Conta bancária').locator('option:checked')).toHaveText('Conta G (ficticia) (Banco ficticio)');
    await expect(campoFolha(page, 'Valor recebido')).toHaveValue('6.500,00');
    await campoFolha(page, 'Data do recebimento').fill('2031-04-05');
    await evidencia(page, 'receber', false);
    await botaoFolha(page, 'Receber').dblclick();  // dois toques: um recebimento so
    await expect(aviso(page)).toHaveText(`Receita registrada com sucesso: ${reais(6500)} em Conta G (ficticia).`);
    await esperarLista(page, MES);
    await expect(linha(page, SALARIO)).toHaveClass(/recebida/);
    expect((await linhasMobile(page)).find((l) => l[0] === SALARIO)).toEqual([SALARIO, reais(6500), 'Receb. 05/04 · recebida']);
    expect(await totais(page)).toEqual({ previsto: reais(8545.3), recebido: reais(7800), pendente: reais(745.3) });
    const prev = await previsao(page, SALARIO, MES);
    const dados = await rpc(page, 'dados_recebimento_receita', { p_perfil_id: PERFIL_G, p_orcamento_id: prev.id });
    expect(dados.recebimentos.map((r) => [Number(r.valor), r.data_recebimento, r.conta_nome])).toEqual([[6500, '2031-04-05', 'Conta G (ficticia)']]);
    expect(dados.receita.falta).toBe(0);
    expect(Number((await contaG(page)).saldo_atual)).toBeCloseTo(saldoAntes + 6500, 2);
    await evidencia(page, 'apos-receber');

    // Aluguel: faltam 700; 800 sem justificativa e recusado pelo banco (nada gravado); com justificativa, registra.
    await abrirDetalhes(page, ALUGUEL);
    await botaoFolha(page, 'Receber').click();
    await expect(campoFolha(page, 'Valor recebido')).toHaveValue('700,00');
    await campoFolha(page, 'Valor recebido').fill('800,00');
    await botaoFolha(page, 'Receber').click();
    await expect(folha(page).locator('.mob-mensagem.erro')).toContainText('justificativa');
    await campoFolha(page, 'Justificativa').fill('Reajuste do aluguel ficticio');
    await botaoFolha(page, 'Receber').click();
    await expect(aviso(page)).toHaveText(`Receita registrada com sucesso: ${reais(800)} em Conta G (ficticia).`);
    await esperarLista(page, MES);
    expect((await linhasMobile(page)).find((l) => l[0] === ALUGUEL)[1]).toBe(reais(1300));
    expect(await totais(page)).toEqual({ previsto: reais(8545.3), recebido: reais(8600), pendente: reais(45.3) });
    await abrirDetalhes(page, ALUGUEL);
    await expect(folha(page).locator('.mob-tabela-linha')).toHaveCount(2);
    await expect(detalhe(page, 'Observações')).toContainText('[ACIMA DO PREVISTO] Reajuste do aluguel ficticio');
    expect(Number((await contaG(page)).saldo_atual)).toBeCloseTo(saldoAntes + 7300, 2);
});

test('estornar recebimento: debito compensatorio, receita volta a prevista; cancelar previsao a tira da lista', async ({ page }) => {
    await entrar(page, G);
    const saldoAntes = Number((await contaG(page)).saldo_atual);
    await abrirReceitas(page);
    await abrirDetalhes(page, GRATIFICACAO);
    await botaoFolha(page, 'Estornar').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Estornar recebimento');
    await botaoFolha(page, 'Estornar').click();
    await expect(folha(page).locator('.mob-mensagem.erro')).toHaveText('Informe o motivo do estorno.');
    await campoFolha(page, 'Data do estorno').fill('2031-04-13');
    await campoFolha(page, 'Motivo do estorno').fill('Lancado por engano (teste ficticio)');
    await evidencia(page, 'estornar', false);
    await botaoFolha(page, 'Estornar').click();
    await expect(aviso(page)).toHaveText('Recebimento estornado com sucesso.');
    await esperarLista(page, MES);
    expect((await linhasMobile(page)).find((l) => l[0] === GRATIFICACAO)).toEqual([GRATIFICACAO, reais(800), 'Sem data prevista']);
    expect(Number((await contaG(page)).saldo_atual)).toBeCloseTo(saldoAntes - 800, 2);
    expect(await totais(page)).toEqual({ previsto: reais(8545.3), recebido: reais(7800), pendente: reais(845.3) });
    const prev = await previsao(page, GRATIFICACAO, MES);
    const dados = await rpc(page, 'dados_recebimento_receita', { p_perfil_id: PERFIL_G, p_orcamento_id: prev.id });
    expect(dados.recebimentos.map((r) => r.estornado)).toEqual([true]);
    expect(dados.receita.falta).toBe(800);

    await abrirDetalhes(page, RENDIMENTO);
    await botaoFolha(page, 'Cancelar previsão').click();
    await expect(folha(page)).toContainText(`Remover a previsão de "${RENDIMENTO}" na competência Abr/2031?`);
    await botaoFolha(page, 'Cancelar previsão').click();
    await expect(aviso(page)).toHaveText('Previsão removida.');
    await esperarLista(page, MES);
    await expect(linha(page, RENDIMENTO)).toHaveCount(0);
    expect(await totais(page)).toEqual({ previsto: reais(8500), recebido: reais(7800), pendente: reais(800) });
    const removida = await previsao(page, RENDIMENTO, MES);
    expect([Number(removida.valor_esperado), removida.observacoes]).toEqual([0, 'Removido pelo usuário']);
    expect(Number((await contaG(page)).saldo_atual)).toBeCloseTo(saldoAntes - 800, 2);
});

test('nova receita pelo "+": a fonte nasce prevista na competencia aberta, sem duplicar com dois toques', async ({ page }) => {
    await entrar(page, G);
    await abrirReceitas(page);
    await page.click('#mob-nova');
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Nova receita');
    await expect(folha(page)).toContainText('Competência Abr/2031');
    await botaoFolha(page, 'Salvar').click();
    await expect(folha(page).locator('.mob-mensagem.erro')).toHaveText('Informe nome e tipo da fonte.');
    await campoFolha(page, 'Nome').fill(FREELANCE);
    await campoFolha(page, 'Tipo').selectOption('RENDA_EXTRA');
    await campoFolha(page, 'Valor base mensal').fill('350,00');
    await folha(page).locator('.mob-opcao', { hasText: 'Receita recorrente' }).locator('input').uncheck();
    await expect(campoFolha(page, 'Dia previsto')).toBeDisabled();
    await campoFolha(page, 'Conta bancária').selectOption({ label: 'Conta G (ficticia) (Banco ficticio)' });
    await evidencia(page, 'nova-receita', false);
    await botaoFolha(page, 'Salvar').dblclick();
    await expect(aviso(page)).toHaveText('Fonte de receita criada com sucesso');
    await esperarLista(page, MES);
    expect((await linhasMobile(page)).find((l) => l[0] === FREELANCE)).toEqual([FREELANCE, reais(350), 'Sem data prevista']);
    const fontes = (await rpc(page, 'receitas_fontes_tela', { p_perfil_id: PERFIL_G })).filter((f) => f.nome === FREELANCE);
    expect(fontes.map((f) => [f.tipo, f.recorrente, f.ativo])).toEqual([['RENDA_EXTRA', false, true]]);
    const previsoes = (await rpc(page, 'receitas_orcamentos_tela', { p_perfil_id: PERFIL_G, p_ano: 2031 }))
        .filter((o) => o.item_receita_id === fontes[0].id);
    expect(previsoes.map((o) => [o.mes_referencia, Number(o.valor_esperado)])).toEqual([['2031-04-01', 350]]);
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(4);
});

test('editar a fonte: dados gravados; previa da atualizacao das previsoes, e manter nao muda nada', async ({ page }) => {
    await entrar(page, G);
    await abrirReceitas(page);
    await page.locator('#mob-atrasadas .mob-grupo-cabecalho').click();
    await abrirDetalhes(page, SALARIO, '#mob-atrasadas');
    await botaoFolha(page, 'Editar').click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText(`Editar: ${SALARIO}`);
    await expect(campoFolha(page, 'Nome')).toHaveValue(SALARIO);
    await expect(campoFolha(page, 'Valor base mensal')).toHaveValue('6.500,00');
    await expect(campoFolha(page, 'Dia previsto')).toHaveValue('5');
    await campoFolha(page, 'Descrição').fill('Salario mensal ficticio (editado)');
    await campoFolha(page, 'Valor base mensal').fill('6800,00');
    await evidencia(page, 'editar-fonte', false);
    await botaoFolha(page, 'Salvar').click();
    // Previsoes pendentes com outro valor: a previa do desktop (o que muda e o que fica); "Manter" nao muda nenhuma.
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Atualizar previsões pelo valor-base');
    await expect(folha(page)).toContainText('Fonte de receita atualizada com sucesso.');
    await expect(folha(page)).toContainText(`valor-base ${reais(6800)}`);
    await evidencia(page, 'previa-atualizacao', false);
    await botaoFolha(page, 'Manter as previsões').click();
    await expect(aviso(page)).toContainText('Fonte de receita atualizada com sucesso.');
    await esperarLista(page, MES);
    const fonte = (await rpc(page, 'receitas_fontes_tela', { p_perfil_id: PERFIL_G })).find((f) => f.nome === SALARIO);
    expect([fonte.descricao, Number(fonte.valor_base_mensal)]).toEqual(['Salario mensal ficticio (editado)', 6800]);
    expect(Number((await previsao(page, SALARIO, '2031-03')).valor_esperado)).toBe(6500);
    expect((await linhasMobile(page, '#mob-atrasadas')).map((l) => l[1])).toEqual([reais(6500)]);
});

test('filtros Tipo e Busca como o desktop; somente leitura (usuario H) ve tudo e nao tem acoes', async ({ page }) => {
    await entrar(page, G);
    await abrirReceitas(page);
    await page.click('#mob-filtros');
    await campoFolha(page, 'Tipo').selectOption('ALUGUEL');
    await evidencia(page, 'filtros', false);
    await botaoFolha(page, 'Aplicar').click();
    await expect(page.locator('#mob-filtro-marca')).toBeVisible();
    expect((await linhasMobile(page)).map((l) => l[0])).toEqual([ALUGUEL]);
    expect((await totais(page)).previsto).toBe(reais(1200));
    await page.click('#mob-filtros');
    await botaoFolha(page, 'Limpar').click();
    await expect(page.locator('#mob-filtro-marca')).toBeHidden();
    await page.click('#mob-filtros');
    await campoFolha(page, 'Buscar').fill('salário');
    await botaoFolha(page, 'Aplicar').click();
    expect((await linhasMobile(page)).map((l) => l[0])).toEqual([SALARIO]);

    await page.click('.mob-barra-item#mob-mais');
    await page.click('#mob-sair');
    await page.waitForURL('**/index.html**');
    await entrar(page, H);
    await abrirReceitas(page);
    await expect(page.locator('#mob-nova')).toBeHidden();
    expect((await linhasMobile(page)).length).toBe(4);
    await abrirDetalhes(page, SALARIO);
    await expect(folha(page)).toContainText('Acesso somente de leitura a este perfil.');
    await expect(folha(page).locator('.mob-botao')).toHaveCount(0);
    await evidencia(page, 'somente-leitura', false);
    // O banco recusa a escrita do leitor de qualquer forma (a interface so nao oferece).
    const prev = await previsao(page, GRATIFICACAO, MES);
    const r = await chamarRpc(page, 'receber_receita', { p_perfil_id: PERFIL_G, p_orcamento_id: prev.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: (await contaG(page)).id, data_recebimento: '2031-04-20', valor_recebido: '800.00', falta: 800 } });
    expect(r.status).not.toBe(200);
});

test('larguras de 320 a 430: sem rolagem horizontal, sem sobreposicao; nada e gravado ao abrir', async ({ page }) => {
    await entrar(page, G);
    const antes = await rpc(page, 'receitas_orcamentos_tela', { p_perfil_id: PERFIL_G, p_ano: 2031 });
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        await abrirReceitas(page);
        await page.locator('#mob-atrasadas .mob-grupo-cabecalho').click();
        const medidas = await page.evaluate(() => {
            const dentro = (e) => { const r = e.getBoundingClientRect(); return r.left >= -0.5 && r.right <= window.innerWidth + 0.5; };
            const titulo = document.querySelector('.mob-titulo').getBoundingClientRect();
            const filtros = document.querySelector('#mob-filtros').getBoundingClientRect();
            return {
                rolagem: document.documentElement.scrollWidth > window.innerWidth,
                fora: [...document.querySelectorAll('.mob-cabecalho *, .mob-resumo *, .mob-linha *, .mob-grupo-cabecalho *, .mob-barra-item')]
                    .filter((e) => e.getBoundingClientRect().width > 0 && !dentro(e)).length,
                tituloSobreBotao: titulo.right > filtros.left,
            };
        });
        expect(medidas, `largura ${largura}`).toEqual({ rolagem: false, fora: 0, tituloSobreBotao: false });
        if ([320, 430].includes(largura)) await evidencia(page, `lista-${largura}`);
    }
    // Abrir e navegar nao gera nem altera previsoes (nenhuma materializacao ao abrir a pagina).
    expect(await rpc(page, 'receitas_orcamentos_tela', { p_perfil_id: PERFIL_G, p_ano: 2031 })).toEqual(antes);
});
