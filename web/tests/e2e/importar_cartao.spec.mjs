// FIN-FIDELIDADE-CARTOES-1 — tela original Importar Cartao do Flask (frontend/templates/importar_cartao.html) sobre o
// Supabase. Arquivos CSV FICTICIOS gerados aqui (nada de dado real). Escrita so com o usuario B no "Perfil B", num cartao
// criado aqui, em 03/2033, inativado no fim. O arquivo e lido no navegador: nenhuma chamada /api/ sai da pagina.
import { expect, test } from '@playwright/test';

import { chamarRpc, perfilAtivoId, registrarDialogos } from './despesas.mjs';
import { trocarPerfil } from './moldura.mjs';

const A = { email: process.env.CF_EMAIL_A || 'usuario.a@teste.local', senha: process.env.CF_SENHA_A };
const B = { email: process.env.CF_EMAIL_B || 'usuario.b@teste.local', senha: process.env.CF_SENHA_B };
const CARTAO = 'Cartao Importacao E2E';

test.use({ viewport: { width: 1366, height: 900 } });
test.describe.configure({ mode: 'serial' });

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
    '2033-03-05,Padaria Central,12.50',
    '2033-03-06,Farmacia Boa,30.00',
    '2033-03-12,MERCADO BAIRRO*LOJA 2,50.00',  // ja lancada a mao (conciliacao)
    '2033-03-05,Padaria Central,12.50',        // repetida no proprio arquivo
    '2033-03-08,Pagamento recebido,-500.00',   // credito: nao e despesa
].join('\n');

async function idDaCategoria(page, prefixo) {
    const r = await chamarRpc(page, 'categorias_de_despesa', {});
    return r.corpo.find((c) => c.nome.startsWith(prefixo)).id;
}

async function cartaoPorNome(page, perfil) {
    const r = await chamarRpc(page, 'cartoes_do_perfil', { p_perfil_id: perfil });
    return r.corpo.find((c) => c.nome === CARTAO && c.ativo);
}

async function lancamentosDoMes(page, perfil, cartao) {
    const r = await chamarRpc(page, 'lancamentos_fatura_por_categoria', { p_perfil_id: perfil, p_cartao_id: cartao, p_mes: '2033-03-01', p_filtro: 'todos' });
    return r.corpo.lancamentos.map((l) => [l.descricao, Number(l.valor), l.origem]);
}

async function abrirImportacao(page) {
    await page.goto('/importar-cartao.html');
    await expect(page.locator('#cartaoSelect option', { hasText: CARTAO })).toHaveCount(1);
    await page.selectOption('#cartaoSelect', { label: CARTAO });
    await page.fill('#competenciaInput', '03/2033');
    await page.locator('#competenciaInput').dispatchEvent('input');
}

async function enviar(page, nome, conteudo, tipo = 'text/csv') {
    await page.locator('#csvFile').setInputFiles({ name: nome, mimeType: tipo, buffer: Buffer.from(conteudo) });
}

test('CSV: analise, duplicidade, conciliacao, credito, confirmacao e reimportacao sem duplicar', async ({ page }) => {
    const dialogos = registrarDialogos(page);
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const moradia = await idDaCategoria(page, 'Moradia');
    const criado = await chamarRpc(page, 'criar_cartao', { p_perfil_id: perfil, p_dados: { nome: CARTAO, dia_fechamento: 3, dia_vencimento: 12 },
        p_chave: crypto.randomUUID() });
    expect(criado.status).toBe(200);
    const cartao = criado.corpo.cartao_id;
    const manual = await chamarRpc(page, 'criar_compra', { p_perfil_id: perfil, p_chave: crypto.randomUUID(), p_dados: {
        cartao_id: cartao, descricao: 'Mercado do bairro', valor: '50.00', total_parcelas: 1, data_compra: '2033-03-10',
        mes_fatura: '2033-03-01', categoria_id: moradia } });
    expect(manual.status).toBe(200);

    await abrirImportacao(page);
    await enviar(page, 'fatura-marco.csv', FATURA);
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('CSV analisado com sucesso.');
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText('5 linhas normalizadas');
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText(/Total importável: R\$\s42,50/);

    await page.click('#btnStep4');  // confronto pos-triagem
    await expect(page.locator('#btnImportar')).toBeEnabled();
    await page.click('#btnImportar');
    await expect(page.locator('#resultadoContainer')).toContainText('Importação concluída.');
    await expect(page.locator('#resultadoContainer')).toContainText(/Inseridos:\s*2\./);
    const confirmacao = dialogos.find((d) => d.startsWith('Confirmar importacao'));
    expect(confirmacao).toMatch(/^Confirmar importacao de 2 lancamentos novos\?/);
    expect(await lancamentosDoMes(page, perfil, cartao)).toEqual([
        ['Padaria Central', 12.5, 'csv'], ['Farmacia Boa', 30, 'csv'], ['Mercado do bairro', 50, 'manual']]);

    // Mesmo arquivo de novo: nada novo para importar (duplicidade no banco); nada gravado.
    await abrirImportacao(page);
    await enviar(page, 'fatura-marco.csv', FATURA);
    await expect(page.locator('#resumoConfiguracaoImportacao')).toContainText(/Total importável: R\$\s0,00/);
    await expect(page.locator('#btnStep4')).toBeDisabled();  // nada novo: confronto e importacao desativados
    await expect(page.locator('#btnImportar')).toBeDisabled();
    await expect(page.locator('#btnImportar')).toContainText('(0)');
    await expect(page.locator('body')).toContainText('Duplicado na fatura');
    expect(await lancamentosDoMes(page, perfil, cartao)).toHaveLength(3);

    // PDF/XLSX: leitura em migracao (no Flask, no servidor); nada e analisado nem gravado.
    await abrirImportacao(page);
    await enviar(page, 'fatura.pdf', '%PDF-1.4 ficticio', 'application/pdf');
    await expect(page.locator('#uploadResult')).toContainText('Leitura de PDF e XLSX: em migração');
});

test('mapeamento manual de CSV de outro banco (perfil generico): a tela pede a validacao do layout', async ({ page }) => {
    registrarDialogos(page);
    await entrar(page, B);
    await abrirImportacao(page);
    await enviar(page, 'outro-banco.csv', 'quando;o que;quanto\n15/03/2033;Padaria Central;9,90\n');
    await expect(page.locator('#uploadResult')).toContainText('CSV carregado com sucesso.');
    await expect(page.locator('#uploadResult')).toContainText('Perfil não identificado com confiança.');
    await expect(page.locator('#btnStep3')).toBeEnabled();
});

test('LEITOR nao importa; escrita direta e outro perfil recusados; limpeza do cartao do cenario', async ({ page }) => {
    await entrar(page, A);
    await page.goto('/importar-cartao.html');
    await trocarPerfil(page, 'Empresa');
    await expect(page.locator('#btnImportar')).toBeHidden();
    const empresa = await perfilAtivoId(page);
    const linha = { data_compra: '2033-03-05', descricao_original: 'X', descricao_normalizada: 'X', valor: '1.00', categoria_id: 201 };
    const r = await chamarRpc(page, 'importar_fatura_cartao', { p_perfil_id: empresa, p_cartao_id: 1, p_competencia: '2033-03-01',
        p_linhas: [linha], p_chave: crypto.randomUUID() });
    const outro = await chamarRpc(page, 'analisar_importacao_cartao', { p_perfil_id: Number(process.env.CF_ID_PERFIL_B || '103'),
        p_cartao_id: 1, p_competencia: '2033-03-01', p_linhas: [linha] });
    expect([r.status, outro.status]).toEqual([403, 403]);

    // Limpeza: o cartao criado pelo cenario deixa de receber compras (compras e faturas continuam).
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });  // sai de A
    await entrar(page, B);
    const perfil = await perfilAtivoId(page);
    const cartao = await cartaoPorNome(page, perfil);
    if (cartao) {
        const inativado = await chamarRpc(page, 'inativar_cartao', { p_perfil_id: perfil, p_cartao_id: cartao.id, p_versao: cartao.versao });
        expect(inativado.status).toBe(200);
    }
});
