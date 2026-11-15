// FIN-MVP-MOBILE-09 — Recorrencias mobile (recorrencias-mobile.html). Usuario G, titular do "Perfil G (ficticio)"; leitor H.
// Recorrencias criadas pela tela a partir de 01/2035 (periodo sem outro dado; nada muda nas competencias dos outros testes):
// mensal com boleto, a cada 2 semanas (quarta) e assinatura mensal no cartao "Nubank Master G". Edicao, inativacao com a
// previa da P22 (as ocorrencias geradas de 02/2035 deixam de ser exigiveis) e reativacao com a restauracao delas. Cada
// efeito e conferido pelas funcoes de leitura do desktop (recorrencias_do_perfil, contas_do_mes). Dados FICTICIOS; grava so
// no banco descartavel.
import { expect, test } from '@playwright/test';

import { chamarRpc } from './despesas.mjs';

const G = { email: process.env.CF_EMAIL_G || 'usuario.g@teste.local', senha: process.env.CF_SENHA_G };
const H = { email: process.env.CF_EMAIL_H || 'usuario.h@teste.local', senha: process.env.CF_SENHA_H };
const PERFIL_G = 160;
const MASTER = 'Nubank Master G (ficticio)';
const ALUGUEL = 'Rec Aluguel G';
const FAXINA = 'Rec Faxina G';
const MUSICA = 'Rec Musica G';
const GERADO = '2035-02';  // competencia aberta na Lista (gera as ocorrencias de 02/2035)

const HOJE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo' }).format(new Date());
const [ANO, MES] = HOJE.split('-').map(Number);
const SEGUINTE = MES === 12 ? `01/${ANO + 1}` : `${String(MES + 1).padStart(2, '0')}/${ANO}`;  // efeito padrao da P22

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

const folha = (page) => page.locator('#mob-folha');
const aviso = (page) => page.locator('#mob-aviso');
const campo = (page, rotulo) => folha(page).locator('label.mob-campo', { hasText: new RegExp(`^${rotulo}`) }).locator('input, select, textarea');
const erroDo = (page, rotulo) => folha(page).locator('label.mob-campo', { hasText: new RegExp(`^${rotulo}`) }).locator('.mob-campo-erro');
const exato = (texto) => new RegExp(`^${texto.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`);
const linha = (page, nome) => page.locator('#mob-lista .mob-linha', { has: page.locator('.mob-linha-nome', { hasText: exato(nome) }) });
const recorrencia = async (page, nome) => (await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G })).find((r) => r.nome === nome);
const ocorrencias = async (page, mes, nome) => (await rpc(page, 'contas_do_mes', { p_perfil_id: PERFIL_G, p_mes: `${mes}-01` }))
    .filter((c) => c.nome.startsWith(`${nome} - `));
// Ocorrencias pendentes geradas ate agora (abrir uma competencia gera desde o inicio e o mes seguinte, como no desktop).
async function pendentesGeradas(page, nome) {
    let total = 0;
    for (const mes of ['2035-01', '2035-02', '2035-03', '2035-04']) total += (await ocorrencias(page, mes, nome)).length;
    return total;
}
const reais = (v) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }).replace(/\s/g, ' ');

async function abrirRecorrencias(page) {
    await page.goto('/recorrencias-mobile.html');
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
}

async function abrirDetalhes(page, nome) {
    await linha(page, nome).click();
    await expect(page.locator('#mob-folha-titulo')).toHaveText(nome);
}

async function salvar(page) {
    await page.click('#mob-rec-salvar');
    await expect(page.locator('#mob-folha-fundo')).toBeHidden();
}

test('atalho da pagina principal abre as Recorrencias; lista, resumo e "+" para quem gere o perfil', async ({ page }) => {
    await entrar(page, G);
    const atalho = page.locator('.mob-atalho[data-modulo="recorrencias"]');
    await expect(atalho).not.toHaveAttribute('aria-disabled', 'true');
    await atalho.click();
    await page.waitForURL('**/recorrencias-mobile.html**');
    await expect(page.locator('#mob-lista')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('h1.mob-titulo')).toHaveText('Recorrências');
    await expect(page.locator('#mob-nova')).toBeVisible();
    await expect(page.locator('#mob-somente-leitura')).toBeHidden();
    // O resumo conta as recorrencias do banco (as mesmas do desktop)
    const todas = await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G });
    await expect(page.locator('#mob-qtd-ativas')).toHaveText(`${todas.filter((r) => r.ativo).length} de ${todas.length}`);
    await expect(page.locator('#mob-situacao button[aria-pressed="true"]')).toHaveText('Ativas');
});

test('cadastro: campos obrigatorios junto ao campo; mensal com boleto gravada como no desktop', async ({ page }) => {
    await entrar(page, G);
    await abrirRecorrencias(page);
    await page.click('#mob-nova');
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Nova recorrência');
    await campo(page, 'Data inicial').fill('');
    await page.click('#mob-rec-salvar');
    await expect(erroDo(page, 'Nome')).toHaveText('Informe o nome.');
    await expect(erroDo(page, 'Valor')).toHaveText('Informe um valor maior que zero.');
    await expect(erroDo(page, 'Categoria')).toHaveText('Selecione a categoria.');
    await expect(erroDo(page, 'Data inicial')).toHaveText('Informe a data do primeiro vencimento.');
    expect(await recorrencia(page, ALUGUEL)).toBeUndefined();

    await campo(page, 'Nome').fill(ALUGUEL);
    await campo(page, 'Valor').fill('1.250,00');
    await campo(page, 'Categoria').selectOption({ index: 1 });
    await campo(page, 'Data inicial').fill('2035-01-10');
    await campo(page, 'Meio de pagamento').selectOption('boleto');
    await campo(page, 'Observações').fill('Contrato ficticio');
    await salvar(page);
    await expect(aviso(page)).toHaveText('Recorrência criada. As contas são geradas automaticamente ao abrir a competência em Despesas.');
    const r = await recorrencia(page, ALUGUEL);
    expect([r.tipo_recorrencia, Number(r.valor), r.data_vencimento, r.meio_pagamento, r.descricao, r.ativo])
        .toEqual(['mensal', 1250, '2035-01-10', 'boleto', 'Contrato ficticio', true]);
    await expect(linha(page, ALUGUEL)).toContainText('Mensal, dia 10');
    await expect(linha(page, ALUGUEL)).toContainText('R$ 1.250,00');
});

test('cadastro a cada 2 semanas exige o dia da semana e grava semanal_2_D', async ({ page }) => {
    await entrar(page, G);
    await abrirRecorrencias(page);
    await page.click('#mob-nova');
    await campo(page, 'Nome').fill(FAXINA);
    await campo(page, 'Valor').fill('90');
    await campo(page, 'Categoria').selectOption({ index: 1 });
    await campo(page, 'Data inicial').fill('2035-01-10');
    await campo(page, 'Frequência').selectOption('quinzenal');
    await expect(campo(page, 'Dia da semana')).toBeVisible();
    await page.click('#mob-rec-salvar');
    await expect(erroDo(page, 'Dia da semana')).toHaveText('Selecione o dia da semana.');
    await campo(page, 'Dia da semana').selectOption('3');
    await campo(page, 'Meio de pagamento').selectOption('pix');
    await salvar(page);
    const r = await recorrencia(page, FAXINA);
    expect([r.tipo_recorrencia, Number(r.valor), r.meio_pagamento]).toEqual(['semanal_2_3', 90, 'pix']);
    await expect(linha(page, FAXINA)).toContainText('A cada 2 semanas (quarta-feira)');
});

test('assinatura no cartao: so mensal ou anual; gravada pela funcao do cartao e listada em Cartao de credito', async ({ page }) => {
    await entrar(page, G);
    await abrirRecorrencias(page);
    await page.click('#mob-nova');
    await campo(page, 'Nome').fill(MUSICA);
    await campo(page, 'Valor').fill('21,90');
    await campo(page, 'Categoria').selectOption({ index: 1 });
    await campo(page, 'Data inicial').fill('2035-01-08');
    await campo(page, 'Meio de pagamento').selectOption('cartao');
    await expect(campo(page, 'Frequência').locator('option[value="semanal"]')).toHaveAttribute('disabled', '');
    await expect(campo(page, 'Frequência').locator('option[value="quinzenal"]')).toHaveAttribute('disabled', '');
    await page.click('#mob-rec-salvar');
    await expect(erroDo(page, 'Cartão')).toHaveText('Selecione o cartão.');
    await campo(page, 'Cartão').selectOption({ label: MASTER });
    await expect(folha(page).locator('.mob-ajuda', { hasText: 'Categoria do cartão:' })).toBeVisible();
    await salvar(page);
    await expect(aviso(page)).toContainText('Recorrência no cartão criada.');
    await expect(aviso(page)).toContainText('As compras entram na fatura do cartão.');
    const cartoes = await rpc(page, 'cartoes_do_perfil', { p_perfil_id: PERFIL_G });
    const r = await recorrencia(page, MUSICA);
    expect([r.meio_pagamento, r.cartao_id, r.tipo_recorrencia, Number(r.valor)]).toEqual(['cartao', cartoes.find((c) => c.nome === MASTER).id, 'mensal', 21.9]);
    await expect(page.locator('#mob-lista .mob-grupo[data-grupo="cartao"]').locator('.mob-linha', { hasText: MUSICA })).toBeVisible();
});

test('edicao: valor e frequencia pelas funcoes do desktop; troca entre cartao e outro meio continua recusada', async ({ page }) => {
    await entrar(page, G);
    await abrirRecorrencias(page);
    await abrirDetalhes(page, ALUGUEL);
    await page.click('#mob-rec-editar');
    await expect(campo(page, 'Valor')).toHaveValue('1.250,00');
    await expect(campo(page, 'Meio de pagamento').locator('option[value="cartao"]')).toHaveAttribute('disabled', '');
    await campo(page, 'Valor').fill('1.300,00');
    await salvar(page);
    await expect(aviso(page)).toHaveText('Recorrência atualizada. Vale para as próximas contas; as já geradas não mudam. '
        + 'As contas são geradas automaticamente ao abrir a competência em Despesas.');
    let r = await recorrencia(page, ALUGUEL);
    expect([Number(r.valor), r.tipo_recorrencia, r.meio_pagamento]).toEqual([1300, 'mensal', 'boleto']);

    // No cartao: o meio fica travado; muda o valor pela editar_recorrencia_cartao
    await abrirDetalhes(page, MUSICA);
    await page.click('#mob-rec-editar');
    await expect(campo(page, 'Meio de pagamento')).toBeDisabled();
    await expect(folha(page)).toContainText('Para trocar o cartão por outro meio, inative esta recorrência e cadastre outra');
    await campo(page, 'Valor').fill('24,90');
    await salvar(page);
    await expect(aviso(page)).toContainText('Recorrência no cartão atualizada.');
    r = await recorrencia(page, MUSICA);
    expect([Number(r.valor), r.meio_pagamento]).toEqual([24.9, 'cartao']);
});

test('inativar: previa da P22 com as ocorrencias geradas; confirmar as tira das pendentes e preserva o cadastro', async ({ page }) => {
    await entrar(page, G);
    // Abrir 02/2035 na Lista gera as ocorrencias (como no desktop): duas quartas da Faxina em 02/2035
    await page.goto(`/despesas-mobile.html?mes=${GERADO}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', GERADO);
    expect((await ocorrencias(page, GERADO, FAXINA)).map((c) => [c.data_vencimento, c.status_pagamento]))
        .toEqual([['2035-02-07', 'Pendente'], ['2035-02-21', 'Pendente']]);
    const n = await pendentesGeradas(page, FAXINA);  // todas futuras e pendentes: deixam de ser exigiveis
    expect(n).toBeGreaterThanOrEqual(2);
    await abrirRecorrencias(page);
    await abrirDetalhes(page, FAXINA);
    await page.click('#mob-rec-inativar');
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Inativar recorrência');
    await expect(page.locator('#mob-rec-quantidade')).toHaveText(`${n} ocorrência(s) deixam de ser exigíveis: ${reais(90 * n)}`);
    await expect(folha(page)).toContainText(`a partir de ${SEGUINTE}`);
    await expect(folha(page).locator('.mob-rec-tabela-linha')).toHaveCount(n);
    // Cancelar nao grava
    await folha(page).locator('.mob-botao', { hasText: 'Cancelar' }).click();
    expect((await recorrencia(page, FAXINA)).ativo).toBe(true);
    await abrirDetalhes(page, FAXINA);
    await page.click('#mob-rec-inativar');
    await expect(page.locator('#mob-rec-quantidade')).toContainText(`${n} ocorrência(s)`);
    await page.click('#mob-rec-confirmar');
    await expect(page.locator('#mob-folha-fundo')).toBeHidden();
    await expect(aviso(page)).toHaveText(`Recorrência inativada a partir de ${SEGUINTE}: ${n} ocorrência(s) deixaram de ser exigíveis.`);
    expect((await recorrencia(page, FAXINA)).ativo).toBe(false);
    expect(await pendentesGeradas(page, FAXINA)).toBe(0);  // fora das pendentes (contas_do_mes)
    await expect(linha(page, FAXINA)).toHaveCount(0);  // a lista abre nas Ativas
    await page.click('#mob-situacao button[data-situacao="inativas"]');
    await expect(linha(page, FAXINA)).toContainText('Inativa');
});

test('reativar: previa da retomada com a restauracao opcional das canceladas pela inativacao', async ({ page }) => {
    await entrar(page, G);
    await abrirRecorrencias(page);
    await page.click('#mob-situacao button[data-situacao="inativas"]');
    await abrirDetalhes(page, FAXINA);
    await expect(page.locator('#mob-rec-editar')).toBeVisible();
    await expect(page.locator('#mob-rec-cancelar-futuras')).toBeVisible();
    await page.click('#mob-rec-reativar');
    await expect(page.locator('#mob-folha-titulo')).toHaveText('Reativar recorrência');
    await expect(page.locator('#mob-rec-restaurar')).toBeVisible();
    await expect(folha(page)).toContainText(/Restaurar as \d+ ocorrência\(s\) canceladas pela inativação/);
    const n = Number((await folha(page).locator('.mob-opcao').innerText()).match(/Restaurar as (\d+)/)[1]);
    expect(n).toBeGreaterThanOrEqual(2);
    await page.check('#mob-rec-restaurar');
    await page.click('#mob-rec-confirmar');
    await expect(page.locator('#mob-folha-fundo')).toBeHidden();
    await expect(aviso(page)).toContainText('Recorrência reativada');
    await expect(aviso(page)).toContainText(`${n} ocorrência(s) restaurada(s).`);
    await expect(aviso(page)).toContainText('As contas são geradas automaticamente ao abrir a competência em Despesas.');
    expect((await recorrencia(page, FAXINA)).ativo).toBe(true);
    // A restauracao tira a marca da inativacao (retomar_recorrencia): as ocorrencias voltam ao abrir a competencia em Despesas.
    await page.goto(`/despesas-mobile.html?mes=${GERADO}`);
    await expect(page.locator('#mob-lista')).toHaveAttribute('data-competencia-carregada', GERADO);
    expect((await ocorrencias(page, GERADO, FAXINA)).map((c) => [c.data_vencimento, c.status_pagamento]))
        .toEqual([['2035-02-07', 'Pendente'], ['2035-02-21', 'Pendente']]);
});

test('somente leitura: consulta e detalhes, sem "+" nem acoes; o banco recusa a gravacao', async ({ page }) => {
    await entrar(page, H);
    await abrirRecorrencias(page);
    await expect(page.locator('#mob-nova')).toBeHidden();
    await expect(page.locator('#mob-somente-leitura')).toBeVisible();
    await abrirDetalhes(page, ALUGUEL);
    await expect(folha(page)).toContainText('Acesso somente de leitura a este perfil.');
    await expect(page.locator('#mob-rec-editar, #mob-rec-inativar, #mob-rec-reativar')).toHaveCount(0);
    const r = await recorrencia(page, ALUGUEL);
    const recusa = await chamarRpc(page, 'inativar_recorrencia', { p_perfil_id: PERFIL_G, p_item_id: r.id, p_versao: r.versao });
    expect(recusa.status).not.toBe(200);
    expect((await recorrencia(page, ALUGUEL)).ativo).toBe(true);
});

test('busca e filtros: nome, categoria ou cartao; Todas mostra ativas e inativas', async ({ page }) => {
    await entrar(page, G);
    await abrirRecorrencias(page);
    await page.fill('#mob-busca', 'rec musica');
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(1);
    await expect(linha(page, MUSICA)).toBeVisible();
    await page.fill('#mob-busca', 'nubank master');
    await expect(linha(page, MUSICA)).toBeVisible();
    await page.fill('#mob-busca', 'nada assim');
    await expect(page.locator('#mob-lista .mob-vazio')).toHaveText('Nenhuma recorrência com estes filtros.');
    await page.fill('#mob-busca', '');
    await page.click('#mob-situacao button[data-situacao="todas"]');
    const todas = await rpc(page, 'recorrencias_do_perfil', { p_perfil_id: PERFIL_G });
    await expect(page.locator('#mob-lista .mob-linha')).toHaveCount(todas.length);
});

for (const largura of [320, 375, 430]) {
    test(`responsividade ${largura} px: sem rolagem lateral; detalhes e formulario cabem na tela`, async ({ page }) => {
        await page.setViewportSize({ width: largura, height: 800 });
        await entrar(page, G);
        await abrirRecorrencias(page);
        const largo = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(await largo()).toBeLessThanOrEqual(0);
        await abrirDetalhes(page, ALUGUEL);
        for (const id of ['#mob-rec-editar', '#mob-rec-inativar']) {
            const caixa = await page.locator(id).boundingBox();
            expect(caixa.x + caixa.width).toBeLessThanOrEqual(largura);
        }
        await page.click('#mob-rec-editar');
        await expect(page.locator('#mob-rec-salvar')).toBeVisible();
        expect(await largo()).toBeLessThanOrEqual(0);
    });
}
