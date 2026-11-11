// FIN-CARTAO-AGRUPAMENTO-CATEGORIAS-01 — detalhe da fatura na tela original de Despesas agrupa as compras pela
// Categoria do Cartao gravada (compras_da_fatura) e pelo resumo do cartao (fatura_por_categoria), como o Flask.
// Perfil B, cartao criado aqui, em 02/2038; dados FICTICIOS: "Moradia" -> "Mercado B" (limite R$ 300 neste cartao),
// "Saude" sem Categoria do Cartao. Grava so no banco descartavel; o cartao e inativado no fim.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, normal, perfilAtivoId } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Agrupamento (E2E)';
const MERCADO_B = 340;

test.use({ viewport: { width: 1366, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
        if (msg.type() === 'warning' && /Ponte CSP/.test(msg.text())) problemas.push(msg.text());
    });
    page.on('pageerror', (erro) => problemas.push(`pageerror: ${erro.message}`));
    testInfo.problemas = problemas;
});

test.afterEach(async ({}, testInfo) => {
    expect(testInfo.problemas, 'CSP/erros de JS').toEqual([]);
});

// FIN-FATURA-AJUSTES-02 (P16): quatro colunas alinhadas com o cabecalho, a direita, sem corte, em uma largura. Devolve o espaco flexivel.
async function conferirColunas(page, categorias, largura) {
    await page.setViewportSize({ width: largura, height: 900 });
    const cabecalho = categorias.locator('.categoria-colunas span');
    await expect(cabecalho).toHaveText(['Categoria', 'Previsto', 'Saldo', 'Executado']);
    const linha = categorias.locator('.categoria-linha').first();
    const celulas = ['.categoria-nome', '.categoria-valor', '.categoria-saldo', '.categoria-indicador'].map((c) => linha.locator(c));
    const caixas = await Promise.all(celulas.map((c) => c.boundingBox()));
    const titulos = await Promise.all((await cabecalho.all()).map((c) => c.boundingBox()));
    caixas.forEach((caixa, i) => {
        expect(Math.abs(caixa.x - titulos[i].x), `coluna ${i}`).toBeLessThanOrEqual(1);
        expect(Math.abs(caixa.width - titulos[i].width), `coluna ${i}`).toBeLessThanOrEqual(1);
        if (i) expect(caixa.x, `ordem ${i}`).toBeGreaterThanOrEqual(caixas[i - 1].x + caixas[i - 1].width);
    });
    for (const celula of celulas.slice(1)) {
        expect(await celula.evaluate((e) => getComputedStyle(e).textAlign)).toBe('right');
        expect(await celula.evaluate((e) => e.scrollWidth <= e.clientWidth), 'valor cortado').toBe(true);
    }
    expect(await celulas[0].evaluate((e) => getComputedStyle(e).textAlign)).toMatch(/left|start/);
    const altura = (await linha.boundingBox()).height;
    expect(altura).toBeGreaterThanOrEqual(30);
    expect(altura).toBeLessThanOrEqual(32);
    const blocoEl = categorias;
    expect(await blocoEl.evaluate((e) => e.scrollWidth <= e.clientWidth), 'sem estouro horizontal').toBe(true);
    return caixas[3].x - (caixas[2].x + caixas[2].width);
}

async function entrar(page, conta) {
    await page.goto('/index.html');
    await page.fill('#email', conta.email);
    await page.fill('#senha', conta.senha);
    await page.click('#login-enviar');
    await page.waitForURL('**/contas.html');
    await expect(page.locator('#perfil-financeiro-switcher')).toHaveAttribute('data-perfil-ativo-id', /^\d+$/);
}

async function idDaCategoria(page, nome) {
    const r = await chamarRpc(page, 'categorias_de_despesa', {});
    return r.corpo.find((c) => c.nome === nome).id;
}

const bloco = (detalhe, titulo) => detalhe.locator('.fatura-bloco', { has: detalhe.page().locator('.bloco-titulo', { hasText: titulo }) });

test('detalhe da fatura: parcelada, Categoria do Cartao com limite e Outros, sem perder valor', async ({ page }) => {
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const [moradia, saude] = [await idDaCategoria(page, 'Moradia'), await idDaCategoria(page, 'Saude')];
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 } });
    expect(criado.status).toBe(200);
    const cartao = criado.corpo.cartao_id;
    expect((await chamarRpc(page, 'vincular_limite_cartao', { p_perfil_id: perfil, p_cartao_id: cartao,
        p_dados: { categoria_cartao_id: MERCADO_B, limite_mensal: '300.00' } })).status).toBe(200);
    for (const [descricao, valor, categoria, parcelas] of [['Feira E2E', '120.00', moradia, 1], ['Padaria E2E', '30.00', moradia, 1],
        ['Remedio E2E', '45.00', saude, 1], ['Geladeira E2E', '300.00', moradia, 3]]) {
        const r = await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
            cartao_id: cartao, descricao, valor, total_parcelas: parcelas, data_compra: '2038-02-01', mes_fatura: '2038-02-01',
            categoria_id: categoria } });
        expect(r.status, descricao).toBe(200);
    }
    // A Categoria do Cartao vem da compra gravada (resolvida na gravacao), nao de nova classificacao.
    const lidas = await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2038-02-01' });
    expect(lidas.corpo.map((c) => [c.descricao.replace(/ \(\d+\/\d+\)$/, ''), c.categoria_cartao_id]).sort()).toEqual([
        ['Feira E2E', MERCADO_B], ['Geladeira E2E', MERCADO_B], ['Padaria E2E', MERCADO_B], ['Remedio E2E', null]]);

    await abrirDespesas(page, '2038-02');
    const fatura = despesa(page, `Fatura ${CARTAO} - 02/2038`);
    await fatura.locator('[data-on-click^="toggleDetalhesFatura"]').click();
    const detalhe = fatura.locator('.fatura-detalhes');
    await expect(detalhe.locator('.fatura-container')).toBeVisible();

    // Parcelada (mesmo classificada): so em Compras Parceladas.
    await expect(bloco(detalhe, 'Compras Parceladas').locator('.bloco-subtotal')).toHaveText('R$ 100,00');
    await expect(bloco(detalhe, 'Compras Parceladas')).toContainText('Geladeira E2E');
    await expect(bloco(detalhe, 'Compras Parceladas')).toContainText('01/03');
    await expect(bloco(detalhe, 'Despesas Fixas').locator('.bloco-subtotal')).toHaveText('R$ 0,00');
    // Categoria do Cartao com limite: previsto (limite) e executado (as duas compras a vista).
    const categorias = bloco(detalhe, 'Despesas por Categoria');
    await expect(categorias.locator('.categoria-nome')).toHaveText(['Mercado B']);
    expect(normal(await categorias.locator('.categoria-valor').textContent())).toMatch(/^R\$ 300,00/);
    await expect(categorias.locator('.categoria-indicador')).toHaveText('R$ 150,00');
    // FIN-FATURA-AJUSTES-02 (P16): saldo positivo na cor padrao
    const saldoPositivo = categorias.locator('.categoria-saldo');
    await expect(saldoPositivo).toHaveText('R$ 150,00');
    await expect(saldoPositivo).not.toHaveClass(/negativo/);
    const cor = (l) => l.evaluate((e) => getComputedStyle(e).color);
    expect(await cor(saldoPositivo)).toBe(await cor(categorias.locator('.categoria-valor')));
    await categorias.locator('.categoria-linha').click();
    await expect(categorias.locator('.categoria-detalhes .linha-titulo')).toHaveText(['Feira E2E', 'Padaria E2E']);
    // Sem Categoria do Cartao: Outros.
    await expect(bloco(detalhe, 'Outros Lançamentos').locator('.bloco-subtotal')).toHaveText('R$ 45,00');
    await expect(bloco(detalhe, 'Outros Lançamentos').locator('.linha-titulo')).toHaveText(['Remedio E2E']);
    // Executado = soma das compras do mes (100 + 120 + 30 + 45); previsto pela regra do Flask (limite no lugar do gasto).
    const totais = await detalhe.locator('.fatura-totais .total-valor').allTextContents();
    expect(totais.map(normal)).toEqual(['R$ 445,00', 'R$ 295,00']);

    // Limpeza do cenario: inativa o cartao (compras e faturas continuam registradas).
    const cartoes = await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil });
    const registro = cartoes.corpo.find((c) => c.id === cartao);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao })).status).toBe(200);
});

// MVP-FIN-AJUSTES-01 (P01 a P04): valor da recorrencia antes da cobranca, cabecalho, excedente, previsto igual ao da lista
// e linhas compactas. Perfil B, cartao criado aqui, em 03/2038; dados FICTICIOS.
test('fatura: recorrencia prevista, excedente da categoria, previsto igual ao da lista e linhas compactas', async ({ page }) => {
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const moradia = await idDaCategoria(page, 'Moradia');
    const nome = 'Cartao Ajustes (E2E)';
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome, dia_fechamento: 3, dia_vencimento: 12 } });
    const cartao = criado.corpo.cartao_id;
    expect((await chamarRpc(page, 'vincular_limite_cartao', { p_perfil_id: perfil, p_cartao_id: cartao,
        p_dados: { categoria_cartao_id: MERCADO_B, limite_mensal: '300.00' } })).status).toBe(200);
    const recorrencia = await chamarRpc(page, 'criar_recorrencia_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        nome: 'Streaming E2E', valor: '60.00', categoria_id: moradia, data_vencimento: '2038-03-05', cartao_id: cartao,
        tipo_recorrencia: 'mensal', descricao: '' } });
    expect(recorrencia.status).toBe(200);
    expect((await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: cartao, descricao: 'Mercado do mes com um nome bem longo para nao quebrar a linha da fatura E2E', valor: '350.00',
        total_parcelas: 1, data_compra: '2038-03-02', mes_fatura: '2038-03-01', categoria_id: moradia } })).status).toBe(200);

    await abrirDespesas(page, '2038-03');
    const fatura = despesa(page, `Fatura ${nome} - 03/2038`);
    await fatura.locator('[data-on-click^="toggleDetalhesFatura"]').click();
    const detalhe = fatura.locator('.fatura-detalhes');
    await expect(detalhe.locator('.fatura-container')).toBeVisible();

    // P01: a linha mostra o valor da recorrencia (FIN-CARTOES-EXECUTADO-01: ele ja entra no executado consolidado).
    const fixas = bloco(detalhe, 'Despesas Fixas');
    await expect(fixas.locator('.linha-simples')).toHaveCount(1);
    await expect(fixas.locator('.linha-prevista .linha-valor')).toHaveText('R$ 60,00');
    // FIN-FATURA-AJUSTES-02 (P17): so Data, Descricao e Valor, com a soma das linhas no cabecalho
    await expect(fixas.locator('.linha-legenda')).toHaveCount(0);
    await expect(fixas.locator('.bloco-subtotal')).toHaveText('R$ 60,00');
    await expect(fixas).not.toContainText(/previsto|aguardando/i);

    // FIN-FATURA-AJUSTES-02 (P16): Categoria | Previsto | Saldo | Executado, saldo negativo em vermelho
    const categorias = bloco(detalhe, 'Despesas por Categoria');
    await expect(categorias.locator('.bloco-subtotal')).toHaveCount(0);
    await expect(categorias.locator('.categoria-valor')).toHaveText('R$ 300,00');
    await expect(categorias.locator('.categoria-saldo.negativo')).toHaveText('-R$ 50,00');
    expect(await categorias.locator('.categoria-saldo').evaluate((e) => getComputedStyle(e).color)).toBe('rgb(198, 40, 40)');
    await expect(categorias.locator('.categoria-indicador')).toHaveText('R$ 350,00');
    await expect(categorias).not.toContainText(/Excedente|No limite/);
    const espaco1366 = await conferirColunas(page, categorias, 1366);
    const espaco1920 = await conferirColunas(page, categorias, 1920);
    expect(espaco1920, 'espaco flexivel antes de Executado').toBeGreaterThan(espaco1366);
    await page.setViewportSize({ width: 1366, height: 900 });

    // P03: previsto do detalhe = previsto da lista (o do banco): 60 + 350; FIN-CARTOES-EXECUTADO-01: executado com a fixa
    const totais = (await detalhe.locator('.fatura-totais .total-valor').allTextContents()).map(normal);
    expect(totais).toEqual(['R$ 410,00', 'R$ 410,00']);
    await expect(fatura.locator('.despesa-cell-valor')).toHaveText(/R\$ 410,00/);

    // P04: uma linha so, 28 a 32 px, DATA | DESCRICAO | VALOR, inclusive com descricao longa e em tela estreita.
    await categorias.locator('.categoria-linha').click();
    const conferir = async () => {
        const linhas = detalhe.locator('.linha-simples:visible, .categoria-linha:visible');
        expect(await linhas.count()).toBe(3);
        for (const linha of await linhas.all()) {
            const altura = (await linha.boundingBox()).height;
            expect(altura).toBeGreaterThanOrEqual(28);
            expect(altura).toBeLessThanOrEqual(32);
        }
    };
    await conferir();
    await expect(categorias.locator('.linha-data')).toHaveText('02/03');
    await page.setViewportSize({ width: 390, height: 800 });
    await conferir();
    await page.setViewportSize({ width: 1366, height: 900 });

    // Limpeza do cenario: recorrencia e cartao inativados (com o cartao inativo, a recorrencia ativa seria recusada na geracao)
    const versao = (await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).corpo.find((r) => r.id === recorrencia.corpo.item_id).versao;
    expect((await chamarRpc(page, 'definir_situacao_recorrencia_cartao', { p_perfil_id: perfil, p_item_id: recorrencia.corpo.item_id, p_versao: versao,
        p_ativo: false })).status).toBe(200);
    const cartoes = await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil });
    const registro = cartoes.corpo.find((c) => c.id === cartao);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao })).status).toBe(200);
});
