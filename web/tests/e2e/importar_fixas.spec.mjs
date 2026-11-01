// FIN-CARTAO-IMPORTACAO-FIXAS-01 — tela original Importar Cartao: a previa mostra a classificacao proposta pelo banco
// (despesa fixa com previsto, cobrado e fatura), o usuario corrige (escolhe a recorrencia, lembra a descricao, trata como
// compra comum) e a confirmacao grava tudo de uma vez. CSV FICTICIO; so o usuario B, no "Perfil B", num cartao e em
// recorrencias criados aqui, em 04/2034 (sem gerar o mes: as recorrencias do cenario do E2E nao sao tocadas); tudo
// inativado no fim.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';

const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Fixas E2E';

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
    '2034-04-10,STREAMING PLUS*ASSINATURA,39.90',  // reconhecida pela descricao
    '2034-04-11,MUSICAPP BILL,19.90',              // nao reconhecida: o usuario escolhe a recorrencia
    '2034-04-12,PADARIA E2E,8.00',                 // compra comum
    '2034-04-13,STREAMING PLUS*EXTRA,5.00',        // segunda cobranca do mesmo servico: revisar
].join('\n');

const linhaDe = (page, texto) => page.locator('#editorPrePersistencia tr', { hasText: texto });

async function abrirImportacao(page) {
    await page.goto('/importar-cartao.html');
    await expect(page.locator('#cartaoSelect option', { hasText: CARTAO })).toHaveCount(1);
    await page.selectOption('#cartaoSelect', { label: CARTAO });
    await page.fill('#competenciaInput', '04/2034');
    await page.locator('#competenciaInput').dispatchEvent('input');
}

test('previa classifica despesas fixas, o usuario corrige e a confirmacao grava uma vez', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const moradia = (await chamarRpc(page, 'categorias_de_despesa', {})).corpo.find((c) => c.nome.startsWith('Moradia')).id;
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(),
        p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 } });
    expect(criado.status).toBe(200);
    const cartao = criado.corpo.cartao_id;
    const recorrencias = {};
    for (const [nome, valor] of [['Streaming Plus', '39.90'], ['Musica Max', '19.90']]) {
        const r = await chamarRpc(page, 'criar_recorrencia_cartao', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
            nome, valor, categoria_id: moradia, data_vencimento: '2034-04-10', tipo_recorrencia: 'mensal', cartao_id: cartao } });
        expect(r.status, nome).toBe(200);
        recorrencias[nome] = r.corpo.item_id;
    }

    await abrirImportacao(page);
    await page.locator('#csvFile').setInputFiles({ name: 'fatura-abril.csv', mimeType: 'text/csv', buffer: Buffer.from(FATURA) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('CSV analisado com sucesso.');
    await page.click('#btnStep4');

    // Classificacao proposta na propria linha
    const streaming = linhaDe(page, 'STREAMING PLUS*ASSINATURA');
    await expect(streaming.locator('.import-status-pill')).toHaveText('Despesa fixa');
    await expect(streaming).toContainText(/Streaming Plus · previsto R\$\s39,90 · cobrado R\$\s39,90 · fatura 04\/2034/);
    const extra = linhaDe(page, 'STREAMING PLUS*EXTRA');
    await expect(extra.locator('.import-status-pill')).toHaveText('Revisar');
    await expect(linhaDe(page, 'MUSICAPP BILL').locator('.import-status-pill')).toHaveText('Novo');

    // Correcoes: a recorrencia da musica (lembrando a descricao); a segunda cobranca vira compra comum
    await linhaDe(page, 'MUSICAPP BILL').locator('select[aria-label="Recorrência da cobrança"]').selectOption(String(recorrencias['Musica Max']));
    await expect(linhaDe(page, 'MUSICAPP BILL').locator('.import-status-pill')).toHaveText('Despesa fixa');
    await linhaDe(page, 'MUSICAPP BILL').getByLabel('Lembrar esta descrição').check();
    await extra.locator('button[title="Tratar como compra comum"]').click();
    for (const texto of ['PADARIA E2E', 'STREAMING PLUS*EXTRA']) {
        await linhaDe(page, texto).locator('.import-category-cell select').selectOption(String(moradia));
    }

    await expect(page.locator('#btnImportar')).toContainText('(4)');
    await page.click('#btnImportar');
    await expect(page.locator('#resultadoContainer')).toContainText('Importação concluída.');
    expect(dialogos.find((d) => d.startsWith('Confirmar importacao'))).toMatch(/Despesas fixas reconhecidas: 2/);

    const compras = (await chamarRpc(page, 'compras_da_fatura', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2034-04-01' })).corpo;
    expect(compras.map((c) => [c.descricao, Number(c.valor), c.natureza]).sort()).toEqual([
        ['MUSICAPP BILL', 19.9, 'FIXA'], ['PADARIA E2E', 8, 'OUTROS'], ['STREAMING PLUS*ASSINATURA', 39.9, 'FIXA'],
        ['STREAMING PLUS*EXTRA', 5, 'OUTROS']]);
    const apelidos = (await chamarRpc(page, 'apelidos_da_recorrencia', { p_perfil_id: perfil, p_item_id: recorrencias['Musica Max'] })).corpo;
    expect(apelidos.map((a) => a.apelido)).toEqual(['musicapp bill']);

    // Reimportar o mesmo arquivo: tudo ja existe; nada novo para gravar
    await abrirImportacao(page);
    await page.locator('#csvFile').setInputFiles({ name: 'fatura-abril.csv', mimeType: 'text/csv', buffer: Buffer.from(FATURA) });
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText(/Total importável: R\$\s0,00/);
    await expect(page.locator('#btnImportar')).toContainText('(0)');

    // Limpeza do cenario: recorrencias e cartao inativados (compras e faturas continuam registradas)
    for (const id of Object.values(recorrencias)) {
        const versao = (await chamarRpc(page, 'recorrencias_do_perfil', { p_perfil_id: perfil })).corpo.find((r) => r.id === id).versao;
        expect((await chamarRpc(page, 'definir_situacao_recorrencia_cartao', { p_perfil_id: perfil, p_item_id: id, p_versao: versao,
            p_ativo: false })).status).toBe(200);
    }
    const registro = (await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil })).corpo.find((c) => c.id === cartao);
    expect((await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao, p_versao: registro.versao })).status).toBe(200);
});
