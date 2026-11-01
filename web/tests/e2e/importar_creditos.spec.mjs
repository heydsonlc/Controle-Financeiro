// FIN-CARTAO-NUBANK-CREDITOS-01 — tela original Importar Cartao com um CSV no formato do Nubank: estorno, IOF devolvido e
// ajuste aparecem como Credito (natureza, compra original, tratamento) e entram na confirmacao; o estorno com duas
// compras candidatas pede a escolha; o pagamento recebido fica retirado com o motivo. Depois, o detalhe da fatura em
// Despesas mostra o bloco "Creditos e Ajustes" e o valor a pagar liquido. CSV FICTICIO; so o usuario B, no "Perfil B",
// num cartao criado aqui, em 06/2034; o cartao e inativado no fim.
import { expect, test } from '@playwright/test';

import { abrirDespesas, chamarRpc, despesa, normal, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Creditos E2E';

test.use({ viewport: { width: 1600, height: 900 } });

test.beforeEach(async ({ page }, testInfo) => {
    const problemas = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && /Content Security Policy|Refused to/i.test(msg.text())) problemas.push(msg.text());
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

const FATURA = [
    'date,title,amount',
    '2034-06-20,"Estorno de ""Loja Som E2E"" (Som)","- 50,22"',  // duas compras candidatas: o usuario escolhe
    '2034-06-21,IOF de volta de Nuvem E2E,"- 0,99"',               // a cobranca de IOF da Nuvem E2E
    '2034-06-22,Credito de ajuste E2E,"- 3,00"',                   // ajuste da administradora, sem compra
    '2034-05-30,Pagamento recebido,"- 900,00"',                    // pagamento da fatura anterior: fora
    '2034-06-23,Padaria E2E,"8,00"',                               // compra comum
].join('\n');

const linhaDe = (page, texto) => page.locator('#editorPrePersistencia tr', { hasText: texto });
const bloco = (detalhe, titulo) => detalhe.locator('.fatura-bloco', { has: detalhe.page().locator('.bloco-titulo', { hasText: titulo }) });

async function abrirImportacao(page) {
    await page.goto('/importar-cartao.html');
    await expect(page.locator('#cartaoSelect option', { hasText: CARTAO })).toHaveCount(1);
    await page.selectOption('#cartaoSelect', { label: CARTAO });
    await page.fill('#competenciaInput', '06/2034');
    await page.locator('#competenciaInput').dispatchEvent('input');
}

test('creditos do Nubank: estorno escolhido, IOF vinculado, ajuste e pagamento fora; valor a pagar liquido', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const moradia = (await chamarRpc(page, 'categorias_de_despesa', {})).corpo.find((c) => c.nome.startsWith('Moradia')).id;
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 } });
    expect(criado.status).toBe(200);
    const cartao = criado.corpo.cartao_id;
    for (const [descricao, valor, data] of [['Loja Som E2E', '799.90', '2034-06-02'], ['Loja Som E2E', '129.90', '2034-06-05'],
        ['Nuvem E2E', '28.47', '2034-06-21'], ['IOF de "Nuvem E2E"', '0.99', '2034-06-21']]) {
        const r = await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
            cartao_id: cartao, descricao, valor, total_parcelas: 1, data_compra: data, mes_fatura: '2034-06-01', categoria_id: moradia } });
        expect(r.status, descricao).toBe(200);
    }

    await abrirImportacao(page);
    await page.locator('#csvFile').setInputFiles({ name: 'Nubank_2034-07-12.csv', mimeType: 'text/csv', buffer: Buffer.from(FATURA) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('CSV analisado com sucesso.');
    await page.click('#btnStep4');

    const iof = linhaDe(page, 'IOF de volta de Nuvem E2E');
    await expect(iof.locator('.import-status-pill')).toHaveText('Crédito');
    await expect(iof).toContainText(/Devolucao de IOF · abate R\$\s0,99 da fatura 06\/2034 · compra original: IOF de "Nuvem E2E"/);
    await expect(linhaDe(page, 'Credito de ajuste E2E')).toContainText('Credito ou ajuste da fatura');
    const estorno = linhaDe(page, 'Loja Som E2E');
    await expect(estorno.locator('.import-status-pill')).toHaveText('Revisar');
    await expect(linhaDe(page, 'Pagamento recebido')).toHaveCount(0);  // retirado: pagamento nao e credito desta fatura

    const seletor = estorno.locator('select[aria-label="Compra original do crédito"]');
    const opcao = await seletor.locator('option', { hasText: '799,90' }).getAttribute('value');
    await seletor.selectOption(opcao);
    await expect(estorno.locator('.import-status-pill')).toHaveText('Crédito');
    await expect(estorno).toContainText(/compra original: Loja Som E2E \(R\$\s799,90\), parcial/);
    await linhaDe(page, 'Padaria E2E').locator('.import-category-cell select').selectOption(String(moradia));
    await expect(page.locator('#btnImportar')).toContainText('(4)');
    await page.click('#btnImportar');
    await expect(page.locator('#resultadoContainer')).toContainText('Importação concluída.');
    await expect(page.locator('#resultadoContainer')).toContainText(/Créditos abatidos da fatura: 3 \(R\$\s54,21\)/);
    expect(dialogos.find((d) => d.startsWith('Confirmar importacao'))).toMatch(/Creditos da fatura \(abatem o valor a pagar\): 3/);

    const resumo = (await chamarRpc(page, 'fatura_por_categoria', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2034-06-01' })).corpo;
    expect([Number(resumo.total_compras), Number(resumo.total_creditos), Number(resumo.total_fatura)]).toEqual([967.26, 54.21, 913.05]);
    const lista = (await chamarRpc(page, 'lancamentos_fatura_por_categoria', { p_perfil_id: perfil, p_cartao_id: cartao,
        p_mes: '2034-06-01', p_filtro: 'creditos' })).corpo.lancamentos;
    expect(lista.map((l) => [l.descricao, Number(l.valor), l.compra_original && Number(l.compra_original.valor)])).toEqual([
        ['Estorno de "Loja Som E2E" (Som)', -50.22, 799.9], ['IOF de volta de Nuvem E2E', -0.99, 0.99], ['Credito de ajuste E2E', -3, null]]);

    // Despesas: o detalhe da fatura separa compras e creditos; o executado e o valor a pagar
    await abrirDespesas(page, '2034-06');
    const linhaFatura = despesa(page, `Fatura ${CARTAO} - 06/2034`);
    await linhaFatura.locator('[data-on-click^="toggleDetalhesFatura"]').click();
    const detalhe = linhaFatura.locator('.fatura-detalhes');
    await expect(bloco(detalhe, 'Créditos e Ajustes').locator('.bloco-subtotal')).toHaveText('− R$ 54,21');
    await expect(bloco(detalhe, 'Créditos e Ajustes').locator('.linha-titulo')).toHaveText(
        ['Estorno de "Loja Som E2E" (Som)', 'IOF de volta de Nuvem E2E', 'Credito de ajuste E2E']);
    const totais = (await detalhe.locator('.fatura-totais .total-valor').allTextContents()).map(normal);
    expect(totais[1]).toBe('R$ 913,05');

    // Reimportar o mesmo arquivo: nada novo (nenhum credito abatido de novo)
    await abrirImportacao(page);
    await page.locator('#csvFile').setInputFiles({ name: 'Nubank_2034-07-12.csv', mimeType: 'text/csv', buffer: Buffer.from(FATURA) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText(/Total importável: R\$\s0,00/);
    await expect(page.locator('#btnImportar')).toContainText('(0)');

    // Limpeza do cenario: cartao inativado (compras, creditos e faturas continuam registrados)
    const registro = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.id === cartao);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao })).status).toBe(200);
});
