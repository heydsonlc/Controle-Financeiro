// FIN-CARTAO-NUBANK-PARCELADAS-01 — tela original Importar Cartao com um CSV no formato do Nubank: a parcela nova aparece
// como Compra parcelada e entra na confirmacao (antes ficava retida como "possivel parcelamento fora deste MVP"); a
// parcela ja cadastrada (datada pelo ciclo da fatura) e reconhecida; o numero ambiguo pede a decisao. CSV FICTICIO; so o
// usuario B, no "Perfil B", num cartao criado aqui, em 05/2034; o cartao e inativado no fim.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Parceladas E2E';

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

// Formato do Nubank: a parcela no fim do titulo; da 2a em diante, a data e o inicio do ciclo da fatura
const FATURA = [
    'date,title,amount',
    '2034-04-28,Loja Movel E2E - Parcela 2/4,"314,07"',  // parcela nova, sem compra cadastrada
    '2034-04-28,Notebook E2E - Parcela 2/3,"100,00"',    // parcela da compra cadastrada (10/05): ja existe
    '2034-05-08,Mercado E2E 03/10,"50,00"',               // numero ambiguo: o usuario decide
    '2034-05-09,Padaria E2E,"8,00"',                      // compra comum
].join('\n');

const linhaDe = (page, texto) => page.locator('#editorPrePersistencia tr', { hasText: texto });

async function abrirImportacao(page) {
    await page.goto('/importar-cartao.html');
    await expect(page.locator('#cartaoSelect option', { hasText: CARTAO })).toHaveCount(1);
    await page.selectOption('#cartaoSelect', { label: CARTAO });
    await page.fill('#competenciaInput', '05/2034');
    await page.locator('#competenciaInput').dispatchEvent('input');
}

test('parcelas do Nubank: nova entra como compra parcelada, cadastrada e reconhecida, ambigua decidida', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const moradia = (await chamarRpc(page, 'categorias_de_despesa', {})).corpo.find((c) => c.nome.startsWith('Moradia')).id;
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 } });
    expect(criado.status).toBe(200);
    const cartao = criado.corpo.cartao_id;
    const compra = await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: cartao, descricao: 'Notebook E2E', valor: '300.00', total_parcelas: 3, data_compra: '2034-04-10',
        mes_fatura: '2034-04-01', categoria_id: moradia } });
    expect(compra.status).toBe(200);

    await abrirImportacao(page);
    await page.locator('#csvFile').setInputFiles({ name: 'Nubank_2034-05-12.csv', mimeType: 'text/csv', buffer: Buffer.from(FATURA) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('CSV analisado com sucesso.');
    await page.click('#btnStep4');

    const movel = linhaDe(page, 'Loja Movel E2E');
    await expect(movel.locator('.import-status-pill')).toHaveText('Compra parcelada');
    await expect(movel).toContainText('Parcela 02/04');
    const mercado = linhaDe(page, 'Mercado E2E 03/10');
    await expect(mercado.locator('.import-status-pill')).toHaveText('Revisar');
    await expect(mercado).toContainText('Possível parcela 03/10: parcelada ou à vista?');
    await expect(linhaDe(page, 'Notebook E2E')).toHaveCount(0);  // retirada: a parcela ja cadastrada

    await mercado.locator('button[title="Confirmar parcela 03/10"]').click();
    await expect(mercado.locator('.import-status-pill')).toHaveText('Compra parcelada');
    for (const texto of ['Loja Movel E2E', 'Mercado E2E 03/10', 'Padaria E2E']) {
        await linhaDe(page, texto).locator('.import-category-cell select').selectOption(String(moradia));
    }
    await expect(page.locator('#btnImportar')).toContainText('(3)');
    await page.click('#btnImportar');
    await expect(page.locator('#resultadoContainer')).toContainText('Importação concluída.');
    expect(dialogos.find((d) => d.startsWith('Confirmar importacao'))).toMatch(/Compras parceladas: 2/);

    const compras = (await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2034-05-01' })).corpo;
    expect(compras.map((c) => [c.descricao, Number(c.valor), c.natureza, `${c.numero_parcela}/${c.total_parcelas}`]).sort()).toEqual([
        ['Loja Movel E2E', 314.07, 'PARCELADA', '2/4'], ['Mercado E2E', 50, 'PARCELADA', '3/10'],
        ['Notebook E2E', 100, 'PARCELADA', '2/3'], ['Padaria E2E', 8, 'OUTROS', '1/1']]);
    const fatura = (await chamarRpc(page, 'fatura_por_categoria', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2034-05-01' })).corpo;
    expect(Number(fatura.total_compras_parceladas)).toBeCloseTo(464.07, 2);

    // Reimportar o mesmo arquivo: tudo ja existe (inclusive a parcela decidida); nada novo para gravar
    await abrirImportacao(page);
    await page.locator('#csvFile').setInputFiles({ name: 'Nubank_2034-05-12.csv', mimeType: 'text/csv', buffer: Buffer.from(FATURA) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText(/Total importável: R\$\s0,00/);
    await expect(page.locator('#btnImportar')).toContainText('(0)');

    // Limpeza do cenario: cartao inativado (compras e faturas continuam registradas)
    const registro = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.id === cartao);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao })).status).toBe(200);
});
