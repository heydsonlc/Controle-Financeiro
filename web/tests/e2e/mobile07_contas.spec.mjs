// FIN-MVP-MOBILE-07 — Contas e Movimentacoes mobile (atalho Contas). Usuario G, titular do "Perfil G (ficticio)" (o mesmo dos
// demais modulos mobile); somente leitura: usuario H. Cenario (semear_contas_mobile_e2e e anteriores), no mes atual: na
// Conta G, recebimentos (Receitas), pagamento de despesa ("Energia G"), pagamento estornado ("Academia G"), pagamento da
// fatura do Master e transferencia para a Reserva G; na Reserva G, saldo inicial de R$ 1.500,00, a transferencia recebida e
// um ajuste de saldo. Outros specs podem gravar movimentos nas mesmas contas: tudo e conferido contra as funcoes de leitura
// do desktop (contas_bancarias_tela, extrato_conta_bancaria, conferir_saldo_conta), nunca contra valores fixos de saldo.
import { mkdirSync } from 'node:fs';
import path from 'node:path';

import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const CONTA_G = 'Conta G (ficticia)';
const RESERVA_G = 'Reserva G (ficticia)';
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const MES = HOJE.slice(0, 7);
const CELULAR = { width: 390, height: 844 };
const DESKTOP = { width: 1366, height: 900 };
const EVIDENCIAS = process.env.CF_MOBILE07_EVIDENCIAS || '';  // capturas da homologacao (opcional)

test.use({ viewport: CELULAR, isMobile: true, hasTouch: true });
test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
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

const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');
const normal = (t) => String(t).replace(/\s/g, ' ').trim();
const contasDoBanco = (page) => rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' });
const contaDoBanco = async (page, nome) => (await contasDoBanco(page)).find((c) => c.nome === nome);
const ultimoDia = (mes) => { const [a, m] = mes.split('-').map(Number); return `${mes}-${String(new Date(Date.UTC(a, m, 0)).getUTCDate()).padStart(2, '0')}`; };
const extratoDoBanco = (page, contaId, inicio = `${MES}-01`, fim = ultimoDia(MES)) => rpc(page, 'extrato_conta_bancaria', {
    p_perfil_id: PERFIL_G, p_conta_bancaria_id: contaId, p_inicio: inicio, p_fim: fim, p_limite: 200, p_incluir_saldo: true });

async function abrirContas(page, contaId = null, mes = MES) {
    await page.goto(`/contas-mobile.html?mes=${mes}${contaId ? `&conta=${contaId}` : ''}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}

const linhas = (page) => page.locator('#mob-lista .mob-movimento');
const linhaDe = (page, natureza, valor) => page.locator(`#mob-lista .mob-movimento[data-natureza="${natureza}"]`, {
    has: page.locator('.mob-linha-valor', { hasText: valor }) }).first();
const folha = (page) => page.locator('#mob-folha');
const detalhe = (page, rotulo) => folha(page).locator('.mob-detalhes dt', { hasText: new RegExp(`^${rotulo}$`) }).locator('xpath=following-sibling::dd[1]');

// ---------------------------------------------------------------------------------------------------------------

test('atalho Contas abre as Contas; seletor com as contas do perfil; saldo do banco, igual ao do desktop', async ({ page }) => {
    await entrar(page, G);
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="contas"]');
    await expect(atalho).toHaveAttribute('href', `contas-mobile.html?mes=${MES}`);
    await atalho.click();
    await page.waitForURL(`**/contas-mobile.html?mes=${MES}**`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('h1.mob-titulo')).toHaveText('Contas');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil G (ficticio)');
    const banco = await contasDoBanco(page);
    // O nome do desktop (nomes diferentes: sem mais nada; nenhuma agencia nem numero).
    await expect(page.locator('#mob-conta option')).toHaveText(banco.map((c) => c.nome));
    const contaG = banco.find((c) => c.nome === CONTA_G);
    await expect(page.locator('#mob-conta')).toHaveValue(String(contaG.id));
    await expect(page).toHaveURL(new RegExp(`conta=${contaG.id}`));
    await expect(page.locator('#mob-saldo-valor')).toHaveText(reais(contaG.saldo_atual));
    // Saldo registrado = saldo inicial + creditos - debitos (conferencia do desktop): sem aviso de divergencia.
    const conferencia = await rpc(page, 'conferir_saldo_conta', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: contaG.id });
    expect(conferencia.consistente).toBe(true);
    await expect(page.locator('#mob-saldo-divergencia')).toHaveCount(0);
    await expect(page.locator('#mob-competencia')).toHaveText(new RegExp(`/${MES.slice(0, 4)}$`));
    await expect(page.locator('#mob-transferir')).toHaveAttribute('href', `lancamento-mobile.html?mes=${MES}&tipo=transferencia&origem=${contaG.id}`);
    await expect(page.locator('.mob-barra .mob-barra-item')).toHaveText(['Início', 'Lançar', 'Resumo', 'Mais']);
    await evidencia(page, 'contas-390');
    // O mesmo saldo na tela Contas Bancarias do desktop (mesmo banco).
    await page.setViewportSize(DESKTOP);
    await page.goto('/contas-bancarias.html');
    const linhaDesktop = page.locator('article.conta-row', { has: page.locator('h3', { hasText: CONTA_G }) });
    await expect(linhaDesktop).toBeVisible();
    expect(normal(await linhaDesktop.textContent())).toContain(reais(contaG.saldo_atual));
});

test('movimentacoes do mes: a ordem e os movimentos do extrato do desktop; data, descricao, valor com sinal e natureza', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    await abrirContas(page, contaG.id);
    const extrato = await extratoDoBanco(page, contaG.id);
    await expect(linhas(page)).toHaveCount(extrato.length);
    expect(await linhas(page).evaluateAll((els) => els.map((e) => Number(e.dataset.id)))).toEqual(extrato.map((m) => m.id));
    // Os movimentos do cenario, cada um com o sinal da sua natureza.
    await expect(linhaDe(page, 'despesa', reais(180))).toContainText('Pagamento de despesa');
    await expect(linhaDe(page, 'despesa', reais(180)).locator('.mob-linha-valor')).toHaveText(`− ${reais(180)}`);
    await expect(linhaDe(page, 'estorno', reais(99.9)).locator('.mob-linha-valor')).toHaveText(`+ ${reais(99.9)}`);
    await expect(linhaDe(page, 'despesa', reais(99.9)).locator('.mob-linha-valor')).toHaveText(`− ${reais(99.9)}`);
    await expect(linhaDe(page, 'transferencia', reais(300))).toContainText('Transferência enviada');
    await expect(linhaDe(page, 'transferencia', reais(300)).locator('.mob-linha-valor')).toHaveText(`− ${reais(300)}`);
    await expect(linhaDe(page, 'receita', reais(800)).locator('.mob-linha-valor')).toHaveText(`+ ${reais(800)}`);
    await expect(linhaDe(page, 'fatura', reais(100))).toContainText('Pagamento de fatura');
    // Entrada: classe propria (valor em destaque discreto); saida, a cor normal.
    await expect(linhaDe(page, 'receita', reais(800))).toHaveClass(/entrada/);
    await expect(linhaDe(page, 'despesa', reais(180))).not.toHaveClass(/entrada/);
    const primeira = extrato[0];
    await expect(linhas(page).first().locator('.mob-movimento-data')).toHaveText(`${primeira.data_movimento.slice(8, 10)}/${primeira.data_movimento.slice(5, 7)}`);
    await evidencia(page, 'movimentos-conta-g');
});

test('trocar de conta: saldo e extrato da outra conta (saldo inicial, transferencia recebida e ajuste), sem voltar ao inicio', async ({ page }) => {
    await entrar(page, G);
    const reserva = await contaDoBanco(page, RESERVA_G);
    await abrirContas(page);
    await page.selectOption('#mob-conta', String(reserva.id));
    await expect(page).toHaveURL(new RegExp(`conta=${reserva.id}`));
    await expect(page.locator('#mob-saldo-valor')).toHaveText(reais(reserva.saldo_atual));
    await expect(page.locator('#mob-saldo')).toContainText('Poupança · Banco ficticio');
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', new RegExp(`^${reserva.id}:`));
    const extrato = await extratoDoBanco(page, reserva.id);
    await expect(linhas(page)).toHaveCount(extrato.length);
    await expect(linhaDe(page, 'transferencia', reais(300))).toContainText('Transferência recebida');
    await expect(linhaDe(page, 'ajuste', reais(12.34)).locator('.mob-linha-valor')).toHaveText(`+ ${reais(12.34)}`);
    // O saldo e o do banco (com o saldo inicial de R$ 1.500,00), nao a soma das linhas exibidas.
    const somaDasLinhas = extrato.reduce((t, m) => t + (m.tipo === 'CREDITO' ? 1 : -1) * Number(m.valor), 0);
    expect(Math.round(Number(reserva.saldo_atual) * 100)).not.toBe(Math.round(somaDasLinhas * 100));
    expect(Number((await rpc(page, 'conferir_saldo_conta', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: reserva.id })).saldo_inicial)).toBe(1500);
    await evidencia(page, 'movimentos-reserva');
});

test('detalhes: origem de cada movimento (despesa, estorno, transferencia, fatura, ajuste), so leitura e caminhos para os modulos', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const reserva = await contaDoBanco(page, RESERVA_G);
    await abrirContas(page, contaG.id);
    const somenteFechar = async () => {
        await expect(folha(page).locator('button.mob-botao')).toHaveText(['Fechar']);  // nenhuma acao de escrita
        await page.click('#mob-folha-fechar');
    };
    // Pagamento de despesa: a despesa, a competencia, a situacao e o caminho para a Lista de Despesas.
    await linhaDe(page, 'despesa', reais(180)).click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Pagamento de despesa');
    await expect(detalhe(page, 'Valor')).toHaveText(`− ${reais(180)}`);
    await expect(detalhe(page, 'Conta')).toHaveText(CONTA_G);
    await expect(detalhe(page, 'Tipo')).toHaveText('Saída (débito)');
    await expect(detalhe(page, 'Despesa')).toContainText('Energia G (ficticia)');
    await expect(detalhe(page, 'Situação da despesa')).toHaveText('Pago');
    await expect(page.locator('#mob-ver-origem')).toHaveAttribute('href', `despesas-mobile.html?mes=${MES}`);
    await expect(detalhe(page, 'Saldo após o movimento')).toHaveText(/^R\$/);
    await evidencia(page, 'detalhe-despesa', false);
    await somenteFechar();
    // Estorno: o movimento original e a despesa (que voltou a pendente).
    await linhaDe(page, 'estorno', reais(99.9)).click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Estorno');
    await expect(detalhe(page, 'Tipo')).toHaveText('Entrada (crédito)');
    await expect(detalhe(page, 'Estorno de')).toContainText(`− ${reais(99.9)}`);
    await expect(detalhe(page, 'Despesa')).toContainText('Academia G (ficticia)');
    await somenteFechar();
    // Transferencia: a conta de destino e o caminho para ela.
    await linhaDe(page, 'transferencia', reais(300)).click();
    await expect(detalhe(page, 'Conta de destino')).toHaveText(RESERVA_G);
    await expect(page.locator('#mob-ver-origem')).toHaveAttribute('href', `contas-mobile.html?mes=${MES}&conta=${reserva.id}`);
    await evidencia(page, 'detalhe-transferencia', false);
    await somenteFechar();
    // Pagamento de fatura: o cartao e a competencia da fatura, e o caminho para os Cartoes.
    await linhaDe(page, 'fatura', reais(100)).click();
    await expect(detalhe(page, 'Fatura')).toHaveText('Nubank Master G (ficticio) · Set/2031');
    await expect(detalhe(page, 'Situação da fatura')).toHaveText('Paga');
    await expect(page.locator('#mob-ver-origem')).toHaveAttribute('href', /^cartoes-mobile\.html\?mes=2031-09&cartao=\d+$/);
    await somenteFechar();
    // Recebimento: o caminho para as Receitas (o estorno do recebimento fica la).
    await linhaDe(page, 'receita', reais(800)).click();
    await expect(page.locator('#mob-ver-origem')).toHaveAttribute('href', `receitas-mobile.html?mes=${MES}`);
    await somenteFechar();
    // Ajuste: so visualizacao (incluir, alterar e excluir ajuste ficam no desktop).
    await page.selectOption('#mob-conta', String(reserva.id));
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', new RegExp(`^${reserva.id}:`));
    await linhaDe(page, 'ajuste', reais(12.34)).click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Ajuste de saldo');
    await expect(folha(page)).toContainText('Ajustes de saldo são incluídos, alterados ou excluídos só no desktop');
    await somenteFechar();
});

test('filtros (tipo e periodo) e meses; a consulta nao altera saldo nenhum', async ({ page }) => {
    await entrar(page, G);
    const antes = await contasDoBanco(page);
    const contaG = antes.find((c) => c.nome === CONTA_G);
    await abrirContas(page, contaG.id);
    const extrato = await extratoDoBanco(page, contaG.id);
    // Tipo: entradas; estornos.
    await page.click('#mob-filtros');
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Filtros');
    await evidencia(page, 'filtros', false);
    await folha(page).locator('.mob-campo', { hasText: 'Tipo de movimentação' }).locator('select').selectOption('entradas');
    await page.click('#mob-filtros-aplicar');
    await expect(linhas(page)).toHaveCount(extrato.filter((m) => m.tipo === 'CREDITO').length);
    await expect(page.locator('#mob-lista .mob-movimento:not(.entrada)')).toHaveCount(0);
    await expect(page.locator('#mob-filtro-marca')).toBeVisible();
    await page.click('#mob-filtros');
    await folha(page).locator('.mob-campo', { hasText: 'Tipo de movimentação' }).locator('select').selectOption('estorno');
    await page.click('#mob-filtros-aplicar');
    await expect(linhas(page)).toHaveCount(extrato.filter((m) => m.movimento_original_id).length);
    // Periodo: do dia 1 ao dia 5 (a mesma consulta do desktop, com inicio e fim).
    const fim = `${MES}-${String(Math.min(5, Number(HOJE.slice(8, 10)))).padStart(2, '0')}`;
    await page.click('#mob-filtros');
    await folha(page).locator('.mob-campo', { hasText: 'Tipo de movimentação' }).locator('select').selectOption('');
    await folha(page).locator('.mob-campo', { hasText: 'Até' }).locator('input').fill(fim);
    await page.click('#mob-filtros-aplicar');
    const doPeriodo = await extratoDoBanco(page, contaG.id, `${MES}-01`, fim);
    await expect(linhas(page)).toHaveCount(doPeriodo.length);
    await expect(page.locator('#mob-competencia')).toHaveText(`01/${MES.slice(5, 7)}/${MES.slice(0, 4)} a ${fim.slice(8, 10)}/${MES.slice(5, 7)}/${MES.slice(0, 4)}`);
    await expect(page.locator('#mob-mes-anterior')).toBeDisabled();
    // Data inicial maior que a final: recusada no painel.
    await page.click('#mob-filtros');
    await folha(page).locator('.mob-campo', { has: page.locator('span', { hasText: /^De$/ }) }).locator('input').fill(`${MES}-20`);
    await folha(page).locator('.mob-campo', { hasText: 'Até' }).locator('input').fill(`${MES}-10`);
    await page.click('#mob-filtros-aplicar');
    await expect(folha(page)).toContainText('A data inicial não pode ser maior que a final.');
    // Limpar: volta ao mes, com todos os movimentos.
    await page.click('#mob-filtros-limpar');
    await expect(linhas(page)).toHaveCount(extrato.length);
    await expect(page.locator('#mob-filtro-marca')).toBeHidden();
    // Meses: o anterior (o extrato do desktop para o mes) e de volta.
    const anterior = `${MES.slice(0, 4)}-${MES.slice(5, 7)}` === `${MES.slice(0, 4)}-01`
        ? `${Number(MES.slice(0, 4)) - 1}-12` : `${MES.slice(0, 4)}-${String(Number(MES.slice(5, 7)) - 1).padStart(2, '0')}`;
    await page.click('#mob-mes-anterior');
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-carregado', `${contaG.id}:${anterior}-01:${ultimoDia(anterior)}`);
    await expect(linhas(page)).toHaveCount((await extratoDoBanco(page, contaG.id, `${anterior}-01`, ultimoDia(anterior))).length);
    await page.click('#mob-mes-seguinte');
    await expect(linhas(page)).toHaveCount(extrato.length);
    // Nada mudou no banco: os mesmos saldos e a conferencia consistente.
    expect((await contasDoBanco(page)).map((c) => [c.id, c.saldo_atual])).toEqual(antes.map((c) => [c.id, c.saldo_atual]));
    for (const c of antes) {
        expect((await rpc(page, 'conferir_saldo_conta', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: c.id })).consistente, c.nome).toBe(true);
    }
});

test('transferir: o formulario do Registrar Lancamento ja com a origem; de volta as Contas, saldos e extrato atualizados', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const reserva = await contaDoBanco(page, RESERVA_G);
    await abrirContas(page, contaG.id);
    await page.click('#mob-transferir');
    await page.waitForURL(`**/lancamento-mobile.html?mes=${MES}&tipo=transferencia&origem=${contaG.id}`);
    await expect(page.locator('#mob-cadastro')).toHaveAttribute('aria-busy', 'false');
    const origem = page.locator('#mob-cadastro .mob-campo', { hasText: 'Conta de origem' }).locator('select');
    await expect(origem).toHaveValue(String(contaG.id));
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Conta de destino' }).locator('select').selectOption(String(reserva.id));
    await page.locator('#mob-cadastro .mob-campo', { hasText: 'Valor' }).locator('input').fill('10');
    await page.locator('#mob-salvar').dblclick();
    await expect(page.locator('#mob-confirmacao')).toContainText('Transferência realizada');
    await expect(page.locator('#mob-ver-contas')).toHaveAttribute('href', `contas-mobile.html?mes=${MES}&conta=${contaG.id}`);
    await page.click('#mob-ver-contas');
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    const depois = await contaDoBanco(page, CONTA_G);
    expect(Math.round(Number(depois.saldo_atual) * 100)).toBe(Math.round(Number(contaG.saldo_atual) * 100) - 1000);
    await expect(page.locator('#mob-saldo-valor')).toHaveText(reais(depois.saldo_atual));
    await expect(linhaDe(page, 'transferencia', reais(10))).toBeVisible();
    expect((await extratoDoBanco(page, reserva.id)).filter((m) => m.transferencia_id && Number(m.valor) === 10).length).toBe(1);
});

test('somente leitura (usuario H): consulta contas, saldos, movimentos e detalhes; sem transferir; Lancar desabilitado', async ({ page }) => {
    await entrar(page, H);
    const contaG = await contaDoBanco(page, CONTA_G);
    await page.goto(`/inicio.html?mes=${MES}`);
    await expect(page.locator('.mob-atalho[data-modulo="contas"]')).toHaveAttribute('href', `contas-mobile.html?mes=${MES}`);
    await abrirContas(page, contaG.id);
    await expect(page.locator('#mob-saldo-valor')).toHaveText(reais(contaG.saldo_atual));
    await expect(linhas(page)).toHaveCount((await extratoDoBanco(page, contaG.id)).length);
    await expect(page.locator('#mob-transferir')).toBeHidden();
    await expect(page.locator('.mob-barra-item[data-modulo="lancar"]')).toHaveAttribute('title', 'Somente leitura neste perfil');
    await linhaDe(page, 'despesa', reais(180)).click();
    await expect(detalhe(page, 'Despesa')).toContainText('Energia G (ficticia)');
    await expect(folha(page).locator('button.mob-botao')).toHaveText(['Fechar']);
    await evidencia(page, 'somente-leitura', false);
});

test('larguras de 320 a 430: lista e detalhe sem rolagem horizontal nem sobreposicao', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    for (const largura of [320, 375, 390, 430]) {
        await page.setViewportSize({ width: largura, height: 844 });
        await abrirContas(page, contaG.id);
        const medir = () => page.evaluate(() => ({
            rolagem: document.documentElement.scrollWidth > window.innerWidth,
            fora: [...document.querySelectorAll('.mob-conteudo *, .mob-cabecalho *, .mob-barra-item, #mob-folha *')]
                .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.left < -0.5 || r.right > window.innerWidth + 0.5); }).length,
            // Data, descricao e valor de cada linha sem se sobrepor.
            sobrepostos: [...document.querySelectorAll('#mob-lista .mob-movimento')].some((l) => {
                const [d, t, v] = ['.mob-movimento-data', '.mob-linha-texto', '.mob-linha-valor'].map((s) => l.querySelector(s).getBoundingClientRect());
                return d.right > t.left + 0.5 || t.right > v.left + 0.5;
            }),
        }));
        expect(await medir(), `lista em ${largura}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false });
        await linhaDe(page, 'transferencia', reais(300)).click();
        await expect(detalhe(page, 'Conta de destino')).toHaveText(RESERVA_G);
        expect(await medir(), `detalhe em ${largura}`).toEqual({ rolagem: false, fora: 0, sobrepostos: false });
        if ([320, 430].includes(largura)) {
            await page.click('#mob-folha-fechar');
            await evidencia(page, `contas-${largura}`);
        }
    }
});
