// FIN-MVP-MOBILE-08 — Pagamentos mobile (pagamentos-mobile.html). Usuario G, titular do "Perfil G (ficticio)"; leitor H.
// Obrigacoes em 03/2034 (competencia sem outro dado): duas avulsas pendentes, uma avulsa ja paga, uma recorrencia semanal
// (4 tercas) e uma fatura do Master G com compra. A tela le sem gerar recorrencias (05/2034 nunca aberta continua sem as
// ocorrencias) e paga pelos fluxos do desktop: individual (pagar_despesa / pagar_fatura) e lote da recorrencia semanal
// (pagar_despesas_lote). Decisao do titular (opcao A): uma obrigacao por vez; o agrupador semanal leva todas as pendentes.
// Cada efeito e conferido pelas funcoes de leitura do desktop (situacao, pagamentos, saldo, conferencia). Dados FICTICIOS;
// grava so no banco descartavel.
import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MES = '2034-03';
const MES_SEM_GERACAO = '2034-05';
const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const CONTA_G = 'Conta G (ficticia)';
const ROTULO_CONTA_G = 'Conta G (ficticia) (Banco ficticio)';
const MASTER = 'Nubank Master G (ficticio)';
const FATURA_MASTER = `Fatura ${MASTER} - 03/2034`;  // o nome da fatura na lista (contas_do_mes)
const LUZ = 'Pag Luz G';
const INTERNET = 'Pag Internet G';
const JA_PAGA = 'Pag Paga G';
const DIARISTA = 'Pag Diarista G';

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
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
const centavos = (v) => Math.round(Number(v) * 100);
const folha = (page) => page.locator('#mob-folha');
const botaoFolha = (page, texto) => folha(page).locator('.mob-botao', { hasText: texto });
const aviso = (page) => page.locator('#mob-aviso');
const contasDoMes = (page, mes) => rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` });
const doMes = async (page, mes, nome) => (await contasDoMes(page, mes)).filter((c) => c.nome === nome || c.nome.startsWith(`${nome} - `));
const contaDoBanco = async (page, nome) => (await rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' })).find((c) => c.nome === nome);
const consistente = async (page, contaId) => (await rpc(page, 'conferir_saldo_conta', { p_perfil_id: PERFIL_G, p_conta_bancaria_id: contaId })).consistente;
const pendente = (c) => c.status_pagamento !== 'Pago' && c.status_pagamento !== 'Dispensada';

async function abrirPagamentos(page, mes = MES) {
    await page.goto(`/pagamentos-mobile.html?mes=${mes}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', mes);
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}
const exato = (texto) => new RegExp(`^${texto.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`);
const linha = (page, nome) => page.locator('#mob-lista .mob-pag-linha', { has: page.locator('.mob-linha-nome', { hasText: exato(nome) }) });
const marca = (page, nome) => linha(page, nome).locator('.mob-pag-marca input');
const selecionadas = (page) => page.locator('#mob-qtd-selecionadas');
const selecionado = (page) => page.locator('#mob-total-selecionado');

// ---------------------------------------------------------------------------------------------------------------

test('preparo (dados ficticios) e acesso pelo atalho Pagamentos da pagina principal', async ({ page }) => {
    await entrar(page, G);
    const categoria = (await rpc(page, 'categorias_de_despesa', {}))[0].id;
    const criar = (dados) => rpc(page, 'criar_despesa', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(), p_dados: { categoria_id: categoria, ...dados } });
    await criar({ nome: LUZ, valor: '287.30', data_vencimento: `${MES}-15`, competencia: `${MES}-01` });
    await criar({ nome: INTERNET, valor: '129.90', data_vencimento: `${MES}-18`, competencia: `${MES}-01` });
    await criar({ nome: JA_PAGA, valor: '50.00', data_vencimento: `${MES}-10`, competencia: `${MES}-01` });
    await criar({ nome: DIARISTA, valor: '200.00', data_vencimento: `${MES}-07`, recorrente: true, tipo_recorrencia: 'semanal_1_2' });
    const contaG = await contaDoBanco(page, CONTA_G);
    const [paga] = await doMes(page, MES, JA_PAGA);
    await rpc(page, 'pagar_despesa', { p_perfil_id: PERFIL_G, p_conta_id: paga.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaG.id, data_pagamento: HOJE, valor_pago: '50.00', valor_devido: '50.00' } });
    const cartao = (await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G })).find((c) => c.nome === MASTER).id;
    await rpc(page, 'criar_compra', { p_perfil_id: PERFIL_G, p_chave: crypto.randomUUID(), p_dados: { cartao_id: cartao,
        descricao: 'Pag compra G', valor: '312.40', total_parcelas: 1, data_compra: `${MES}-05`, mes_fatura: `${MES}-01`,
        categoria_id: categoria, observacoes: '' } });
    // As ocorrencias semanais nascem quando a competencia e aberta na Lista de Despesas (o gerador do desktop).
    await page.goto(`/despesas-mobile.html?mes=${MES}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', MES);
    expect((await doMes(page, MES, DIARISTA)).length).toBe(4);

    // Atalho Pagamentos habilitado na pagina principal, com a competencia aberta.
    await page.goto(`/inicio.html?mes=${MES}`);
    const atalho = page.locator('.mob-atalho[data-modulo="pagamentos"]');
    await expect(atalho).toHaveAttribute('href', `pagamentos-mobile.html?mes=${MES}`);
    await expect(atalho).not.toHaveAttribute('aria-disabled', 'true');
    await atalho.click();
    await expect(page).toHaveURL(new RegExp(`pagamentos-mobile\\.html\\?mes=${MES}`));
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('.mob-titulo')).toHaveText('Pagamentos');
    await expect(page.locator('#mob-perfil')).toHaveText('Perfil G (ficticio)');
    await expect(page.locator('#mob-competencia')).toContainText('2034');
    await expect(page.locator('.mob-barra-item')).toHaveText(['Início', 'Lançar', 'Resumo', 'Mais']);
    await expect(page.locator('#mob-voltar')).toHaveAttribute('href', /inicio\.html\?mes=2034-03/);
});

test('consulta: so as pendentes da competencia, nos grupos do desktop, com o total pendente do banco', async ({ page }) => {
    await entrar(page, G);
    await abrirPagamentos(page);
    for (const nome of [LUZ, INTERNET, DIARISTA, FATURA_MASTER]) await expect(linha(page, nome), nome).toHaveCount(1);
    await expect(linha(page, JA_PAGA)).toHaveCount(0);  // paga: fora
    await expect(linha(page, LUZ).locator('.mob-linha-data')).toHaveText('Venc. 15/03');
    await expect(linha(page, LUZ).locator('.mob-linha-valor')).toHaveText(reais(287.3));
    await expect(linha(page, DIARISTA).locator('.mob-linha-data')).toContainText('4 ocorrência(s) pendente(s)');
    await expect(linha(page, DIARISTA).locator('.mob-linha-valor')).toHaveText(reais(800));
    await expect(linha(page, FATURA_MASTER).locator('.mob-linha-data')).toContainText(`executado ${reais(312.4)}`);
    // Grupos do desktop (abertos), sem coluna de categoria nem de situacao.
    await expect(page.locator('#mob-lista .mob-grupo-nome')).toContainText(['FATURAS DE CARTÃO DE CRÉDITO', 'DESPESAS RECORRENTES', 'DESPESAS AVULSAS']);
    await expect(page.locator('#mob-lista .mob-grupo-cabecalho[aria-expanded="false"]')).toHaveCount(0);
    // Total pendente: a soma das linhas pendentes de contas_do_mes (o mesmo valor mostrado na Lista de Despesas).
    const total = (await contasDoMes(page, MES)).filter(pendente).reduce((s, c) => s + centavos(c.valor), 0);
    await expect(page.locator('#mob-total-pendente')).toHaveText(reais(total / 100));
    await expect(selecionadas(page)).toHaveText('0');
    await expect(selecionado(page)).toHaveText(reais(0));
    await expect(page.locator('#mob-pagar')).toBeDisabled();
    // Recolher e expandir um grupo.
    const cabecalho = page.locator('.mob-grupo[data-grupo="DESPESAS_AVULSAS"] .mob-grupo-cabecalho');
    await cabecalho.click();
    await expect(linha(page, LUZ)).toBeHidden();
    await cabecalho.click();
    await expect(linha(page, LUZ)).toBeVisible();
});

test('consultar nao grava nada: competencia nunca aberta continua sem as ocorrencias recorrentes', async ({ page }) => {
    await entrar(page, G);
    const antes = (await contasDoMes(page, MES_SEM_GERACAO)).map((c) => c.id).sort();
    const antesMarco = (await contasDoMes(page, MES)).map((c) => `${c.id}:${c.status_pagamento}`).sort();
    await abrirPagamentos(page, MES_SEM_GERACAO);
    await expect(linha(page, DIARISTA)).toHaveCount(0);
    await abrirPagamentos(page, MES);
    expect((await contasDoMes(page, MES_SEM_GERACAO)).map((c) => c.id).sort()).toEqual(antes);
    expect((await doMes(page, MES_SEM_GERACAO, DIARISTA)).length).toBe(0);
    expect((await contasDoMes(page, MES)).map((c) => `${c.id}:${c.status_pagamento}`).sort()).toEqual(antesMarco);
});

test('selecao: uma obrigacao por vez, o agrupador semanal leva todas as pendentes, limpar e trocar a competencia', async ({ page }) => {
    await entrar(page, G);
    await abrirPagamentos(page);
    await marca(page, LUZ).check();
    await expect(selecionadas(page)).toHaveText('1');
    await expect(selecionado(page)).toHaveText(reais(287.3));
    await expect(page.locator('#mob-selecao-valor')).toHaveText(reais(287.3));
    await expect(page.locator('#mob-pagar')).toHaveText('Pagar selecionada');
    // Outra obrigacao com uma ja marcada: nao seleciona e explica (o lote do banco e so da mesma recorrencia).
    await marca(page, INTERNET).click();
    await expect(marca(page, INTERNET)).not.toBeChecked();
    await expect(aviso(page)).toContainText('O pagamento em lote reúne só as ocorrências de uma mesma recorrência semanal');
    await expect(selecionadas(page)).toHaveText('1');
    // Os detalhes abrem sem mudar a selecao.
    await linha(page, LUZ).locator('.mob-pag-abrir').click();
    await expect(folha(page)).toContainText('Vencimento');
    await expect(folha(page)).toContainText('15/03/2034');
    await page.click('#mob-folha-fechar');
    await expect(marca(page, LUZ)).toBeChecked();
    // Desmarcar; o agrupador semanal: as 4 pendentes de uma vez.
    await marca(page, LUZ).uncheck();
    await expect(selecionadas(page)).toHaveText('0');
    await marca(page, DIARISTA).check();
    await expect(selecionadas(page)).toHaveText('4');
    await expect(selecionado(page)).toHaveText(reais(800));
    await expect(page.locator('#mob-pagar')).toHaveText('Pagar selecionadas (4)');
    await page.click('#mob-limpar');
    await expect(selecionadas(page)).toHaveText('0');
    await expect(marca(page, DIARISTA)).not.toBeChecked();
    // Trocar a competencia limpa a selecao.
    await marca(page, LUZ).check();
    await page.click('#mob-mes-seguinte');
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', '2034-04');
    await page.click('#mob-mes-anterior');
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', MES);
    await expect(selecionadas(page)).toHaveText('0');
    await expect(marca(page, LUZ)).not.toBeChecked();
});

test('somente leitura: consulta e detalhes, sem selecao nem pagamento; o banco recusa', async ({ page }) => {
    await entrar(page, H);
    await abrirPagamentos(page);
    await expect(linha(page, LUZ)).toHaveCount(1);
    await expect(page.locator('#mob-lista .mob-pag-marca')).toHaveCount(0);
    await expect(page.locator('#mob-selecao')).toBeHidden();
    await expect(page.locator('#mob-somente-leitura')).toBeVisible();
    await linha(page, LUZ).locator('.mob-pag-abrir').click();
    await expect(folha(page)).toContainText('Acesso somente de leitura a este perfil.');
    await expect(botaoFolha(page, /^Pagar/)).toHaveCount(0);
    await page.click('#mob-folha-fechar');
    await linha(page, DIARISTA).locator('.mob-pag-abrir').click();
    await expect(botaoFolha(page, 'Pagar pendentes')).toHaveCount(0);
    const [luz] = await doMes(page, MES, LUZ);
    const conta = (await rpc(page, 'contas_bancarias_tela', { p_perfil_id: PERFIL_G, p_status: 'ATIVO' })).find((c) => c.nome === CONTA_G);
    const tentativa = await chamarRpc(page, 'pagar_despesa', { p_perfil_id: PERFIL_G, p_conta_id: luz.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: conta.id, data_pagamento: HOJE, valor_pago: '287.30', valor_devido: '287.30' } });
    expect(tentativa.status).not.toBe(200);
    expect((await doMes(page, MES, LUZ))[0].status_pagamento).not.toBe('Pago');
});

test('pagamento individual com valor diferente: classificacao e justificativa, um movimento, saldo e Ver em Contas', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const saldo = centavos(contaG.saldo_atual);
    await abrirPagamentos(page);
    await marca(page, INTERNET).check();
    await page.click('#mob-pagar');
    await expect(page.locator('#mob-folha-titulo')).toHaveText(`Pagar: ${INTERNET}`);
    await folha(page).locator('select').first().selectOption({ label: ROTULO_CONTA_G });
    await folha(page).locator('input[type="radio"][value="parcial"]').check();
    await folha(page).locator('input[type="number"]').fill('135.00');
    // Sem classificar: recusado na tela, nada gravado.
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Classifique a diferença e escreva a justificativa.');
    await folha(page).locator('.mob-campo', { hasText: 'Classificação da diferença' }).locator('select').selectOption('JUROS');
    await folha(page).locator('textarea').fill('Multa por atraso (ficticio)');
    await botaoFolha(page, 'Confirmar pagamento').dblclick();  // toque duplo: um pagamento so
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Pagamento registrado');
    await expect(folha(page)).toContainText(`Despesa paga: ${reais(135)} debitados de ${CONTA_G}`);
    const [internet] = await doMes(page, MES, INTERNET);
    expect(internet.status_pagamento).toBe('Pago');
    const pagamentos = (await rpc(page, 'dados_pagamento_despesa', { p_perfil_id: PERFIL_G, p_conta_id: internet.id })).pagamentos;
    expect(pagamentos.map((p) => [centavos(p.valor_pago), centavos(p.valor_devido), p.tipo_ajuste])).toEqual([[13500, 12990, 'JUROS']]);
    expect(centavos((await contaDoBanco(page, CONTA_G)).saldo_atual)).toBe(saldo - 13500);
    expect(await consistente(page, contaG.id)).toBe(true);
    // Lista e totais atualizados atras do painel; selecao limpa.
    await expect(linha(page, INTERNET)).toHaveCount(0);
    await expect(selecionadas(page)).toHaveText('0');
    // Ver em Contas: a conta debitada no mes do pagamento, com o movimento (nenhum movimento a mais).
    const ver = page.locator('#mob-ver-contas');
    await expect(ver).toHaveAttribute('href', `contas-mobile.html?mes=${HOJE.slice(0, 7)}&conta=${contaG.id}`);
    await ver.click();
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('#mob-lista .mob-movimento', { has: page.locator('.mob-linha-valor', { hasText: reais(135) }) })).not.toHaveCount(0);
});

test('lote da recorrencia semanal: confirmacao com quantidade, total, conta e data; as 4 pagas numa transacao', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const saldo = centavos(contaG.saldo_atual);
    await abrirPagamentos(page);
    await marca(page, DIARISTA).check();
    await page.click('#mob-pagar');
    await expect(page.locator('#mob-folha-titulo')).toHaveText(`Pagar ocorrências: ${DIARISTA}`);
    const painel = folha(page).locator('.mob-detalhes');
    await expect(painel).toContainText('Ocorrências pendentes4');
    await expect(painel).toContainText(`Valor total${reais(800)}`);
    await expect(painel).toContainText(`Data do pagamento${HOJE.slice(8, 10)}/${HOJE.slice(5, 7)}/${HOJE.slice(0, 4)}`);
    // Conta obrigatoria.
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Selecione a conta bancária de débito.');
    await folha(page).locator('select').selectOption({ label: ROTULO_CONTA_G });
    await botaoFolha(page, 'Confirmar pagamento').dblclick();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Pagamento registrado');
    await expect(folha(page)).toContainText('Pagamento em lote concluído');
    await expect(folha(page)).toContainText('4 ocorrência(s) paga(s)');
    const ocorrencias = await doMes(page, MES, DIARISTA);
    expect(ocorrencias.map((o) => o.status_pagamento)).toEqual(['Pago', 'Pago', 'Pago', 'Pago']);
    for (const o of ocorrencias) {
        expect((await rpc(page, 'dados_pagamento_despesa', { p_perfil_id: PERFIL_G, p_conta_id: o.id })).pagamentos.length).toBe(1);
    }
    expect(centavos((await contaDoBanco(page, CONTA_G)).saldo_atual)).toBe(saldo - 80000);
    expect(await consistente(page, contaG.id)).toBe(true);
    await expect(page.locator('#mob-ver-contas')).toHaveAttribute('href', `contas-mobile.html?mes=${HOJE.slice(0, 7)}&conta=${contaG.id}`);
    await page.click('#mob-folha-fechar');
    await expect(linha(page, DIARISTA)).toHaveCount(0);
});

test('fatura do cartao: paga pelo executado, sem duplicar; sai das pendentes e fica paga em Cartoes', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    const saldo = centavos(contaG.saldo_atual);
    await abrirPagamentos(page);
    await marca(page, FATURA_MASTER).check();
    await expect(selecionado(page)).toHaveText(reais(312.4));  // o executado consolidado, valor sugerido
    await page.click('#mob-pagar');
    await expect(page.locator('#mob-folha-titulo')).toHaveText(`Pagar fatura: ${FATURA_MASTER}`);
    await folha(page).locator('select').first().selectOption({ label: ROTULO_CONTA_G });
    await botaoFolha(page, 'Confirmar pagamento').dblclick();
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Pagamento registrado');
    await expect(folha(page)).toContainText(`Fatura paga: ${reais(312.4)} debitados de ${CONTA_G}`);
    const [fatura] = await doMes(page, MES, FATURA_MASTER);
    expect(fatura.status_pagamento).toBe('Pago');
    const dados = await rpc(page, 'dados_pagamento_fatura', { p_perfil_id: PERFIL_G, p_fatura_id: fatura.id });
    expect(dados.fatura.paga).toBe(true);
    expect(dados.pagamentos.length).toBe(1);
    // A compra nunca vira conta a pagar.
    expect((await contasDoMes(page, MES)).filter((c) => c.nome === 'Pag compra G')).toEqual([]);
    expect(centavos((await contaDoBanco(page, CONTA_G)).saldo_atual)).toBe(saldo - 31240);
    expect(await consistente(page, contaG.id)).toBe(true);
    await page.click('#mob-folha-fechar');
    await expect(linha(page, FATURA_MASTER)).toHaveCount(0);
});

test('estado mudou entre a consulta e a confirmacao: recusa clara, nenhum pagamento a mais', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    await abrirPagamentos(page);
    await marca(page, LUZ).check();
    await page.click('#mob-pagar');
    await folha(page).locator('select').first().selectOption({ label: ROTULO_CONTA_G });
    // Outro aparelho paga a Luz com o painel aberto.
    const [luz] = await doMes(page, MES, LUZ);
    await rpc(page, 'pagar_despesa', { p_perfil_id: PERFIL_G, p_conta_id: luz.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaG.id, data_pagamento: HOJE, valor_pago: '287.30', valor_devido: '287.30' } });
    const saldo = centavos((await contaDoBanco(page, CONTA_G)).saldo_atual);
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toHaveText('Esta despesa já está paga.');
    expect((await rpc(page, 'dados_pagamento_despesa', { p_perfil_id: PERFIL_G, p_conta_id: luz.id })).pagamentos.length).toBe(1);
    expect(centavos((await contaDoBanco(page, CONTA_G)).saldo_atual)).toBe(saldo);
    await page.click('#mob-folha-fechar');
    await abrirPagamentos(page);
    await expect(linha(page, LUZ)).toHaveCount(0);
});

test('lote com as pendentes mudando no meio: o banco recusa inteiro (tudo ou nada) e a lista e conferida de novo', async ({ page }) => {
    await entrar(page, G);
    const contaG = await contaDoBanco(page, CONTA_G);
    await abrirPagamentos(page, '2034-04');  // gerada pelo preparo (ate o mes seguinte): 4 tercas pendentes
    await expect(linha(page, DIARISTA).locator('.mob-linha-data')).toContainText('4 ocorrência(s) pendente(s)');
    await marca(page, DIARISTA).check();
    await page.click('#mob-pagar');
    await folha(page).locator('select').selectOption({ label: ROTULO_CONTA_G });
    // Outro aparelho paga uma das ocorrencias com o painel aberto.
    const [primeira] = await doMes(page, '2034-04', DIARISTA);
    await rpc(page, 'pagar_despesa', { p_perfil_id: PERFIL_G, p_conta_id: primeira.id, p_chave: crypto.randomUUID(),
        p_dados: { conta_bancaria_id: contaG.id, data_pagamento: HOJE, valor_pago: '200.00', valor_devido: '200.00' } });
    const saldo = centavos((await contaDoBanco(page, CONTA_G)).saldo_atual);
    await botaoFolha(page, 'Confirmar pagamento').click();
    await expect(folha(page).locator('.mob-mensagem')).toContainText('Nenhuma ocorrência foi paga.');
    await expect(folha(page).locator('.mob-mensagem')).toContainText('Feche e confira a lista atualizada antes de pagar de novo.');
    await expect(botaoFolha(page, 'Confirmar pagamento')).toBeDisabled();
    expect((await doMes(page, '2034-04', DIARISTA)).filter((o) => o.status_pagamento === 'Pago').length).toBe(1);
    expect(centavos((await contaDoBanco(page, CONTA_G)).saldo_atual)).toBe(saldo);
    expect(await consistente(page, contaG.id)).toBe(true);
    // Fechar rele a lista: agora 3 pendentes.
    await botaoFolha(page, 'Cancelar').click();
    await expect(linha(page, DIARISTA).locator('.mob-linha-data')).toContainText('3 ocorrência(s) pendente(s)');
});

for (const largura of [320, 375, 390, 430]) {
    test(`responsividade ${largura}px: sem rolagem horizontal, linhas e barra da selecao inteiras`, async ({ page }) => {
        await page.setViewportSize({ width: largura, height: 800 });
        await entrar(page, G);
        await abrirPagamentos(page, '2034-04');  // aberta pelo preparo (gerada ate o mes seguinte): ocorrencias pendentes
        const marcas = page.locator('#mob-lista .mob-pag-marca input:not([disabled])');
        if (await marcas.count()) await marcas.first().check();
        const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
        expect(larguras[0]).toBeLessThanOrEqual(larguras[1]);
        for (const seletor of ['#mob-resumo', '#mob-lista', '#mob-limpar', '#mob-pagar', '#mob-selecao-valor']) {
            const caixa = await page.locator(seletor).boundingBox();
            if (!caixa) continue;
            expect(caixa.x, seletor).toBeGreaterThanOrEqual(0);
            expect(caixa.x + caixa.width, seletor).toBeLessThanOrEqual(largura);
        }
        // O valor selecionado nao fica sob os botoes da barra.
        const total = await page.locator('#mob-selecao-valor').boundingBox();
        const limpar = await page.locator('#mob-limpar').boundingBox();
        const lado = total.x + total.width <= limpar.x;
        const acima = total.y + total.height <= limpar.y;
        expect(lado || acima, 'total selecionado sem sobrepor os botoes').toBe(true);
        // Rotulos dos botoes inteiros (sem quebra cortada).
        for (const id of ['#mob-limpar', '#mob-pagar']) {
            const medida = await page.locator(id).evaluate((b) => [b.scrollWidth, b.clientWidth, b.scrollHeight, b.clientHeight]);
            expect(medida[0], `${id}: largura`).toBeLessThanOrEqual(medida[1]);
            expect(medida[2], `${id}: altura`).toBeLessThanOrEqual(medida[3]);
        }
        const linhas = page.locator('#mob-lista .mob-pag-linha');
        for (let i = 0; i < Math.min(await linhas.count(), 6); i += 1) {
            const valor = await linhas.nth(i).locator('.mob-linha-valor').boundingBox();
            expect(valor.x + valor.width).toBeLessThanOrEqual(largura);
        }
    });
}
